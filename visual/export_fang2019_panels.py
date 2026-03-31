from __future__ import annotations

import argparse
import csv
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.tri as mtri
import meshio
import numpy as np


mpl.rcParams.update(
    {
        "font.family": "serif",
        "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
        "mathtext.fontset": "stix",
        "font.size": 18,
        "figure.dpi": 180,
    }
)


@dataclass(frozen=True)
class FangCase:
    tag: str
    label: str
    color: str
    line_style: str


FANG_CASES: Tuple[FangCase, ...] = (
    FangCase("H01E", r"$H = 0.1E$", "#E84040", "-"),
    FangCase("H02E", r"$H = 0.2E$", "#F5A623", "--"),
    FangCase("H05E", r"$H = 0.5E$", "#4A90D9", "-."),
)

SNAPSHOT_TAGS: Tuple[Tuple[str, str], ...] = (
    ("d020", r"$d_{\max}\approx0.20$"),
    ("d060", r"$d_{\max}\approx0.60$"),
    ("d090", r"$d_{\max}\approx0.90$"),
    ("final", "Final"),
)


def _triangle_cells(mesh: meshio.Mesh) -> np.ndarray:
    for cell_block in mesh.cells:
        if cell_block.type == "triangle":
            return np.asarray(cell_block.data, dtype=int)
    raise ValueError("No triangle cells found in VTU file.")


def _extract_field(mesh: meshio.Mesh, field_name: str) -> Tuple[np.ndarray, str]:
    if field_name in mesh.point_data:
        values = np.asarray(mesh.point_data[field_name]).reshape(-1)
        return values, "point"

    try:
        cell_dict = mesh.cell_data_dict[field_name]
    except Exception:
        cell_dict = {}
    if "triangle" in cell_dict:
        values = np.asarray(cell_dict["triangle"]).reshape(-1)
        return values, "cell"

    for idx, cell_block in enumerate(mesh.cells):
        if cell_block.type != "triangle":
            continue
        if idx < len(mesh.cell_data.get(field_name, [])):
            values = np.asarray(mesh.cell_data[field_name][idx]).reshape(-1)
            return values, "cell"

    raise KeyError(f"Field not found in VTU: {field_name}")


def _plot_scalar(ax, mesh: meshio.Mesh, field_name: str, cmap: str, vmin: float, vmax: float) -> None:
    points = np.asarray(mesh.points[:, :2], dtype=float)
    triangles = _triangle_cells(mesh)
    triangulation = mtri.Triangulation(points[:, 0], points[:, 1], triangles)
    values, location = _extract_field(mesh, field_name)

    if location == "point":
        artist = ax.tripcolor(triangulation, values, shading="gouraud", cmap=cmap, vmin=vmin, vmax=vmax)
    else:
        artist = ax.tripcolor(triangulation, facecolors=values, shading="flat", cmap=cmap, vmin=vmin, vmax=vmax)

    ax.set_aspect("equal")
    ax.set_xlim(-0.5, 18.5)
    ax.set_ylim(15.0, 35.5)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_frame_on(True)
    return artist


def _find_snapshot(case_dir: Path, tag: str) -> Path:
    if tag == "final":
        path = case_dir / "result_final.vtu"
        if path.exists():
            return path
    matches = sorted(case_dir.glob(f"result_{tag}_*.vtu"))
    if not matches:
        raise FileNotFoundError(f"Missing Fang snapshot: {case_dir} / {tag}")
    return matches[-1]


