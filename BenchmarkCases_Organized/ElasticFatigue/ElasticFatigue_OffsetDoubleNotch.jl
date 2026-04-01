#!/usr/bin/env julia

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
using LineSearches: BackTracking
ENV["GKSwstype"] = "100"
using Plots
gr(show=false)

const PLOT_FONT_FAMILY = "Times New Roman"
default(
    fontfamily=PLOT_FONT_FAMILY,
    titlefontfamily=PLOT_FONT_FAMILY,
    guidefontfamily=PLOT_FONT_FAMILY,
    tickfontfamily=PLOT_FONT_FAMILY,
    legend_font_family=PLOT_FONT_FAMILY,
    tick_direction=:in,
)

include(joinpath(@__DIR__, "..", "_gui_runtime_override.jl"))
using .GuiRuntimeOverride

const GUI_RUNTIME = load_runtime_override(ARGS)
const GUI_PARAMS = runtime_params(GUI_RUNTIME)
const GUI_RUN_MODE = get_string(GUI_RUNTIME, "run_mode", "compute")

# ============================================================================
# Offset double-notch brittle fatigue benchmark
#
# Purpose
#   Elastic fatigue of a tall rectangular plate with two slightly offset
#   edge precracks. The goal is to observe crack coalescence.
#
# Model
#   - AT1 phase-field with the same length-scale-insensitive degradation
#     model used in the TPB benchmark script
#   - same elastic constants / fatigue threshold / constitutive update as
#     `TPB_lengthscaleinsens_Rscan.jl`
#   - displacement-controlled cyclic loading at the top edge
#
# Study
#   - single loading amplitude
#   - scan three notch-offset geometries:
#       aligned / current / larger offset
#   - write per-case CSV + process VTU + final VTU/PNG
# ============================================================================

# ============================================================================
# Geometry
# ============================================================================
const W = 18.0
const H = 50.0
const A_LEFT = 2.5
const A_RIGHT = 2.5
const OFFSET_CASES = [
    ("aligned", 25.0, 25.0),
    ("offset_mid", 27.0, 23.0),
    ("offset_large", 29.0, 21.0),
]

# ============================================================================
# Material / phase-field
# ============================================================================
const E_mat = get_float(GUI_PARAMS, "E_mat", 20.8)
const ν_mat = get_float(GUI_PARAMS, "nu_mat", 0.30)
const Gc = get_float(GUI_PARAMS, "Gc", 5e-4)
const ls = get_float(GUI_PARAMS, "ls", 0.10)
const l0 = ls
const η_k = 1e-15

const σc = 0.2
const m = 3 * E_mat * Gc / (4 * ls * σc^2)
const ψ_Crit = σc^2 / (2 * E_mat)
const kf = 0.5
const αT = ψ_Crit / kf

# ============================================================================
# Loading
# ============================================================================
const U_MAX = get_float(GUI_PARAMS, "U_MAX", 0.05)   # mm
const R_RATIO = get_float(GUI_PARAMS, "R_RATIO", 0.10)
const MAX_CYCLES = get_int(GUI_PARAMS, "MAX_CYCLES", 1500)
const N_STEPS_PER_CYCLE = get_int(GUI_PARAMS, "N_STEPS_PER_CYCLE", 8)

# ============================================================================
# Mesh
# x full-span, y only a central band covering both notches and the ligament
# ============================================================================
const h_coarse = get_float(GUI_PARAMS, "h_coarse", 3.0)
const h_band = get_float(GUI_PARAMS, "h_band", 0.15)
const PRECRACK_HALF_WIDTH = 0.5 * h_band
const REFINE_XMIN = 0.0
const REFINE_XMAX = W
const BAND_MARGIN_Y = get_float(GUI_PARAMS, "BAND_MARGIN_Y", 3.0)
# ============================================================================
# Output / stopping
# ============================================================================
const OUTPUT_DIR = runtime_output_dir(GUI_RUNTIME, "results_ElasticFatigue_OffsetDoubleNotch")
const D_CRACK = 0.95
const D_THROUGH = 0.995
const COALESCE_TOL = max(0.5 * l0, 0.05)
const STAGNATION_WINDOW = 20
const STAGNATION_GAP_TOL = 0.02
const VTK_BRIDGE_LEVELS = [0.20, 0.50, 0.80, 1.00]
const PNG_DPI = 180

