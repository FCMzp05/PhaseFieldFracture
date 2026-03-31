using Gmsh: gmsh
using Gridap
using Gridap.Geometry
using Gridap.Geometry: get_cell_coordinates
using Gridap.TensorValues
using Gridap.CellData
using Gridap.FESpaces
using Gridap.Algebra
using GridapGmsh
using LinearAlgebra
using Statistics
using Printf
using DelimitedFiles
ENV["GKSwstype"] = "100"
using Plots
gr(show=false)

include(joinpath(@__DIR__, "..", "_gui_runtime_override.jl"))
using .GuiRuntimeOverride

const GUI_RUNTIME = load_runtime_override(ARGS)
const GUI_PARAMS = runtime_params(GUI_RUNTIME)

# ============================================================================
# Fang et al. (2019) flat grooved specimen
#
# Reference implementation style:
# - same constitutive/algorithmic route as Du_fig4.jl
# - plane strain 3D radial return
# - linear isotropic hardening
# - no volumetric split
# - history field H = max(SSE + SPD)
# - AT2 phase-field, g(d) = (1-d)^2 + k
#
# This script scans H/E values while keeping the elastic modulus fixed.
# The label H = 0.1E / 0.2E / 0.5E means the isotropic hardening modulus
# H_hard is scaled as H_ratio * E, not that E itself changes.
# and records timing for each scan case.
# ============================================================================

# ============================================================================
# Geometry
# ============================================================================

const W = 18.0
const H_specimen = 50.0
const r_notch = 2.5

const LEFT_NOTCH_X = 0.0
const LEFT_NOTCH_Y = 30.0
const RIGHT_NOTCH_X = W
const RIGHT_NOTCH_Y = 20.0

# ============================================================================
# Material
# ============================================================================

struct MaterialData
    E::Float64
    ν::Float64
    G::Float64
    λ::Float64
    σy0::Float64
    H_hard::Float64
end

function create_material(; H_ratio::Float64=0.1)
    E = get_float(GUI_PARAMS, "E", 71_480.0)
    ν = get_float(GUI_PARAMS, "nu", 0.3)
    G = E / (2 * (1 + ν))
    λ = E * ν / ((1 + ν) * (1 - 2 * ν))
    σy0 = get_float(GUI_PARAMS, "sigma_y0", 345.0)
    H_hard = H_ratio * E
    return MaterialData(E, ν, G, λ, σy0, H_hard)
end

const lc = get_float(GUI_PARAMS, "lc", 0.2)
const Gc = get_float(GUI_PARAMS, "Gc", 9.31)
const η_stab = 1e-4
const THICKNESS = 1.0

# ============================================================================
# Loading / solver controls
# ============================================================================

const u_total = get_float(GUI_PARAMS, "u_total", 0.30)
const N_STEPS = get_int(GUI_PARAMS, "N_STEPS", 1000)
const Δu = u_total / N_STEPS
const STOP_REACTION_KN = 0.1
const STOP_AFTER_STEPS = 2

const max_stagger = 30
const stagger_tol = 1e-6

# ============================================================================
# Mesh / output
# ============================================================================

const h_fine = lc / 2
const h_coarse = get_float(GUI_PARAMS, "h_coarse", 3.0)

const BASE_OUTPUT_DIR = "results_PlasticFracture_FlatGrooved"
const HISO_SCAN = [0.1, 0.2, 0.5]
const SNAPSHOT_DAMAGE_LEVELS = [0.20, 0.60, 0.90, 0.99]

# ============================================================================
# Elasticity
# ============================================================================

function elastic_stiffness_plane_strain(mat::MaterialData)
    λ, μ = mat.λ, mat.G
    C1111 = λ + 2μ
    C1122 = λ
    C1212 = μ
    return SymFourthOrderTensorValue(
        C1111, 0.0, C1122,
        0.0, C1212, 0.0,
        C1122, 0.0, C1111
    )
end

const ε = symmetric_gradient

# ============================================================================
# Plasticity state
# ============================================================================

mutable struct PlasticStateData
    εp::SymTensorValue{2,Float64,3}
    εp33::Float64
    εp_eq::Float64
end

PlasticStateData() = PlasticStateData(SymTensorValue{2,Float64}(0.0, 0.0, 0.0), 0.0, 0.0)

