# peng_pf_ui

`peng_pf_ui` 是一个面向相场断裂 benchmark 的桌面 GUI，目的是把现有算例整理成统一入口：选择 case、修改参数、生成网格、启动计算、查看结果、导出图板。前端使用 `Python + PyQt5`，结果曲线与实时预览使用 `matplotlib`，后端同时连接两类求解链路：一类是 GUI 内置的 `Julia + Gridap/Gmsh` 协议算例，另一类是仓库内 `BenchmarkCases_Organized/` 下的批处理 benchmark 脚本。

GUI 主入口是 [gui/gui_main.py](/home/dazhi_zhao/peng_pf_ui/gui/gui_main.py)，算例注册与参数分组在 [gui/case_registry.py](/home/dazhi_zhao/peng_pf_ui/gui/case_registry.py)，运行结果通过 [gui/run_manifest.py](/home/dazhi_zhao/peng_pf_ui/gui/run_manifest.py) 统一整理到 `gui/gui_results/runs/<case_id>/<run_id>/`。其中 `SENT` 和 `SENS` 由 [gui/gui_solver.jl](/home/dazhi_zhao/peng_pf_ui/gui/gui_solver.jl) 直接生成网格、曲线、快照与 `VTU`；其余 fatigue / plastic benchmark 通过 `BenchmarkCases_Organized` 中对应 Julia 脚本运行，再由 GUI 回收结果并在 `Post-process` 中展示。`visual/` 目录提供每类 benchmark 对应的导出面板，用于生成统一风格的结果图。

当前代码中的算例按四类组织：

- `Elastic Fracture`：`SENT Tension`、`SENS Shear`
- `Elastic Fatigue`：`TPB Fatigue`、`Offset Double-Notch Fatigue`
- `Plastic Fracture`：`Flat Grooved Scan`、`Double-Notched Monotonic`
- `Plastic Fatigue`：`SENT Elasto-Plastic Fatigue`、`CT Elasto-Plastic Fatigue`

GUI 工作流固定为 `Mesh -> Compute -> Post-process`。参数面板按 `Geometry / Mesh / Material / Phase Field / Loading / Smoke` 分组；结果视图根据算例能力切换为 `Mesh`、`Damage`、`Displacement`、`Curve`、`Summary Table`、`Comparison Curve`、`Visual Export`。运行时会保存参数副本、结果清单、原始输出文件和导出图，方便回看最近一次结果，也方便后续脚本处理。

当前进展：`Post-process` 已改为固定适配预览，去掉内部滑条并禁用该页 `Ctrl` 缩放链路；`Open In ParaView` 已移除；协议类 `Visual Export` 已去掉点位标题并保持横向 `1x2`。  
当前进展补充：页头缓存开关已收进 `More` 菜单，不再直接占用主界面视觉位置。  
当前进展补充：界面卡片阴影与残余渐变已全部移除，整体改为更纯的扁平化纯色设计。  
当前进展补充：新增 [install.md](install.md)，并把 GUI 的 Julia 环境解析改为优先跟随当前激活的 conda 环境，不再依赖作者本机绝对路径。  
当前进展补充：`install.md` 已补充 Linux 桌面字体与 `fontconfig` 前提，明确 `Times` 系字体回退链和检查命令。  
当前进展补充：`install.md` 已补充 GR 系统运行库、Julia 官方 `juliaup` 安装路径和常见故障排查。  
当前进展补充：仓库根目录已新增 [Project.toml](/home/dazhi_zhao/peng_pf_ui/Project.toml)，GUI 在未显式设置 `JULIA_PROJECT` 时会优先使用仓库自带 Julia 项目。  
当前进展补充：`Post-process` 的 `Visual Export` 视图已改为更紧凑的预览高度，并隐藏无关 `VTK` 信息；导出图中顶部列标题与协议曲线 `A/B/C` 标注已去掉。  
当前进展补充：`Compute` 右侧第二张实时预览已由位移云图改为 `Von Mises` 云图；`Post-process` 的 `History` 下拉已移除，序列浏览改为仅对 `Damage / Displacement / Von Mises` 生效的顶栏加粗可拖拽时间轴，`Mesh / Visual Export` 不再显示时间轴；协议类 `Visual Export` 的 `field panel` 已扩为横向 `1x3`，内容为 `damage / displacement magnitude / von Mises stress`。  
下一步：继续观察顶栏时间轴在 batch benchmark 大量历史帧下的可读性与响应速度，并评估是否需要进一步补刻度或关键帧标记。

## 环境

- Python 环境名：`gui_envs`
- 环境文件：[environment.yml](/home/dazhi_zhao/peng_pf_ui/environment.yml)
- Python 侧核心依赖：`PyQt5`、`matplotlib`、`meshio`、`numpy`、`pandas`、`scipy`
- Julia 使用系统安装，不通过 conda 提供
- Julia 项目文件：[Project.toml](/home/dazhi_zhao/peng_pf_ui/Project.toml)
- 新机器安装步骤见 [install.md](install.md)
- 新机器建议同时安装系统 `fontconfig` 和 serif 字体包，保证 GUI、matplotlib 与 Julia/GR 图面字体一致

## 输入与输出

- 输入：在 GUI 中选择预设算例并填写参数；或直接向 Julia 后端传入 JSON 参数文件，例如 [gui/params_default.json](/home/dazhi_zhao/peng_pf_ui/gui/params_default.json)
- 输出：写入 `gui/gui_results/runs/<case_id>/<run_id>/`，包含 `runtime_params.json`、`manifest.json`、网格图、曲线、快照、`VTU` 和 `visual export` 图片

## 运行

GUI 输入：GUI 内选择算例并编辑参数  
GUI 输出：运行目录下的网格、曲线、快照、`VTU`、manifest 和导出图  
Linux + Python 运行方式：激活 `gui_envs` 后启动主界面  
完整 CLI：

```bash
cd /path/to/peng_pf_ui
eval "$("$HOME/miniforge3/bin/conda" shell.bash hook)"
conda activate gui_envs
python gui/gui_main.py
```

Julia 后端输入：JSON 参数文件  
Julia 后端输出：`gui/gui_results/` 下对应 case 的原始结果文件  
Linux + Python 环境下运行方式：在已准备好 Julia 环境后直接调用后端脚本  
完整 CLI：

```bash
cd /path/to/peng_pf_ui
eval "$("$HOME/miniforge3/bin/conda" shell.bash hook)"
conda activate gui_envs
julia gui/gui_solver.jl gui/params_default.json
```
