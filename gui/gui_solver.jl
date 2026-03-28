using Gmsh: gmsh
using Gridap
using Gridap.Geometry
using Gridap.TensorValues
using Gridap.CellData
using Gridap.FESpaces
using Gridap.Algebra
using GridapGmsh
using LinearAlgebra
using Printf

ENV["GKSwstype"] = "100"
using Plots
gr(show=false)

function resolve_plot_font_family()
    font_dirs = filter(isdir, [
        "/usr/share/fonts",
        "/usr/local/share/fonts",
        joinpath(homedir(), ".fonts"),
        joinpath(homedir(), ".local", "share", "fonts"),
    ])
    for font_dir in font_dirs
        for (root, _, files) in walkdir(font_dir)
            for file in files
                lower_name = lowercase(file)
                if occursin("times", lower_name) && endswith(lower_name, ".ttf")
                    return "Times New Roman"
                end
            end
        end
    end
    return "Times"
end

const PLOT_FONT_FAMILY = resolve_plot_font_family()
default(
    fontfamily=PLOT_FONT_FAMILY,
    titlefontfamily=PLOT_FONT_FAMILY,
    guidefontfamily=PLOT_FONT_FAMILY,
    tickfontfamily=PLOT_FONT_FAMILY,
    legend_font_family=PLOT_FONT_FAMILY,
)

const CASE_SENT = "SENT"
const CASE_SENS = "SENS"

const GUI_DIR = @__DIR__
const OUTPUT_DIR = joinpath(GUI_DIR, "gui_results")
const STOP_FLAG_PATH = joinpath(GUI_DIR, "gui_stop.flag")
const PNG_DPI = 140
const PNG_NX = 220
const PNG_NY = 220
const SAVE_VTK = true
const ENABLE_PNG = true
const F_STOP_TOL = 1.0e-3
const VTK_ONSET_LEVEL = 0.999
const VTK_FORCE_DROP_LEVELS = (0.75, 0.50, 0.25)
const REFINE_XMIN_SENT = 0.45
const REFINE_XMAX_SENT = 1.00
const REFINE_YMIN_SENT = 0.40
const REFINE_YMAX_SENT = 0.60
const REFINE_XMIN_SENS = 0.49
const REFINE_XMAX_SENS = 1.00
const REFINE_YMIN_SENS = 0.00
const REFINE_YMAX_SENS = 0.55

abstract type AbstractCaseParams end

struct SentParams <: AbstractCaseParams
    W::Float64
    H::Float64
    a0::Float64
    E::Float64
    nu::Float64
    Gc::Float64
    l0::Float64
    eta_k::Float64
    h_fine::Float64
    h_coarse::Float64
    N_steps_coarse::Int
    du_coarse::Float64
    du_fine::Float64
    u_end::Float64
    snapshot_every::Int
end

struct SensParams <: AbstractCaseParams
    W::Float64
    H::Float64
    a0::Float64
    E::Float64
    nu::Float64
    Gc::Float64
    l0::Float64
    eta_k::Float64
    h_fine::Float64
    h_coarse::Float64
    du_shear::Float64
    u_end::Float64
    snapshot_every::Int
end

const CaseParams = Union{SentParams,SensParams}

struct RunConfig
    case_name::String
    run_mode::String
    mesh_file::String
    params::CaseParams
end

case_name(::SentParams) = CASE_SENT
case_name(::SensParams) = CASE_SENS

@inline y_notch(params::CaseParams) = 0.5 * params.H
@inline ch_precrack(params::CaseParams) = 0.5 * params.h_fine
@inline lambda_mat(params::CaseParams) = params.E * params.nu / ((1 + params.nu) * (1 - 2 * params.nu))
@inline shear_mat(params::CaseParams) = params.E / (2 * (1 + params.nu))

mesh_msh_name(name::String) = "mesh_$(name).msh"
mesh_png_name(name::String) = "mesh_$(name).png"
curve_csv_name(name::String) = "F_u_curve_$(name).csv"
curve_png_name(name::String) = "F_u_curve_$(name).png"
damage_final_name(name::String) = "d_final_$(name).png"
displacement_final_name(name::String) = "u_mag_final_$(name).png"
snapshot_name(name::String, step::Int) = @sprintf("snap_%s_%04d.png", name, step)
vtk_prefix(name::String) = "result_$(name)_"
vtk_filename(name::String, suffix::String) = vtk_prefix(name) * suffix

function emit_line(msg::AbstractString)
    println(msg)
    flush(stdout)
end

emit_info(msg::AbstractString) = emit_line("INFO " * msg)
emit_error(msg::AbstractString) = emit_line("ERROR " * msg)

function parse_flat_json(path::String)
    text = read(path, String)
    pairs = Dict{String,String}()
    for m in eachmatch(r"\"([^\"]+)\"\s*:\s*([^,\}\n]+)", text)
        key = m.captures[1]
        raw = strip(m.captures[2])
        pairs[key] = replace(raw, "\"" => "")
    end
    return pairs
end

function require_key(data::Dict{String,String}, key::String)
    haskey(data, key) || error("Missing key in params file: " * key)
    return data[key]
end

