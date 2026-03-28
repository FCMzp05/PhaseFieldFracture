# ============================================================================
# 单边缺口拉伸试样（SENT）弹性相场断裂
#
# 文献: Miehe, Hofacker, Welschinger, CMAME 199 (2010) 2765–2778
#       "A phase field model for rate-independent crack propagation:
#        Robust algorithmic implementation based on operator splits"
#
# 对标: Section 5.1 — Single edge notched tension test (Fig. 7 & Fig. 8)
#
# 物理模型:
#   AT2 相场模型（Miehe 2010 原始形式）
#   Amor 体积-偏量分解（拉压不对称）
#   历史变量场方法（驱动力 H = max(H_old, ψ⁺)）
#   交错算法（先位移后相场）
#
# 几何与材料 (Section 5.1):
#   正方形板 1×1 mm²，水平预裂纹从左边界中点延伸至中心
#   λ = 121,150 MPa, G = 80,770 MPa (对应 E≈210,950 MPa, ν≈0.3)
#   Gc = 2.7×10⁻³ kN/mm = 2.7 N/mm
#   l₀ = 0.015 mm (l₁ in paper)
#
# 边界条件 (Fig. 6a):
#   底边: ux=0, uy=0 (完全固定)
#   顶边: ux=0, uy=u (位移控制，仅竖向)
#
# 加载方案:
#   前 500 步: Δu = 1e-5 mm
#   此后: Δu = 1e-6 mm（捕捉断裂过程）
#
# 预期结果 (Fig. 7a):
#   峰值载荷 F_peak ≈ 0.60 kN 附近，位移 u ≈ 5.4e-3 mm
#   断裂位移 u ≈ 6.0e-3 mm
# ============================================================================

using Gmsh: gmsh
using Gridap
using Gridap.Geometry
using Gridap.Geometry: get_node_coordinates, get_cell_coordinates
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
using DelimitedFiles

# ============================================================================
# 几何参数
# ============================================================================
const W = 1.0        # 试样宽度 (mm)
const H = 1.0        # 试样高度 (mm)
const a0 = 0.5       # 预裂纹长度：从左边界到中心 (mm)
const y_notch = 0.5  # 预裂纹高度位置 (mm)
const CH_PRECRACK_FACTOR = 0.5   # 裂纹总宽度取 h_fine，因此半宽为 0.5*h_fine

# ============================================================================
# 材料参数 (Miehe 2010 Section 5.1)
# 原文给 Lamé 常数: λ=121.15 kN/mm², μ=80.77 kN/mm²
# 换算: E = μ(3λ+2μ)/(λ+μ) ≈ 210,950 MPa, ν = λ/[2(λ+μ)] ≈ 0.3
# ============================================================================
const λ_mat = 121_150.0   # MPa = 121.15 kN/mm²
const G_mat =  80_770.0   # MPa = 80.77 kN/mm²
const E_mat = G_mat * (3λ_mat + 2G_mat) / (λ_mat + G_mat)
const ν_mat = λ_mat / (2 * (λ_mat + G_mat))

# ============================================================================
# 相场参数
# ============================================================================
const Gc   = 2.7          # 临界能量释放率 (N/mm)
const l0   = 0.015        # 长度尺度参数 (mm)，按原文恢复
const η_k  = 0.0          # 残余刚度按原文设为 0

# ============================================================================
# 网格参数
# ============================================================================
const h_fine   = 0.005    # 裂纹路径细网格 (mm)
const h_coarse = 0.05     # 远场粗网格 (mm)
const REFINE_XMIN_SENT = 0.45   # SENT 固定矩形细化区左边界
const REFINE_XMAX_SENT = 1.00   # SENT 固定矩形细化区右边界
const REFINE_YMIN_SENT = 0.40   # SENT 固定矩形细化区下边界（关于 y=0.5 对称）
const REFINE_YMAX_SENT = 0.60   # SENT 固定矩形细化区上边界

