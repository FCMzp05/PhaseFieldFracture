from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib as mpl

mpl.use("Agg")
import matplotlib.pyplot as plt
import meshio
import numpy as np


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from visual.gui_case_exporters import (
    _compute_protocol_von_mises,
    _configure_vertical_colorbar,
    _merged_boundary_loops,
    _scalar_field,
    _triangulation,
    _vector_field,
)


def _geometry_payload(mesh: meshio.Mesh):
    points, cells, triangulation = _triangulation(mesh)
    xmin, ymin = points.min(axis=0)
    xmax, ymax = points.max(axis=0)
    padx = max(0.02 * (xmax - xmin), 1.0e-3)
    pady = max(0.02 * (ymax - ymin), 1.0e-3)
    return {
        "points": points,
        "cells": cells,
        "triangulation": triangulation,
        "boundary_loops": _merged_boundary_loops(points, cells),
        "xlim": (xmin - padx, xmax + padx),
        "ylim": (ymin - pady, ymax + pady),
    }


def _field_payload(
    mesh: meshio.Mesh,
    field: str,
    young_modulus: float,
    poisson_ratio: float,
    geometry: dict[str, object],
):
    if field == "damage":
        values = _scalar_field(mesh, "d")
        return values, plt.get_cmap("turbo"), mpl.colors.Normalize(0.0, 1.0), r"$d$"
    if field == "displacement":
        values = np.linalg.norm(_vector_field(mesh, "uh"), axis=1)
        finite_values = values[np.isfinite(values)]
        vmax = float(np.max(finite_values)) if finite_values.size else 1.0e-12
        return values, plt.get_cmap("viridis"), mpl.colors.Normalize(0.0, max(vmax, 1.0e-12)), "mm"
    if field == "von_mises":
        points = np.asarray(geometry["points"], dtype=float)
        cells = np.asarray(geometry["cells"], dtype=int)
        damage = _scalar_field(mesh, "d")
        displacement = _vector_field(mesh, "uh")
        values = _compute_protocol_von_mises(points, cells, displacement, damage, young_modulus, poisson_ratio)
        finite_values = values[np.isfinite(values)]
        vmax = float(np.percentile(finite_values, 98.0)) if finite_values.size else 1.0e-12
        return values, plt.get_cmap("plasma"), mpl.colors.Normalize(0.0, max(vmax, 1.0e-12)), "MPa"
    raise ValueError(f"Unsupported field: {field}")


def _render_preview(
    mesh: meshio.Mesh,
    geometry: dict[str, object],
    field: str,
    output_path: Path,
    young_modulus: float,
    poisson_ratio: float,
) -> None:
    values, cmap, norm, colorbar_title = _field_payload(mesh, field, young_modulus, poisson_ratio, geometry)
    triangulation = geometry["triangulation"]

    figure = plt.figure(figsize=(7.6, 5.8), dpi=200)
    figure.patch.set_facecolor("white")
    axis = figure.add_axes([0.055, 0.08, 0.79, 0.84])
    axis.set_facecolor("white")

    axis.tripcolor(triangulation, values, shading="gouraud", cmap=cmap, norm=norm, rasterized=True)

    for index, loop in enumerate(geometry["boundary_loops"]):
        closed = np.vstack([loop, loop[0]])
        axis.plot(
            closed[:, 0],
            closed[:, 1],
            color="black",
            linewidth=2.6 if index == 0 else 1.3,
            solid_capstyle="round",
            solid_joinstyle="round",
            zorder=5,
        )

    axis.set_xlim(*geometry["xlim"])
    axis.set_ylim(*geometry["ylim"])
    axis.set_aspect("equal")
    axis.axis("off")

    colorbar_axis = figure.add_axes([0.865, 0.08, 0.03, 0.84])
    colorbar = figure.colorbar(mpl.cm.ScalarMappable(norm=norm, cmap=cmap), cax=colorbar_axis)
    _configure_vertical_colorbar(colorbar, norm, colorbar_title)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, bbox_inches="tight", facecolor="white")
    plt.close(figure)


def render_previews(
    input_path: Path,
    outputs: dict[str, Path],
    young_modulus: float,
    poisson_ratio: float,
) -> None:
    if not outputs:
        raise ValueError("At least one preview output must be requested.")
    mesh = meshio.read(input_path)
    geometry = _geometry_payload(mesh)
    for field, output_path in outputs.items():
        _render_preview(mesh, geometry, field, output_path, young_modulus, poisson_ratio)


def render_preview(input_path: Path, field: str, output_path: Path, young_modulus: float, poisson_ratio: float) -> None:
    render_previews(input_path, {field: output_path}, young_modulus, poisson_ratio)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render GUI live preview PNG from VTU data.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--field", choices=("damage", "displacement", "von_mises"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--damage-output", type=Path)
    parser.add_argument("--displacement-output", type=Path)
    parser.add_argument("--von-mises-output", type=Path)
    parser.add_argument("--young-modulus", type=float, default=210950.0)
    parser.add_argument("--poisson-ratio", type=float, default=0.3)
    args = parser.parse_args()

    outputs: dict[str, Path] = {}
    if args.damage_output is not None:
        outputs["damage"] = args.damage_output
    if args.displacement_output is not None:
        outputs["displacement"] = args.displacement_output
    if args.von_mises_output is not None:
        outputs["von_mises"] = args.von_mises_output
    if not outputs:
        if args.field is None or args.output is None:
            parser.error("Either provide --field/--output or at least one batch output argument.")
        outputs[args.field] = args.output

    render_previews(args.input, outputs, args.young_modulus, args.poisson_ratio)


if __name__ == "__main__":
    main()