function parse_sent_params(data::Dict{String,String})
    return SentParams(
        parse(Float64, require_key(data, "W")),
        parse(Float64, require_key(data, "H")),
        parse(Float64, require_key(data, "a0")),
        parse(Float64, require_key(data, "E")),
        parse(Float64, require_key(data, "nu")),
        parse(Float64, require_key(data, "Gc")),
        parse(Float64, require_key(data, "l0")),
        parse(Float64, require_key(data, "eta_k")),
        parse(Float64, require_key(data, "h_fine")),
        parse(Float64, require_key(data, "h_coarse")),
        parse(Int, require_key(data, "N_steps_coarse")),
        parse(Float64, require_key(data, "du_coarse")),
        parse(Float64, require_key(data, "du_fine")),
        parse(Float64, require_key(data, "u_end")),
        parse(Int, require_key(data, "snapshot_every")),
    )
end

function parse_sens_params(data::Dict{String,String})
    return SensParams(
        parse(Float64, require_key(data, "W")),
        parse(Float64, require_key(data, "H")),
        parse(Float64, require_key(data, "a0")),
        parse(Float64, require_key(data, "E")),
        parse(Float64, require_key(data, "nu")),
        parse(Float64, require_key(data, "Gc")),
        parse(Float64, require_key(data, "l0")),
        parse(Float64, require_key(data, "eta_k")),
        parse(Float64, require_key(data, "h_fine")),
        parse(Float64, require_key(data, "h_coarse")),
        parse(Float64, require_key(data, "du_shear")),
        parse(Float64, require_key(data, "u_end")),
        parse(Int, require_key(data, "snapshot_every")),
    )
end

function parse_params(path::String)
    data = parse_flat_json(path)
    selected_case = uppercase(get(data, "case_name", CASE_SENT))
    params = if selected_case == CASE_SENT
        parse_sent_params(data)
    elseif selected_case == CASE_SENS
        parse_sens_params(data)
    else
        error("Unsupported case_name: " * selected_case)
    end
    run_mode = get(data, "run_mode", "compute")
    mesh_file = get(data, "mesh_file", "")
    return RunConfig(selected_case, run_mode, mesh_file, params)
end

function validate_common_params(params::CaseParams)
    params.W > 0 || error("W must be > 0")
    params.H > 0 || error("H must be > 0")
    0.0 < params.a0 < params.W || error("a0 must be in (0, W)")
    params.E > 0 || error("E must be > 0")
    0.0 < params.nu < 0.5 || error("nu must be in (0, 0.5)")
    params.Gc > 0 || error("Gc must be > 0")
    params.l0 > 0 || error("l0 must be > 0")
    params.h_fine > 0 || error("h_fine must be > 0")
    params.h_coarse > 0 || error("h_coarse must be > 0")
    params.snapshot_every >= 1 || error("snapshot_every must be >= 1")
    params.h_fine <= params.h_coarse || error("h_fine should be <= h_coarse")
    return nothing
end

function validate_params(params::SentParams)
    validate_common_params(params)
    params.N_steps_coarse >= 0 || error("N_steps_coarse must be >= 0")
    params.du_coarse > 0 || error("du_coarse must be > 0")
    params.du_fine > 0 || error("du_fine must be > 0")
    params.u_end > 0 || error("u_end must be > 0")
    return nothing
end

function validate_params(params::SensParams)
    validate_common_params(params)
    params.du_shear > 0 || error("du_shear must be > 0")
    params.u_end > 0 || error("u_end must be > 0")
    return nothing
end

function clear_case_outputs(selected_case::String; mesh::Bool=false, compute::Bool=false)
    mkpath(OUTPUT_DIR)
    if isfile(STOP_FLAG_PATH)
        rm(STOP_FLAG_PATH; force=true)
    end
    for name in readdir(OUTPUT_DIR)
        path = joinpath(OUTPUT_DIR, name)
        isfile(path) || continue
        if mesh && (name == mesh_msh_name(selected_case) || name == mesh_png_name(selected_case))
            rm(path; force=true)
            continue
        end
        if !compute
            continue
        end
        if startswith(name, "snap_$(selected_case)_") ||
           startswith(name, vtk_prefix(selected_case)) ||
           name == curve_csv_name(selected_case) ||
           name == curve_png_name(selected_case) ||
           name == damage_final_name(selected_case) ||
           name == displacement_final_name(selected_case)
            rm(path; force=true)
        end
    end
end

prepare_mesh_output_dir(selected_case::String) = clear_case_outputs(selected_case; mesh=true, compute=true)
prepare_compute_output_dir(selected_case::String) = clear_case_outputs(selected_case; compute=true)

function init_live_csv(selected_case::String)
    csv_path = joinpath(OUTPUT_DIR, curve_csv_name(selected_case))
    open(csv_path, "w") do io
        println(io, "step,time_s,u_mm,F_N,F_kN")
    end
    return csv_path
end

function append_csv_row(csv_path::String, step::Int, time_s::Float64, u_mm::Float64, f_n::Float64, f_kn::Float64)
    open(csv_path, "a") do io
        @printf(io, "%d,%.6f,%.12e,%.12e,%.12e\n", step, time_s, u_mm, f_n, f_kn)
    end
end

maybe_stopped() = isfile(STOP_FLAG_PATH)

@inline function miehe_psi_plus(ε_2d::SymTensorValue{2,Float64,3}, λ_val::Float64, G_val::Float64)
    ε11 = ε_2d[1,1]
    ε22 = ε_2d[2,2]
    ε12 = ε_2d[1,2]
    avg = 0.5 * (ε11 + ε22)
    dif = 0.5 * (ε11 - ε22)
    rad = sqrt(dif^2 + ε12^2)
    ε1 = avg + rad
    ε2 = avg - rad
    ε3 = 0.0
    trp = max(ε1 + ε2 + ε3, 0.0)
    return 0.5 * λ_val * trp^2 +
           G_val * (max(ε1, 0.0)^2 + max(ε2, 0.0)^2 + max(ε3, 0.0)^2)