function copy_plastic_state(ps::PlasticStateData)
    return PlasticStateData(ps.εp, ps.εp33, ps.εp_eq)
end

# ============================================================================
# Linear isotropic hardening elastoplasticity
# ============================================================================

function yield_stress(εp_eq::Float64, mat::MaterialData)
    return mat.σy0 + mat.H_hard * εp_eq
end

function plastic_strain_energy(εp_eq::Float64, mat::MaterialData)
    return mat.σy0 * εp_eq + 0.5 * mat.H_hard * εp_eq^2
end

function return_mapping!(
    ε_total::SymTensorValue{2,Float64,3},
    plastic::PlasticStateData,
    mat::MaterialData,
    s_phasefield::Float64;
    update_state::Bool = true
)
    g_s = (1 - s_phasefield)^2 + η_stab
    λ = mat.λ
    μ = mat.G
    EG3 = 3.0 * μ

    εe11 = ε_total[1,1] - plastic.εp[1,1]
    εe22 = ε_total[2,2] - plastic.εp[2,2]
    εe12 = ε_total[1,2] - plastic.εp[1,2]
    εe33 = -plastic.εp33

    trεe = εe11 + εe22 + εe33
    σ11_0 = λ * trεe + 2μ * εe11
    σ22_0 = λ * trεe + 2μ * εe22
    σ33_0 = λ * trεe + 2μ * εe33
    σ12_0 = 2μ * εe12

    p = (σ11_0 + σ22_0 + σ33_0) / 3.0
    s11 = σ11_0 - p
    s22 = σ22_0 - p
    s33 = σ33_0 - p
    s12 = σ12_0
    σ_eq = sqrt(max(1.5 * (s11^2 + s22^2 + s33^2 + 2.0 * s12^2), 0.0))

    σy = yield_stress(plastic.εp_eq, mat)

    if σ_eq <= (1.0 + 1e-6) * σy || σ_eq < 1e-10
        SSE = (σ11_0 * εe11 + σ22_0 * εe22 + σ33_0 * εe33 + 2.0 * σ12_0 * εe12) / 2.0
        return g_s * SymTensorValue{2,Float64}(σ11_0, σ12_0, σ22_0), SSE
    end

    DEQPL = 0.0
    SYIELD = σy
    for _ in 1:20
        RHS = σ_eq - EG3 * DEQPL - SYIELD
        DEQPL = DEQPL + RHS / (EG3 + mat.H_hard)
        SYIELD = yield_stress(plastic.εp_eq + DEQPL, mat)
        if abs(RHS) < 1e-6 * mat.σy0
            break
        end
    end

    inv_σ = 1.0 / σ_eq
    flow11 = s11 * inv_σ
    flow22 = s22 * inv_σ
    flow33 = s33 * inv_σ
    flow12 = s12 * inv_σ

    σ11_new = flow11 * SYIELD + p
    σ22_new = flow22 * SYIELD + p
    σ33_new = flow33 * SYIELD + p
    σ12_new = flow12 * SYIELD

    Δεp11 = 1.5 * flow11 * DEQPL
    Δεp22 = 1.5 * flow22 * DEQPL
    Δεp33 = 1.5 * flow33 * DEQPL
    Δεp12 = 1.5 * flow12 * DEQPL

    εe11_new = εe11 - Δεp11
    εe22_new = εe22 - Δεp22
    εe33_new = εe33 - Δεp33
    εe12_new = εe12 - Δεp12

    SSE = (σ11_new * εe11_new + σ22_new * εe22_new +
           σ33_new * εe33_new + 2.0 * σ12_new * εe12_new) / 2.0

    if update_state
        plastic.εp = plastic.εp + SymTensorValue{2,Float64}(Δεp11, Δεp12, Δεp22)
        plastic.εp33 = plastic.εp33 + Δεp33
        plastic.εp_eq = plastic.εp_eq + DEQPL
    end

    return g_s * SymTensorValue{2,Float64}(σ11_new, σ12_new, σ22_new), SSE
end

# ============================================================================
# History variable
# ============================================================================

function update_history_variable(ψ_total::Real, H_old::Real)
    return (true, max(H_old, ψ_total))
end