# ============================================================================
# 加载参数
# ============================================================================
const N_STEPS_COARSE = 500       # 粗步阶段步数（总步数约1000）
const Δu_coarse      = 8.0e-6    # 粗加载步长
const Δu_fine        = 8.0e-6    # 细加载步长
const u_end          = 8.0e-3    # 最大位移（当前设置下总步数约1000）
const F_STOP_TOL     = 1.0e-3    # 反力停止阈值 [N]，视为“已降到0”

# ============================================================================
# 输出控制
# ============================================================================
const OUTPUT_DIR    = "results_SENT_tension"
const SAVE_VTK      = true
const ENABLE_PNG    = true
const PNG_DPI       = 150
const PNG_NX        = 260
const PNG_NY        = 260
const VTK_ONSET_LEVEL = 0.999   # 第一张：d 刚达到 1
const VTK_FORCE_DROP_LEVELS = (0.75, 0.50, 0.25)  # 之后按反力相对起裂时刻继续下降来保存

# ============================================================================
# Miehe 2010 谱分解（原文风格）
# ψ⁺ = λ/2·<tr(ε)>₊² + G·Σ_a<ε_a>₊²
# 对于当前平面应变实现，取面内两个主应变与 ε₃=0
# ============================================================================
@inline function miehe_psi_plus(ε_2d::SymTensorValue{2,Float64,3})
    ε11 = ε_2d[1,1]
    ε22 = ε_2d[2,2]
    ε12 = ε_2d[1,2]
    avg = 0.5 * (ε11 + ε22)
    dif = 0.5 * (ε11 - ε22)
    rad = sqrt(dif^2 + ε12^2)
    ε1  = avg + rad
    ε2  = avg - rad
    ε3  = 0.0
    trp = max(ε1 + ε2 + ε3, 0.0)
    return 0.5 * λ_mat * trp^2 +
           G_mat * (max(ε1, 0.0)^2 + max(ε2, 0.0)^2 + max(ε3, 0.0)^2)
end

# 降解函数 g(d) = (1-d)² + η_k
@inline g_deg(d::Float64) = (1.0 - clamp(d, 0.0, 1.0))^2 + η_k

# ============================================================================
# 弹性刚度张量 (平面应变，各向同性)
# ============================================================================
function elastic_stiffness()
    C1111 = λ_mat + 2G_mat
    C1122 = λ_mat
    C1212 = G_mat
    return SymFourthOrderTensorValue(
        C1111, 0.0,   C1122,
        0.0,   C1212, 0.0,
        C1122, 0.0,   C1111
    )
end
const C_elastic = elastic_stiffness()
const ε_op = symmetric_gradient

# ============================================================================
# 更新历史变量函数（供 update_state! 使用）
# H_{n+1} = max(H_n, ψ⁺_current)
# ============================================================================
# 历史变量更新
# Gridap update_state! 要求返回 (need_to_update::Bool, new_state...)
function update_H(state, psi_plus)
    new_H = max(state, psi_plus)
    return new_H > state, new_H
end

