# peng_pf_ui

面向相场断裂 benchmark 的桌面 GUI。前端使用 `Python + PyQt5`，后端使用 `Julia`，目标是把“选定预设算例 -> 修改参数 -> 运行 -> 查看结果”稳定放进一个可调试的界面。

## 当前状态

### 已完成

- 稳定入口为 `gui/gui_main.py`
- GUI 已整理为四大类 case 选择：
  - `Elastic Fracture`
  - `Elastic Fatigue`
  - `Plastic Fracture`
  - `Plastic Fatigue`
- 当前已接通 8 个 benchmark case：
  - `SENT tension`
  - `SENS shear`
  - `TPB fatigue`
  - `Offset double-notch fatigue`
  - `Flat grooved scan`
  - `Double-notched monotonic`
  - `SENT elasto-plastic fatigue`
  - `CT elasto-plastic fatigue`
- 已支持 `Mesh -> Compute -> Post-process` 工作流
- 已支持参数编辑、日志显示、进度更新、曲线刷新、历史结果切换、最新 VTK 打开
- 已接入 `RunManifest` 统一结果读取
- 已统一为按运行隔离的时间戳结果目录：`gui/gui_results/runs/<case_id>/<run_id>/`
- 每次运行都会归档 `runtime_params.json / manifest.json / native/`
- 已显式接入 `Preview / Full / Debug` 运行档位，`run_profile` 会写入 runtime payload 与 manifest
- 已支持三类 scan case 的扫描列表编辑：
  - `Offset double-notch fatigue`
  - `Flat grooved scan`
  - `Double-notched monotonic`
- 已接入 `visual` 导出链路，当前 `SENT / SENS / Flat grooved` 可自动生成并显示导出图
- 已统一绘图字体为 `Times New Roman`，并将刻度方向收敛为朝内
- 已将 GUI 主界面与内嵌曲线图字号整体上调 4 个字号
- 已去掉 case 下拉中的 `[Ready]` 一类状态后缀，并收敛部分说明性命名
- 已改为启动前清理旧 GUI 缓存，关闭窗口后自动删除未另存的运行结果，避免下次打开直接回显旧网格/快照
- 已删除顶层历史 `Miehe2010_*` 原型脚本，`Elastic Fracture` 统一维护在 `gui/gui_solver.jl`
- 已补最小自动化验证基线：运行档位逻辑、scan payload 序列化、manifest 兼容、headless GUI 交互

### 部分完成

- 参数面板已按 `Material / Phase Field / Loading / Smoke / Geometry / Mesh` 分组，但仍是直接编辑，不是更强约束的“只开放少量加载参数”
- 首层功能选择已并入顶部 `Category / Case` 两级选择，不是独立卡片入口页
- `SENT / SENS` 支持实时日志、进度、快照、VTK、曲线刷新；batch case 当前以日志流和结束后回填结果为主
- 结果视图切换已支持 `Mesh / Damage / Displacement / Visual Export`，但 fatigue / plastic fatigue 的专用可视化仍未补齐

### 未完成

- 自定义 `.msh` 网格导入
- fatigue / plastic fatigue 专用 `visual exporter`
- 视频导出（`mp4` / `gif`）
- 更完整的系统测试与长程 benchmark 验证

## 环境约定

- Python 环境以后统一使用 `gui_envs`
- 环境文件为 `environment.yml`
- Julia 不通过 conda 安装，使用系统 Julia
- 官方 Julia 安装路径为 `/home/dazhi_zhao/opt/julia-1.12.5/bin/julia`
- 在新的 WSL 登录 shell 中，默认命令 `julia` 解析到 `/home/dazhi_zhao/bin/julia`
- GUI 运行 Julia 时显式设置：
  - `JULIA_PROJECT=/home/dazhi_zhao/miniforge3/envs/gui_envs/share/julia/environments/gui_envs`
  - `JULIA_DEPOT_PATH=/home/dazhi_zhao/miniforge3/envs/gui_envs/share/julia`

## 安装与运行

激活环境：

```bash
eval "$(/home/dazhi_zhao/miniforge3/bin/conda shell.bash hook)"
conda activate gui_envs
```

启动 GUI：

```bash
python gui/gui_main.py
```

单独运行 Julia 后端：

```bash
julia gui/gui_solver.jl gui/params_default.json
```

## 输入与输出

- 输入：在 GUI 中选择预设 case，并填写参数；或直接向 `gui/gui_solver.jl` 传入 JSON 参数文件
- 输出：运行结果写入 `gui/gui_results/runs/<case_id>/<run_id>/`，包括 `runtime_params.json`、manifest、曲线、快照、VTK、mesh 预览和 `visual` 导出图；batch case runtime payload 额外包含 `run_profile / scan_cases`
- 关闭 GUI 且未另存时，`gui/gui_results/` 下的 GUI 缓存会被自动清理

## 仓库结构

```text
peng_pf_ui/
├── README.md
├── environment.yml
├── BenchmarkCases_Organized/
├── visual/
└── gui/
    ├── gui_main.py
    ├── gui_solver.jl
    ├── case_registry.py
    ├── run_manifest.py
    ├── params_default.json
    └── gui_results/
```

## 下一步

- 补更完整的系统测试与长程 benchmark 验证
- 评估 fatigue / plastic fatigue 的专用结果视图
- 继续明确排除 `visual exporter` 新需求，先稳定主工作流、界面命名和缓存清理行为