# ============================================================================
# FE helpers
# ============================================================================

function project_to_fe_space(q, V_proj, dΩ)
    a(u, v) = ∫(u * v) * dΩ
    b(v) = ∫(v * q) * dΩ
    op = AffineFEOperator(a, b, V_proj, V_proj)
    return solve(op)
end

function array_to_fe_field(arr, V_dg0, V_proj, dΩ)
    f_dg = FEFunction(V_dg0, arr)
    a(u, v) = ∫(u * v) * dΩ
    b(v) = ∫(v * f_dg) * dΩ
    op = AffineFEOperator(a, b, V_proj, V_proj)
    return solve(op)
end

# ============================================================================
# Mesh
# ============================================================================

function create_mesh(output_dir::String)
    println("\n创建 Fang 2019 flat-grooved 网格...")
    println("  几何: W=$(W)mm × H=$(H_specimen)mm, r=$(r_notch)mm")
    println("  网格: h_fine=$(h_fine)mm, h_coarse=$(h_coarse)mm")

    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.model.add("Fang2019_flat_grooved")

    pt = 1
    gmsh.model.geo.addPoint(0.0, 0.0, 0.0, h_coarse, pt); pt_BL = pt; pt += 1
    gmsh.model.geo.addPoint(W, 0.0, 0.0, h_coarse, pt); pt_BR = pt; pt += 1

    y_right_notch_bottom = RIGHT_NOTCH_Y - r_notch
    y_right_notch_top = RIGHT_NOTCH_Y + r_notch
    gmsh.model.geo.addPoint(W, y_right_notch_bottom, 0.0, h_fine, pt); pt_R_NB = pt; pt += 1
    gmsh.model.geo.addPoint(W, RIGHT_NOTCH_Y, 0.0, h_fine, pt); pt_R_NC = pt; pt += 1
    gmsh.model.geo.addPoint(W, y_right_notch_top, 0.0, h_fine, pt); pt_R_NT = pt; pt += 1
    gmsh.model.geo.addPoint(W - r_notch, RIGHT_NOTCH_Y, 0.0, h_fine, pt); pt_R_NL = pt; pt += 1

    gmsh.model.geo.addPoint(W, H_specimen, 0.0, h_coarse, pt); pt_TR = pt; pt += 1
    gmsh.model.geo.addPoint(0.0, H_specimen, 0.0, h_coarse, pt); pt_TL = pt; pt += 1

    y_left_notch_bottom = LEFT_NOTCH_Y - r_notch
    y_left_notch_top = LEFT_NOTCH_Y + r_notch
    gmsh.model.geo.addPoint(0.0, y_left_notch_top, 0.0, h_fine, pt); pt_L_NT = pt; pt += 1
    gmsh.model.geo.addPoint(0.0, LEFT_NOTCH_Y, 0.0, h_fine, pt); pt_L_NC = pt; pt += 1
    gmsh.model.geo.addPoint(0.0, y_left_notch_bottom, 0.0, h_fine, pt); pt_L_NB = pt; pt += 1
    gmsh.model.geo.addPoint(r_notch, LEFT_NOTCH_Y, 0.0, h_fine, pt); pt_L_NR = pt; pt += 1

    line = 1
    gmsh.model.geo.addLine(pt_BL, pt_BR, line); line_bottom = line; line += 1
    gmsh.model.geo.addLine(pt_BR, pt_R_NB, line); line_right_lower = line; line += 1
    gmsh.model.geo.addCircleArc(pt_R_NB, pt_R_NC, pt_R_NL, line); line_right_arc1 = line; line += 1
    gmsh.model.geo.addCircleArc(pt_R_NL, pt_R_NC, pt_R_NT, line); line_right_arc2 = line; line += 1
    gmsh.model.geo.addLine(pt_R_NT, pt_TR, line); line_right_upper = line; line += 1
    gmsh.model.geo.addLine(pt_TR, pt_TL, line); line_top = line; line += 1
    gmsh.model.geo.addLine(pt_TL, pt_L_NT, line); line_left_upper = line; line += 1
    gmsh.model.geo.addCircleArc(pt_L_NT, pt_L_NC, pt_L_NR, line); line_left_arc1 = line; line += 1
    gmsh.model.geo.addCircleArc(pt_L_NR, pt_L_NC, pt_L_NB, line); line_left_arc2 = line; line += 1
    gmsh.model.geo.addLine(pt_L_NB, pt_BL, line); line_left_lower = line; line += 1
    gmsh.model.geo.addLine(pt_L_NR, pt_R_NL, line); line_crack_path = line; line += 1

    outer_loop = [
        line_bottom,
        line_right_lower, line_right_arc1, line_right_arc2, line_right_upper,
        line_top,
        line_left_upper, line_left_arc1, line_left_arc2, line_left_lower
    ]
    gmsh.model.geo.addCurveLoop(outer_loop, 1)
    gmsh.model.geo.addPlaneSurface([1], 1)

    gmsh.model.addPhysicalGroup(2, [1], 1)
    gmsh.model.setPhysicalName(2, 1, "Domain")
    gmsh.model.addPhysicalGroup(1, [line_bottom], 1)
    gmsh.model.setPhysicalName(1, 1, "bottom")
    gmsh.model.addPhysicalGroup(1, [line_top], 2)
    gmsh.model.setPhysicalName(1, 2, "top")

    gmsh.model.geo.synchronize()

    # Slanted refinement band following the expected crack path, plus refinement
    # around the two notch arcs. This is closer to the paper's mesh than two
    # axis-aligned refinement boxes and keeps the total cell count lower.
    gmsh.model.mesh.field.add("Distance", 1)
    gmsh.model.mesh.field.setNumbers(1, "CurvesList", [
        line_crack_path,
        line_left_arc1, line_left_arc2,
        line_right_arc1, line_right_arc2
    ])
    gmsh.model.mesh.field.setNumber(1, "Sampling", 300)

    gmsh.model.mesh.field.add("Threshold", 2)
    gmsh.model.mesh.field.setNumber(2, "InField", 1)
    gmsh.model.mesh.field.setNumber(2, "LcMin", h_fine)
    gmsh.model.mesh.field.setNumber(2, "LcMax", h_coarse)
    gmsh.model.mesh.field.setNumber(2, "DistMin", 3.0)
    gmsh.model.mesh.field.setNumber(2, "DistMax", 12.0)

    gmsh.model.mesh.field.setAsBackgroundMesh(2)
    gmsh.model.mesh.generate(2)

    num_nodes = length(gmsh.model.mesh.getNodes()[1])
    elem_types, elem_tags, _ = gmsh.model.mesh.getElements(2)
    n_tri = 0
    for (etype, tags) in zip(elem_types, elem_tags)
        if etype == 2
            n_tri += length(tags)
        end
    end
    println("  节点数: $(num_nodes)")
    println("  三角形单元数: $(n_tri)")
    println("  h_fine = $(h_fine) mm = lc/2")
    println("  refinement = slanted band + notch arcs")

    mesh_file = joinpath(output_dir, "mesh.msh")
    gmsh.write(mesh_file)
    gmsh.finalize()
    return mesh_file
