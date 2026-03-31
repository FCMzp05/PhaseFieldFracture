# peng_pf_ui

一个面向相场断裂 benchmark 的桌面 GUI 项目。当前实现采用 `Python + PyQt5` 作为前端，`Julia` 作为后端求解器，目标是把“修改参数 -> 运行算例 -> 实时查看结果”的流程稳定地放进 GUI。

本 README 已合并最新 `GUI_SPEC.md` 的目标、优先级、当前进度与下一步；`GUI_SPEC.md` 继续保留，作为更完整的需求来源。

## 当前进度

### 已完成

- 已打通 `Elastic Fracture` 下的两个弹性断裂算例：
  - `SENT tension`
  - `SENS shear`
- 已实现 `Mesh / Compute / Post-process` 三段式工作流
- 已实现：
  - 参数编辑
  - 网格生成
  - 计算启动 / 停止
  - 实时日志
  - 实时 `F-u` 曲线刷新
  - 损伤场 / 位移场结果查看
  - 历史快照切换
  - 打开最新 `VTK` 到 ParaView
  - 导出当前算例结果
- 当前可用入口：
  - `gui/gui_main.py`：稳定主入口
  - `gui/gui_main_modern.py`：modern UI demo，复用同一套主流程

### 未完成

- 首屏四大类入口：
  - `Elastic Fracture`
  - `Elastic Fatigue`
  - `Plastic Fracture`
  - `Plastic Fatigue`
- 预设 benchmark case 分层选择
- `Elastic Fatigue / Plastic Fracture / Plastic Fatigue` 三类算例接入
- 自定义 `.msh` 网格导入
- `a-N` 曲线流程
- 视频导出（`mp4` / `gif`）
- 以“类别 + 算例 + 时间戳”组织的统一结果目录
- `Preview / Full / Debug` 运行模式切换

## 最新 GUI 规格总览

### 产品定位

- GUI 是现有 Julia benchmark 的外壳，不重写求解器
- 优先做成“稳定、好调试、好改”的参数化运行器，而不是完全自由建模软件
- 用户优先选择已有 benchmark case，再修改少量关键参数启动计算

### 目标功能分层

1. 首屏先做功能选择
   - `Elastic Fracture`
   - `Elastic Fatigue`
   - `Plastic Fracture`
   - `Plastic Fatigue`
2. 第二层选择预设几何 / 预设算例
3. 参数面板优先开放加载相关参数
4. 运行中实时显示日志、进度、图像、曲线
5. 结果区支持按算例类型切换主要可视化内容
6. 结果统一落盘，并支持后处理与视频生成

### 预设算例规划

| 类别 | 预设算例 | 规格优先级 | 当前状态 |
|------|----------|------------|----------|
| Elastic Fracture | `SENT tension` | 最高 | 已完成 |
| Elastic Fracture | `SENS shear` | 高 | 已完成 |
| Elastic Fatigue | `TPB fatigue` / `Offset double-notch fatigue` | 中 | 未开始 |
| Plastic Fracture | `Flat grooved specimen` / `Double-notched monotonic specimen` | 中 | 未开始 |
| Plastic Fatigue | `SENT elasto-plastic fatigue` / `CT elasto-plastic fatigue` | 最后 | 未开始 |

### 第一版实现原则

- 先以预设 benchmark 为核心，不从零建模
- 参数开放以加载相关参数为主
- 几何、材料、相场、疲劳、塑性等基础参数默认使用脚本预设值
- 运行时必须可见：
  - 当前算例
  - 当前步数 / 循环数
  - 当前位移 / 载荷
  - 当前反力 / 裂纹长度
  - 当前运行时间
  - 日志
  - 进度条

## 当前实现与规格的对应关系

| 规格项 | 当前实现情况 |
|--------|--------------|
| Julia 子进程 + stdout 协议 | 已完成 |
| `STEP / PROGRESS / SNAPSHOT / VTK / DONE` 实时更新 | 已完成 |
| `Mesh / Compute / Post-process` 三阶段流程 | 已完成 |
| `SENT / SENS` 参数化运行 | 已完成 |
| 结果图、曲线、日志联动刷新 | 已完成 |
| ParaView 打开最新结果 | 已完成 |
| 首屏四类功能入口 | 未完成 |
| benchmark case 分层导航 | 未完成 |
| 疲劳算例 `CYCLE / a-N` | 未完成 |
| 塑性与弹塑性疲劳算例 | 未完成 |
| 自定义网格导入 | 未完成 |
| 视频生成 | 未完成 |
| 统一时间戳结果目录 | 未完成 |
| 运行模式切换 | 未完成 |

## 下一步

下一步先做信息架构收敛，不先堆新算例：

1. 增加首屏四大类入口和第二层预设 case 选择。
2. 在不破坏现有 `SENT / SENS` 工作流的前提下，把当前 GUI 从“直接选 `SENT / SENS`”过渡到“先选类别，再选 benchmark case”。
3. 同步收敛参数面板，优先保留加载相关参数，其他参数作为预设或高级选项。

这一步完成后，再接入下一类算例，优先是 `Elastic Fatigue`。

## 仓库结构

```text
peng_pf_ui/
├── GUI_SPEC.md
├── Miehe2010_SENT_tension.jl
├── Miehe2010_SENS_shear.jl
├── README.md
├── environment.yml
├── BenchmarkCases_Organized/
├── visual/
└── gui/
    ├── gui_main.py
    ├── gui_main_modern.py
    ├── gui_main_modern.qss
    ├── gui_solver.jl
    ├── params_default.json
    └── gui_results/            # runtime outputs, ignored by git
```

## 运行环境

当前项目保留一个环境文件：

- `environment.yml`

该环境统一描述：

- `conda` 环境名 `pf_env`
- Python 运行时版本
- GUI 所需 Python 包
- Julia 运行时版本
- 当前确认过的 Julia 顶层包版本说明

当前 GUI 默认通过激活后的 `pf_env` 启动 Julia 后端。

## 安装

```bash
conda env create -f environment.yml
conda activate pf_env
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

## 当前工作流

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

当前典型输出包括：

- mesh preview
- damage snapshots
- displacement image
- force-displacement curve
- `VTK` files
- temporary runtime parameter files

这些输出数据不作为源码的一部分，已通过 `.gitignore` 忽略。

## 调试建议

优先在命令行直接调 Julia 侧：

```bash
cd /home/dazhi_zhao/peng_pf_ui/gui
julia gui_solver.jl params_default.json
```

如果 Julia 报错，先看终端完整错误栈，不要先在 GUI 日志里猜。

## 相关文件

- `GUI_SPEC.md`
- `environment.yml`
- `gui/gui_main.py`
- `gui/gui_main_modern.py`
- `gui/gui_solver.jl`
