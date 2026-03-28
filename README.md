# peng_pf_ui

一个面向相场断裂算例的桌面 GUI 项目。

当前仓库以两个 Julia 算例为基础：

- `Miehe2010_SENT_tension.jl`
- `Miehe2010_SENS_shear.jl`

Python GUI 负责参数输入、启动 Julia 后端、接收运行日志，并实时刷新曲线与图像结果。

## 项目状态

- 已支持 `SENT` 和 `SENS` 两个弹性断裂算例
- 已实现 `Mesh / Compute / Post-process` 三段式工作流
- `gui/gui_main.py` 是当前更稳的主入口
- `gui/gui_main_modern.py` 是新的 modern GUI demo

`gui/gui_main_modern.py` 当前仍是 demo 状态：

- 可以启动和演示主流程
- 已加入 modern layout 和样式
- 视觉细节、信息密度和局部排版还在继续调整
- 如果你要稳定跑流程，优先使用 `gui/gui_main.py`

## 功能概览

- 参数编辑
- `SENT / SENS` 算例切换
- 网格生成
- 计算启动与停止
- 实时日志显示
- 实时 `F-u` 曲线刷新
- 损伤场 / 位移场结果查看
- 历史快照切换
- ParaView 打开最新 `VTK`

## 仓库结构

```text
peng_pf_ui/
├── GUI_SPEC.md
├── Miehe2010_SENT_tension.jl
├── Miehe2010_SENS_shear.jl
├── README.md
├── requirements.txt
└── gui/
    ├── gui_main.py
    ├── gui_main_modern.py
    ├── gui_main_modern.qss
    ├── gui_solver.jl
    ├── params_default.json
    └── gui_results/            # runtime outputs, ignored by git
```

## 运行环境

### Python

当前 Python GUI 显式依赖：

- `PyQt5==5.15.11`
- `matplotlib==3.10.8`

仓库已提供 [requirements.txt](requirements.txt)。

### Julia

后端由 Julia 脚本驱动，当前项目默认使用 `pf_env` 环境中的 Julia。

当前 README 默认约定：

- `conda` 环境名：`pf_env`
- `julia` 可执行程序在激活 `pf_env` 后可直接调用
- GUI 会在内部通过 `conda activate pf_env` 启动 Julia 后端

## 安装

推荐继续使用你现在的 `pf_env`。

如果只补 Python 依赖，可以执行：

```bash
eval "$(/home/dazhi_zhao/miniforge3/bin/conda shell.bash hook)"
conda activate pf_env
pip install -r requirements.txt
```

## 快速开始

先激活环境：

```bash
eval "$(/home/dazhi_zhao/miniforge3/bin/conda shell.bash hook)"
conda activate pf_env
```

启动稳定版 GUI：

```bash
python gui/gui_main.py
```

启动 modern demo GUI：

```bash
python gui/gui_main_modern.py
```

单独运行 Julia 后端：

```bash
julia gui/gui_solver.jl gui/params_default.json
```

## 工作流

### 1. Mesh

- 设置几何与网格参数
- 生成对应算例的 `.msh` 和预览图

### 2. Compute

- 在已生成网格上运行求解
- 实时输出状态、进度、快照和曲线

### 3. Post-process

- 在 `Mesh / Damage / Displacement` 之间切换
- 浏览历史图像结果
- 打开最新 `VTK` 到 ParaView

## 输出结果

运行结果默认写入：

- `gui/gui_results/`

典型输出包括：

- mesh preview
- damage snapshots
- displacement image
- force-displacement curve
- `VTK` files
- temporary runtime parameter files

这些输出数据不作为源码的一部分，已经通过 `.gitignore` 忽略。

## 当前限制

- 当前只覆盖 `SENT` 和 `SENS`
- `gui/gui_main_modern.py` 仍处于 demo 阶段，不保证视觉已经完全收敛
- Julia 环境仍依赖本地已有的 `pf_env`
- 更完整的疲劳、塑性和弹塑性疲劳流程尚未接入

## 开发说明

- Python 前端：`PyQt5 + matplotlib`
- Julia 后端：统一由 `gui/gui_solver.jl` 调度
- GUI 与后端通过标准输出协议通信

协议示例：

```text
INFO ...
STEP 50 U 4.00e-04 F 3.21e+02 DMAX 0.0032
PROGRESS 5.1
SNAPSHOT gui_results/snap_000050.png
VTK gui_results/result_000050.vtu
DONE
ERROR ...
```

## 路线图

- 继续收敛 `gui/gui_main_modern.py` 的布局与视觉
- 补足更清晰的结果管理和导出流程
- 扩展更多材料与载荷模型
- 逐步接入 fatigue / plasticity 相关算例

## 相关文件

- [GUI_SPEC.md](GUI_SPEC.md)
- [gui_main.py](gui/gui_main.py)
- [gui_main_modern.py](gui/gui_main_modern.py)
- [gui_solver.jl](gui/gui_solver.jl)