end

# ============================================================================
# Stress update helpers
# ============================================================================

function compute_elastoplastic_stress!(
    uh, dh, plastic_states::Vector{PlasticStateData},
    mat::MaterialData, Ω, update::Bool;
    cell_points=nothing
)
    nc = num_cells(Ω)
    if cell_points === nothing
        quad = CellQuadrature(Ω, 2)
        cell_points = get_cell_points(quad)
    end
    εh = ε(uh)
    ε_qp = evaluate(εh, cell_points)
    d_qp = evaluate(dh, cell_points)

    σ_vals = Vector{SymTensorValue{2,Float64,3}}(undef, nc)
    sse_vals = zeros(nc)
    for i in 1:nc
        ε_cell = ε_qp[i][1]
        d_cell = clamp(d_qp[i][1], 0.0, 1.0)
        σ_vals[i], sse_vals[i] = return_mapping!(ε_cell, plastic_states[i], mat, d_cell, update_state=update)
    end
    return σ_vals, sse_vals
end

# ============================================================================
# Displacement solve
# ============================================================================

function solve_displacement(
    dh, plastic_states::Vector{PlasticStateData},
    mat::MaterialData, C_tensor,
    u_val::Float64, V_u, dΩ, Ω,
    uh_prev, u_prev::Float64;
    cell_points_cache=nothing
)
    g_d(d) = (1 - d)^2 + η_stab
    nc = num_cells(Ω)
    plastic_work = [copy_plastic_state(ps) for ps in plastic_states]

    Δu_step = u_val - u_prev
    n_sub = max(1, ceil(Int, abs(Δu_step) / 0.002))
    uh = uh_prev

    for sub in 1:n_sub
        u_cur = u_prev + Δu_step * sub / n_sub
        u_bottom(x) = VectorValue(0.0, 0.0)
        u_top(x) = VectorValue(0.0, u_cur)
        U_u_cur = TrialFESpace(V_u, [u_bottom, u_top])

        plastic_sub_start = [copy_plastic_state(ps) for ps in plastic_work]

        for _ in 1:10
            u_old = copy(get_free_dof_values(uh))

            σp_vals = Vector{SymTensorValue{2,Float64,3}}(undef, nc)
            for i in 1:nc
                σp_vals[i] = C_tensor ⊙ plastic_work[i].εp
            end
            σp_field = CellField(σp_vals, Ω)

            a(u, v) = ∫((g_d ∘ dh) * (C_tensor ⊙ ε(u)) ⊙ ε(v)) * dΩ
            l(v) = ∫((g_d ∘ dh) * σp_field ⊙ ε(v)) * dΩ

            op = AffineFEOperator(a, l, U_u_cur, V_u)
            uh = solve(op)

            for i in 1:nc
                plastic_work[i].εp = plastic_sub_start[i].εp
                plastic_work[i].εp33 = plastic_sub_start[i].εp33
                plastic_work[i].εp_eq = plastic_sub_start[i].εp_eq
            end
            compute_elastoplastic_stress!(uh, dh, plastic_work, mat, Ω, true,
                                          cell_points=cell_points_cache)

            u_change = norm(get_free_dof_values(uh) - u_old) / (norm(get_free_dof_values(uh)) + 1e-10)
            if u_change < 1e-5
                break
            end
        end
    end

    for i in 1:nc
        plastic_states[i].εp = plastic_work[i].εp
        plastic_states[i].εp33 = plastic_work[i].εp33
        plastic_states[i].εp_eq = plastic_work[i].εp_eq
    end
    return uh