end

@inline g_deg(d::Float64, eta_k::Float64) = (1.0 - clamp(d, 0.0, 1.0))^2 + eta_k

function elastic_stiffness(λ_val::Float64, G_val::Float64)
    return SymFourthOrderTensorValue(
        λ_val + 2G_val, 0.0, λ_val,
        0.0, G_val, 0.0,
        λ_val, 0.0, λ_val + 2G_val
    )
end

function create_mesh(params::SentParams)
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.model.add("SENT_tension_gui")

    CH = ch_precrack(params)
    notch_y = y_notch(params)

    gmsh.model.geo.addPoint(0.0, 0.0, 0.0, params.h_coarse, 1)
    gmsh.model.geo.addPoint(params.W, 0.0, 0.0, params.h_coarse, 2)
    gmsh.model.geo.addPoint(params.W, notch_y, 0.0, params.h_coarse, 10)
    gmsh.model.geo.addPoint(params.W, params.H, 0.0, params.h_coarse, 3)
    gmsh.model.geo.addPoint(0.0, params.H, 0.0, params.h_coarse, 4)
    gmsh.model.geo.addPoint(0.0, notch_y + CH, 0.0, params.h_coarse, 5)
    gmsh.model.geo.addPoint(params.a0, notch_y + CH, 0.0, params.h_fine, 6)
    gmsh.model.geo.addPoint(params.a0, notch_y, 0.0, params.h_fine, 7)
    gmsh.model.geo.addPoint(params.a0, notch_y - CH, 0.0, params.h_fine, 8)
    gmsh.model.geo.addPoint(0.0, notch_y - CH, 0.0, params.h_coarse, 9)

    gmsh.model.geo.addLine(1, 2, 1)
    gmsh.model.geo.addLine(2, 10, 2)
    gmsh.model.geo.addLine(10, 3, 10)
    gmsh.model.geo.addLine(3, 4, 3)
    gmsh.model.geo.addLine(4, 5, 4)
    gmsh.model.geo.addLine(5, 6, 5)
    gmsh.model.geo.addLine(6, 7, 6)
    gmsh.model.geo.addLine(7, 8, 7)
    gmsh.model.geo.addLine(8, 9, 8)
    gmsh.model.geo.addLine(9, 1, 9)

    gmsh.model.geo.addCurveLoop([1, 2, 10, 3, 4, 5, 6, 7, 8, 9], 1)
    gmsh.model.geo.addPlaneSurface([1], 1)
    gmsh.model.geo.synchronize()

    gmsh.model.addPhysicalGroup(2, [1], 1)
    gmsh.model.setPhysicalName(2, 1, "Domain")
    gmsh.model.addPhysicalGroup(1, [1], 1)
    gmsh.model.setPhysicalName(1, 1, "bottom")
    gmsh.model.addPhysicalGroup(1, [3], 2)
    gmsh.model.setPhysicalName(1, 2, "top")

    gmsh.model.mesh.field.add("Box", 1)
    gmsh.model.mesh.field.setNumber(1, "VIn", params.h_fine)
    gmsh.model.mesh.field.setNumber(1, "VOut", params.h_coarse)
    gmsh.model.mesh.field.setNumber(1, "XMin", REFINE_XMIN_SENT * params.W)
    gmsh.model.mesh.field.setNumber(1, "XMax", REFINE_XMAX_SENT * params.W)
    gmsh.model.mesh.field.setNumber(1, "YMin", REFINE_YMIN_SENT * params.H)
    gmsh.model.mesh.field.setNumber(1, "YMax", REFINE_YMAX_SENT * params.H)
    gmsh.model.mesh.field.setAsBackgroundMesh(1)

    gmsh.option.setNumber("Mesh.Algorithm", 6)
    gmsh.option.setNumber("Mesh.RecombineAll", 0)
    gmsh.option.setNumber("Mesh.Smoothing", 2)

    gmsh.model.mesh.generate(2)
    mesh_file = joinpath(OUTPUT_DIR, mesh_msh_name(CASE_SENT))
    gmsh.write(mesh_file)
    n_nodes = length(gmsh.model.mesh.getNodes()[1])
    n_quads = length(gmsh.model.mesh.getElementsByType(3)[1])
    n_trias = length(gmsh.model.mesh.getElementsByType(2)[1])
    gmsh.finalize()

    emit_info(@sprintf("%s mesh generated: nodes=%d trias=%d quads=%d", CASE_SENT, n_nodes, n_trias, n_quads))
    return mesh_file
end