# ============================================================================
# Constitutive / fatigue helpers aligned with TPB_lengthscaleinsens_Rscan
# ============================================================================
function ElasFourthOrderConstTensor(E, ν, PlanarState)
    if PlanarState == 1
        C1111 = E / (1 - ν * ν)
        C1122 = (ν * E) / (1 - ν * ν)
        C1112 = 0.0
        C2222 = E / (1 - ν * ν)
        C2212 = 0.0
        C1212 = E / (2 * (1 + ν))
    elseif PlanarState == 2
        C1111 = (E * (1 - ν * ν)) / ((1 + ν) * (1 - ν - 2 * ν * ν))
        C1122 = (ν * E) / (1 - ν - 2 * ν * ν)
        C1112 = 0.0
        C2222 = (E * (1 - ν)) / (1 - ν - 2 * ν * ν)
        C2212 = 0.0
        C1212 = E / (2 * (1 + ν))
    else
        error("Unsupported planar state")
    end
    return SymFourthOrderTensorValue(C1111, C1112, C1122,
                                     C1112, C1212, C2212,
                                     C1122, C2212, C2222)
end

const C_mat = ElasFourthOrderConstTensor(E_mat, ν_mat, 2)
const I2 = SymTensorValue{2,Float64}(1.0, 0.0, 1.0)
const I4 = I2 ⊗ I2
const I4_sym = one(SymFourthOrderTensorValue{2,Float64})
const P_vol = 0.5 * I4
const P_dev = I4_sym - P_vol
const ε_op = symmetric_gradient

degDer(ϕ) = (m * ϕ) / (0.25 * m^2 * ϕ^4 - 0.5 * m^2 * ϕ^2 + 0.25 * m^2 -
                        m * ϕ^4 + m * ϕ^2 + ϕ^4)

phase_degradation(s) = (s^2) / (s^2 + m * (1 - s) * (0.5 + 0.5 * s))

function σfun(ε_total, ε_prev, s_prev)
    σ_elas = C_mat ⊙ ε_total
    gs = phase_degradation(s_prev)
    if tr(ε_prev) >= 0
        σ = gs * σ_elas
    else
        σ = gs * (P_dev ⊙ σ_elas) + (P_vol ⊙ σ_elas)
    end
    return σ
end

function ψPos(ε_in, Fdg)
    σ_elas = C_mat ⊙ ε_in
    if tr(ε_in) >= 0
        return 0.5 * (ε_in ⊙ σ_elas) / Fdg
    else
        return 0.5 * ((P_dev ⊙ σ_elas) ⊙ (P_dev ⊙ ε_in)) / Fdg
    end
end

function ψPosOrg(ε_in)
    σ_elas = C_mat ⊙ ε_in
    if tr(ε_in) >= 0
        return 0.5 * (ε_in ⊙ σ_elas)
    else
        return 0.5 * ((P_dev ⊙ σ_elas) ⊙ (P_dev ⊙ ε_in))
    end
end

function new_EnergyState(ψPlusPrev_in, ψhPos_in)
    ψPlus_in = ψhPos_in
    ψPlus_out = ψPlus_in >= ψPlusPrev_in ? ψPlus_in : ψPlusPrev_in
    return true, ψPlus_out
end

FatigueDegrad(αb) = @. ifelse(αb >= αT, ((2 * αT) / (αb + αT))^2, 1.0)

function FatiguehistoryVariable(ψhPos_in, αPrev, αbPrev)
    α = ψhPos_in
    αb = α >= αPrev ? αbPrev + abs(α - αPrev) : αbPrev
    return αb
