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
- 已将 GUI、Matplotlib 内嵌图与 `BenchmarkCases_Organized` 的 Julia/GR 绘图字体收敛为同一套 serif 策略，优先使用 `Times`，消除 `Times New Roman.ttf` 告警，并将刻度方向收敛为朝内
- 已将 GUI 主界面与内嵌曲线图字号整体上调 4 个字号
- 已去掉 case 下拉中的 `[Ready]` 一类状态后缀，并收敛部分说明性命名
- 已改为启动前清理旧 GUI 缓存，关闭窗口后自动删除未另存的运行结果，避免下次打开直接回显旧网格/快照
- 已删除顶层历史 `Miehe2010_*` 原型脚本，`Elastic Fracture` 统一维护在 `gui/gui_solver.jl`
- 已补最小自动化验证基线：运行档位逻辑、scan payload 序列化、manifest 兼容、headless GUI 交互
- 已将 `Post-process` 视图改为按 case 能力动态裁剪，fatigue / plastic fatigue 可直接查看 `Curve` 历史
- 已补 `Post-process` 动态视图的 headless 回归测试
- 已为 scan 类 benchmark 补 `Summary Table / Comparison Curve` 专用结果视图
- 已补 scan manifest 收集与 scan 结果视图的 headless 回归测试
- 已统一主界面排版层级，补 header / card / badge / tab / form 的现代化样式
- 已补窗口缩放下的响应式排版，窄宽度时主区自动上下堆叠，左侧参数区可滚动，操作按钮改为纵向排布
- 已统一界面英文文案风格：词组使用 Title Case，句子使用正常句式
- 已补第一版轻量动效：窗口首屏淡入、Tab 切换淡入、预览图交叉淡入、进度条缓动刷新
- 已补第二批交互动效：按钮 hover 微抬升、运行完成 toast 提示、case 切换时左侧参数分组轻微展开
- 已将左侧参数分组改为可收放交互，并统一结果区图片 / 曲线 / 表格切换节奏
- 已去掉 GUI 烟测中的 Matplotlib `tight_layout` 告警，收敛绘图区边距控制
- 已收敛整窗级首屏淡入，避免部分环境下出现首屏空白风险
- 已取消左侧表单自动批量 reveal，仅保留用户触发的分组收放动画，收敛左侧动画噪声
- 已修复 GUI 下 `Generate Mesh` 的 Julia 子进程环境干扰问题，避免 `QApplication` 存在时卡在 mesh preview 生成
- 已将顶部 case badge 收紧为紧凑胶囊，补 mesh / post-process 图片预览的缩放与上下滚动控件，并把完成 toast 调整到底部左侧，收敛 tab 与预览标题尺寸
- 已收敛 `ImagePreviewWidget` 刷新链路，不再对整块预览器做透明动画，修复缩放控件消失与 `Generate Mesh` 过程中的预览不稳定问题
- 已修正主工作流 tab 胶囊尺寸、统一滚动条视觉，并收敛 compute 预览区上下最小高度，避免曲线区被快照区域挤压
- 已整体放大 GUI 字号，并把界面配色收敛到更深的蓝灰方案，增强可读性和层次对比

### 部分完成

- 参数面板已按 `Material / Phase Field / Loading / Smoke / Geometry / Mesh` 分组，但仍是直接编辑，不是更强约束的“只开放少量加载参数”
- 首层功能选择已并入顶部 `Category / Case` 两级选择，不是独立卡片入口页
- `SENT / SENS` 支持实时日志、进度、快照、VTK、曲线刷新；batch case 当前以日志流和结束后回填结果为主
- 结果视图已按 case 动态切换 `Mesh / Damage / Displacement / Curve / Summary Table / Comparison Curve / Visual Export`
- 界面已较明显区分页面标题、分组标题、状态信息与结果区，但仍未细化更小窗口下的控件密度
- 英文文案风格已统一，但仍未系统梳理更细的术语风格

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
- 继续细化更小窗口下的表单密度、字号与按钮尺寸
- 继续统一术语风格与英文缩写显示规则
- 评估 scan 类 benchmark 的表格筛选、列排序与导出
- 继续补更细的交互动效，重点看按钮 hover、状态卡提示和运行完成反馈
- 继续收敛动画细节，重点看 offscreen 绘制 warning、分组 reveal 节奏和完成提示层级
- 继续打磨左侧分组默认展开策略和结果区切换细节，避免动画存在感过强
- 继续区分“代码侧 warning”和“Qt offscreen 插件提示”，优先清理前者
- 继续避免把动画挂在整页容器上，优先保留局部控件级过渡
- 继续保持动画语义单一：自动状态刷新不抢用户手动交互
- 继续评估是否要进一步细化 serif 字体回退顺序，减少不同 Linux 环境下的细微字形差异
- 继续明确排除 `visual exporter` 新需求，先稳定主工作流、界面命名和缓存清理行为
- 继续细化预览区交互，重点看超大图片下的横向滚动、快捷键缩放和控件占宽
- 继续观察 mesh 生成过程中的实时预览刷新，重点看首张快照到达时的交互稳定性
- 继续观察 compute 预览区在更小窗口与不同字体环境下的曲线留白和滚动条细节
- 继续观察更大字号与更深配色在不同 Linux 字体回退和显示缩放下的控件密度
