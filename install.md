# install.md

目标：在一台新的 Linux x86_64 桌面机器上，`git clone` 本仓库后，安装 Julia 和 Python 环境，最后直接运行 `python gui/gui_main.py`。

## 约束

- 以下命令默认在 `bash` 中执行。
- 以下命令默认仓库已经 clone 到 `REPO_ROOT`。
- 以下流程默认机器有图形桌面；纯 headless 机器不能正常打开 PyQt GUI。
- 若系统已经有可用的 `conda` 或 `julia`，可跳过对应安装步骤，但版本尽量对齐到 `Python 3.13` 和 `Julia 1.12.5`。

## 字体与桌面前提

- GUI 和 matplotlib 图默认使用衬线字体。
- [gui/gui_main.py](/home/dazhi_zhao/peng_pf_ui/gui/gui_main.py) 的 Qt 字体回退顺序是 `Times -> Times New Roman -> Nimbus Roman No9 L -> TeX Gyre Termes -> Liberation Serif -> DejaVu Serif`。
- 多个导出脚本与 Julia 绘图脚本直接偏向 `Times` 或 `Times New Roman`，例如 [gui/gui_solver.jl](/home/dazhi_zhao/peng_pf_ui/gui/gui_solver.jl)、[visual/_protocol_case_export.py](/home/dazhi_zhao/peng_pf_ui/visual/_protocol_case_export.py)、[visual/export_fang2019_panels.py](/home/dazhi_zhao/peng_pf_ui/visual/export_fang2019_panels.py)。
- 因此新机器建议额外安装系统级 serif 字体；否则程序通常还能运行，但图面字体可能退回默认字体，Julia/GR 与 Python/matplotlib 的外观也可能不一致。
- `environment.yml` 里的 conda 字体包主要服务 Python 环境，不能替代系统 Julia/GR 对系统字体的依赖。
- Julia `Plots` 默认走 `GR` 后端；`GR` 官方在 Ubuntu 上额外要求 `libxt6 libxrender1 libxext6 libglx-mesa0 libqt6widgets6`。
- GUI 本身要求本地桌面会话；Julia 子进程虽然在代码里禁用了交互式显示，但主 GUI 仍需要 `DISPLAY` 或 Wayland 图形会话。
- 仓库根目录现在自带 [Project.toml](/home/dazhi_zhao/peng_pf_ui/Project.toml)，GUI 在未显式设置 `JULIA_PROJECT` 时会优先使用这个 Julia 项目。

## 给 agent 的执行步骤

### 1. 进入仓库

```bash
export REPO_ROOT="/path/to/peng_pf_ui"
cd "$REPO_ROOT"
```

### 2. 安装系统桌面依赖、GR 运行库和字体

下面是 Ubuntu / Debian 示例。其他发行版安装等价包即可。

```bash
sudo apt-get update
sudo apt-get install -y \
  curl \
  tar \
  xz-utils \
  fontconfig \
  libxt6 \
  libxrender1 \
  libxext6 \
  libglx-mesa0 \
  libqt6widgets6 \
  fonts-urw-base35 \
  fonts-texgyre \
  fonts-dejavu-core \
  fonts-liberation2
```

可选：如果系统允许安装微软核心字体，也可以补装 `ttf-mscorefonts-installer`，这样 `Times New Roman` 会直接可用。

### 3. 安装 Miniforge

如果系统里已经有 `conda`，跳过这一步。

```bash
cd "$HOME"
curl -L -o Miniforge3-Linux-x86_64.sh \
  https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh
bash Miniforge3-Linux-x86_64.sh -b -p "$HOME/miniforge3"
eval "$("$HOME/miniforge3/bin/conda" shell.bash hook)"
conda config --set auto_activate_base false
```

### 4. 安装 Julia 1.12.5

优先使用官方推荐的 `juliaup`。仓库当前验证版本是 `1.12.5`。

推荐方案：

```bash
curl -fsSL https://install.julialang.org | sh -s -- --yes
export PATH="$HOME/.juliaup/bin:$PATH"
grep -qxF 'export PATH="$HOME/.juliaup/bin:$PATH"' "$HOME/.bashrc" || \
  echo 'export PATH="$HOME/.juliaup/bin:$PATH"' >> "$HOME/.bashrc"
juliaup add 1.12.5
juliaup default 1.12.5
julia --version
```

如果 `juliaup` 不可用，再用下面的手工 tarball 方案。

回退方案：

```bash
export JULIA_VERSION="1.12.5"
mkdir -p "$HOME/opt" "$HOME/.local/bin"
curl -L -o "/tmp/julia-${JULIA_VERSION}.tar.gz" \
  "https://julialang-s3.julialang.org/bin/linux/x64/1.12/julia-${JULIA_VERSION}-linux-x86_64.tar.gz"
tar -xzf "/tmp/julia-${JULIA_VERSION}.tar.gz" -C "$HOME/opt"
ln -sf "$HOME/opt/julia-${JULIA_VERSION}/bin/julia" "$HOME/.local/bin/julia"
export PATH="$HOME/.local/bin:$PATH"
grep -qxF 'export PATH="$HOME/.local/bin:$PATH"' "$HOME/.bashrc" || \
  echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
julia --version
```

