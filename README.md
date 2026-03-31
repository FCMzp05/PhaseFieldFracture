# peng_pf_ui

一个面向相场断裂 benchmark 的桌面 GUI 项目。当前实现采用 `Python + PyQt5` 作为前端，`Julia` 作为后端求解器，目标是把“修改参数 -> 运行算例 -> 实时查看结果”的流程稳定地放进 GUI。

本 README 已合并最新 `GUI_SPEC.md` 的目标、优先级、当前进度与下一步；`GUI_SPEC.md` 继续保留，作为更完整的需求来源。

## 当前进度

### 已完成

- 已重建 `gui_envs` 运行环境，并补齐 `meshio`
- 已把最新 Julia benchmark 代码统一整理到 `BenchmarkCases_Organized/`
- 已把 GUI 从硬编码 `SENT / SENS` 收敛到“四大类 -> benchmark case”选择结构
- 已接通 8 个可运行 case：
  - `SENT tension`
  - `SENS shear`
  - `TPB fatigue`
  - `Offset double-notch fatigue`
  - `Fang flat grooved scan`
  - `Double-notched monotonic`
  - `SENT elasto-plastic fatigue`
  - `CT elasto-plastic fatigue`
- 已为新增 5 个 batch case 接通 GUI 参数编辑
- 已实现 batch benchmark 的 runtime JSON 参数覆盖，不再只能跑脚本硬编码默认值
- 已把新增 batch case 默认参数收敛到最小 smoke run，方便先跑通一小步
- 已实现 `RunManifest` 结果契约，GUI 后处理、导出和历史读取统一基于 manifest
- 已把 `visual` 作为导出模板落地首个 exporter：
  - `Fang2019` damage panel
  - `Fang2019` equivalent plastic strain panel
  - `Fang2019` force-displacement comparison
- 已完成 `visual` 第一阶段标准化：
  - 新增统一 exporter 注册入口
  - `SENT / SENS / Fang` 统一走 `case_registry -> visual exporter -> manifest`
  - 计算完成后自动生成并显示 visual 导出图
- 已将 `visual/` 下原有 5 个 `.ipynb` 全部转为 `.py` 脚本，不再依赖 notebook
- 已保留 `SENT / SENS` 的 `Mesh / Compute / Post-process` 三段式工作流
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

### 未完成

- 自定义 `.msh` 网格导入
- fatigue / plastic fatigue 的专用 `visual exporter`
- 视频导出（`mp4` / `gif`）
- 以“类别 + 算例 + 时间戳”组织的统一结果目录
- `Preview / Full / Debug` 运行模式切换
- scan 型 case 的扫描列表编辑
- 更完整的系统测试与长程 benchmark 验证

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
| Elastic Fatigue | `TPB fatigue` / `Offset double-notch fatigue` | 中 | 已接通 |
| Plastic Fracture | `Flat grooved specimen` / `Double-notched monotonic specimen` | 中 | 已接通 |
| Plastic Fatigue | `SENT elasto-plastic fatigue` / `CT elasto-plastic fatigue` | 最后 | 已接通 |

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
| 四大类入口 + case registry | 已完成 |
| `RunManifest` 统一结果读取 | 已完成 |
| `visual` 导出模板接入（Fang） | 已完成 |
| `visual` 统一 exporter 接口（SENT / SENS / Fang） | 已完成 |
| `Plastic Fracture -> Fang flat grooved scan` | 已完成 |
| 其余 5 个 batch case 的 GUI 接入 | 已完成 |
| batch case GUI 参数覆盖 | 已完成 |
| batch case 最小 smoke run 默认参数 | 已完成 |
| 结果图、曲线、日志联动刷新 | 已完成 |
| ParaView 打开最新结果 | 已完成 |
| fatigue / plastic fatigue 基础 `a-N` 曲线读取 | 已完成 |
| 自定义网格导入 | 未完成 |
| 视频生成 | 未完成 |
| 统一时间戳结果目录 | 未完成 |
| 运行模式切换 | 未完成 |

## 下一步

下一步不再是“先接首个 fatigue case”，而是补齐已接入 case 的第二阶段能力：

1. 为 fatigue / plastic fatigue 补专用 `visual exporter`，优先 `Li / CT`。
2. 统一时间戳结果目录和结果归档结构。
3. 补 scan 型 case 的扫描列表编辑，而不只是共享标量参数。

当前不再维护 `modern` 分支，只保留 `gui/gui_main.py`。

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
    ├── case_registry.py
    ├── run_manifest.py
    ├── gui_solver.jl
    ├── params_default.json
    └── gui_results/            # runtime outputs, ignored by git
```

## 运行环境

当前项目保留一个环境文件：

- `environment.yml`

该环境统一描述：

- `conda` 环境名 `gui_envs`
- Python 运行时版本
- GUI 所需 Python 包
- `visual` exporter 所需 Python 包
- `meshio=5.3.5`
- Julia 运行时版本
- 当前确认过的 Julia 顶层包版本说明

当前 GUI 默认优先尝试 `gui_envs`，并兼容本机已有环境名 `pf_env` 与 `pf-env`。

## 安装

```bash
conda env create -f environment.yml
conda activate gui_envs
```

## 快速开始

先激活环境：

```bash
eval "$(/home/dazhi_zhao/miniforge3/bin/conda shell.bash hook)"
conda activate gui_envs
```

启动稳定版 GUI：

```bash
python gui/gui_main.py
```

单独运行 Julia 后端：

```bash
julia gui/gui_solver.jl gui/params_default.json
```

## 当前工作流

### 1. Mesh

- `SENT / SENS`：
  - 设置几何与网格参数
  - 生成对应算例的 `.msh` 和预览图
- `Fang flat grooved scan`：
  - 网格在 benchmark 计算阶段内部生成，不单独暴露 mesh run

### 2. Compute

- `SENT / SENS`：
  - 在已生成网格上运行求解
  - 实时输出状态、进度、快照和曲线
- 其余 6 个 batch case：
  - 直接运行 batch benchmark
  - 在 GUI 里编辑共享参数后生成 runtime JSON
  - 实时显示日志，结束后统一扫描结果并生成 manifest

### 3. Post-process

- 在 `Mesh / Damage / Displacement / Visual Export` 之间切换
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
- visual exporter panels
- `VTK` files
- temporary runtime parameter files
- run manifest JSON

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
- `gui/case_registry.py`
- `gui/run_manifest.py`
- `gui/gui_solver.jl`