# ============================================================================
# 网格生成（原始裂纹槽几何 + 固定矩形细化区 + 三角形网格）
# ============================================================================
function create_mesh()
    mkpath(OUTPUT_DIR)
    println("\n生成 SENT 网格（预裂纹 a₀ = $(a0) mm，三角形局部加密）...")

    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.model.add("SENT_tension")

    CH = CH_PRECRACK_FACTOR * h_fine
    # ── 原始裂纹槽几何 ──
    gmsh.model.geo.addPoint(0.0,         0.0,           0.0, h_coarse, 1)
    gmsh.model.geo.addPoint(W,           0.0,           0.0, h_coarse, 2)
    gmsh.model.geo.addPoint(W,           y_notch,       0.0, h_coarse, 10)
    gmsh.model.geo.addPoint(W,           H,             0.0, h_coarse, 3)
    gmsh.model.geo.addPoint(0.0,         H,             0.0, h_coarse, 4)
    gmsh.model.geo.addPoint(0.0,         y_notch+CH,    0.0, h_coarse, 5)
    gmsh.model.geo.addPoint(a0,          y_notch+CH,    0.0, h_fine,   6)
    gmsh.model.geo.addPoint(a0,          y_notch,       0.0, h_fine,   7)
    gmsh.model.geo.addPoint(a0,          y_notch-CH,    0.0, h_fine,   8)
    gmsh.model.geo.addPoint(0.0,         y_notch-CH,    0.0, h_coarse, 9)

    gmsh.model.geo.addLine(1, 2,  1)
    gmsh.model.geo.addLine(2, 10, 2)
    gmsh.model.geo.addLine(10, 3, 10)
    gmsh.model.geo.addLine(3, 4,  3)
    gmsh.model.geo.addLine(4, 5,  4)
    gmsh.model.geo.addLine(5, 6,  5)
    gmsh.model.geo.addLine(6, 7,  6)
    gmsh.model.geo.addLine(7, 8,  7)
    gmsh.model.geo.addLine(8, 9,  8)
    gmsh.model.geo.addLine(9, 1,  9)

    gmsh.model.geo.addCurveLoop([1, 2, 10, 3, 4, 5, 6, 7, 8, 9], 1)
    gmsh.model.geo.addPlaneSurface([1], 1)
    gmsh.model.geo.synchronize()

    gmsh.model.addPhysicalGroup(2, [1],  1);  gmsh.model.setPhysicalName(2, 1, "Domain")
    gmsh.model.addPhysicalGroup(1, [1],  1);  gmsh.model.setPhysicalName(1, 1, "bottom")
    gmsh.model.addPhysicalGroup(1, [3],  2);  gmsh.model.setPhysicalName(1, 2, "top")

    # ── 固定矩形细化区，不随 l0 改变 ──
    gmsh.model.mesh.field.add("Box", 1)
    gmsh.model.mesh.field.setNumber(1, "VIn",  h_fine)
    gmsh.model.mesh.field.setNumber(1, "VOut", h_coarse)
    gmsh.model.mesh.field.setNumber(1, "XMin", REFINE_XMIN_SENT)
    gmsh.model.mesh.field.setNumber(1, "XMax", REFINE_XMAX_SENT)
    gmsh.model.mesh.field.setNumber(1, "YMin", REFINE_YMIN_SENT)
    gmsh.model.mesh.field.setNumber(1, "YMax", REFINE_YMAX_SENT)
    gmsh.model.mesh.field.setAsBackgroundMesh(1)

    gmsh.option.setNumber("Mesh.Algorithm", 6)
    gmsh.option.setNumber("Mesh.RecombineAll", 0)
    gmsh.option.setNumber("Mesh.Smoothing", 2)

    gmsh.model.mesh.generate(2)
    mesh_file = joinpath(OUTPUT_DIR, "mesh_SENT.msh")
    gmsh.write(mesh_file)

    n_nodes = length(gmsh.model.mesh.getNodes()[1])
    n_quads = length(gmsh.model.mesh.getElementsByType(3)[1])
    n_trias = length(gmsh.model.mesh.getElementsByType(2)[1])
    println("  网格节点数:   $(n_nodes)")
    println("  三角形单元数: $(n_trias)")
    println("  四边形单元数: $(n_quads)")
    println("  固定细化框: x ∈ [$(REFINE_XMIN_SENT), $(REFINE_XMAX_SENT)], y ∈ [$(REFINE_YMIN_SENT), $(REFINE_YMAX_SENT)]")

    gmsh.finalize()
    return mesh_file
end