### 5. 创建 Python 环境

```bash
eval "$("$HOME/miniforge3/bin/conda" shell.bash hook)"
cd "$REPO_ROOT"
conda env create -f environment.yml || conda env update -f environment.yml --prune
conda activate gui_envs
python -V
```

### 6. 检查字体是否可见

下面命令只要至少有一项返回的是 `NimbusRoman`、`TeXGyreTermes`、`LiberationSerif`、`DejaVuSerif` 或 `Times New Roman`，就够用。

```bash
fc-match "Times"
fc-match "Times New Roman"
fc-match "Nimbus Roman No9 L"
fc-match "TeX Gyre Termes"
```

### 7. 实例化仓库自带 Julia 项目

必须在 `conda activate gui_envs` 之后执行。

```bash
export JULIA_DEPOT_PATH="$CONDA_PREFIX/share/julia"
export JULIA_PROJECT="$REPO_ROOT"
julia --project="$REPO_ROOT" -e 'using Pkg; Pkg.instantiate(); Pkg.precompile()'
```

### 8. 验证 Python、Julia 和字体

```bash
python -c 'import PyQt5, matplotlib, meshio, numpy, pandas, scipy; print("python ok")'
python -c 'from matplotlib import font_manager as fm; print(fm.findfont("Times New Roman", fallback_to_default=True))'
julia --project="$REPO_ROOT" -e 'using Gmsh, Gridap, GridapGmsh, LineSearches, Plots; println("julia ok")'
julia --project="$REPO_ROOT" -e 'using Plots; gr(); p=plot([0,1],[0,1]); savefig(p, "gr_smoke.png"); println("gr ok")'
```

### 9. 启动 GUI

```bash
cd "$REPO_ROOT"
eval "$("$HOME/miniforge3/bin/conda" shell.bash hook)"
conda activate gui_envs
python gui/gui_main.py
```

## 常见故障

- 报错 `could not load library ... libXt`、`libXrender`、`libXext`、`libGL` 或 `Qt6Widgets`：
  先重新执行第 2 步，确认 GR 依赖已安装。
- `fc-match "Times"` 没有匹配到 serif 字体：
  继续安装 `fonts-urw-base35`、`fonts-texgyre`、`fonts-liberation2`，然后重开终端再查一次。
- `python gui/gui_main.py` 报 Qt 平台插件或 `xcb` 错误：
  先确认当前是在本地图形桌面终端里运行，而不是纯 SSH/无显示环境。
- 机器是纯 headless：
  本仓库的 GUI 目标不是 headless 运行；可以跑后端 Julia 脚本，但不能把“能打开 GUI”作为验收条件。

## 一次性执行版

下面这段命令按顺序跑完后，就可以直接启动 GUI。

```bash
export REPO_ROOT="/path/to/peng_pf_ui"
cd "$HOME"
sudo apt-get update
sudo apt-get install -y \
  curl \
  tar \
  xz-utils \
  fontconfig \
  libxt6 \
  libxrender1 \
  libxext6 \
  libglx-mesa0 \
  libqt6widgets6 \
  fonts-urw-base35 \
  fonts-texgyre \
  fonts-dejavu-core \
  fonts-liberation2

curl -L -o Miniforge3-Linux-x86_64.sh \
  https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh
bash Miniforge3-Linux-x86_64.sh -b -p "$HOME/miniforge3"
eval "$("$HOME/miniforge3/bin/conda" shell.bash hook)"
conda config --set auto_activate_base false

curl -fsSL https://install.julialang.org | sh -s -- --yes
export PATH="$HOME/.juliaup/bin:$PATH"
juliaup add 1.12.5
juliaup default 1.12.5

cd "$REPO_ROOT"
conda env create -f environment.yml || conda env update -f environment.yml --prune
conda activate gui_envs

export JULIA_DEPOT_PATH="$CONDA_PREFIX/share/julia"
export JULIA_PROJECT="$REPO_ROOT"
julia --project="$REPO_ROOT" -e 'using Pkg; Pkg.instantiate(); Pkg.precompile()'

fc-match "Times"
fc-match "Nimbus Roman No9 L"
python -c 'import PyQt5, matplotlib, meshio, numpy, pandas, scipy; print("python ok")'
python -c 'from matplotlib import font_manager as fm; print(fm.findfont("Times New Roman", fallback_to_default=True))'
julia --project="$REPO_ROOT" -e 'using Gmsh, Gridap, GridapGmsh, LineSearches, Plots; println("julia ok")'
julia --project="$REPO_ROOT" -e 'using Plots; gr(); p=plot([0,1],[0,1]); savefig(p, "gr_smoke.png"); println("gr ok")'
python gui/gui_main.py
```

## 参考

- Julia 官方安装文档：<https://docs.julialang.org/en/v1/manual/installation/>
- Julia 平台安装说明：<https://julialang.org/downloads/platform/>
- GR 官方 Linux 依赖说明：<https://gr-framework.org/julia.html>