end

# ============================================================================
# Phase-field solve
# ============================================================================

function solve_phase_field(dh_prev, H_field, V_d, U_d, dΩ)
    a(d, φ) = ∫(
        (Gc / lc + 2.0 * H_field) * d * φ +
        Gc * lc * ∇(d) ⋅ ∇(φ)
    ) * dΩ
    b(φ) = ∫(2.0 * H_field * φ) * dΩ

    op = AffineFEOperator(a, b, U_d, V_d)
    dh_solved = solve(op)

    d_new = get_free_dof_values(dh_solved)
    d_old = get_free_dof_values(dh_prev)
    for i in eachindex(d_new)
        if !isfinite(d_new[i])
            d_new[i] = d_old[i]
        end
        d_new[i] = clamp(max(d_new[i], d_old[i]), 0.0, 1.0)
    end
    return FEFunction(U_d, d_new)
end

# ============================================================================
# Plotting / output helpers
# ============================================================================

function plot_mesh_png(Ω, output_dir)
    cell_coords = get_cell_coordinates(Ω)
    nc = num_cells(Ω)

    p = plot(aspect_ratio=:equal, size=(500, 800), dpi=200,
             xlabel="x (mm)", ylabel="y (mm)",
             title="Fang 2019 mesh ($(nc) elements)",
             legend=false, grid=false)

    for i in 1:nc
        verts = cell_coords[i]
        xs = [v[1] for v in verts]; push!(xs, xs[1])
        ys = [v[2] for v in verts]; push!(ys, ys[1])
        plot!(p, xs, ys, linecolor=:black, linewidth=0.15, label="")
    end

    savefig(p, joinpath(output_dir, "geometry_mesh.png"))
    closeall()
end