function create_mesh(params::SensParams)
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.model.add("SENS_shear_gui")

    CH = ch_precrack(params)
    notch_y = y_notch(params)

    gmsh.model.geo.addPoint(0.0, 0.0, 0.0, params.h_coarse, 1)
    gmsh.model.geo.addPoint(params.W, 0.0, 0.0, params.h_coarse, 2)
    gmsh.model.geo.addPoint(params.W, notch_y, 0.0, params.h_coarse, 10)
    gmsh.model.geo.addPoint(params.W, params.H, 0.0, params.h_coarse, 3)
    gmsh.model.geo.addPoint(0.0, params.H, 0.0, params.h_coarse, 4)
    gmsh.model.geo.addPoint(0.0, notch_y + CH, 0.0, params.h_coarse, 5)
    gmsh.model.geo.addPoint(params.a0, notch_y + CH, 0.0, params.h_fine, 6)
    gmsh.model.geo.addPoint(params.a0, notch_y, 0.0, params.h_fine, 7)
    gmsh.model.geo.addPoint(params.a0, notch_y - CH, 0.0, params.h_fine, 8)
    gmsh.model.geo.addPoint(0.0, notch_y - CH, 0.0, params.h_coarse, 9)

    gmsh.model.geo.addLine(1, 2, 1)
    gmsh.model.geo.addLine(2, 10, 2)
    gmsh.model.geo.addLine(10, 3, 10)
    gmsh.model.geo.addLine(3, 4, 3)
    gmsh.model.geo.addLine(4, 5, 4)
    gmsh.model.geo.addLine(5, 6, 5)
    gmsh.model.geo.addLine(6, 7, 6)
    gmsh.model.geo.addLine(7, 8, 7)
    gmsh.model.geo.addLine(8, 9, 8)
    gmsh.model.geo.addLine(9, 1, 9)

    gmsh.model.geo.addCurveLoop([1, 2, 10, 3, 4, 5, 6, 7, 8, 9], 1)
    gmsh.model.geo.addPlaneSurface([1], 1)
    gmsh.model.geo.synchronize()

    gmsh.model.addPhysicalGroup(2, [1], 1)
    gmsh.model.setPhysicalName(2, 1, "Domain")
    gmsh.model.addPhysicalGroup(1, [1], 1)
    gmsh.model.setPhysicalName(1, 1, "bottom")
    gmsh.model.addPhysicalGroup(1, [3], 2)
    gmsh.model.setPhysicalName(1, 2, "top")
    gmsh.model.addPhysicalGroup(1, [4, 9], 3)
    gmsh.model.setPhysicalName(1, 3, "left")

    gmsh.model.mesh.field.add("Box", 1)
    gmsh.model.mesh.field.setNumber(1, "VIn", params.h_fine)
    gmsh.model.mesh.field.setNumber(1, "VOut", params.h_coarse)
    gmsh.model.mesh.field.setNumber(1, "XMin", REFINE_XMIN_SENS)
    gmsh.model.mesh.field.setNumber(1, "XMax", REFINE_XMAX_SENS)
    gmsh.model.mesh.field.setNumber(1, "YMin", REFINE_YMIN_SENS)
    gmsh.model.mesh.field.setNumber(1, "YMax", REFINE_YMAX_SENS)
    gmsh.model.mesh.field.setAsBackgroundMesh(1)

    gmsh.option.setNumber("Mesh.Algorithm", 6)
    gmsh.option.setNumber("Mesh.RecombineAll", 0)
    gmsh.option.setNumber("Mesh.Smoothing", 2)

    gmsh.model.mesh.generate(2)
    mesh_file = joinpath(OUTPUT_DIR, mesh_msh_name(CASE_SENS))
    gmsh.write(mesh_file)
    n_nodes = length(gmsh.model.mesh.getNodes()[1])
    n_quads = length(gmsh.model.mesh.getElementsByType(3)[1])
    n_trias = length(gmsh.model.mesh.getElementsByType(2)[1])
    gmsh.finalize()

    emit_info(@sprintf("%s mesh generated: nodes=%d trias=%d quads=%d", CASE_SENS, n_nodes, n_trias, n_quads))
    return mesh_file
end

function plot_mesh(mesh_file::String, out_file::String)
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.open(mesh_file)

    node_tags, node_coords, _ = gmsh.model.mesh.getNodes()
    node_map = Dict{Int,Tuple{Float64,Float64}}()
    for i in eachindex(node_tags)
        j = 3 * (i - 1)
        node_map[Int(node_tags[i])] = (node_coords[j + 1], node_coords[j + 2])
    end

    quad_nodes = gmsh.model.mesh.getElementsByType(3)[2]
    tri_nodes = gmsh.model.mesh.getElementsByType(2)[2]
    p = plot(aspect_ratio=:equal, size=(700, 700), dpi=200,
             xlabel="x (mm)", ylabel="y (mm)", legend=false, grid=false,
             title="", framestyle=:box)

    for i in 1:(length(quad_nodes) ÷ 4)
        ids = quad_nodes[4*(i-1)+1:4*i]
        pts = [node_map[Int(id)] for id in ids]
        plot!(p, Shape(first.(pts), last.(pts)), fillcolor=:white, linecolor=:gray55, linewidth=0.35)
    end

    for i in 1:(length(tri_nodes) ÷ 3)
        ids = tri_nodes[3*(i-1)+1:3*i]
        pts = [node_map[Int(id)] for id in ids]
        plot!(p, Shape(first.(pts), last.(pts)), fillcolor=:white, linecolor=:gray55, linewidth=0.25)
    end

    savefig(p, out_file)
    gmsh.finalize()
    emit_info("Mesh preview saved: " * abspath(out_file))
end

function plot_scalar_field(params::CaseParams, field; out_file::String, dpi::Int=PNG_DPI, cmap=:jet, vmin=0.0, vmax=1.0, nx::Int=PNG_NX, ny::Int=PNG_NY)
    xs = collect(range(0.0, params.W, length=nx))
    ys = collect(range(0.0, params.H, length=ny))
    z = fill(NaN, ny, nx)
    notch_y = y_notch(params)
    for (j, y) in enumerate(ys)
        for (i, x) in enumerate(xs)
            val = try
                field(Gridap.Geometry.Point(x, y))
            catch
                NaN
            end
            z[j, i] = isfinite(val) ? clamp(val, vmin, vmax) : NaN
        end
    end
    p = heatmap(xs, ys, z;
                aspect_ratio=:equal, size=(820, 700), dpi=dpi,
                xlabel="x (mm)", ylabel="y (mm)", title="",
                color=cgrad(cmap), clims=(vmin, vmax), colorbar=true,
                legend=false, grid=false, framestyle=:box,
                xlims=(0.0, params.W), ylims=(0.0, params.H))
    plot!(p, [0.0, params.a0], [notch_y, notch_y], color=:white, linewidth=1.2, label=false)
    savefig(p, out_file)