# ============================================================================
# 绘制网格
# ============================================================================
function plot_mesh(mesh_file::String)
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
    tri_nodes  = gmsh.model.mesh.getElementsByType(2)[2]
    n_quads = length(quad_nodes) ÷ 4
    n_trias = length(tri_nodes) ÷ 3
    n_cells = n_quads + n_trias

    p = plot(aspect_ratio=:equal, size=(700, 700), dpi=200,
             xlabel="x (mm)", ylabel="y (mm)", legend=false, grid=false,
             title="SENT Mesh  ($(n_cells) elements)")

    for i in 1:n_quads
        ids = quad_nodes[4*(i-1)+1:4*i]
        pts = [node_map[Int(id)] for id in ids]
        xs = [pt[1] for pt in pts]
        ys = [pt[2] for pt in pts]
        plot!(p, Shape(xs, ys), fillcolor=:white, linecolor=:gray55, linewidth=0.35)
    end

    for i in 1:n_trias
        ids = tri_nodes[3*(i-1)+1:3*i]
        pts = [node_map[Int(id)] for id in ids]
        xs = [pt[1] for pt in pts]
        ys = [pt[2] for pt in pts]
        plot!(p, Shape(xs, ys), fillcolor=:white, linecolor=:gray55, linewidth=0.25)
    end

    savefig(p, joinpath(OUTPUT_DIR, "mesh_SENT.png"))
    gmsh.finalize()
    println("  ✓ 网格图: mesh_SENT.png")
end

# ============================================================================
# 标量场云图（PNG，规则网格采样后的平滑热图）
# ============================================================================
function plot_scalar_field(field;
                           title_str::String, out_file::String,
                           dpi::Int=PNG_DPI, cmap=:jet,
                           vmin=0.0, vmax=1.0,
                           nx::Int=PNG_NX, ny::Int=PNG_NY)
    xs = collect(range(0.0, W, length=nx))
    ys = collect(range(0.0, H, length=ny))
    z = fill(NaN, ny, nx)
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
                xlabel="x (mm)", ylabel="y (mm)", title=title_str,
                color=cgrad(cmap), clims=(vmin, vmax), colorbar=true,
                legend=false, grid=false, framestyle=:box,
                xlims=(0.0, W), ylims=(0.0, H))
    plot!(p, [0.0, a0], [y_notch, y_notch], color=:white, linewidth=1.2, label=false)
    savefig(p, out_file)
end

# ============================================================================
# 求解位移场子问题（线性弹性，降解刚度）
# 弱形式: ∫ g(d)·C:ε(u):ε(v) dΩ = ∫ t·v dΓ  （无体力，无面力）
# ============================================================================
function solve_displacement(sh, U_u, V_u, dΩ)
    a_u(u, v) = ∫( (x -> g_deg(sh(x))) ⊙ (C_elastic ⊙ ε_op(u) ⊙ ε_op(v)) )dΩ
    l_u(v)    = 0.0   # 无外部面力（位移通过 Dirichlet BC 施加）

    # 构建线性算子
    op = AffineFEOperator(a_u, l_u, U_u, V_u)
    uh = solve(op)
    return uh
end

# ============================================================================
# 求解相场子问题（AT2 线性问题）
# 弱形式: ∫[(Gc/l₀ + 2H)·d·q + Gc·l₀·∇d·∇q] dΩ = ∫[2H·q] dΩ
# ============================================================================
function solve_phasefield(H_field, U_d, V_d, dΩ)
    coeff_diag(x)  = Gc / l0 + 2.0 * H_field(x)
    coeff_rhs(x)   = 2.0 * H_field(x)

    a_d(d, q) = ∫( coeff_diag ⊙ d ⊙ q + Gc * l0 * (∇(d) ⋅ ∇(q)) )dΩ
    l_d(q)    = ∫( coeff_rhs ⊙ q )dΩ

    op = AffineFEOperator(a_d, l_d, U_d, V_d)
    dh = solve(op)
    return dh
end

# ============================================================================
# 反力计算（顶边积分）
# F_y = ∫_top σ_yy dΓ = ∫_top g(d)·[λ·tr(ε) + 2G·ε_yy] dΓ
# 实际实现：在顶部节点处取残差（reaction force）
# 简化为：从平衡方程对顶边节点的反力求和
# 这里使用体积积分方法：F = ∫_Ω σ:ε(v_test) dΩ
# ============================================================================