function plot_cell_scalar_png(cell_coords, cell_values::Vector{Float64};
    title::String, out_file::String, cmap=:jet, dpi::Int=150,
    vmin::Union{Nothing,Float64}=nothing, vmax::Union{Nothing,Float64}=nothing)

    cmin = isnothing(vmin) ? minimum(cell_values) : vmin
    cmax = isnothing(vmax) ? maximum(cell_values) : vmax
    if !(cmax > cmin)
        cmax = cmin + 1e-12
    end

    p = plot(aspect_ratio=:equal, size=(500, 800), dpi=dpi,
             xlabel="x (mm)", ylabel="y (mm)", title=title, legend=false)
    grad = cgrad(cmap)

    for i in eachindex(cell_coords)
        verts = cell_coords[i]
        xs = [v[1] for v in verts]
        ys = [v[2] for v in verts]
        val = isfinite(cell_values[i]) ? cell_values[i] : cmin
        t = clamp((val - cmin) / (cmax - cmin), 0.0, 1.0)
        plot!(p, Shape(xs, ys), fillcolor=grad[t], linecolor=:transparent, linewidth=0.0, label="")
    end
    savefig(p, out_file)
    closeall()
end

function save_snapshot(
    tag::String,
    uh,
    dh,
    plastic_states,
    H_prev,
    Ω,
    V_dg0,
    V_proj,
    dΩ,
    cell_points_cache,
    cell_coords,
    output_dir
)
    d_qp = evaluate(dh, cell_points_cache)
    d_vals = [clamp(mean(d_qp[i]), 0.0, 1.0) for i in eachindex(d_qp)]
    epspeq_vals = [ps.εp_eq for ps in plastic_states]
    H_field = project_to_fe_space(H_prev, V_proj, dΩ)
    epspeq_field = array_to_fe_field(epspeq_vals, V_dg0, V_proj, dΩ)

    plot_cell_scalar_png(
        cell_coords, d_vals,
        title="Damage d | $(tag)",
        out_file=joinpath(output_dir, "damage_$(tag).png"),
        cmap=:jet, dpi=150, vmin=0.0, vmax=1.0
    )

    writevtk(
        Ω,
        joinpath(output_dir, "result_$(tag)"),
        cellfields=[
            "d" => dh,
            "u" => uh,
            "epspeq" => epspeq_field,
            "H" => H_field
        ],
        nsubcells=4
    )
end

function plot_force_displacement_single(u_hist, f_hist, output_dir, H_ratio)
    p = plot(
        u_hist, f_hist,
        linewidth=2.2,
        color=:blue,
        xlabel="Displacement u (mm)",
        ylabel="Force (kN)",
        title=@sprintf("Fang 2019 flat grooved specimen | H = %.1fE", H_ratio),
        legend=false,
        grid=true
    )
    savefig(p, joinpath(output_dir, @sprintf("F_u_curve_flat_grooved_H%02dE.png", round(Int, 10 * H_ratio))))
    closeall()
end

function plot_force_displacement_comparison(curves, output_dir)
    p = plot(
        xlabel="Displacement u (mm)",
        ylabel="Force (kN)",
        title="Fang 2019 flat grooved specimen | H scan",
        grid=true,
        size=(850, 620),
        dpi=220,
        legend=:bottomright
    )

    colors = [:blue, :red, :green, :orange, :black]
    for (i, curve) in enumerate(curves)
        plot!(p, curve.u_hist, curve.f_hist,
              linewidth=2.1,
              color=colors[mod1(i, length(colors))],
              label=@sprintf("H = %.1fE", curve.H_ratio))
    end
    savefig(p, joinpath(output_dir, "F_u_curve_scan.png"))
    closeall()
end

# ============================================================================
# Single-case simulation
# ============================================================================