end

function plot_displacement_magnitude(params::CaseParams, uh, out_file::String)
    u_mag(x) = norm(uh(x))
    xs = collect(range(0.0, params.W, length=PNG_NX))
    ys = collect(range(0.0, params.H, length=PNG_NY))
    vmax = 0.0
    for y in ys, x in xs
        val = try
            u_mag(Gridap.Geometry.Point(x, y))
        catch
            NaN
        end
        if isfinite(val)
            vmax = max(vmax, val)
        end
    end
    vmax = max(vmax, 1.0e-12)
    plot_scalar_field(params, u_mag;
                      out_file=out_file,
                      cmap=:viridis,
                      vmin=0.0,
                      vmax=vmax)
end

function write_curve_plot(u_history, F_kN_history, selected_case::String; color=:royalblue)
    p_fu = plot(u_history .* 1e3, F_kN_history,
                xlabel="Displacement u (x10^-3 mm)", ylabel="Reaction F (kN)",
                title="",
                linewidth=2, color=color, legend=false,
                size=(800, 500), dpi=150, grid=true, framestyle=:box)
    out_file = joinpath(OUTPUT_DIR, curve_png_name(selected_case))
    savefig(p_fu, out_file)
    return out_file
end

function write_paraview_vtk(trian, filebase; cellfields)
    writevtk(trian, filebase; nsubcells=1, cellfields=cellfields)
end

function run_mesh_stage(params::CaseParams)
    selected_case = case_name(params)
    validate_params(params)
    prepare_mesh_output_dir(selected_case)

    emit_info("Starting $(selected_case) mesh stage")
    mesh_file = create_mesh(params)
    if maybe_stopped()
        emit_info("Stopped by user")
        emit_line("DONE")
        return
    end

    if ENABLE_PNG
        mesh_png = joinpath(OUTPUT_DIR, mesh_png_name(selected_case))
        plot_mesh(mesh_file, mesh_png)
        emit_line("SNAPSHOT " * abspath(mesh_png))
    end

    emit_line("DONE")
end