end

αNC(s_in, ψhPos_in) = phase_degradation(s_in) * ψhPos_in

function cycle_displacements(umax::Float64)
    umin = R_RATIO * umax
    branch = N_STEPS_PER_CYCLE ÷ 4
    vals = Float64[]
    append!(vals, range(umin, umax, length=branch + 1)[2:end])
    append!(vals, range(umax, umin, length=branch + 1)[2:end])
    append!(vals, range(umin, 0.0, length=branch + 1)[2:end])
    append!(vals, range(0.0, umin, length=branch + 1)[2:end])
    return vals
end

function project_field(q, model, dΩ, order)
    reffe = ReferenceFE(lagrangian, Float64, order)
    V = FESpace(model, reffe, conformity = :L2)
    a(u, v) = ∫(u * v) * dΩ
    b(v) = ∫(v * q) * dΩ
    return solve(AffineFEOperator(a, b, V, V))
end

# ============================================================================
# Mesh
# ============================================================================
function create_mesh(case_dir::String, y_left::Float64, y_right::Float64)
    mkpath(case_dir)
    mesh_file = joinpath(case_dir, "mesh_offset_double_notch.msh")
    if isfile(mesh_file)
        println("\nReusing offset double-notch fatigue mesh...")
        return mesh_file
    end

    println("\nCreating offset double-notch fatigue mesh...")

    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.model.add("OffsetDoubleNotchFatigue")

    ch = PRECRACK_HALF_WIDTH
    # outer rectangle + right slit + left slit
    gmsh.model.geo.addPoint(0.0, 0.0, 0.0, h_coarse, 1)
    gmsh.model.geo.addPoint(W, 0.0, 0.0, h_coarse, 2)
    gmsh.model.geo.addPoint(W, y_right - ch, 0.0, h_coarse, 3)
    gmsh.model.geo.addPoint(W - A_RIGHT, y_right - ch, 0.0, h_band, 4)
    gmsh.model.geo.addPoint(W - A_RIGHT, y_right,      0.0, h_band, 5)
    gmsh.model.geo.addPoint(W - A_RIGHT, y_right + ch, 0.0, h_band, 6)
    gmsh.model.geo.addPoint(W, y_right + ch, 0.0, h_coarse, 7)
    gmsh.model.geo.addPoint(W, H, 0.0, h_coarse, 8)
    gmsh.model.geo.addPoint(0.0, H, 0.0, h_coarse, 9)
    gmsh.model.geo.addPoint(0.0, y_left + ch, 0.0, h_coarse, 10)
    gmsh.model.geo.addPoint(A_LEFT, y_left + ch, 0.0, h_band, 11)
    gmsh.model.geo.addPoint(A_LEFT, y_left,      0.0, h_band, 12)
    gmsh.model.geo.addPoint(A_LEFT, y_left - ch, 0.0, h_band, 13)
    gmsh.model.geo.addPoint(0.0, y_left - ch, 0.0, h_coarse, 14)

    gmsh.model.geo.addLine(1, 2, 1)
    gmsh.model.geo.addLine(2, 3, 2)
    gmsh.model.geo.addLine(3, 4, 3)
    gmsh.model.geo.addLine(4, 5, 4)
    gmsh.model.geo.addLine(5, 6, 5)
    gmsh.model.geo.addLine(6, 7, 6)
    gmsh.model.geo.addLine(7, 8, 7)
    gmsh.model.geo.addLine(8, 9, 8)
    gmsh.model.geo.addLine(9, 10, 9)
    gmsh.model.geo.addLine(10, 11, 10)
    gmsh.model.geo.addLine(11, 12, 11)
    gmsh.model.geo.addLine(12, 13, 12)
    gmsh.model.geo.addLine(13, 14, 13)
    gmsh.model.geo.addLine(14, 1, 14)

    gmsh.model.geo.addCurveLoop([1,2,3,4,5,6,7,8,9,10,11,12,13,14], 1)
    gmsh.model.geo.addPlaneSurface([1], 1)
    gmsh.model.geo.synchronize()

    gmsh.model.addPhysicalGroup(2, [1], 1)
    gmsh.model.setPhysicalName(2, 1, "Domain")
    gmsh.model.addPhysicalGroup(1, [1], 1)
    gmsh.model.setPhysicalName(1, 1, "bottom")
    gmsh.model.addPhysicalGroup(1, [8], 2)
    gmsh.model.setPhysicalName(1, 2, "top")
    gmsh.model.addPhysicalGroup(0, [1], 3)
    gmsh.model.setPhysicalName(0, 3, "left_anchor")

    root_left_x = A_LEFT
    root_left_y = y_left
    root_right_x = W - A_RIGHT
    root_right_y = y_right
    y_band_min = max(0.0, min(y_left, y_right) - BAND_MARGIN_Y)
    y_band_max = min(H, max(y_left, y_right) + BAND_MARGIN_Y)
    gmsh.model.geo.synchronize()

    gmsh.model.mesh.field.add("Box", 1)
    gmsh.model.mesh.field.setNumber(1, "VIn", h_band)
    gmsh.model.mesh.field.setNumber(1, "VOut", h_coarse)
    gmsh.model.mesh.field.setNumber(1, "XMin", REFINE_XMIN)
    gmsh.model.mesh.field.setNumber(1, "XMax", REFINE_XMAX)
    gmsh.model.mesh.field.setNumber(1, "YMin", y_band_min)
    gmsh.model.mesh.field.setNumber(1, "YMax", y_band_max)
    gmsh.model.mesh.field.setNumber(1, "Thickness", 0.0)
    gmsh.model.mesh.field.setAsBackgroundMesh(1)

    gmsh.option.setNumber("Mesh.Algorithm", 6)
    gmsh.option.setNumber("Mesh.RecombineAll", 0)
    gmsh.option.setNumber("Mesh.Smoothing", 2)
    gmsh.model.mesh.generate(2)

    gmsh.write(mesh_file)

    n_nodes = length(gmsh.model.mesh.getNodes()[1])
    n_trias = length(gmsh.model.mesh.getElementsByType(2)[1])
    println("  nodes = $(n_nodes)")
    println("  triangles = $(n_trias)")
    @printf("  h_band = %.5f mm, h_coarse = %.3f mm\n", h_band, h_coarse)
    @printf("  notch roots: left(%.2f, %.2f), right(%.2f, %.2f)\n",
            root_left_x, root_left_y, root_right_x, root_right_y)
    @printf("  refine band: x ∈ [%.1f, %.1f], y ∈ [%.1f, %.1f]\n",
            REFINE_XMIN, REFINE_XMAX, y_band_min, y_band_max)
    println("  refinement = full-span horizontal band covering both precracks")

    gmsh.finalize()
    return mesh_file