def build_fang_damage_panel(native_output_dir: Path, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(len(FANG_CASES), len(SNAPSHOT_TAGS), figsize=(14, 12))

    for row_index, case in enumerate(FANG_CASES):
        case_dir = native_output_dir / case.tag
        for col_index, (tag, title) in enumerate(SNAPSHOT_TAGS):
            ax = axes[row_index, col_index]
            mesh = meshio.read(_find_snapshot(case_dir, tag))
            artist = _plot_scalar(ax, mesh, "d", "turbo", 0.0, 1.0)
            if row_index == 0:
                ax.set_title(title)
            if col_index == 0:
                ax.set_ylabel(case.label)

    cbar = fig.colorbar(artist, ax=axes, shrink=0.92, pad=0.02)
    cbar.set_label("Damage d")
    fig.suptitle("Fang 2019 damage milestones", y=0.995)
    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    return output_path


def build_fang_epspeq_panel(native_output_dir: Path, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    epspeq_max = 0.0
    cached_meshes: Dict[Tuple[str, str], meshio.Mesh] = {}
    for case in FANG_CASES:
        case_dir = native_output_dir / case.tag
        for tag, _title in SNAPSHOT_TAGS:
            mesh = meshio.read(_find_snapshot(case_dir, tag))
            cached_meshes[(case.tag, tag)] = mesh
            values, _ = _extract_field(mesh, "epspeq")
            epspeq_max = max(epspeq_max, float(np.max(values)))

    fig, axes = plt.subplots(len(FANG_CASES), len(SNAPSHOT_TAGS), figsize=(14, 12))
    for row_index, case in enumerate(FANG_CASES):
        for col_index, (tag, title) in enumerate(SNAPSHOT_TAGS):
            ax = axes[row_index, col_index]
            artist = _plot_scalar(ax, cached_meshes[(case.tag, tag)], "epspeq", "plasma", 0.0, epspeq_max or 1.0)
            if row_index == 0:
                ax.set_title(title)
            if col_index == 0:
                ax.set_ylabel(case.label)

    cbar = fig.colorbar(artist, ax=axes, shrink=0.92, pad=0.02)
    cbar.set_label(r"Equivalent plastic strain $\bar{\varepsilon}^p$")
    fig.suptitle("Fang 2019 equivalent plastic strain milestones", y=0.995)
    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    return output_path


def build_fang_force_displacement(native_output_dir: Path, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(9.0, 6.2))
    milestone_specs = (
        (0.20, "o"),
        (0.60, "s"),
        (0.90, "^"),
    )

    for case in FANG_CASES:
        csv_path = native_output_dir / case.tag / f"force_displacement_{case.tag}.csv"
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))

        u_vals = np.array([float(row["u_mm"]) for row in rows], dtype=float)
        f_vals = np.array([float(row["F_kN"]) for row in rows], dtype=float)
        d_vals = np.array([float(row["d_max"]) for row in rows], dtype=float)

        ax.plot(u_vals, f_vals, linewidth=2.2, color=case.color, linestyle=case.line_style, label=case.label)
        for target_d, marker in milestone_specs:
            idx = int(np.argmin(np.abs(d_vals - target_d)))
            ax.plot(
                u_vals[idx],
                f_vals[idx],
                marker=marker,
                linestyle="None",
                color=case.color,
                markersize=8.0,
                markeredgecolor="black",
                markeredgewidth=0.8,
            )

    ax.grid(True, alpha=0.3)
    ax.set_xlabel("Displacement u (mm)")
    ax.set_ylabel("Force F (kN)")
    ax.set_title("Fang 2019 force-displacement comparison")
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    return output_path


def export_fang2019_panels(native_output_dir: Path, output_dir: Path) -> Dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    curve_source = native_output_dir / "F_u_curve_scan.png"
    curve_target = output_dir / "fang_force_displacement_comparison.png"
    if curve_source.exists():
        shutil.copy2(curve_source, curve_target)
    else:
        build_fang_force_displacement(native_output_dir, curve_target)

    damage_path = build_fang_damage_panel(native_output_dir, output_dir / "fang_damage_panel.png")
    epspeq_path = build_fang_epspeq_panel(native_output_dir, output_dir / "fang_epspeq_panel.png")

    return {
        "damage_panel": str(damage_path),
        "epspeq_panel": str(epspeq_path),
        "force_displacement_comparison": str(curve_target),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Fang2019 panel figures.")
    parser.add_argument("native_output_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    outputs = export_fang2019_panels(args.native_output_dir, args.output_dir)
    for key, value in outputs.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