function run_single_case(H_ratio::Float64)
    mat = create_material(H_ratio=H_ratio)
    C_tensor = elastic_stiffness_plane_strain(mat)

    case_dir = joinpath(BASE_OUTPUT_DIR, @sprintf("H%02dE", round(Int, 10 * H_ratio)))
    mkpath(case_dir)

    println("\n" * "=" ^ 80)
    @printf("Fang 2019 flat grooved specimen | H = %.1fE\n", H_ratio)
    println("=" ^ 80)
    println("  E = $(mat.E/1e3) GPa, ν = $(mat.ν), σy = $(mat.σy0) MPa")
    println("  H = $(mat.H_hard) MPa ($(H_ratio)E)")
    println("  Gc = $(Gc) N/mm, lc = $(lc) mm")
    println("  平面应变, 无 energy split, AT2, k=$(η_stab)")
    println("=" ^ 80)

    run_t0 = time()

    mesh_file = create_mesh(case_dir)
    model = GmshDiscreteModel(mesh_file)
    writevtk(model, joinpath(case_dir, "mesh"))

    Ω = Triangulation(model)
    dΩ = Measure(Ω, 2)

    plot_mesh_png(Ω, case_dir)

    Γ_top = BoundaryTriangulation(model, tags="top")
    dΓ_top = Measure(Γ_top, 2)
    n_Γ_top = get_normal_vector(Γ_top)

    order = 1

    reffe_u = ReferenceFE(lagrangian, VectorValue{2,Float64}, order)
    V_u = TestFESpace(model, reffe_u, conformity=:H1,
                      dirichlet_tags=["bottom", "top"],
                      dirichlet_masks=[(true, true), (false, true)])

    reffe_d = ReferenceFE(lagrangian, Float64, order)
    V_d = TestFESpace(model, reffe_d, conformity=:H1)
    U_d = TrialFESpace(V_d)

    reffe_dg0 = ReferenceFE(lagrangian, Float64, 0)
    V_dg0 = FESpace(model, reffe_dg0, conformity=:L2)
    reffe_L2 = ReferenceFE(lagrangian, Float64, order)
    V_L2 = FESpace(model, reffe_L2, conformity=:L2)

    quad_cache = CellQuadrature(Ω, 2)
    cell_points_cache = get_cell_points(quad_cache)

    nc = num_cells(Ω)
    println("  单元数: $(nc)")

    plastic_states = [PlasticStateData() for _ in 1:nc]
    H_prev = CellState(0.0, dΩ)

    dh = interpolate_everywhere(x -> 0.0, U_d)
    u_bottom_init(x) = VectorValue(0.0, 0.0)
    u_top_init(x) = VectorValue(0.0, 0.0)
    U_u_init = TrialFESpace(V_u, [u_bottom_init, u_top_init])
    uh = zero(U_u_init)

    disp_history = Float64[]
    force_history = Float64[]
    dmax_history = Float64[]
    epspeq_history = Float64[]
    time_history = Float64[]
    cell_coords = get_cell_coordinates(Ω)

    u_prev = 0.0
    peak_force_kN = -Inf
    reaction_stop_trigger_step::Union{Nothing,Int} = nothing
    snapshot_done = falses(length(SNAPSHOT_DAMAGE_LEVELS))

    println("\n开始单调拉伸...")

    for step in 1:N_STEPS
        u_val = step * Δu

        try
            uh = solve_displacement(
                dh, plastic_states, mat, C_tensor,
                u_val, V_u, dΩ, Ω, uh, u_prev;
                cell_points_cache=cell_points_cache
            )
        catch e
            if isa(e, SingularException)
                println("\n  奇异矩阵 (step=$(step), u=$(round(u_val,digits=4))mm), 停止")
                break
            else
                rethrow(e)
            end
        end

        σ_cell, sse_cell = compute_elastoplastic_stress!(uh, dh, plastic_states, mat, Ω, false,
                                                         cell_points=cell_points_cache)

        ψ_total_arr = zeros(nc)
        for i in 1:nc
            ψp = plastic_strain_energy(plastic_states[i].εp_eq, mat)
            ψ_total_arr[i] = sse_cell[i] + ψp
        end
        ψ_dg = FEFunction(V_dg0, ψ_total_arr)
        update_state!(update_history_variable, H_prev, ψ_dg)

        for _ in 1:max_stagger
            d_old = copy(get_free_dof_values(dh))
            H_field = project_to_fe_space(H_prev, V_L2, dΩ)
            dh = solve_phase_field(dh, H_field, V_d, U_d, dΩ)
            d_new = get_free_dof_values(dh)
            res = norm(d_new - d_old) / (norm(d_new) + 1e-10)
            if res < stagger_tol
                break
            end
        end

        σ_field = CellField(σ_cell, Ω)
        reaction = sum(∫(n_Γ_top ⋅ σ_field) * dΓ_top)
        F_y = reaction[2] * THICKNESS
        F_y_kN = F_y / 1000.0

        d_max = maximum(get_free_dof_values(dh))
        epspeq_max = maximum(ps.εp_eq for ps in plastic_states)
        elapsed_s = time() - run_t0

        push!(disp_history, u_val)
        push!(force_history, F_y_kN)
        push!(dmax_history, d_max)
        push!(epspeq_history, epspeq_max)
        push!(time_history, elapsed_s)

        peak_force_kN = max(peak_force_kN, F_y_kN)

        if step % 10 == 0 || step <= 5
            @printf("  step %4d/%d | u = %.4f mm | F = %.3f kN | d_max = %.4f | εp_max = %.6f\n",
                    step, N_STEPS, u_val, F_y_kN, d_max, epspeq_max)
        end

        for (i, threshold) in enumerate(SNAPSHOT_DAMAGE_LEVELS)
            if !snapshot_done[i] && d_max >= threshold
                tag = @sprintf("d%03d_step%04d", round(Int, 100 * threshold), step)
                try
                    save_snapshot(tag, uh, dh, plastic_states, H_prev, Ω, V_dg0, V_L2, dΩ,
                                  cell_points_cache, cell_coords, case_dir)
                catch e
                    @warn "过程快照保存失败: $e" maxlog=3
                end
                snapshot_done[i] = true
            end
        end

        u_prev = u_val

        if isnothing(reaction_stop_trigger_step)
            if peak_force_kN > STOP_REACTION_KN && F_y_kN <= STOP_REACTION_KN
                reaction_stop_trigger_step = step
                @printf("  反力降到 %.3f kN (step=%d)，将再计算 %d 步后停止\n",
                        STOP_REACTION_KN, step, STOP_AFTER_STEPS)
            end
        elseif step >= reaction_stop_trigger_step + STOP_AFTER_STEPS
            @printf("  已完成阈值后 %d 步 (当前 step=%d)，停止计算\n",
                    STOP_AFTER_STEPS, step)
            break
        end
    end

    csv_file = joinpath(case_dir, @sprintf("force_displacement_H%02dE.csv", round(Int, 10 * H_ratio)))
    open(csv_file, "w") do io
        println(io, "step,time_s,u_mm,F_kN,d_max,epspeq_max")
        for i in eachindex(disp_history)
            @printf(io, "%d,%.8f,%.8f,%.8f,%.8f,%.8f\n",
                    i, time_history[i], disp_history[i], force_history[i], dmax_history[i], epspeq_history[i])
        end
    end

    plot_force_displacement_single(disp_history, force_history, case_dir, H_ratio)
    save_snapshot("final", uh, dh, plastic_states, H_prev, Ω, V_dg0, V_L2, dΩ,
                  cell_points_cache, cell_coords, case_dir)

    runtime_s = time() - run_t0

    return (
        H_ratio = H_ratio,
        runtime_s = runtime_s,
        n_steps = length(disp_history),
        u_final = isempty(disp_history) ? 0.0 : disp_history[end],
        f_peak = isempty(force_history) ? 0.0 : maximum(force_history),
        d_final = isempty(dmax_history) ? 0.0 : dmax_history[end],
        u_hist = copy(disp_history),
        f_hist = copy(force_history),
    )
end

# ============================================================================
# Scan driver
# ============================================================================

function run_simulation()
    mkpath(BASE_OUTPUT_DIR)
    rows = NamedTuple[]
    for H_ratio in HISO_SCAN
        push!(rows, run_single_case(H_ratio))
    end

    summary_csv = joinpath(BASE_OUTPUT_DIR, "scan_summary.csv")
    open(summary_csv, "w") do io
        println(io, "H_ratio,runtime_s,n_steps,u_final_mm,f_peak_kN,d_final")
        for row in rows
            @printf(io, "%.2f,%.8f,%d,%.8f,%.8f,%.8f\n",
                    row.H_ratio, row.runtime_s, row.n_steps, row.u_final, row.f_peak, row.d_final)
        end
    end

    plot_force_displacement_comparison(rows, BASE_OUTPUT_DIR)
    println("\nScan summary saved: $(summary_csv)")
end

function main()
    run_simulation()
end

if abspath(PROGRAM_FILE) == @__FILE__
    main()
end