end

# ============================================================================
# Plot helpers
# ============================================================================
function save_mesh_plot(cell_coords, out_file)
    p = plot(aspect_ratio=:equal, size=(560, 1080), dpi=PNG_DPI,
             xlabel="x (mm)", ylabel="y (mm)", title="Offset double-notch mesh",
             legend=false, grid=false, framestyle=:box,
             xmirror=false, ymirror=false, guidefontsize=15, tickfontsize=8,
             tick_direction=:in, foreground_color_axis=:black,
             foreground_color_border=:black, foreground_color_guide=:black)
    for pts in cell_coords
        xs = [v[1] for v in pts]
        ys = [v[2] for v in pts]
        plot!(p, Shape(xs, ys), fillcolor=:white, fillalpha=0.0,
              linecolor=:gray55, linewidth=0.2, label="")
    end
    savefig(p, out_file)
    closeall()
end

function save_damage_plot(cell_coords, d_vals::Vector{Float64}; title_str, out_file)
    grad = cgrad(:jet)
    p = plot(aspect_ratio=:equal, size=(560, 1080), dpi=PNG_DPI,
             xlabel="x (mm)", ylabel="y (mm)", title=title_str,
             legend=false, colorbar=true, grid=false, framestyle=:box,
             xlims=(0.0, W), ylims=(0.0, H))
    for i in eachindex(cell_coords)
        xs = [v[1] for v in cell_coords[i]]
        ys = [v[2] for v in cell_coords[i]]
        ξ = clamp(d_vals[i], 0.0, 1.0)
        plot!(p, Shape(xs, ys), fillcolor=grad[ξ],
              linecolor=:transparent, linewidth=0.0, label="")
    end
    savefig(p, out_file)
    closeall()
