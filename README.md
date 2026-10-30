# Repository for *From Brittle Fracture to Elastoplastic Fatigue: An Open-Source Phase Field Framework in Julia*

`PhaseFieldFracture` is the companion repository for the paper P. Zhang, D. Zhao, K. Tang, *From brittle fracture to elastoplastic fatigue: An open-source phase field framework in Julia*, Advances in Engineering Software 220, 104222 (2026), https://doi.org/10.1016/j.advengsoft.2026.104222. It contains the Julia/Gridap implementation, benchmark scripts, and GUI used to reproduce and explore the results reported in the paper.

## Three key features

### 1. Unified multi-regime framework

One codebase covers elastic fracture, elastic fatigue, ductile fracture, and elastoplastic fatigue with a shared solver structure.

### 2. Transparent single-language implementation

The governing equations are mapped directly into Julia through Gridap's weak-form API, keeping theory and implementation closely aligned.

### 3. Reproducible validated benchmarks with GUI access

Eight validated benchmarks, from brittle fracture to GH4169 elastoplastic fatigue, are provided with reproducible scripts and GUI-based inspection.

## Benchmarks in this repository

- `Elastic Fracture`: `SENT Tension`, `SENS Shear`
- `Elastic Fatigue`: `TPB Fatigue`, `Offset Double-Notch Fatigue`
- `Plastic Fracture`: `Flat Grooved Scan`, `Double-Notched Monotonic`
- `Plastic Fatigue`: `SENT Elasto-Plastic Fatigue`, `CT Elasto-Plastic Fatigue`

## Workflow

- Fixed workflow: `Mesh -> Compute -> Post-process`
- Parameter groups: `Geometry / Mesh / Material / Phase Field / Loading / Smoke`
- Post-processing views: `Mesh`, `Damage`, `Displacement`, `Von Mises`, `Curve`, `Summary Table`, `Comparison Curve`, `Results Summary`
- Run artifacts are collected under `gui/gui_results/runs/<case_id>/<run_id>/`

Linux is the recommended platform for routine use.

## Repository layout

- `gui/gui_main.py`: main desktop entry point
- `gui/case_registry.py`: benchmark registration and parameter grouping
- `gui/gui_solver.jl`: Julia backend for the built-in protocol cases
- `gui/run_manifest.py`: run metadata and result bookkeeping
- `BenchmarkCases_Organized/`: Julia benchmark scripts for fatigue and plastic cases
- `visual/`: export panels and plotting helpers
- `environment.yml`: Python runtime environment
- `Project.toml`: Julia project environment

## Quick start

```bash
git clone https://github.com/FCMzp05/PhaseFieldFracture
cd /path/to/PhaseFieldFracture
export REPO_ROOT="$(pwd)"
eval "$("$HOME/miniforge3/bin/conda" shell.bash hook)"
conda env create -f environment.yml || conda env update -f environment.yml --prune
conda activate gui_envs

export JULIA_DEPOT_PATH="$CONDA_PREFIX/share/julia"
export JULIA_PROJECT="$REPO_ROOT"
julia --project="$REPO_ROOT" -e 'using Pkg; Pkg.instantiate(); Pkg.precompile()'
python gui/gui_main.py
```

## Launch the GUI

Input: benchmark selection and parameter edits in the GUI  
Output: mesh files, curves, snapshots, `VTU`, manifests, and summary figures under `gui/gui_results/runs/<case_id>/<run_id>/`  
Run on Linux:

```bash
cd /path/to/PhaseFieldFracture
export REPO_ROOT="$(pwd)"
eval "$("$HOME/miniforge3/bin/conda" shell.bash hook)"
conda activate gui_envs
export JULIA_DEPOT_PATH="$CONDA_PREFIX/share/julia"
export JULIA_PROJECT="$REPO_ROOT"
python gui/gui_main.py
```

## Run the Julia backend directly

Input: a JSON parameter file such as `gui/params_default.json`  
Output: raw result files under `gui/gui_results/` for the selected case  
Run on Linux:

```bash
cd /path/to/PhaseFieldFracture
export REPO_ROOT="$(pwd)"
eval "$("$HOME/miniforge3/bin/conda" shell.bash hook)"
conda activate gui_envs
export JULIA_DEPOT_PATH="$CONDA_PREFIX/share/julia"
export JULIA_PROJECT="$REPO_ROOT"
julia gui/gui_solver.jl gui/params_default.json
```

## Citation

If you use this repository, please cite:

```bibtex
@article{zhang2026phasefield,
  title   = {From brittle fracture to elastoplastic fatigue: An open-source phase field framework in {Julia}},
  author  = {Zhang, Peng and Zhao, Dazhi and Tang, Keke},
  journal = {Advances in Engineering Software},
  volume  = {220},
  pages   = {104222},
  year    = {2026},
  doi     = {10.1016/j.advengsoft.2026.104222}
}
```