function run_compute_stage(params::SentParams, mesh_file::String)
    validate_params(params)
    prepare_compute_output_dir(CASE_SENT)
    csv_path = init_live_csv(CASE_SENT)

    λ_val = lambda_mat(params)
    G_val = shear_mat(params)
    C_elastic = elastic_stiffness(λ_val, G_val)
    ε_op = symmetric_gradient

    isfile(mesh_file) || error("mesh_file does not exist: " * mesh_file)

    emit_info("Starting $(CASE_SENT) compute stage")
    emit_info(@sprintf("E=%.3f nu=%.5f Gc=%.5f l0=%.5f", params.E, params.nu, params.Gc, params.l0))

    model = GmshDiscreteModel(mesh_file)
    Ω = Triangulation(model)
    dΩ = Measure(Ω, 2)
    n_cells = num_cells(Ω)
    emit_info("Grid cells: $(n_cells)")

    order = 1
    reffe_u = ReferenceFE(lagrangian, VectorValue{2,Float64}, order)
    reffe_d = ReferenceFE(lagrangian, Float64, order)
    reffe_dg = ReferenceFE(lagrangian, Float64, 0)

    V_u = TestFESpace(model, reffe_u, conformity=:H1,
                      dirichlet_tags=["bottom", "top"],
                      dirichlet_masks=[(true, true), (true, true)])
    V_d = TestFESpace(model, reffe_d, conformity=:H1)
    U_d = TrialFESpace(V_d)
    V_dg = FESpace(model, reffe_dg, conformity=:L2)

    dh = interpolate_everywhere(x -> 0.0, U_d)
    H_vals = zeros(n_cells)
    H_fe = FEFunction(V_dg, H_vals)
    quad_cache = CellQuadrature(Ω, 2)
    cell_pts = get_cell_points(quad_cache)

    Γ_top = BoundaryTriangulation(model; tags=["top"])
    dΓ_top = Measure(Γ_top, 2)
    n_top = get_normal_vector(Γ_top)
    e_axis = VectorValue(0.0, 1.0)

    u_history = Float64[]
    F_kN_history = Float64[]

    total_est_steps = params.N_steps_coarse + ceil(Int, max(params.u_end - params.N_steps_coarse * params.du_coarse, 0.0) / params.du_fine)
    total_est_steps = max(total_est_steps, 1)

    step = 0
    u_current = 0.0
    next_vtk_level = 1
    crack_started = false
    F_onset = 0.0
    uh = nothing
    run_t0 = time()

    emit_info("Solver loop entered")

    while u_current < params.u_end
        if maybe_stopped()
            emit_info("Stopped by user")
            emit_line("DONE")
            return
        end

        step += 1
        Δu = step <= params.N_steps_coarse ? params.du_coarse : params.du_fine
        u_current = min(u_current + Δu, params.u_end)

        u_bc_bottom(x) = VectorValue(0.0, 0.0)
        u_bc_top(x) = VectorValue(0.0, u_current)
        U_u = TrialFESpace(V_u, [u_bc_bottom, u_bc_top])

        min_stagger = 2
        max_stagger = 20
        stagger_tol = 1e-4
        d_old = dh
        uh = nothing
        H_prev_vals = copy(H_vals)
        H_step_vals = copy(H_vals)
        H_step_fe = H_fe
        u_err = Inf
        d_err = Inf
        u_prev_vals = nothing

        for stagger_iter in 1:max_stagger
            if maybe_stopped()
                emit_info("Stopped by user during stagger iteration")
                emit_line("DONE")
                return
            end

            g_d = x -> g_deg(dh(x), params.eta_k)
            a_u(u, v) = ∫( g_d * (C_elastic ⊙ ε_op(u) ⊙ ε_op(v)) )dΩ
            l_u(v) = ∫( VectorValue(0.0, 0.0) ⋅ v )dΩ
            op_u = AffineFEOperator(a_u, l_u, U_u, V_u)
            uh = solve(op_u)

            u_curr_vals = copy(get_free_dof_values(uh))
            if stagger_iter > 1
                u_err = norm(u_curr_vals .- u_prev_vals) / (norm(u_curr_vals) + 1e-15)
            end
            u_prev_vals = u_curr_vals

            ε_qp = evaluate(ε_op(uh), cell_pts)
            psi_qp = zeros(n_cells)
            for ic in 1:n_cells
                psi_max = 0.0
                for iq in 1:length(ε_qp[ic])
                    psi_max = max(psi_max, miehe_psi_plus(ε_qp[ic][iq], λ_val, G_val))
                end
                psi_qp[ic] = psi_max
            end
            H_step_vals .= max.(H_prev_vals, psi_qp)
            H_step_fe = FEFunction(V_dg, H_step_vals)

            a_d(d, q) = ∫( (params.Gc / params.l0 + 2.0 * H_step_fe) * d * q
                         + params.Gc * params.l0 * (∇(d) ⋅ ∇(q)) )dΩ
            l_d(q) = ∫( (2.0 * H_step_fe) * q )dΩ
            op_d = AffineFEOperator(a_d, l_d, U_d, V_d)
            dh_new = solve(op_d)

            d_vals_new = get_free_dof_values(dh_new)
            d_vals_prev = get_free_dof_values(d_old)
            d_vals_new .= max.(d_vals_new, d_vals_prev)
            d_vals_new .= clamp.(d_vals_new, 0.0, 1.0)
            dh_new = FEFunction(U_d, d_vals_new)

            Δd_norm = norm(get_free_dof_values(dh_new) .- get_free_dof_values(dh))
            d_norm = norm(get_free_dof_values(dh_new)) + 1e-15
            d_err = Δd_norm / d_norm
            dh = dh_new

            if stagger_iter >= min_stagger && max(u_err, d_err) < stagger_tol
                break
            end
        end

        H_vals .= H_step_vals
        H_fe = H_step_fe

        g_d = x -> g_deg(dh(x), params.eta_k)
        σ_deg = g_d * (C_elastic ⊙ ε_op(uh))
        traction_top = σ_deg ⋅ n_top
        F_axis = sum(∫( traction_top ⋅ e_axis )dΓ_top)
        F_kN = F_axis * 1e-3
        d_max = maximum(get_free_dof_values(dh))
        time_s = time() - run_t0

        push!(u_history, u_current)
        push!(F_kN_history, F_kN)
        append_csv_row(csv_path, step, time_s, u_current, F_axis, F_kN)

        emit_line(@sprintf("STEP %d U %.12e F %.12e DMAX %.12e", step, u_current, F_axis, d_max))
        emit_line(@sprintf("PROGRESS %.2f", min(100.0, 100 * step / total_est_steps)))

        if SAVE_VTK && !crack_started && d_max >= VTK_ONSET_LEVEL
            crack_started = true
            F_onset = max(F_axis, F_STOP_TOL)
            fname = joinpath(OUTPUT_DIR, vtk_filename(CASE_SENT, @sprintf("onset_step%04d", step)))
            write_paraview_vtk(Ω, fname, cellfields=["d" => dh, "uh" => uh, "H" => H_fe])
            emit_line("VTK " * abspath(fname * ".vtu"))
        end

        while SAVE_VTK && crack_started && next_vtk_level <= length(VTK_FORCE_DROP_LEVELS) &&
              F_axis <= VTK_FORCE_DROP_LEVELS[next_vtk_level] * F_onset
            target_ratio = VTK_FORCE_DROP_LEVELS[next_vtk_level]
            fname = joinpath(OUTPUT_DIR, vtk_filename(CASE_SENT, @sprintf("drop%02d_step%04d", round(Int, 100 * target_ratio), step)))
            write_paraview_vtk(Ω, fname, cellfields=["d" => dh, "uh" => uh, "H" => H_fe])
            emit_line("VTK " * abspath(fname * ".vtu"))
            next_vtk_level += 1
        end

        if ENABLE_PNG && (step == 1 || step % params.snapshot_every == 0 || d_max > 0.95 || u_current >= params.u_end)
            png_path = joinpath(OUTPUT_DIR, snapshot_name(CASE_SENT, step))
            plot_scalar_field(params, dh;
                              out_file=png_path,
                              vmin=0.0,
                              vmax=1.0)
            emit_line("SNAPSHOT " * abspath(png_path))
            write_curve_plot(u_history, F_kN_history, CASE_SENT; color=:royalblue)
        end

        if step > 1 && F_axis <= F_STOP_TOL
            emit_info(@sprintf("Reaction force reached stop tolerance at step %d", step))
            break
        end
    end

    if SAVE_VTK && uh !== nothing
        final_vtu = joinpath(OUTPUT_DIR, vtk_filename(CASE_SENT, "final"))
        write_paraview_vtk(Ω, final_vtu, cellfields=["d" => dh, "uh" => uh, "H" => H_fe])
        emit_line("VTK " * abspath(final_vtu * ".vtu"))
    end

    final_png = joinpath(OUTPUT_DIR, damage_final_name(CASE_SENT))
    plot_scalar_field(params, dh;
                      out_file=final_png,
                      vmin=0.0,
                      vmax=1.0)
    emit_line("SNAPSHOT " * abspath(final_png))

    displacement_png = joinpath(OUTPUT_DIR, displacement_final_name(CASE_SENT))
    plot_displacement_magnitude(params, uh, displacement_png)
    emit_line("DISPLACEMENT " * abspath(displacement_png))

    write_curve_plot(u_history, F_kN_history, CASE_SENT; color=:royalblue)
    emit_info("F-u CSV saved to " * abspath(csv_path))
    emit_line("DONE")
