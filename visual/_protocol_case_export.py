from __future__ import annotations

import csv
import re
import shutil
from pathlib import Path

import matplotlib as mpl
mpl.use("Agg")
import matplotlib.pyplot as plt
import meshio
import numpy as np


mpl.rcParams.update(
    {
        "font.family": "Times New Roman",
        "font.serif": ["Times New Roman"],
        "mathtext.fontset": "stix",
        "font.size": 18,
        "figure.dpi": 180,
        "xtick.direction": "in",
        "ytick.direction": "in",
    }
)


def _first_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def _extract_step(path: Path) -> int:
    match = re.search(r"(\d+)(?=\.png$)", path.name)
    return int(match.group(1)) if match else -1


def _snapshot_candidates(native_output_dir: Path, patterns: list[str]) -> list[Path]:
    for pattern in patterns:
        matches = sorted(
            (path for path in native_output_dir.glob(pattern) if path.is_file()),
            key=lambda path: (_extract_step(path), path.name),
        )
        if matches:
            return matches
    return []


def _select_snapshot_panel(paths: list[Path]) -> list[Path]:
    if len(paths) <= 3:
        return paths
    candidate_indices = [0, len(paths) // 2, len(paths) - 1]
    selected_indices: list[int] = []
    for index in candidate_indices:
        if index not in selected_indices:
            selected_indices.append(index)
    return [paths[index] for index in selected_indices]


def _copy_or_render_curve(
    native_output_dir: Path,
    output_path: Path,
    png_candidates: list[str],
    csv_candidates: list[str],
    title: str,
) -> Path:
    curve_png = _first_existing([native_output_dir / name for name in png_candidates])
    if curve_png is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(curve_png, output_path)
        return output_path

    csv_path = _first_existing([native_output_dir / name for name in csv_candidates])
    if csv_path is None:
        raise FileNotFoundError(f"Missing curve payload in {native_output_dir}")

    x_values: list[float] = []
    y_values: list[float] = []
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            x_values.append(float(row["u_mm"]))
            y_values.append(float(row["F_kN"]))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7.2, 5.4))
    ax.plot(x_values, y_values, color="#1f77b4", linewidth=2.2)
    ax.set_xlabel("Displacement u (mm)")
    ax.set_ylabel("Force F (kN)")
    ax.set_title(title)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    return output_path


def _copy_or_render_mesh(
    native_output_dir: Path,
    output_path: Path,
    mesh_png_name: str,
    mesh_msh_name: str,
    title: str,
) -> Path:
    mesh_png = native_output_dir / mesh_png_name
    if mesh_png.exists():
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(mesh_png, output_path)
        return output_path

    mesh_msh = native_output_dir / mesh_msh_name
    if not mesh_msh.exists():
        raise FileNotFoundError(f"Missing mesh payload in {native_output_dir}")

    mesh = meshio.read(mesh_msh)
    triangles = np.asarray(mesh.cells_dict["triangle"], dtype=int)
    coords = np.asarray(mesh.points[:, :2], dtype=float)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6.2, 6.2))
    ax.triplot(coords[:, 0], coords[:, 1], triangles, color="#5A8FAA", linewidth=0.35)
    ax.set_aspect("equal")
    ax.set_axis_off()
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    return output_path


def _build_snapshot_panel(snapshot_paths: list[Path], output_path: Path, title: str) -> Path:
    if not snapshot_paths:
        raise FileNotFoundError("No snapshot PNG files found for visual export.")

    selected_paths = _select_snapshot_panel(snapshot_paths)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, len(selected_paths), figsize=(5.1 * len(selected_paths), 4.8))
    if len(selected_paths) == 1:
        axes = [axes]

    for ax, path in zip(axes, selected_paths):
        image = plt.imread(path)
        ax.imshow(image)
        ax.set_axis_off()
        step = _extract_step(path)
        ax.set_title(f"Step {step}" if step >= 0 else path.stem)

    fig.suptitle(title, y=0.98)
    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    return output_path


def export_protocol_case_panels(
    native_output_dir: Path,
    output_dir: Path,
    *,
    case_prefix: str,
    display_name: str,
    mesh_png_name: str,
    mesh_msh_name: str,
    curve_png_names: list[str],
    curve_csv_names: list[str],
    snapshot_patterns: list[str],
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)

    snapshot_paths = _snapshot_candidates(native_output_dir, snapshot_patterns)
    panel_path = _build_snapshot_panel(
        snapshot_paths,
        output_dir / f"{case_prefix}_damage_panel.png",
        f"{display_name} damage snapshots",
    )
    curve_path = _copy_or_render_curve(
        native_output_dir,
        output_dir / f"{case_prefix}_force_displacement_curve.png",
        curve_png_names,
        curve_csv_names,
        f"{display_name} force-displacement",
    )
    mesh_path = _copy_or_render_mesh(
        native_output_dir,
        output_dir / f"{case_prefix}_mesh_overview.png",
        mesh_png_name,
        mesh_msh_name,
        f"{display_name} mesh",
    )

    return {
        "force_displacement_curve": str(curve_path),
        "mesh_overview": str(mesh_path),
        "damage_panel": str(panel_path),
    }