end

# ============================================================================
# Crack-tip / coalescence metrics
# ============================================================================
function safe_eval(field, x, y, default)
    try
        val = field(Gridap.Geometry.Point(x, y))
        return isfinite(val) ? val : default
    catch
        return default
    end
end

function crack_tips_from_field(sh, y_left, y_right)
    xs_left = collect(range(A_LEFT, W, length=1601))
    x_left_tip = A_LEFT
    for x in xs_left
        dval = 1.0 - safe_eval(sh, x, y_left, 1.0)
        if dval >= D_CRACK
            x_left_tip = x
        end
    end

    xs_right = collect(range(W - A_RIGHT, 0.0, length=1601))
    x_right_tip = W - A_RIGHT
    for x in xs_right
        dval = 1.0 - safe_eval(sh, x, y_right, 1.0)
        if dval >= D_CRACK
            x_right_tip = x
        end
    end
    return x_left_tip, x_right_tip
end

function aligned_through_damage(sh, y_line::Float64)
    xs = range(A_LEFT, W - A_RIGHT, length=801)
    for x in xs
        dval = 1.0 - safe_eval(sh, x, y_line, 1.0)
        if dval < D_THROUGH
            return false
        end
    end
    return true
end

@inline left_extension(x_left_tip) = max(0.0, x_left_tip - A_LEFT)
@inline right_extension(x_right_tip) = max(0.0, (W - A_RIGHT) - x_right_tip)
@inline ligament_gap(x_left_tip, x_right_tip) = max(0.0, x_right_tip - x_left_tip)

# ============================================================================
# Solvers
# ============================================================================
function solve_displacement(uh_prev, sh, FdhPrev, U_u, V_u, dΩ)
    a(u, v) = ∫((ε_op(v) ⊙ (σfun ∘ (ε_op(u), ε_op(uh_prev), sh)))) * dΩ
    b(v) = 0.0
    op = AffineFEOperator(a, b, U_u, V_u)
    return solve(op)
end

function solve_phasefield(sh_prev, x0_pf, ψhPlusPrev, V_d, U_d, dΩ)
    nls = NLSolver(show_trace=false, method=:newton, linesearch=BackTracking(), iterations=10)
    solver = FESolver(nls)
    U_loc = TrialFESpace(V_d)
    res(s, ϕ) = ∫((3/4)*Gc*ls*∇(ϕ)⋅∇(s) + (degDer∘(s))*ψhPlusPrev*ϕ - ((3/8)*Gc/ls)*ϕ) * dΩ
    op = FEOperator(res, U_loc, V_d)
    sh_out = FEFunction(U_loc, x0_pf)
    sh_out, cache = solve!(sh_out, solver, op, nothing)
    return sh_out, get_free_dof_values(sh_out), cache
end

# ============================================================================
# Result type
# ============================================================================
Base.@kwdef mutable struct RunResult
    case_label::String = ""
    y_left::Float64 = 0.0
    y_right::Float64 = 0.0
    cycles::Vector{Float64} = Float64[]
    time_hist::Vector{Float64} = Float64[]
    gap_hist::Vector{Float64} = Float64[]
    left_hist::Vector{Float64} = Float64[]
    right_hist::Vector{Float64} = Float64[]
    dmax_hist::Vector{Float64} = Float64[]
    alpha_hist::Vector{Float64} = Float64[]
    fmin_hist::Vector{Float64} = Float64[]
    cycle_coalescence::Union{Nothing,Float64} = nothing
    cycle_stagnation::Union{Nothing,Float64} = nothing
    runtime_s::Float64 = 0.0