end

function run_compute_stage(params::SensParams, mesh_file::String)
    validate_params(params)
    prepare_compute_output_dir(CASE_SENS)
    csv_path = init_live_csv(CASE_SENS)

    λ_val = lambda_mat(params)
    G_val = shear_mat(params)
    C_elastic = elastic_stiffness(λ_val, G_val)
    ε_op = symmetric_gradient

    isfile(mesh_file) || error("mesh_file does not exist: " * mesh_file)

    emit_info("Starting $(CASE_SENS) compute stage")
    emit_info(@sprintf("E=%.3f nu=%.5f Gc=%.5f l0=%.5f", params.E, params.nu, params.Gc, params.l0))

    model = GmshDiscreteModel(mesh_file)
    Ω = Triangulation(model)
    dΩ = Measure(Ω, 2)
    n_cells = num_cells(Ω)
    emit_info("Grid cells: $(n_cells)")

    order = 1
    reffe_u = ReferenceFE(lagrangian, VectorValue{2,Float64}, order)
    reffe_d = ReferenceFE(lagrangian, Float64, order)
    reffe_dg = ReferenceFE(lagrangian, Float64, 0)

    V_u = TestFESpace(model, reffe_u, conformity=:H1,
                      dirichlet_tags=["bottom", "top", "left"],
                      dirichlet_masks=[(true, true), (true, true), (false, true)])
    V_d = TestFESpace(model, reffe_d, conformity=:H1)
    U_d = TrialFESpace(V_d)
    V_dg = FESpace(model, reffe_dg, conformity=:L2)

    dh = interpolate_everywhere(x -> 0.0, U_d)
    H_vals = zeros(n_cells)
    H_fe = FEFunction(V_dg, H_vals)
    quad_cache = CellQuadrature(Ω, 2)
    cell_pts = get_cell_points(quad_cache)

    Γ_top = BoundaryTriangulation(model; tags=["top"])
    dΓ_top = Measure(Γ_top, 2)
    n_top = get_normal_vector(Γ_top)
    e_axis = VectorValue(1.0, 0.0)

    u_history = Float64[]
    F_kN_history = Float64[]

    total_est_steps = ceil(Int, params.u_end / params.du_shear)
    total_est_steps = max(total_est_steps, 1)

    step = 0
    u_current = 0.0
    next_vtk_level = 1
    crack_started = false
    F_onset = 0.0
    uh = nothing
    run_t0 = time()

    emit_info("Solver loop entered")

    while u_current < params.u_end
        if maybe_stopped()
            emit_info("Stopped by user")
            emit_line("DONE")
            return
        end

        step += 1
        u_current = min(u_current + params.du_shear, params.u_end)

        u_bc_bottom(x) = VectorValue(0.0, 0.0)
        u_bc_top(x) = VectorValue(u_current, 0.0)
        u_bc_left(x) = VectorValue(0.0, 0.0)
        U_u = TrialFESpace(V_u, [u_bc_bottom, u_bc_top, u_bc_left])

        min_stagger = 2
        max_stagger = 20
        stagger_tol = 1e-4
        d_old = dh
        uh = nothing
        H_prev_vals = copy(H_vals)
        H_step_vals = copy(H_vals)
        H_step_fe = H_fe
        u_err = Inf
        d_err = Inf
        u_prev_vals = nothing

        for stagger_iter in 1:max_stagger
            if maybe_stopped()
                emit_info("Stopped by user during stagger iteration")
                emit_line("DONE")
                return
            end

            g_d = x -> g_deg(dh(x), params.eta_k)
            a_u(u, v) = ∫( g_d * (C_elastic ⊙ ε_op(u) ⊙ ε_op(v)) )dΩ
            l_u(v) = ∫( VectorValue(0.0, 0.0) ⋅ v )dΩ
            op_u = AffineFEOperator(a_u, l_u, U_u, V_u)
            uh = solve(op_u)

            u_curr_vals = copy(get_free_dof_values(uh))
            if stagger_iter > 1
                u_err = norm(u_curr_vals .- u_prev_vals) / (norm(u_curr_vals) + 1e-15)
            end
            u_prev_vals = u_curr_vals

            ε_qp = evaluate(ε_op(uh), cell_pts)
            psi_qp = zeros(n_cells)
            for ic in 1:n_cells
                psi_max = 0.0
                for iq in 1:length(ε_qp[ic])
                    psi_max = max(psi_max, miehe_psi_plus(ε_qp[ic][iq], λ_val, G_val))
                end
                psi_qp[ic] = psi_max
            end
            H_step_vals .= max.(H_prev_vals, psi_qp)
            H_step_fe = FEFunction(V_dg, H_step_vals)

            a_d(d, q) = ∫( (params.Gc / params.l0 + 2.0 * H_step_fe) * d * q
                         + params.Gc * params.l0 * (∇(d) ⋅ ∇(q)) )dΩ
            l_d(q) = ∫( (2.0 * H_step_fe) * q )dΩ
            op_d = AffineFEOperator(a_d, l_d, U_d, V_d)
            dh_new = solve(op_d)

            d_vals_new = get_free_dof_values(dh_new)
            d_vals_prev = get_free_dof_values(d_old)
            d_vals_new .= max.(d_vals_new, d_vals_prev)
            d_vals_new .= clamp.(d_vals_new, 0.0, 1.0)
            dh_new = FEFunction(U_d, d_vals_new)

            Δd_norm = norm(get_free_dof_values(dh_new) .- get_free_dof_values(dh))
            d_norm = norm(get_free_dof_values(dh_new)) + 1e-15
            d_err = Δd_norm / d_norm
            dh = dh_new

            if stagger_iter >= min_stagger && max(u_err, d_err) < stagger_tol
                break
            end
        end

        H_vals .= H_step_vals
        H_fe = H_step_fe

        g_d = x -> g_deg(dh(x), params.eta_k)
        σ_deg = g_d * (C_elastic ⊙ ε_op(uh))
        traction_top = σ_deg ⋅ n_top
        F_axis = sum(∫( traction_top ⋅ e_axis )dΓ_top)
        F_kN = F_axis * 1e-3
        d_max = maximum(get_free_dof_values(dh))
        time_s = time() - run_t0

        push!(u_history, u_current)
        push!(F_kN_history, F_kN)
        append_csv_row(csv_path, step, time_s, u_current, F_axis, F_kN)

        emit_line(@sprintf("STEP %d U %.12e F %.12e DMAX %.12e", step, u_current, F_axis, d_max))
        emit_line(@sprintf("PROGRESS %.2f", min(100.0, 100 * step / total_est_steps)))

        if SAVE_VTK && !crack_started && d_max >= VTK_ONSET_LEVEL
            crack_started = true
            F_onset = max(F_axis, F_STOP_TOL)
            fname = joinpath(OUTPUT_DIR, vtk_filename(CASE_SENS, @sprintf("onset_step%04d", step)))
            write_paraview_vtk(Ω, fname, cellfields=["d" => dh, "uh" => uh, "H" => H_fe])
            emit_line("VTK " * abspath(fname * ".vtu"))
        end

        while SAVE_VTK && crack_started && next_vtk_level <= length(VTK_FORCE_DROP_LEVELS) &&
              F_axis <= VTK_FORCE_DROP_LEVELS[next_vtk_level] * F_onset
            target_ratio = VTK_FORCE_DROP_LEVELS[next_vtk_level]
            fname = joinpath(OUTPUT_DIR, vtk_filename(CASE_SENS, @sprintf("drop%02d_step%04d", round(Int, 100 * target_ratio), step)))
            write_paraview_vtk(Ω, fname, cellfields=["d" => dh, "uh" => uh, "H" => H_fe])
            emit_line("VTK " * abspath(fname * ".vtu"))
            next_vtk_level += 1
        end

        if ENABLE_PNG && (step == 1 || step % params.snapshot_every == 0 || d_max > 0.95 || u_current >= params.u_end)
            png_path = joinpath(OUTPUT_DIR, snapshot_name(CASE_SENS, step))
            plot_scalar_field(params, dh;
                              out_file=png_path,
                              vmin=0.0,
                              vmax=1.0)
            emit_line("SNAPSHOT " * abspath(png_path))
            write_curve_plot(u_history, F_kN_history, CASE_SENS; color=:firebrick)
        end

        if step > 1 && F_axis <= F_STOP_TOL
            emit_info(@sprintf("Reaction force reached stop tolerance at step %d", step))
            break
        end
    end

    if SAVE_VTK && uh !== nothing
        final_vtu = joinpath(OUTPUT_DIR, vtk_filename(CASE_SENS, "final"))
        write_paraview_vtk(Ω, final_vtu, cellfields=["d" => dh, "uh" => uh, "H" => H_fe])
        emit_line("VTK " * abspath(final_vtu * ".vtu"))
    end

    final_png = joinpath(OUTPUT_DIR, damage_final_name(CASE_SENS))
    plot_scalar_field(params, dh;
                      out_file=final_png,
                      vmin=0.0,
                      vmax=1.0)
    emit_line("SNAPSHOT " * abspath(final_png))

    displacement_png = joinpath(OUTPUT_DIR, displacement_final_name(CASE_SENS))
    plot_displacement_magnitude(params, uh, displacement_png)
    emit_line("DISPLACEMENT " * abspath(displacement_png))

    write_curve_plot(u_history, F_kN_history, CASE_SENS; color=:firebrick)
    emit_info("F-u CSV saved to " * abspath(csv_path))
    emit_line("DONE")
end

function main()
    length(ARGS) == 1 || error("Usage: julia gui/gui_solver.jl gui/params_default.json")
    params_path = abspath(ARGS[1])
    config = parse_params(params_path)
    if config.run_mode == "mesh"
        run_mesh_stage(config.params)
    elseif config.run_mode == "compute"
        run_compute_stage(config.params, config.mesh_file)
    else
        error("Unsupported run_mode: " * config.run_mode)
    end
end

try
    main()
catch err
    emit_error(sprint(showerror, err))
    for line in split(sprint(Base.show_backtrace, catch_backtrace()), '\n')
        isempty(line) || emit_info(line)
    end
    exit(1)
end