# ============================================================================
# 主求解循环
# ============================================================================
function run_simulation()
    mkpath(OUTPUT_DIR)
    println("="^70)
    println(" SENT 弹性相场断裂  |  Miehe 2010, Section 5.1")
    println("="^70)
    @printf "  λ = %.0f MPa,  G = %.0f MPa\n" λ_mat G_mat
    @printf "  E ≈ %.0f MPa,  ν ≈ %.4f\n" E_mat ν_mat
    @printf "  Gc = %.4f N/mm,  l₀ = %.4f mm\n" Gc l0
    @printf "  h_fine = %.4f mm = l₀/%.1f\n" h_fine (l0/h_fine)
    println("="^70)

    # ── 网格 ──
    mesh_file = create_mesh()
    model = GmshDiscreteModel(mesh_file)
    if ENABLE_PNG; plot_mesh(mesh_file); end

    # ── 区域与测度 ──
    Ω  = Triangulation(model)
    dΩ = Measure(Ω, 2)

    n_cells = num_cells(Ω)
    cell_coords = get_cell_coordinates(Ω)
    println("\n网格单元数: $(n_cells)")

    # ── 有限元空间 ──
    order  = 1
    reffe_u  = ReferenceFE(lagrangian, VectorValue{2,Float64}, order)
    reffe_d  = ReferenceFE(lagrangian, Float64, order)
    reffe_dg = ReferenceFE(lagrangian, Float64, 0)

    # 位移：底边完全固定，顶边 ux=0、uy=u_apply
    V_u = TestFESpace(model, reffe_u, conformity=:H1,
                      dirichlet_tags   = ["bottom", "top"],
                      dirichlet_masks  = [(true,true), (true,true)])

    # 相场：无 Dirichlet BC（自然边界条件 ∂d/∂n = 0 自动满足）
    V_d = TestFESpace(model, reffe_d, conformity=:H1)
    U_d = TrialFESpace(V_d)

    # DG0 空间存储历史变量
    V_dg = FESpace(model, reffe_dg, conformity=:L2)

    # ── 初始场 ──
    dh     = interpolate_everywhere(x -> 0.0, U_d)   # d=0，完整材料
    H_vals = zeros(n_cells)                             # DG0 历史变量（单元常数）
    H_fe   = FEFunction(V_dg, H_vals)                   # 供相场方程与输出使用

    quad_cache   = CellQuadrature(Ω, 2)
    cell_pts     = get_cell_points(quad_cache)

    # ── 顶边反力积分所需边界对象 ──
    Γ_top  = BoundaryTriangulation(model; tags=["top"])
    dΓ_top = Measure(Γ_top, 2)
    n_top  = get_normal_vector(Γ_top)
    e_y    = VectorValue(0.0, 1.0)

    # ── 数据记录 ──
    u_history = Float64[]
    F_history = Float64[]
    F_kN_history = Float64[]
    time_history = Float64[]

    step = 0
    u_current = 0.0
    next_vtk_level = 1
    crack_started = false
    F_onset = 0.0
    uh = nothing
    run_t0 = time()

    println("\n开始单调加载（调试版，总步数约200；前 100 步 Δu=4.0e-5 mm，之后 Δu=4.0e-5 mm）")
    println("停止条件：顶边反力 F ≤ $(F_STOP_TOL) N")
    println("VTK 输出：第一张在 d_max≈1 时保存，随后按反力降至起裂时刻的 $(collect(VTK_FORCE_DROP_LEVELS)) 倍保存，并额外保存最终帧")
    println("PNG 输出：仅保存最终损伤云图")

    @label sim_loop
    while u_current < u_end
        step += 1

        # ── 步长选择 ──
        if step <= N_STEPS_COARSE
            Δu = Δu_coarse
        else
            Δu = Δu_fine
        end
        u_current = min(u_current + Δu, u_end)

        # ── 位移边界条件 ──
        u_bc_bottom(x) = VectorValue(0.0, 0.0)
        u_bc_top(x)    = VectorValue(0.0, u_current)
        U_u = TrialFESpace(V_u, [u_bc_bottom, u_bc_top])

        # ── 交错迭代（位移 → 历史变量 → 相场） ──
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

            # Step 1: 求解位移（线性，g(d)·C:ε(u):ε(v) = 0）
            g_d = g_deg ∘ dh
            a_u(u, v) = ∫( g_d * (C_elastic ⊙ ε_op(u) ⊙ ε_op(v)) )dΩ
            l_u(v)    = ∫( VectorValue(0.0,0.0) ⋅ v )dΩ
            op_u = AffineFEOperator(a_u, l_u, U_u, V_u)
            uh   = solve(op_u)

            u_curr_vals = copy(get_free_dof_values(uh))
            if stagger_iter > 1
                u_err = norm(u_curr_vals .- u_prev_vals) / (norm(u_curr_vals) + 1e-15)
            end
            u_prev_vals = u_curr_vals

            # Step 2: 参考 phasefieldx，每次交错都用当前 u 重算驱动力，
            #         但只与上一步历史 H_n 比较，不在当前步内继续累积
            εh     = ε_op(uh)
            ε_qp   = evaluate(εh, cell_pts)
            psi_qp = zeros(n_cells)
            for ic in 1:n_cells
                nqp = length(ε_qp[ic])
                psi_max = 0.0
                for iq in 1:nqp
                    psi_max = max(psi_max, miehe_psi_plus(ε_qp[ic][iq]))
                end
                psi_qp[ic] = psi_max
            end
            H_step_vals .= max.(H_prev_vals, psi_qp)
            H_step_fe = FEFunction(V_dg, H_step_vals)

            # Step 3: 求解相场（AT2 线性问题）
            a_d(d, q) = ∫( (Gc/l0 + 2.0*H_step_fe) * d * q
                         + Gc * l0 * (∇(d) ⋅ ∇(q)) )dΩ
            l_d(q)    = ∫( (2.0*H_step_fe) * q )dΩ
            op_d = AffineFEOperator(a_d, l_d, U_d, V_d)
            dh_new = solve(op_d)

            # Step 4: 强制不可逆性 d_{n+1} ≥ d_n
            d_vals_new  = get_free_dof_values(dh_new)
            d_vals_prev = get_free_dof_values(d_old)
            d_vals_new  .= max.(d_vals_new, d_vals_prev)
            d_vals_new  .= clamp.(d_vals_new, 0.0, 1.0)
            dh_new = FEFunction(U_d, d_vals_new)

            # Step 5: 收敛检查 ‖Δd‖/‖d‖
            Δd_norm = norm(get_free_dof_values(dh_new) .- get_free_dof_values(dh))
            d_norm  = norm(get_free_dof_values(dh_new)) + 1e-15
            d_err   = Δd_norm / d_norm
            dh = dh_new

            if stagger_iter >= min_stagger && max(u_err, d_err) < stagger_tol
                break
            end
        end
        H_vals .= H_step_vals
        H_fe = H_step_fe

        # ── 计算顶边纵向反力 Fy = ∫_top (σ·n)·e_y dΓ ──
        σ_deg = (g_deg ∘ dh) * (C_elastic ⊙ ε_op(uh))
        traction_top = σ_deg ⋅ n_top
        F_y = sum(∫( traction_top ⋅ e_y )dΓ_top)
        F_kN = F_y * 1e-3   # 换算为 kN（1 N/mm² × mm² = N, ×1e-3 = kN）

        # ── 统计 d_max ──
        d_at_nodes = get_free_dof_values(dh)
        d_max      = maximum(d_at_nodes)

        push!(u_history,    u_current)
        push!(F_history,    F_y)
        push!(F_kN_history, F_kN)
        push!(time_history, time() - run_t0)

        # ── 输出日志（每 50 步或关键步）──
        if step % 50 == 0 || d_max > 0.3 || step <= 5
            @printf "  步 %4d | u = %.2e mm | F = %.4f kN | d_max = %.4f\n" step u_current F_kN d_max
        end

        # ── VTK 输出：仅保存关键裂纹阶段 5 帧 ──
        if SAVE_VTK && !crack_started && d_max >= VTK_ONSET_LEVEL
            crack_started = true
            F_onset = max(F_y, F_STOP_TOL)
            fname = joinpath(OUTPUT_DIR, @sprintf("result_onset_step%04d", step))
            writevtk(Ω, fname,
                     cellfields=["d"  => dh,
                                 "uh" => uh,
                                 "H"  => H_fe])
            println(@sprintf("  ✓ 保存起裂 VTK: d_max ≈ 1 at step %d", step))
        end

        while SAVE_VTK && crack_started && next_vtk_level <= length(VTK_FORCE_DROP_LEVELS) &&
              F_y <= VTK_FORCE_DROP_LEVELS[next_vtk_level] * F_onset
            target_ratio = VTK_FORCE_DROP_LEVELS[next_vtk_level]
            fname = joinpath(OUTPUT_DIR,
                             @sprintf("result_drop%02d_step%04d", round(Int, 100 * target_ratio), step))
            writevtk(Ω, fname,
                     cellfields=["d"  => dh,
                                 "uh" => uh,
                                 "H"  => H_fe])
            println(@sprintf("  ✓ 保存扩展 VTK: F <= %.2f * F_onset at step %d", target_ratio, step))
            next_vtk_level += 1
        end

        # ── 停止判断：反力降到 0 ──
        if step > 1 && F_y <= F_STOP_TOL
            println("\n>>> 反力已降到 0 附近 (F = $(round(F_y,digits=6)) N)，模拟结束")
            break
        end
    end

    if SAVE_VTK
        final_vtu = joinpath(OUTPUT_DIR, "result_final")
        writevtk(Ω, final_vtu,
                 cellfields=["d"  => dh,
                             "uh" => uh,
                             "H"  => H_fe])
        println("✓ 最终 VTK: result_final")
    end

    # ── 保存 F-u 数据 ──
    step_history = collect(1:length(u_history))
    fu_data = hcat(step_history, time_history, u_history, F_history, F_kN_history)
    fu_file = joinpath(OUTPUT_DIR, "F_u_curve.csv")
    open(fu_file, "w") do f
        println(f, "step,time_s,u_mm,F_N,F_kN")
        writedlm(f, fu_data, ',')
    end
    println("\n✓ F-u 数据已保存: $(fu_file)")

    # ── 绘制 F-u 曲线 ──
    p_fu = plot(u_history .* 1e3, F_kN_history,
                xlabel="位移 u (×10⁻³ mm)", ylabel="反力 F (kN)",
                title="SENT 拉伸 F-u 曲线  (Miehe 2010 Fig.7a)",
                linewidth=2, color=:royalblue, legend=false,
                size=(800, 500), dpi=150, grid=true)
    annotate!(p_fu, u_history[end]*1e3*0.6, maximum(F_kN_history)*0.9,
              text("l₀=$(l0) mm, Gc=$(Gc) N/mm", :left, 10))
    savefig(p_fu, joinpath(OUTPUT_DIR, "F_u_curve_SENT.png"))
    println("✓ F-u 曲线图: F_u_curve_SENT.png")

    # ── 最终损伤云图 ──
    plot_scalar_field(dh,
        title_str = "Final phase-field d  (SENT tension, Miehe 2010)",
        out_file  = joinpath(OUTPUT_DIR, "d_final_SENT.png"),
        vmin=0.0, vmax=1.0)
    println("✓ 最终损伤云图: d_final_SENT.png")

    println("\n" * "="^70)
    println(" 模拟完成！输出目录: $(OUTPUT_DIR)/")
    println("="^70)

    return u_history, F_kN_history, dh
end

# ============================================================================
# 运行
# ============================================================================
run_simulation()
