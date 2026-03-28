# peng_pf_ui

## 当前状态

这个仓库当前包含两个 Julia 相场断裂算例：

- `Miehe2010_SENT_tension.jl`
- `Miehe2010_SENS_shear.jl`
- `gui/gui_solver.jl`
- `gui/gui_main.py`
- `gui/params_default.json`

Julia runtime environment:

- `conda` 环境名：`pf_env`
- Julia 项目目录：`$CONDA_PREFIX/julia_project`
- Julia depot 目录：`$CONDA_PREFIX/julia_depot`
- 激活 `pf_env` 后默认使用 `pf_env` 内部的 Julia 1.10.4

Python runtime environment:

- `pf_env` now includes Python 3.13, `pip`, `PyQt5`, and `matplotlib`
- The GUI can be started directly from `pf_env`
- The GUI launches the Julia backend internally through `conda activate pf_env`

激活方式：

```bash
eval "$(/home/dazhi_zhao/miniforge3/bin/conda shell.bash hook)"
conda activate pf_env
```

当前已验证：

- Julia 可以正常启动
- `Gmsh`、`Gridap`、`GridapGmsh`、`Plots` 可正常导入
- `python`、`pip`、`PyQt5`、`matplotlib` are available inside `pf_env`
- `Miehe2010_SENS_shear.jl` 可成功启动并生成网格输出
- `gui/gui_solver.jl` 可读取 `params.json`、输出 `INFO/STEP/PROGRESS/SNAPSHOT/VTK/DONE` 协议
- `gui/gui_main.py` can start directly from `pf_env`

## Stage Status

- [x] Phase 1: minimal SENT GUI completed
- [ ] Phase 2: current phase, build the `Mesh / Compute / Post-process` workflow
- [ ] Phase 3: future phase, extend to fatigue and plasticity cases

Phase 1 completed:

- SENT parameter editing
- `Run` starts the Julia backend
- `Stop` uses `gui/gui_stop.flag` for safe shutdown
- real-time damage PNG refresh
- real-time `F-u` curve refresh
- log window, status text, progress bar
- `CSV`, `PNG`, `VTK` outputs

Phase 2 current target:

- Mesh:
  expose mesh-related parameters only, and display the mesh image immediately after meshing
- Compute:
  show real-time residual, force-displacement curve, and damage contour during the solve
- Post-process:
  allow switching between mesh view, damage contour, and displacement contour

Next features to implement:

1. `SENS` case switching
2. ParaView integration
3. post-process history browsing

## Run

Start the GUI:

```bash
eval "$(/home/dazhi_zhao/miniforge3/bin/conda shell.bash hook)"
conda activate pf_env
python gui/gui_main.py
```

Run the Julia backend directly:

```bash
eval "$(/home/dazhi_zhao/miniforge3/bin/conda shell.bash hook)"
conda activate pf_env
julia gui/gui_solver.jl gui/params_default.json
```

Runtime output directory:

- `gui/gui_results/mesh_SENT.msh`
- `gui/gui_results/F_u_curve.csv`
- `gui/gui_results/snap_*.png`
- `gui/gui_results/d_final_SENT.png`
- `gui/gui_results/result_final.vtu`

## 项目目标

目标是把当前基于命令行的 Julia 仿真程序改造成一个可视化桌面程序：

- 前端：Python GUI
- 后端：Julia 求解器
- 交互方式：Python 启动 Julia 子进程，Julia 输出进度和结果，GUI 实时刷新

最终要实现的是一个“参数输入 -> 运行求解 -> 实时显示损伤场和曲线”的界面程序，而不是继续手工修改 `.jl` 文件中的 `const` 参数。

## 目标架构

推荐架构直接采用 `GUI_SPEC.md` 的方案：

- Python 使用 `PyQt5` 构建 GUI
- 曲线区使用 `matplotlib`
- Julia 作为后台计算进程运行
- Python 将参数写入 `params.json`
- Python 启动：内部调用 `julia gui/gui_solver.jl params.json`
- Julia 通过标准输出 `stdout` 向 Python 持续发送状态行
- Julia 定期保存 PNG / VTK / CSV 文件
- Python 收到路径或进度信息后更新界面

建议的通信格式：

```text
INFO ...
STEP 50 U 4.00e-04 F 3.21e+02 DMAX 0.0032
PROGRESS 5.1
SNAPSHOT gui_results/snap_000050.png
VTK gui_results/result_000050.vtu
CYCLE 100 A 0.523 DMAX 0.234
DONE
ERROR ...
```

## GUI 开发要求整合

基于 `GUI_SPEC.md`，GUI 至少应覆盖以下功能。

### Phase 2 workflow target

The next implementation stage is organized into three workflow blocks:

- Mesh:
  provide mesh-related inputs only, run meshing first, and display the generated mesh image
- Compute:
  display the real-time residual, force-displacement curve, and damage contour while solving
- Post-process:
  provide a view switcher for mesh, damage, and displacement contour results

### 1. 参数输入面板

左侧参数区按组组织：

- 材料参数：`E`、`ν`、`σ_y0`、`n`
- 相场参数：`Gc`、`l0`、`αT`、`η`
- 加载参数：`u_max`、`N_coarse`、`Δu_coarse`、`Δu_fine`、`R`、`N_cycles`、`N_steps_per_cycle`
- 网格参数：`h_fine`、`h_coarse`、`a0`、`W`、`H`

要求：

- 不同算例下只启用相关参数
- 不适用参数灰掉，不隐藏
- 参数分组清晰，便于调试

### 2. 算例和网格来源选择

顶部应有两个下拉框：

- 算例类型
- 网格来源

算例类型目标上支持：

- 弹性断裂-拉伸（SENT）
- 弹性断裂-剪切（SENS）
- 弹性疲劳
- 塑性断裂
- 弹塑性疲劳

但当前仓库实际已有的本地 Julia 脚本只有：

- SENT 弹性断裂
- SENS 弹性断裂

因此第一阶段 GUI 实现应先基于这两个脚本落地，其他三类作为后续扩展目标保留在设计中。

网格来源支持：

- 自动生成
- 导入已有 `.msh`

### 3. 运行与停止

界面应提供：

- `Run` 按钮：启动 Julia 后端
- `Stop` 按钮：中断 Julia 后端

建议停止机制：

- Python 创建 `gui_stop.flag`
- Julia 每步检查该文件
- 若存在则打印 `INFO Stopped by user` 并安全退出

### 4. 右侧可视化区

右上：

- 损伤场 PNG 实时显示
- 使用 `QLabel + QPixmap`

右下：

- 曲线实时刷新
- 弹性/塑性断裂：`F-u`
- 疲劳类：`a-N`

### 5. 进度和日志

界面应包含：

- 进度条
- 当前状态文字
- 日志窗口

日志区直接显示 Julia 输出的最近若干行，方便调试。

### 6. ParaView 联动

下一步将实现：

- Julia 输出最新 `VTK` 路径
- Python 记录最近一次 `VTK`
- 提供 “Open in ParaView” 按钮

## 建议代码组织

建议不要直接改原始算例脚本，而是在仓库中增加独立 GUI 层：

```text
peng_pf_ui/
├── Miehe2010_SENT_tension.jl
├── Miehe2010_SENS_shear.jl
├── GUI_SPEC.md
├── README.md
└── gui/
    ├── gui_main.py
    ├── gui_solver.jl
    ├── params_default.json
    └── gui_results/
```

职责划分：

- 原始 `.jl` 脚本：保留为参考和算法来源
- `gui_solver.jl`：读取 JSON、调度算例、输出统一 stdout 协议
- `gui_main.py`：界面、线程、日志、图像、曲线、进程管理

## Phase Implementation Notes

Phase 1 completed:

1. 基于 `Miehe2010_SENT_tension.jl` 跑通 GUI 后端
2. Support parameter editing
3. Launch Julia with `Run`
4. Refresh damage PNG in real time
5. Refresh the `F-u` curve in real time
6. Support `Stop`

Phase 2 current target:

- Mesh:
  expose mesh-related parameters only, and display the generated mesh image after meshing
- Compute:
  show real-time residual, force-displacement curve, and damage contour during the solve
- Post-process:
  switch between mesh, damage, and displacement contour views

Phase 3 and later will cover the fatigue and plasticity cases described in `GUI_SPEC.md`. Those scripts are not present in this repository yet.

## Python GUI 实现建议

建议按照 `GUI_SPEC.md` 中的两类结构实现：

- `JuliaWorker(QThread)`：负责启动 Julia 子进程、读取 stdout、解析协议、发信号
- `MainWindow(QMainWindow)`：负责参数面板、图片显示、曲线区、日志区和按钮状态

推荐 Python 依赖：

```bash
eval "$(/home/dazhi_zhao/miniforge3/bin/conda shell.bash hook)"
conda activate pf_env
python -m pip install PyQt5 matplotlib
```

## 当前结论

这个仓库现在已经具备做 GUI 封装的基础条件：

- Julia 环境已可用
- 两个基础弹性算例已就绪
- `GUI_SPEC.md` 已给出明确的界面目标和通信方案
- 第一阶段最小可用 SENT GUI 已落地

The next direct task is Phase 2:

- 接入 `Miehe2010_SENS_shear.jl`
- 增加 `SENS` 算例切换
- 增加 ParaView 联动
- 增加后处理历史浏览