end

# ============================================================================
# Main
# ============================================================================
function run_all()
    mkpath(OUTPUT_DIR)
    println("=" ^ 78)
    println("Offset double-notch brittle fatigue | notch-offset scan")
    println("=" ^ 78)
    @printf("  E = %.0f MPa, nu = %.2f, Gc = %.3f N/mm, l0 = %.4f mm\n", E_mat, ν_mat, Gc, l0)
    @printf("  alphaT = %.6f N/mm^2, R = %.2f\n", αT, R_RATIO)
    @printf("  Umax = %.4f mm\n", U_MAX)
    println("  offset cases = $(map(x -> x[1], OFFSET_CASES))")
    println("  cycles <= $(MAX_CYCLES), substeps/cycle = $(N_STEPS_PER_CYCLE)")
    all_results = RunResult[]

    for (case_label, y_left, y_right) in OFFSET_CASES
        case_tag = case_label
        case_dir = joinpath(OUTPUT_DIR, case_tag)
        mkpath(case_dir)

        mesh_file = create_mesh(case_dir, y_left, y_right)
        model = GmshDiscreteModel(mesh_file)
        Ω = Triangulation(model)
        dΩ = Measure(Ω, 2)

        order = 1
        reffe_u = ReferenceFE(lagrangian, VectorValue{2,Float64}, order)
        reffe_d = ReferenceFE(lagrangian, Float64, order)
        V_u = TestFESpace(model, reffe_u, conformity=:H1,
                          dirichlet_tags=["bottom", "top", "left_anchor"],
                          dirichlet_masks=[(false, true), (false, true), (true, false)])
        V_d = TestFESpace(model, reffe_d, conformity=:H1)
        U_d = TrialFESpace(V_d)
        cell_coords = get_cell_coordinates(Ω)
        quad_cache = CellQuadrature(Ω, 2)
        cell_pts = get_cell_points(quad_cache)

        save_mesh_plot(cell_coords, joinpath(case_dir, "mesh.png"))

        println("\n" * "-" ^ 78)
        @printf("Running case: %s | y_left = %.2f, y_right = %.2f\n", case_label, y_left, y_right)
        println("-" ^ 78)

        sh = interpolate_everywhere(x -> 1.0, U_d)
        x0_pf = ones(Float64, num_free_dofs(V_d))
        ψPlusPrev = CellState(ψ_Crit, dΩ)
        αPrev = CellState(0.0, dΩ)
        αbPrev = CellState(0.0, dΩ)
        αhPlusPrev = project_field(αPrev, model, dΩ, order)
        αbhPlusPrev = project_field(αbPrev, model, dΩ, order)
        result = RunResult(case_label=case_label, y_left=y_left, y_right=y_right)
        run_t0 = time()
        next_vtk_idx = 1
        cycle_u = cycle_displacements(U_MAX)
        u0_bottom(x) = VectorValue(0.0, 0.0)
        u0_top(x) = VectorValue(0.0, 0.0)
        u0_anchor(x) = VectorValue(0.0, 0.0)
        U_u0 = TrialFESpace(V_u, [u0_bottom, u0_top, u0_anchor])
        uh_last = FEFunction(U_u0, zeros(Float64, num_free_dofs(U_u0)))

        gap0 = ligament_gap(A_LEFT, W - A_RIGHT)
        for cycle in 1:MAX_CYCLES
            for u_val in cycle_u
                u_bc_bottom(x) = VectorValue(0.0, 0.0)
                u_bc_top(x) = VectorValue(0.0, u_val)
                u_bc_left_anchor(x) = VectorValue(0.0, 0.0)
                U_u = TrialFESpace(V_u, [u_bc_bottom, u_bc_top, u_bc_left_anchor])
                FdhPrev = FatigueDegrad ∘ αbhPlusPrev
                uh = solve_displacement(uh_last, sh, FdhPrev, U_u, V_u, dΩ)
                uh_last = uh
                ψhPos_in = ψPos ∘ (ε_op(uh), FdhPrev)
                update_state!(new_EnergyState, ψPlusPrev, ψhPos_in)
                ψhPlusPrev = project_field(ψPlusPrev, model, dΩ, order)
                sh, x0_pf, _ = solve_phasefield(sh, x0_pf, ψhPlusPrev, V_d, U_d, dΩ)

                ψhPosOrg_in = ψPosOrg ∘ (ε_op(uh))
                αPrev = αNC ∘ (sh, ψhPosOrg_in)
                αbPrev = FatiguehistoryVariable ∘ (αPrev, αhPlusPrev, αbhPlusPrev)
                αhPlusPrev = project_field(αPrev, model, dΩ, order)
                αbhPlusPrev = project_field(αbPrev, model, dΩ, order)
            end

            x_left_tip, x_right_tip = crack_tips_from_field(sh, y_left, y_right)
            gap_now = ligament_gap(x_left_tip, x_right_tip)
            a_left = left_extension(x_left_tip)
            a_right = right_extension(x_right_tip)
            dmax_now = 1.0 - minimum(get_free_dof_values(sh))
            α_qp = evaluate(αbhPlusPrev, cell_pts)
            alpha_max = maximum([maximum(α_qp[i]) for i in eachindex(α_qp)])
            f_qp = evaluate(FatigueDegrad ∘ αbhPlusPrev, cell_pts)
            f_min = minimum([minimum(f_qp[i]) for i in eachindex(f_qp)])

            push!(result.cycles, cycle)
            push!(result.time_hist, time() - run_t0)
            push!(result.gap_hist, gap_now)
            push!(result.left_hist, a_left)
            push!(result.right_hist, a_right)
            push!(result.dmax_hist, dmax_now)
            push!(result.alpha_hist, alpha_max)
            push!(result.fmin_hist, f_min)

            if cycle <= 5 || cycle % 50 == 0 || gap_now < gap0
                @printf("  cycle %4d | aL = %.4f mm | aR = %.4f mm | gap = %.4f mm | d_max = %.4f | f_min = %.4f\n",
                        cycle, a_left, a_right, gap_now, dmax_now, f_min)
            end

            bridge_progress = clamp((gap0 - gap_now) / max(gap0, 1e-12), 0.0, 1.0)
            while uh_last !== nothing &&
                  next_vtk_idx <= length(VTK_BRIDGE_LEVELS) &&
                  bridge_progress >= VTK_BRIDGE_LEVELS[next_vtk_idx]
                ψhPlusPrev = project_field(ψPlusPrev, model, dΩ, order)
                f_field = FatigueDegrad ∘ αbhPlusPrev
                out_tag = @sprintf("result_bridge%02d_cycle%04d",
                                   round(Int, 100 * VTK_BRIDGE_LEVELS[next_vtk_idx]), cycle)
                writevtk(
                    Ω,
                    joinpath(case_dir, out_tag),
                    cellfields=["d" => (1.0 - sh), "u" => uh_last, "H" => ψhPlusPrev,
                                "alpha" => αbhPlusPrev, "falpha" => f_field],
                    nsubcells=4
                )
                next_vtk_idx += 1
            end

            if isnothing(result.cycle_coalescence) && gap_now <= COALESCE_TOL
                result.cycle_coalescence = cycle
                if isapprox(y_left, y_right; atol=1e-8)
                    println(@sprintf("  aligned coalescence first reached at cycle %d; waiting for full through-damage", cycle))
                else
                    println(@sprintf("  coalescence reached at cycle %d", cycle))
                    break
                end
            end

            if isapprox(y_left, y_right; atol=1e-8) &&
               !isnothing(result.cycle_coalescence) &&
               aligned_through_damage(sh, y_left)
                println(@sprintf("  full through-damage reached at cycle %d", cycle))
                break
            end

            if cycle >= STAGNATION_WINDOW &&
               dmax_now >= 0.999 &&
               f_min <= 1e-6
                recent_gaps = @view result.gap_hist[end-STAGNATION_WINDOW+1:end]
                if maximum(recent_gaps) - minimum(recent_gaps) <= STAGNATION_GAP_TOL
                    result.cycle_stagnation = cycle
                    println(@sprintf("  crack-growth stagnation detected at cycle %d (gap ≈ %.4f mm)", cycle, gap_now))
                    break
                end
            end
        end

        result.runtime_s = time() - run_t0

        open(joinpath(case_dir, "history.csv"), "w") do io
            println(io, "cycle,time_s,left_extension_mm,right_extension_mm,gap_mm,d_max,alpha_max,f_min")
            for i in eachindex(result.cycles)
                @printf(io, "%d,%.8f,%.8f,%.8f,%.8f,%.8f,%.8f,%.8f\n",
                        round(Int, result.cycles[i]), result.time_hist[i], result.left_hist[i],
                        result.right_hist[i], result.gap_hist[i], result.dmax_hist[i],
                        result.alpha_hist[i], result.fmin_hist[i])
            end
        end

        if uh_last !== nothing
            ψhPlusPrev = project_field(ψPlusPrev, model, dΩ, order)
            f_field = FatigueDegrad ∘ αbhPlusPrev
            writevtk(
                Ω,
                joinpath(case_dir, "result_final"),
                cellfields=["d" => (1.0 - sh), "u" => uh_last, "H" => ψhPlusPrev,
                            "alpha" => αbhPlusPrev, "falpha" => f_field],
                nsubcells=4
            )

            s_qp_final = evaluate(sh, cell_pts)
            d_cell_final = [1.0 - mean(s_qp_final[i]) for i in 1:length(s_qp_final)]
            save_damage_plot(
                cell_coords, d_cell_final;
                title_str=@sprintf("Final damage | %s", case_label),
                out_file=joinpath(case_dir, "damage_final.png")
            )
        end

        push!(all_results, result)
    end

    open(joinpath(OUTPUT_DIR, "scan_summary.csv"), "w") do io
        println(io, "case_label,y_left_mm,y_right_mm,cycle_coalescence,cycle_stagnation,runtime_s")
        for res in all_results
            cyc = isnothing(res.cycle_coalescence) ? -1.0 : res.cycle_coalescence
            cyc_stag = isnothing(res.cycle_stagnation) ? -1.0 : res.cycle_stagnation
            @printf(io, "%s,%.8f,%.8f,%.0f,%.0f,%.8f\n",
                    res.case_label, res.y_left, res.y_right, cyc, cyc_stag, res.runtime_s)
        end
    end
end

function build_mesh_assets_only()
    mkpath(OUTPUT_DIR)
    println("=" ^ 78)
    println("Offset double-notch brittle fatigue | mesh stage")
    println("=" ^ 78)
    for (case_label, y_left, y_right) in OFFSET_CASES
        case_dir = joinpath(OUTPUT_DIR, case_label)
        mkpath(case_dir)
        mesh_file = create_mesh(case_dir, y_left, y_right)
        model = GmshDiscreteModel(mesh_file)
        Ω = Triangulation(model)
        dΩ = Measure(Ω, 2)
        cell_coords = get_cell_coordinates(Ω)
        save_mesh_plot(cell_coords, joinpath(case_dir, "mesh.png"))
        println("  mesh ready: $(case_label)")
    end
end

function main()
    if GUI_RUN_MODE == "mesh"
        build_mesh_assets_only()
        println("Mesh stage completed.")
        return
    end
    run_all()
end

if abspath(PROGRAM_FILE) == @__FILE__
    main()
end
