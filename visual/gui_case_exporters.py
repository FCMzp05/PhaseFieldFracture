from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

import matplotlib as mpl

mpl.use("Agg")
import matplotlib.collections as mc
import matplotlib.pyplot as plt
import matplotlib.tri as mtri
import meshio
import numpy as np
from matplotlib.gridspec import GridSpec
from matplotlib.patches import Rectangle


mpl.rcParams.update(
    {
        "font.family": "serif",
        "font.serif": ["Times New Roman", "Times", "Nimbus Roman No9 L", "DejaVu Serif"],
        "mathtext.fontset": "stix",
        "font.size": 18,
        "figure.dpi": 200,
        "xtick.direction": "in",
        "ytick.direction": "in",
    }
)

TRIANGLE_CELL_TYPES = ("triangle", "triangle6")
MESH_FACE_COLOR = "#B8D4E8"
MESH_EDGE_COLOR = "#5A8FAA"
PANEL_BORDER_COLOR = "black"
CURVE_COLORS = ("#1f4f82", "#b4473c", "#2d7d6e", "#ad7a1f", "#7a5c97")


def _load_runtime_params(runtime_params_path: Path | None) -> dict[str, object]:
    if runtime_params_path is None or not runtime_params_path.exists():
        return {}
    try:
        payload = json.loads(runtime_params_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if isinstance(payload, dict) and isinstance(payload.get("params"), dict):
        return dict(payload["params"])
    if isinstance(payload, dict):
        return dict(payload)
    return {}


def _natural_sort_key(path: Path):
    numbers = tuple(int(token) for token in re.findall(r"\d+", path.stem))
    return numbers, path.name


def _sorted_matches(base_dir: Path, pattern: str) -> list[Path]:
    return sorted((path for path in base_dir.glob(pattern) if path.is_file()), key=_natural_sort_key)


def _first_existing(base_dir: Path, *patterns: str) -> Path | None:
    for pattern in patterns:
        matches = _sorted_matches(base_dir, pattern)
        if matches:
            return matches[0]
    return None


def _unique_paths(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    ordered: list[Path] = []
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        ordered.append(path)
    return ordered


def _select_evenly_spaced(paths: list[Path], count: int) -> list[Path]:
    if count <= 0 or not paths:
        return []
    if len(paths) <= count:
        return paths
    indices = np.linspace(0, len(paths) - 1, count)
    selected = [paths[int(round(index))] for index in indices]
    return _unique_paths(selected)


def _read_csv_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _triangle_block(mesh: meshio.Mesh):
    for block_index, cell_block in enumerate(mesh.cells):
        if cell_block.type in TRIANGLE_CELL_TYPES:
            cells = np.asarray(cell_block.data, dtype=int)
            if cells.ndim != 2 or cells.shape[1] < 3:
                continue
            return block_index, cells[:, :3]
    raise KeyError("No triangle cells found in mesh.")


def _triangle_cells(mesh: meshio.Mesh) -> np.ndarray:
    _, cells = _triangle_block(mesh)
    return cells


def _merged_points_and_cells(
    coords: np.ndarray,
    cells: np.ndarray,
    tol: float = 1.0e-10,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    quantized = np.round(coords / tol).astype(np.int64)
    representative_by_key: dict[tuple[int, int], int] = {}
    remap = np.empty(len(coords), dtype=int)
    for index, key in enumerate(quantized):
        tuple_key = (int(key[0]), int(key[1]))
        representative = representative_by_key.setdefault(tuple_key, index)
        remap[index] = representative

    unique_ids, inverse = np.unique(remap, return_inverse=True)
    merged_coords = coords[unique_ids]
    merged_cells = inverse[cells]
    if merged_cells.size:
        merged_cells = np.asarray(
            [tri for tri in merged_cells if len({int(tri[0]), int(tri[1]), int(tri[2])}) == 3],
            dtype=int,
        )
    else:
        merged_cells = np.empty((0, 3), dtype=int)
    return merged_coords, merged_cells, inverse


def _merge_point_values(values: np.ndarray, inverse: np.ndarray, merged_size: int) -> np.ndarray:
    values_2d = values if values.ndim == 2 else values[:, None]
    merged_values = np.zeros((merged_size, values_2d.shape[1]), dtype=float)
    counts = np.zeros(merged_size, dtype=float)
    np.add.at(merged_values, inverse, values_2d)
    np.add.at(counts, inverse, 1.0)
    merged_values /= np.maximum(counts[:, None], 1.0)
    return merged_values


def _align_point_field_by_coordinates(
    source_points: np.ndarray,
    source_values: np.ndarray,
    target_points: np.ndarray,
    tol: float = 1.0e-10,
) -> np.ndarray:
    source_values_2d = source_values if source_values.ndim == 2 else source_values[:, None]
    source_index_by_key = {
        tuple(np.round(point / tol).astype(np.int64)): index for index, point in enumerate(source_points)
    }
    aligned = np.zeros((len(target_points), source_values_2d.shape[1]), dtype=float)
    for index, point in enumerate(target_points):
        key = tuple(np.round(point / tol).astype(np.int64))
        source_index = source_index_by_key.get(key)
        if source_index is None:
            raise KeyError(f"Target point {point.tolist()} is missing in source field alignment.")
        aligned[index] = source_values_2d[source_index]
    if source_values.ndim == 1:
        return aligned[:, 0]
    return aligned


def _field_to_points(mesh: meshio.Mesh, name: str, *, merge_duplicates: bool = True) -> np.ndarray:
    if name in mesh.point_data:
        values = np.asarray(mesh.point_data[name], dtype=float)
        if values.ndim == 1:
            values = values[:, None]
        raw_values = values
    else:
        block_index, cells = _triangle_block(mesh)
        if name not in mesh.cell_data or block_index >= len(mesh.cell_data[name]):
            raise KeyError(f"Field '{name}' not found in mesh.")

        values = np.asarray(mesh.cell_data[name][block_index], dtype=float)
        if values.ndim == 1:
            values = values[:, None]

        raw_values = np.zeros((len(mesh.points), values.shape[1]), dtype=float)
        weights = np.zeros(len(mesh.points), dtype=float)
        for local_node in range(3):
            np.add.at(raw_values, cells[:, local_node], values)
            np.add.at(weights, cells[:, local_node], 1.0)
        raw_values /= np.maximum(weights[:, None], 1.0)

    if not merge_duplicates:
        return raw_values

    coords = np.asarray(mesh.points[:, :2], dtype=float)
    cells = _triangle_cells(mesh)
    merged_coords, _, inverse = _merged_points_and_cells(coords, cells)
    return _merge_point_values(raw_values, inverse, len(merged_coords))


def _scalar_field(mesh: meshio.Mesh, name: str) -> np.ndarray:
    values = _field_to_points(mesh, name)
    if values.shape[1] == 1:
        return values[:, 0]
    raise ValueError(f"Field '{name}' is not scalar.")


def _vector_field(mesh: meshio.Mesh, name: str, min_cols: int = 2) -> np.ndarray:
    values = _field_to_points(mesh, name)
    if values.shape[1] < min_cols:
        raise ValueError(f"Field '{name}' does not have {min_cols} components.")
    return values[:, :min_cols]


def _triangulation(
    mesh: meshio.Mesh,
    *,
    xlim: tuple[float, float] | None = None,
    ylim: tuple[float, float] | None = None,
    triangle_filter=None,
):
    raw_points = np.asarray(mesh.points[:, :2], dtype=float)
    raw_cells = _triangle_cells(mesh)
    points, cells, _ = _merged_points_and_cells(raw_points, raw_cells)
    mask = np.ones(len(cells), dtype=bool)
    if xlim is not None or ylim is not None:
        cx = points[cells, 0].mean(axis=1)
        cy = points[cells, 1].mean(axis=1)
        if xlim is not None:
            mask &= (cx >= xlim[0]) & (cx <= xlim[1])
        if ylim is not None:
            mask &= (cy >= ylim[0]) & (cy <= ylim[1])
    if triangle_filter is not None:
        mask &= triangle_filter(points, cells)
    cells = cells[mask]
    if len(cells) == 0:
        raise ValueError("No triangles remain after filtering.")
    return points, cells, mtri.Triangulation(points[:, 0], points[:, 1], triangles=cells)


def _edge_key(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


def _polygon_area(points: np.ndarray) -> float:
    x = points[:, 0]
    y = points[:, 1]
    return 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def _merged_boundary_loops(coords: np.ndarray, cells: np.ndarray, tol: float = 1.0e-10) -> list[np.ndarray]:
    merged_coords, merged_cells, _ = _merged_points_and_cells(coords, cells, tol=tol)
    if len(merged_cells) == 0:
        return []

    edge_count: dict[tuple[int, int], int] = defaultdict(int)
    for tri in merged_cells:
        for local_node in range(3):
            edge_count[_edge_key(int(tri[local_node]), int(tri[(local_node + 1) % 3]))] += 1

    boundary_edges = [edge for edge, count in edge_count.items() if count == 1]
    adjacency: dict[int, list[int]] = defaultdict(list)
    for a, b in boundary_edges:
        adjacency[a].append(b)
        adjacency[b].append(a)

    unused = set(boundary_edges)
    loops: list[np.ndarray] = []
    while unused:
        start, current = min(unused)
        loop_nodes = [start, current]
        unused.remove((start, current))
        previous = start
        safety = 0
        while safety < len(boundary_edges) + 5:
            safety += 1
            candidates = [
                node for node in sorted(adjacency[current]) if node != previous and _edge_key(current, node) in unused
            ]
            if not candidates:
                closing_edge = _edge_key(current, loop_nodes[0])
                if closing_edge in unused:
                    unused.remove(closing_edge)
                break
            next_node = candidates[0]
            loop_nodes.append(next_node)
            unused.remove(_edge_key(current, next_node))
            previous, current = current, next_node
            if current == loop_nodes[0]:
                loop_nodes.pop()
                break
        if len(loop_nodes) >= 3:
            loop = merged_coords[np.asarray(loop_nodes, dtype=int)]
            if _polygon_area(loop) > 1.0e-12:
                loops.append(loop)

    loops.sort(key=_polygon_area, reverse=True)
    return loops


def _draw_mesh_overview(ax, mesh_path: Path, *, mesh_linewidth: float = 0.25):
    mesh = meshio.read(mesh_path)
    coords, triangles, _ = _triangulation(mesh)

    ax.add_collection(mc.PolyCollection(coords[triangles], facecolor=MESH_FACE_COLOR, edgecolor="none", zorder=1))
    ax.triplot(coords[:, 0], coords[:, 1], triangles, color=MESH_EDGE_COLOR, linewidth=mesh_linewidth, zorder=2)

    loops = _merged_boundary_loops(coords, triangles)
    for index, loop in enumerate(loops):
        closed = np.vstack([loop, loop[0]])
        linewidth = 2.6 if index == 0 else 1.3
        ax.plot(
            closed[:, 0],
            closed[:, 1],
            color="black",
            linewidth=linewidth,
            solid_capstyle="round",
            solid_joinstyle="round",
            zorder=3,
        )

    xmin, ymin = coords.min(axis=0)
    xmax, ymax = coords.max(axis=0)
    padx = max(0.02 * (xmax - xmin), 1.0e-3)
    pady = max(0.02 * (ymax - ymin), 1.0e-3)
    ax.set_xlim(xmin - padx, xmax + padx)
    ax.set_ylim(ymin - pady, ymax + pady)
    ax.set_aspect("equal")
    ax.axis("off")


def _save_figure(fig: plt.Figure, output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    return output_path


def _bounds_from_crop_or_tri(
    xlim: tuple[float, float] | None,
    ylim: tuple[float, float] | None,
    tri: mtri.Triangulation,
):
    if xlim is not None and ylim is not None:
        return xlim, ylim
    tri_x = np.asarray(tri.x, dtype=float)
    tri_y = np.asarray(tri.y, dtype=float)
    x_bounds = (float(np.min(tri_x)), float(np.max(tri_x)))
    y_bounds = (float(np.min(tri_y)), float(np.max(tri_y)))
    return xlim or x_bounds, ylim or y_bounds


def _colorbar_formatter(norm: mpl.colors.Normalize):
    span = float(norm.vmax - norm.vmin)
    if span >= 20.0:
        decimals = 0
    elif span >= 2.0:
        decimals = 1
    elif span >= 0.2:
        decimals = 2
    else:
        decimals = 3
    return mpl.ticker.FuncFormatter(lambda value, _pos: f"{value:.{decimals}f}")


def _configure_vertical_colorbar(cb, norm: mpl.colors.Normalize, title: str):
    cb.set_ticks(np.linspace(norm.vmin, norm.vmax, 5))
    cb.ax.yaxis.set_major_formatter(_colorbar_formatter(norm))
    cb.ax.tick_params(labelsize=18)
    cb.ax.set_title(title, fontsize=22, pad=8)


def _style_curve_axes(ax, xlabel: str, ylabel: str, title: str):
    ax.set_facecolor("white")
    ax.grid(True, color="#c7d3de", linewidth=1.0, alpha=0.85)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.tick_params(direction="in", colors="#1f3347")
    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_color("#2b435b")
        spine.set_linewidth(1.1)


def _rounded_percentile_max(values, percentile: float, *, floor: float = 0.0, round_to: float | None = None) -> float:
    array = np.asarray(values, dtype=float).ravel()
    array = array[np.isfinite(array) & (array > floor)]
    if array.size == 0:
        base_value = 1.0
    else:
        base_value = float(np.percentile(array, percentile))
    if round_to is not None and round_to > 0.0:
        base_value = float(np.ceil(base_value / round_to) * round_to)
    return max(base_value, 1.0e-6)


def _extract_int_from_name(path: Path, token: str) -> int | None:
    match = re.search(rf"{token}(\d+)", path.stem)
    return int(match.group(1)) if match else None


def _compute_protocol_von_mises(
    points: np.ndarray,
    cells: np.ndarray,
    displacement: np.ndarray,
    damage: np.ndarray,
    young_modulus: float,
    poisson_ratio: float,
) -> np.ndarray:
    lam = young_modulus * poisson_ratio / ((1.0 + poisson_ratio) * (1.0 - 2.0 * poisson_ratio))
    shear = young_modulus / (2.0 * (1.0 + poisson_ratio))

    p1 = points[cells[:, 0]]
    p2 = points[cells[:, 1]]
    p3 = points[cells[:, 2]]
    u1 = displacement[cells[:, 0]]
    u2 = displacement[cells[:, 1]]
    u3 = displacement[cells[:, 2]]

    twice_area = (p2[:, 0] - p1[:, 0]) * (p3[:, 1] - p1[:, 1]) - (p3[:, 0] - p1[:, 0]) * (p2[:, 1] - p1[:, 1])
    twice_area = np.where(np.abs(twice_area) < 1.0e-14, np.sign(twice_area) * 1.0e-14 + 1.0e-14, twice_area)

    d_n1_dx = (p2[:, 1] - p3[:, 1]) / twice_area
    d_n1_dy = (p3[:, 0] - p2[:, 0]) / twice_area
    d_n2_dx = (p3[:, 1] - p1[:, 1]) / twice_area
    d_n2_dy = (p1[:, 0] - p3[:, 0]) / twice_area
    d_n3_dx = (p1[:, 1] - p2[:, 1]) / twice_area
    d_n3_dy = (p2[:, 0] - p1[:, 0]) / twice_area

    exx = u1[:, 0] * d_n1_dx + u2[:, 0] * d_n2_dx + u3[:, 0] * d_n3_dx
    eyy = u1[:, 1] * d_n1_dy + u2[:, 1] * d_n2_dy + u3[:, 1] * d_n3_dy
    exy = 0.5 * (
        u1[:, 0] * d_n1_dy
        + u2[:, 0] * d_n2_dy
        + u3[:, 0] * d_n3_dy
        + u1[:, 1] * d_n1_dx
        + u2[:, 1] * d_n2_dx
        + u3[:, 1] * d_n3_dx
    )

    trace = exx + eyy
    s_xx = lam * trace + 2.0 * shear * exx
    s_yy = lam * trace + 2.0 * shear * eyy
    s_zz = lam * trace
    s_xy = 2.0 * shear * exy
    sigma_vm = np.sqrt(
        0.5 * ((s_xx - s_yy) ** 2 + (s_yy - s_zz) ** 2 + (s_zz - s_xx) ** 2) + 3.0 * s_xy**2
    )

    damage_cell = damage[cells].mean(axis=1)
    degraded_sigma = np.clip((1.0 - damage_cell) ** 2, 0.0, 1.0) * sigma_vm
    area = 0.5 * np.abs(twice_area)

    weighted = np.zeros(len(points), dtype=float)
    weights = np.zeros(len(points), dtype=float)
    for local_node in range(3):
        np.add.at(weighted, cells[:, local_node], degraded_sigma * area)
        np.add.at(weights, cells[:, local_node], area)
    return weighted / np.maximum(weights, 1.0e-30)


def _export_geometry_gallery(output_path: Path, title: str, items: list[tuple[str, Path]]):
    if not items:
        raise FileNotFoundError("No mesh files found for geometry export.")
    figure, axes = plt.subplots(1, len(items), figsize=(5.2 * len(items), 4.6))
    if len(items) == 1:
        axes = [axes]
    for ax, (label, mesh_path) in zip(axes, items):
        _draw_mesh_overview(ax, mesh_path)
        ax.set_title(label, fontsize=22, pad=8)
    figure.suptitle(title, y=0.995, fontsize=24)
    figure.tight_layout()
    return _save_figure(figure, output_path)


def _export_line_chart(
    output_path: Path,
    *,
    title: str,
    xlabel: str,
    ylabel: str,
    series: list[dict[str, object]],
    marker_points: list[dict[str, object]] | None = None,
):
    figure, ax = plt.subplots(figsize=(8.4, 5.6))
    for index, item in enumerate(series):
        x_values = np.asarray(item["x"], dtype=float)
        y_values = np.asarray(item["y"], dtype=float)
        color = str(item.get("color") or CURVE_COLORS[index % len(CURVE_COLORS)])
        linestyle = str(item.get("linestyle") or "-")
        linewidth = float(item.get("linewidth") or 2.4)
        label = str(item.get("label") or "")
        ax.plot(x_values, y_values, color=color, linestyle=linestyle, linewidth=linewidth, label=label)

    for marker in marker_points or []:
        x_value = float(marker["x"])
        y_value = float(marker["y"])
        ax.plot(
            x_value,
            y_value,
            marker=str(marker.get("marker") or "o"),
            color=str(marker.get("color") or "#1f4f82"),
            markersize=float(marker.get("markersize") or 8.0),
            markeredgecolor="black",
            markeredgewidth=0.8,
            linestyle="None",
        )
        label = str(marker.get("label") or "")
        if label:
            ax.annotate(
                label,
                (x_value, y_value),
                xytext=(8, 8),
                textcoords="offset points",
                fontsize=14,
                color="#102438",
            )

    _style_curve_axes(ax, xlabel, ylabel, title)
    if any(str(item.get("label") or "") for item in series):
        legend = ax.legend(loc="best")
        if legend is not None:
            legend.get_frame().set_facecolor("white")
            legend.get_frame().set_edgecolor("#c6d0da")
    figure.tight_layout()
    return _save_figure(figure, output_path)


def _export_protocol_panel(
    output_path: Path,
    *,
    snaps: list[dict[str, object]],
    col_titles: list[str],
    row_specs: list[tuple[str, str, mpl.colors.Normalize, str, str]],
    note_key: str,
    line_segment: tuple[tuple[float, float], tuple[float, float]] | None = None,
):
    n_rows = len(row_specs)
    n_cols = len(snaps)
    figure = plt.figure(figsize=(4.6 * n_cols + 1.5, 4.0 * n_rows + 0.8))
    grid = GridSpec(
        n_rows,
        n_cols,
        figure=figure,
        hspace=0.10,
        wspace=0.035,
        left=0.10,
        right=0.88,
        top=0.91,
        bottom=0.05,
    )
    axes = [[figure.add_subplot(grid[r, c]) for c in range(n_cols)] for r in range(n_rows)]

    for row_index, (field_key, cmap_name, norm, row_label, cbar_title) in enumerate(row_specs):
        cmap = plt.get_cmap(cmap_name)
        for col_index, snap in enumerate(snaps):
            ax = axes[row_index][col_index]
            ax.tripcolor(snap["tri"], snap[field_key], cmap=cmap, norm=norm, shading="gouraud", rasterized=True)
            if line_segment is not None:
                (x0, y0), (x1, y1) = line_segment
                ax.plot([x0, x1], [y0, y1], color="white", linewidth=1.4, solid_capstyle="round")
            ax.set_xlim(0.0, 1.0)
            ax.set_ylim(0.0, 1.0)
            ax.set_aspect("equal")
            ax.axis("off")
            ax.add_patch(
                Rectangle((0, 0), 1, 1, transform=ax.transAxes, fill=False, edgecolor=PANEL_BORDER_COLOR, linewidth=2.3, zorder=20)
            )
            ax.text(
                0.50,
                0.91,
                str(snap.get(note_key, "")),
                transform=ax.transAxes,
                ha="center",
                va="top",
                fontsize=22,
                color="white",
                zorder=25,
            )
            if row_index == 0 and col_index < len(col_titles):
                ax.set_title(col_titles[col_index], fontsize=20, pad=7)

        position = axes[row_index][0].get_position()
        figure.text(0.06, 0.5 * (position.y0 + position.y1), row_label, rotation=90, ha="center", va="center", fontsize=20)
        top_position = axes[row_index][-1].get_position()
        cax = figure.add_axes([top_position.x1 + 0.012, position.y0, 0.018, position.height])
        colorbar = figure.colorbar(mpl.cm.ScalarMappable(norm=norm, cmap=cmap), cax=cax)
        _configure_vertical_colorbar(colorbar, norm, cbar_title)

    return _save_figure(figure, output_path)


def _export_square_panel_2x2(
    output_path: Path,
    *,
    snaps: list[dict[str, object]],
    field_key: str,
    cmap_name: str,
    norm: mpl.colors.Normalize,
    cbar_title: str,
    title: str,
    xlim: tuple[float, float] | None = None,
    ylim: tuple[float, float] | None = None,
):
    figure, axes = plt.subplots(2, 2, figsize=(9.2, 7.6), gridspec_kw={"hspace": 0.08, "wspace": 0.04})
    cmap = plt.get_cmap(cmap_name)
    for axis in axes.ravel():
        axis.axis("off")

    for ax, snap in zip(axes.ravel(), snaps):
        ax.tripcolor(snap["tri"], snap[field_key], cmap=cmap, norm=norm, shading="gouraud", rasterized=True)
        if xlim is not None:
            ax.set_xlim(xlim)
        if ylim is not None:
            ax.set_ylim(ylim)
        ax.set_aspect("equal")
        ax.axis("off")
        note = str(snap.get("note") or "")
        if note:
            ax.text(0.5, 0.92, note, transform=ax.transAxes, ha="center", va="top", fontsize=18, color="white", zorder=15)

    figure.subplots_adjust(left=0.05, right=0.88, top=0.94, bottom=0.05)
    colorbar_axis = figure.add_axes([0.91, 0.10, 0.025, 0.80])
    colorbar = figure.colorbar(mpl.cm.ScalarMappable(norm=norm, cmap=cmap), cax=colorbar_axis)
    _configure_vertical_colorbar(colorbar, norm, cbar_title)
    figure.suptitle(title, y=0.99, fontsize=22)
    return _save_figure(figure, output_path)


def _export_scan_panel(
    output_path: Path,
    *,
    case_rows: list[dict[str, object]],
    field_key: str,
    cmap_name: str,
    norm: mpl.colors.Normalize,
    cbar_title: str,
    title: str,
    xlim: tuple[float, float] | None = None,
    ylim: tuple[float, float] | None = None,
    col_titles: list[str] | None = None,
):
    if not case_rows:
        raise FileNotFoundError("No case rows found for panel export.")
    first_tri = case_rows[0]["snaps"][0]["tri"]
    x_bounds, y_bounds = _bounds_from_crop_or_tri(xlim, ylim, first_tri)
    crop_w = max(x_bounds[1] - x_bounds[0], 1.0e-6)
    crop_h = max(y_bounds[1] - y_bounds[0], 1.0e-6)
    n_rows = len(case_rows)
    n_cols = max(len(row["snaps"]) for row in case_rows)

    cell_w = 3.4
    cell_h = cell_w * crop_h / crop_w
    l_pad, r_pad, t_pad, b_pad = 1.1, 1.0, 0.7, 0.25
    hspace, wspace = 0.08, 0.04
    fig_w = l_pad + n_cols * cell_w * (1.0 + wspace) + r_pad
    fig_h = t_pad + n_rows * cell_h * (1.0 + hspace) + b_pad
    figure = plt.figure(figsize=(fig_w, fig_h))
    left = l_pad / fig_w
    right = 1.0 - r_pad / fig_w
    bottom = b_pad / fig_h
    top = 1.0 - t_pad / fig_h
    grid = GridSpec(n_rows, n_cols, figure=figure, left=left, right=right, bottom=bottom, top=top, hspace=hspace, wspace=wspace)
    axes = [[figure.add_subplot(grid[r, c]) for c in range(n_cols)] for r in range(n_rows)]
    cmap = plt.get_cmap(cmap_name)

    for row_index, row in enumerate(case_rows):
        for col_index in range(n_cols):
            ax = axes[row_index][col_index]
            if col_index < len(row["snaps"]):
                snap = row["snaps"][col_index]
                ax.tripcolor(snap["tri"], snap[field_key], cmap=cmap, norm=norm, shading="gouraud", rasterized=True)
                note = str(snap.get("note") or "")
                if note:
                    ax.text(0.50, 0.91, note, transform=ax.transAxes, ha="center", va="top", fontsize=18, color="white", zorder=10)
            ax.set_xlim(x_bounds)
            ax.set_ylim(y_bounds)
            ax.set_aspect("equal")
            ax.axis("off")
            ax.add_patch(
                Rectangle((0, 0), 1, 1, transform=ax.transAxes, fill=False, edgecolor=PANEL_BORDER_COLOR, linewidth=1.8, zorder=20)
            )
            if row_index == 0 and col_titles is not None and col_index < len(col_titles):
                ax.set_title(col_titles[col_index], fontsize=20, pad=7)
        position = axes[row_index][0].get_position()
        figure.text(left - 0.015, 0.5 * (position.y0 + position.y1), str(row["label"]), ha="right", va="center", rotation=90, fontsize=20)

    position_top = axes[0][-1].get_position()
    position_bottom = axes[-1][-1].get_position()
    colorbar_axis = figure.add_axes([position_top.x1 + 0.012, position_bottom.y0, 0.018, position_top.y1 - position_bottom.y0])
    colorbar = figure.colorbar(mpl.cm.ScalarMappable(norm=norm, cmap=cmap), cax=colorbar_axis)
    _configure_vertical_colorbar(colorbar, norm, cbar_title)
    figure.suptitle(title, y=0.995, fontsize=22)
    return _save_figure(figure, output_path)


def _protocol_curve_points(csv_path: Path, step_numbers: list[int | None], *, x_scale: float) -> tuple[list[float], list[float], list[dict[str, object]]]:
    rows = _read_csv_rows(csv_path)
    x_values: list[float] = []
    y_values: list[float] = []
    rows_by_step: dict[int, tuple[float, float]] = {}
    for row in rows:
        try:
            step = int(float(row["step"]))
            x_value = float(row["u_mm"]) * x_scale
            y_value = float(row["F_kN"])
        except (KeyError, TypeError, ValueError):
            continue
        x_values.append(x_value)
        y_values.append(y_value)
        rows_by_step[step] = (x_value, y_value)

    markers: list[dict[str, object]] = []
    marker_labels = ("A", "B", "C")
    marker_shapes = ("o", "s", "^")
    for index, step in enumerate(step_numbers):
        if step is None or step not in rows_by_step or index >= len(marker_labels):
            continue
        marker_x, marker_y = rows_by_step[step]
        markers.append(
            {
                "x": marker_x,
                "y": marker_y,
                "label": marker_labels[index],
                "marker": marker_shapes[index],
                "color": CURVE_COLORS[min(index, len(CURVE_COLORS) - 1)],
            }
        )
    return x_values, y_values, markers


def export_sent_panels(
    native_output_dir: Path,
    output_dir: Path,
    runtime_params_path: Path | None = None,
) -> dict[str, str]:
    params = _load_runtime_params(runtime_params_path)
    young_modulus = float(params.get("E", 210950.0))
    poisson_ratio = float(params.get("nu", 0.3))

    mesh_path = _first_existing(native_output_dir, "mesh_SENT.msh")
    curve_csv = _first_existing(native_output_dir, "F_u_curve_SENT.csv", "F_u_curve.csv")
    onset_path = _first_existing(native_output_dir, "result_onset*.vtu")
    drop_paths = _sorted_matches(native_output_dir, "result_drop*.vtu")
    final_path = _first_existing(native_output_dir, "result_final*.vtu")
    snap_paths = _unique_paths([path for path in [onset_path, drop_paths[-1] if drop_paths else None, final_path] if path is not None])
    if len(snap_paths) < 3:
        snap_paths = _select_evenly_spaced(_sorted_matches(native_output_dir, "result_*.vtu"), 3)
    if not snap_paths:
        raise FileNotFoundError(f"Missing SENT VTK payload in {native_output_dir}")

    snaps: list[dict[str, object]] = []
    marker_steps: list[int | None] = []
    for path in snap_paths:
        mesh = meshio.read(path)
        points, cells, tri = _triangulation(mesh)
        damage = _scalar_field(mesh, "d")
        displacement = _vector_field(mesh, "uh", 2)
        von_mises = _compute_protocol_von_mises(points, cells, displacement, damage, young_modulus, poisson_ratio)
        displacement_um = float(np.nanmax(displacement[:, 1]) * 1.0e3)
        snaps.append({"tri": tri, "d": damage, "svm": von_mises, "note": rf"$u_y={displacement_um:.2f}\ \mu m$"})
        marker_steps.append(_extract_int_from_name(path, "step"))

    stress_max = _rounded_percentile_max(np.concatenate([snap["svm"] for snap in snaps]), 98.0, floor=10.0, round_to=200.0)
    panel_path = _export_protocol_panel(
        output_dir / "sent_field_panel.png",
        snaps=snaps,
        col_titles=[
            "Point A (Onset)",
            "Point B (Post-Peak)",
            "Point C (Final)",
        ][: len(snaps)],
        row_specs=[
            ("d", "turbo", mpl.colors.Normalize(0.0, 1.0), r"Damage field $d$", "$d$"),
            ("svm", "plasma", mpl.colors.Normalize(0.0, stress_max), r"Von Mises stress $\sigma_\mathrm{vm}$", "MPa"),
        ],
        note_key="note",
        line_segment=((0.0, 0.5), (0.5, 0.5)),
    )

    outputs: dict[str, str] = {}
    if mesh_path is not None:
        outputs["mesh_overview"] = str(_export_geometry_gallery(output_dir / "sent_mesh_overview.png", "SENT mesh overview", [("SENT", mesh_path)]))
    if curve_csv is not None:
        x_values, y_values, markers = _protocol_curve_points(curve_csv, marker_steps, x_scale=1.0e3)
        outputs["force_displacement_curve"] = str(
            _export_line_chart(
                output_dir / "sent_force_curve.png",
                title="SENT force-displacement",
                xlabel="Displacement u (μm)",
                ylabel="Force F (kN)",
                series=[{"x": x_values, "y": y_values, "color": CURVE_COLORS[0]}],
                marker_points=markers,
            )
        )
    outputs["field_panel"] = str(panel_path)
    return outputs


def export_sens_panels(
    native_output_dir: Path,
    output_dir: Path,
    runtime_params_path: Path | None = None,
) -> dict[str, str]:
    params = _load_runtime_params(runtime_params_path)
    young_modulus = float(params.get("E", 210950.0))
    poisson_ratio = float(params.get("nu", 0.3))

    mesh_path = _first_existing(native_output_dir, "mesh_SENS.msh")
    curve_csv = _first_existing(native_output_dir, "F_u_curve_SENS.csv", "F_u_curve.csv")
    onset_path = _first_existing(native_output_dir, "result_onset*.vtu")
    drop_paths = _sorted_matches(native_output_dir, "result_drop*.vtu")
    final_path = _first_existing(native_output_dir, "result_final*.vtu")
    snap_paths = _unique_paths([path for path in [onset_path, drop_paths[-1] if drop_paths else None, final_path] if path is not None])
    if len(snap_paths) < 3:
        snap_paths = _select_evenly_spaced(_sorted_matches(native_output_dir, "result_*.vtu"), 3)
    if not snap_paths:
        raise FileNotFoundError(f"Missing SENS VTK payload in {native_output_dir}")

    snaps: list[dict[str, object]] = []
    marker_steps: list[int | None] = []
    for path in snap_paths:
        mesh = meshio.read(path)
        points, cells, tri = _triangulation(mesh)
        damage = _scalar_field(mesh, "d")
        displacement = _vector_field(mesh, "uh", 2)
        von_mises = _compute_protocol_von_mises(points, cells, displacement, damage, young_modulus, poisson_ratio)
        displacement_um = float(np.nanmax(displacement[:, 0]) * 1.0e3)
        snaps.append({"tri": tri, "d": damage, "svm": von_mises, "note": rf"$u_x={displacement_um:.2f}\ \mu m$"})
        marker_steps.append(_extract_int_from_name(path, "step"))

    stress_max = _rounded_percentile_max(np.concatenate([snap["svm"] for snap in snaps]), 98.0, floor=10.0, round_to=200.0)
    panel_path = _export_protocol_panel(
        output_dir / "sens_field_panel.png",
        snaps=snaps,
        col_titles=[
            "Point A (Onset)",
            "Point B (Post-Peak)",
            "Point C (Final)",
        ][: len(snaps)],
        row_specs=[
            ("d", "turbo", mpl.colors.Normalize(0.0, 1.0), r"Damage field $d$", "$d$"),
            ("svm", "plasma", mpl.colors.Normalize(0.0, stress_max), r"Von Mises stress $\sigma_\mathrm{vm}$", "MPa"),
        ],
        note_key="note",
        line_segment=((0.0, 0.5), (0.5, 0.5)),
    )

    outputs: dict[str, str] = {}
    if mesh_path is not None:
        outputs["mesh_overview"] = str(_export_geometry_gallery(output_dir / "sens_mesh_overview.png", "SENS mesh overview", [("SENS", mesh_path)]))
    if curve_csv is not None:
        x_values, y_values, markers = _protocol_curve_points(curve_csv, marker_steps, x_scale=1.0e3)
        outputs["force_displacement_curve"] = str(
            _export_line_chart(
                output_dir / "sens_force_curve.png",
                title="SENS force-displacement",
                xlabel="Shear displacement u (μm)",
                ylabel="Force F (kN)",
                series=[{"x": x_values, "y": y_values, "color": CURVE_COLORS[1]}],
                marker_points=markers,
            )
        )
    outputs["field_panel"] = str(panel_path)
    return outputs


def export_tpb_panels(
    native_output_dir: Path,
    output_dir: Path,
    runtime_params_path: Path | None = None,
) -> dict[str, str]:
    del runtime_params_path
    mesh_path = _first_existing(native_output_dir, "BeamWithNotchSymThreePtBending.msh")
    case_dir = native_output_dir / "AT1" if (native_output_dir / "AT1").is_dir() else native_output_dir
    cycle_paths = _sorted_matches(case_dir, "cycle_*.vtu")
    history_csv = _first_existing(case_dir, "history.csv")
    if not cycle_paths:
        raise FileNotFoundError(f"Missing TPB cycle VTK files in {case_dir}")

    sample_mesh = meshio.read(cycle_paths[0])
    sample_points = np.asarray(sample_mesh.points[:, :2], dtype=float)
    xmin, ymin = sample_points.min(axis=0)
    xmax, ymax = sample_points.max(axis=0)
    height = ymax - ymin
    x_center = 0.5 * (xmin + xmax)
    crop_x = (x_center - 0.5 * height, x_center + 0.5 * height)
    crop_y = (ymin, ymax)

    snaps: list[dict[str, object]] = []
    for path in _select_evenly_spaced(cycle_paths, 4):
        mesh = meshio.read(path)
        _, _, tri = _triangulation(mesh, xlim=crop_x, ylim=crop_y)
        s_field = _scalar_field(mesh, "s")
        fdeg = _scalar_field(mesh, "Fdeg")
        cycle = _extract_int_from_name(path, "cycle")
        snaps.append({"tri": tri, "d": np.clip(1.0 - s_field, 0.0, 1.0), "fdeg": fdeg, "note": f"N = {cycle or 0}"})

    outputs: dict[str, str] = {}
    if mesh_path is not None:
        outputs["mesh_overview"] = str(_export_geometry_gallery(output_dir / "tpb_mesh_overview.png", "TPB mesh overview", [("AT1", mesh_path)]))
    if history_csv is not None:
        rows = _read_csv_rows(history_csv)
        x_values = [float(row["cycle"]) for row in rows if row.get("cycle")]
        y_values = [float(row["delta_a"]) for row in rows if row.get("delta_a")]
        outputs["crack_growth_curve"] = str(
            _export_line_chart(
                output_dir / "tpb_crack_growth.png",
                title="TPB fatigue crack growth",
                xlabel="Cycle N",
                ylabel="Crack extension Δa (mm)",
                series=[{"x": x_values, "y": y_values, "color": CURVE_COLORS[0], "label": "AT1"}],
            )
        )
    outputs["fatigue_panel"] = str(
        _export_square_panel_2x2(
            output_dir / "tpb_fatigue_panel.png",
            snaps=snaps,
            field_key="fdeg",
            cmap_name="plasma_r",
            norm=mpl.colors.Normalize(0.0, 1.0),
            cbar_title=r"$f(\bar{\alpha})$",
            title="TPB fatigue degradation",
            xlim=crop_x,
            ylim=crop_y,
        )
    )
    outputs["damage_panel"] = str(
        _export_square_panel_2x2(
            output_dir / "tpb_damage_panel.png",
            snaps=snaps,
            field_key="d",
            cmap_name="turbo",
            norm=mpl.colors.Normalize(0.0, 1.0),
            cbar_title="$d$",
            title="TPB damage snapshots",
            xlim=crop_x,
            ylim=crop_y,
        )
    )
    return outputs


def _ordered_case_dirs(base_dir: Path, labels: list[str] | None = None, *, predicate) -> list[Path]:
    if labels:
        ordered = [base_dir / label for label in labels if (base_dir / label).is_dir() and predicate(base_dir / label)]
        if ordered:
            return ordered
    return sorted((path for path in base_dir.iterdir() if path.is_dir() and predicate(path)), key=lambda path: path.name)


def _scan_mesh_items(case_dirs: list[Path], mesh_name: str) -> list[tuple[str, Path]]:
    items: list[tuple[str, Path]] = []
    for case_dir in case_dirs:
        mesh_path = case_dir / mesh_name
        if mesh_path.exists():
            items.append((case_dir.name, mesh_path))
    return items


def _comparison_series_from_csv(case_dirs: list[Path], csv_name: str, x_key: str, y_key: str) -> list[dict[str, object]]:
    series: list[dict[str, object]] = []
    for index, case_dir in enumerate(case_dirs):
        csv_path = case_dir / csv_name
        if not csv_path.exists():
            continue
        rows = _read_csv_rows(csv_path)
        x_values: list[float] = []
        y_values: list[float] = []
        for row in rows:
            try:
                x_values.append(float(row[x_key]))
                y_values.append(float(row[y_key]))
            except (KeyError, TypeError, ValueError):
                continue
        if x_values and y_values:
            series.append(
                {
                    "label": case_dir.name,
                    "x": x_values,
                    "y": y_values,
                    "color": CURVE_COLORS[index % len(CURVE_COLORS)],
                }
            )
    return series


def export_offset_double_notch_panels(
    native_output_dir: Path,
    output_dir: Path,
    runtime_params_path: Path | None = None,
) -> dict[str, str]:
    del runtime_params_path
    summary_csv = _first_existing(native_output_dir, "scan_summary.csv")
    ordered_labels = [row["case_label"] for row in _read_csv_rows(summary_csv)] if summary_csv is not None else None
    case_dirs = _ordered_case_dirs(
        native_output_dir,
        ordered_labels,
        predicate=lambda path: (path / "history.csv").exists(),
    )
    if not case_dirs:
        raise FileNotFoundError(f"Missing offset double-notch case directories in {native_output_dir}")

    case_rows: list[dict[str, object]] = []
    column_titles: list[str] | None = None
    for case_dir in case_dirs:
        preferred_paths = [
            _first_existing(case_dir, "result_bridge20*.vtu"),
            _first_existing(case_dir, "result_bridge50*.vtu"),
            _first_existing(case_dir, "result_bridge80*.vtu"),
            _first_existing(case_dir, "result_final*.vtu"),
        ]
        snap_paths = [path for path in preferred_paths if path is not None]
        if len(snap_paths) < 4:
            snap_paths = _select_evenly_spaced(_sorted_matches(case_dir, "result_*.vtu"), 4)
        snaps: list[dict[str, object]] = []
        current_titles: list[str] = []
        for path in snap_paths:
            mesh = meshio.read(path)
            _, _, tri = _triangulation(mesh)
            damage = _scalar_field(mesh, "d")
            fatigue = _scalar_field(mesh, "falpha")
            cycle = _extract_int_from_name(path, "cycle")
            title = "Final" if "final" in path.stem else path.stem.replace("result_", "").replace("_", " ")
            current_titles.append(title.title())
            snaps.append({"tri": tri, "d": damage, "falpha": fatigue, "note": f"N = {cycle}" if cycle is not None else "Final"})
        if column_titles is None and current_titles:
            column_titles = current_titles
        case_rows.append({"label": case_dir.name, "snaps": snaps})

    outputs: dict[str, str] = {}
    mesh_items = _scan_mesh_items(case_dirs, "mesh_offset_double_notch.msh")
    if mesh_items:
        outputs["mesh_overview"] = str(_export_geometry_gallery(output_dir / "offset_mesh_overview.png", "Offset double-notch meshes", mesh_items))
    comparison_series = _comparison_series_from_csv(case_dirs, "history.csv", "cycle", "gap_mm")
    if comparison_series:
        outputs["comparison_curve"] = str(
            _export_line_chart(
                output_dir / "offset_gap_comparison.png",
                title="Offset double-notch gap comparison",
                xlabel="Cycle N",
                ylabel="Ligament gap (mm)",
                series=comparison_series,
            )
        )
    outputs["fatigue_panel"] = str(
        _export_scan_panel(
            output_dir / "offset_fatigue_panel.png",
            case_rows=case_rows,
            field_key="falpha",
            cmap_name="plasma_r",
            norm=mpl.colors.Normalize(0.0, 1.0),
            cbar_title=r"$f(\bar{\alpha})$",
            title="Offset double-notch fatigue degradation",
            col_titles=column_titles,
        )
    )
    outputs["damage_panel"] = str(
        _export_scan_panel(
            output_dir / "offset_damage_panel.png",
            case_rows=case_rows,
            field_key="d",
            cmap_name="turbo",
            norm=mpl.colors.Normalize(0.0, 1.0),
            cbar_title="$d$",
            title="Offset double-notch damage snapshots",
            col_titles=column_titles,
        )
    )
    return outputs


def export_fang2019_panels(
    native_output_dir: Path,
    output_dir: Path,
    runtime_params_path: Path | None = None,
) -> dict[str, str]:
    del runtime_params_path
    summary_csv = _first_existing(native_output_dir, "scan_summary.csv")
    summary_rows = _read_csv_rows(summary_csv) if summary_csv is not None else []
    ordered_labels = [row["label"] for row in summary_rows if row.get("label")]
    label_map = {
        row["label"]: rf"$H = {float(row['H_ratio']):.1f}E$" for row in summary_rows if row.get("label") and row.get("H_ratio")
    }
    case_dirs = _ordered_case_dirs(
        native_output_dir,
        ordered_labels,
        predicate=lambda path: any(path.glob("force_displacement_*.csv")),
    )
    if not case_dirs:
        raise FileNotFoundError(f"Missing Fang scan case directories in {native_output_dir}")

    crop_x = (-0.5, 18.5)
    crop_y = (15.0, 35.5)
    case_rows: list[dict[str, object]] = []
    epspeq_samples: list[np.ndarray] = []
    col_titles: list[str] | None = None
    for case_dir in case_dirs:
        csv_path = _first_existing(case_dir, "force_displacement_*.csv")
        rows = _read_csv_rows(csv_path) if csv_path is not None else []
        rows_by_step = {int(float(row["step"])): row for row in rows if row.get("step")}
        preferred_paths = [
            _first_existing(case_dir, "result_d020*.vtu"),
            _first_existing(case_dir, "result_d060*.vtu"),
            _first_existing(case_dir, "result_d090*.vtu"),
            _first_existing(case_dir, "result_final*.vtu"),
        ]
        snap_paths = [path for path in preferred_paths if path is not None]
        if len(snap_paths) < 4:
            snap_paths = _select_evenly_spaced(_sorted_matches(case_dir, "result_*.vtu"), 4)
        snaps: list[dict[str, object]] = []
        titles: list[str] = []
        for path in snap_paths:
            mesh = meshio.read(path)
            _, _, tri = _triangulation(mesh, xlim=crop_x, ylim=crop_y)
            damage = _scalar_field(mesh, "d")
            epspeq = _scalar_field(mesh, "epspeq")
            step = _extract_int_from_name(path, "step")
            if "final" in path.stem and rows:
                row = rows[-1]
            else:
                row = rows_by_step.get(step) if step is not None else None
            note = rf"$u = {float(row['u_mm']):.4f}$ mm" if row is not None and row.get("u_mm") else ""
            title = "Final" if "final" in path.stem else path.stem.replace("result_", "").replace("_", " ")
            titles.append(title.title())
            snaps.append({"tri": tri, "d": damage, "epspeq": epspeq, "note": note})
        epspeq_samples.append(snaps[-1]["epspeq"])
        if col_titles is None and titles:
            col_titles = titles
        case_rows.append({"label": label_map.get(case_dir.name, case_dir.name), "snaps": snaps})

    epspeq_max = _rounded_percentile_max(np.concatenate(epspeq_samples), 99.0, floor=1.0e-6)
    outputs: dict[str, str] = {}
    mesh_items = _scan_mesh_items(case_dirs, "mesh.msh")
    if mesh_items:
        outputs["mesh_overview"] = str(_export_geometry_gallery(output_dir / "fang_mesh_overview.png", "Flat-grooved meshes", mesh_items))
    comparison_series: list[dict[str, object]] = []
    for index, case_dir in enumerate(case_dirs):
        csv_path = _first_existing(case_dir, "force_displacement_*.csv")
        if csv_path is None:
            continue
        rows = _read_csv_rows(csv_path)
        u_values = [float(row["u_mm"]) for row in rows if row.get("u_mm")]
        f_values = [float(row["F_kN"]) for row in rows if row.get("F_kN")]
        if u_values and f_values:
            comparison_series.append(
                {
                    "label": case_dir.name,
                    "x": u_values,
                    "y": f_values,
                    "color": CURVE_COLORS[index % len(CURVE_COLORS)],
                }
            )
    if comparison_series:
        outputs["force_displacement_comparison"] = str(
            _export_line_chart(
                output_dir / "fang_force_comparison.png",
                title="Flat-grooved force-displacement comparison",
                xlabel="Displacement u (mm)",
                ylabel="Force F (kN)",
                series=comparison_series,
            )
        )
    outputs["epspeq_panel"] = str(
        _export_scan_panel(
            output_dir / "fang_epspeq_panel.png",
            case_rows=case_rows,
            field_key="epspeq",
            cmap_name="plasma",
            norm=mpl.colors.Normalize(0.0, epspeq_max),
            cbar_title=r"$\varepsilon^p_\mathrm{eq}$",
            title="Flat-grooved equivalent plastic strain",
            xlim=crop_x,
            ylim=crop_y,
            col_titles=col_titles,
        )
    )
    outputs["damage_panel"] = str(
        _export_scan_panel(
            output_dir / "fang_damage_panel.png",
            case_rows=case_rows,
            field_key="d",
            cmap_name="turbo",
            norm=mpl.colors.Normalize(0.0, 1.0),
            cbar_title="$d$",
            title="Flat-grooved damage snapshots",
            xlim=crop_x,
            ylim=crop_y,
            col_titles=col_titles,
        )
    )
    return outputs


def export_double_notched_panels(
    native_output_dir: Path,
    output_dir: Path,
    runtime_params_path: Path | None = None,
) -> dict[str, str]:
    del runtime_params_path
    summary_csv = _first_existing(native_output_dir, "scan_summary.csv")
    summary_rows = _read_csv_rows(summary_csv) if summary_csv is not None else []
    ordered_labels = [row["case_tag"] for row in summary_rows if row.get("case_tag")]
    case_dirs = _ordered_case_dirs(
        native_output_dir,
        ordered_labels,
        predicate=lambda path: (path / "force_displacement.csv").exists(),
    )
    if not case_dirs:
        raise FileNotFoundError(f"Missing double-notched scan directories in {native_output_dir}")

    case_rows: list[dict[str, object]] = []
    epspeq_samples: list[np.ndarray] = []
    col_titles: list[str] | None = None
    for case_dir in case_dirs:
        preferred_paths = [
            _first_existing(case_dir, "result_d020*.vtu"),
            _first_existing(case_dir, "result_d060*.vtu"),
            _first_existing(case_dir, "result_d090*.vtu"),
            _first_existing(case_dir, "result_final*.vtu"),
        ]
        snap_paths = [path for path in preferred_paths if path is not None]
        if len(snap_paths) < 4:
            snap_paths = _select_evenly_spaced(_sorted_matches(case_dir, "result_*.vtu"), 4)
        snaps: list[dict[str, object]] = []
        titles: list[str] = []
        for path in snap_paths:
            mesh = meshio.read(path)
            _, _, tri = _triangulation(mesh)
            damage = _scalar_field(mesh, "d")
            epspeq = _scalar_field(mesh, "epspeq")
            displacement = _vector_field(mesh, "u", 2)
            titles.append("Final" if "final" in path.stem else path.stem.replace("result_", "").replace("_", " ").title())
            snaps.append({"tri": tri, "d": damage, "epspeq": epspeq, "note": rf"$u = {float(np.nanmax(displacement[:, 1])):.3f}$ mm"})
        epspeq_samples.append(snaps[-1]["epspeq"])
        if col_titles is None and titles:
            col_titles = titles
        case_rows.append({"label": case_dir.name, "snaps": snaps})

    epspeq_max = _rounded_percentile_max(np.concatenate(epspeq_samples), 99.0, floor=1.0e-6)
    outputs: dict[str, str] = {}
    mesh_items = _scan_mesh_items(case_dirs, "mesh_double_notched.msh")
    if mesh_items:
        outputs["mesh_overview"] = str(
            _export_geometry_gallery(output_dir / "double_notched_mesh_overview.png", "Double-notched meshes", mesh_items)
        )
    comparison_series = _comparison_series_from_csv(case_dirs, "force_displacement.csv", "u_mm", "F_kN")
    if comparison_series:
        outputs["force_displacement_comparison"] = str(
            _export_line_chart(
                output_dir / "double_notched_force_comparison.png",
                title="Double-notched force-displacement comparison",
                xlabel="Displacement u (mm)",
                ylabel="Force F (kN)",
                series=comparison_series,
            )
        )
    outputs["epspeq_panel"] = str(
        _export_scan_panel(
            output_dir / "double_notched_epspeq_panel.png",
            case_rows=case_rows,
            field_key="epspeq",
            cmap_name="plasma",
            norm=mpl.colors.Normalize(0.0, epspeq_max),
            cbar_title=r"$\varepsilon^p_\mathrm{eq}$",
            title="Double-notched equivalent plastic strain",
            col_titles=col_titles,
        )
    )
    outputs["damage_panel"] = str(
        _export_scan_panel(
            output_dir / "double_notched_damage_panel.png",
            case_rows=case_rows,
            field_key="d",
            cmap_name="turbo",
            norm=mpl.colors.Normalize(0.0, 1.0),
            cbar_title="$d$",
            title="Double-notched damage snapshots",
            col_titles=col_titles,
        )
    )
    return outputs


def _fatigue_degradation(alpha_bar: np.ndarray, alpha_t: float) -> np.ndarray:
    alpha_t = max(float(alpha_t), 1.0e-12)
    return np.where(alpha_bar <= alpha_t, 1.0, (2.0 * alpha_t / (alpha_bar + alpha_t)) ** 2)


def _nearest_regular_path(regular_paths: list[Path], target_cycle: int) -> Path | None:
    if not regular_paths:
        return None
    return min(
        regular_paths,
        key=lambda path: abs((_extract_int_from_name(path, "N") or target_cycle) - target_cycle),
    )


def _export_sent_fatigue_main_panel(
    output_path: Path,
    *,
    snaps: list[dict[str, object]],
    column_titles: list[str],
    row_specs: list[tuple[str, str, mpl.colors.Normalize, str, str]],
    xlim: tuple[float, float],
    ylim: tuple[float, float],
):
    n_rows = len(row_specs)
    n_cols = len(snaps)
    crop_w = max(xlim[1] - xlim[0], 1.0e-6)
    crop_h = max(ylim[1] - ylim[0], 1.0e-6)
    cell_w = 3.8
    cell_h = cell_w * crop_h / crop_w
    l_pad, r_pad, t_pad, b_pad = 0.8, 1.0, 0.7, 0.25
    hspace, wspace = 0.12, 0.04
    figure = plt.figure(figsize=(l_pad + n_cols * cell_w * (1.0 + wspace) + r_pad, t_pad + n_rows * cell_h * (1.0 + hspace) + b_pad))
    left = l_pad / figure.get_size_inches()[0]
    right = 1.0 - r_pad / figure.get_size_inches()[0]
    bottom = b_pad / figure.get_size_inches()[1]
    top = 1.0 - t_pad / figure.get_size_inches()[1]
    grid = GridSpec(n_rows, n_cols, figure=figure, left=left, right=right, bottom=bottom, top=top, hspace=hspace, wspace=wspace)
    axes = [[figure.add_subplot(grid[r, c]) for c in range(n_cols)] for r in range(n_rows)]

    for row_index, (field_key, cmap_name, norm, row_label, cbar_title) in enumerate(row_specs):
        cmap = plt.get_cmap(cmap_name)
        for col_index, snap in enumerate(snaps):
            ax = axes[row_index][col_index]
            ax.tripcolor(snap["tri"], snap[field_key], cmap=cmap, norm=norm, shading="gouraud", rasterized=True)
            ax.set_xlim(xlim)
            ax.set_ylim(ylim)
            ax.set_aspect("equal")
            ax.axis("off")
            ax.add_patch(
                Rectangle((0, 0), 1, 1, transform=ax.transAxes, fill=False, edgecolor=PANEL_BORDER_COLOR, linewidth=1.8, zorder=20)
            )
            ax.text(0.5, 0.92, str(snap.get("note") or ""), transform=ax.transAxes, ha="center", va="top", fontsize=16, color="white")
            if row_index == 0 and col_index < len(column_titles):
                ax.set_title(column_titles[col_index], fontsize=18, pad=6)

        position = axes[row_index][0].get_position()
        figure.text(left - 0.02, 0.5 * (position.y0 + position.y1), row_label, ha="right", va="center", rotation=90, fontsize=18)
        top_position = axes[row_index][-1].get_position()
        colorbar_axis = figure.add_axes([top_position.x1 + 0.012, position.y0, 0.018, position.height])
        colorbar = figure.colorbar(mpl.cm.ScalarMappable(norm=norm, cmap=cmap), cax=colorbar_axis)
        _configure_vertical_colorbar(colorbar, norm, cbar_title)

    figure.suptitle("SENT elasto-plastic fatigue field evolution", y=0.995, fontsize=22)
    return _save_figure(figure, output_path)


def export_sent_fatigue_panels(
    native_output_dir: Path,
    output_dir: Path,
    runtime_params_path: Path | None = None,
) -> dict[str, str]:
    params = _load_runtime_params(runtime_params_path)
    alpha_t = float(params.get("alpha_T", 11.25))
    mesh_path = _first_existing(native_output_dir, "mesh.msh")
    cycle_csv = _first_existing(native_output_dir, "cycle_summary.csv")
    milestone_paths = sorted((path for path in native_output_dir.glob("result_a*_N*.vtu") if path.is_file()), key=_natural_sort_key)
    regular_paths = sorted((path for path in native_output_dir.glob("result_N*.vtu") if path.is_file()), key=_natural_sort_key)
    selected_milestones = _select_evenly_spaced(milestone_paths, 4)
    if not selected_milestones:
        raise FileNotFoundError(f"Missing SENT fatigue milestone VTK files in {native_output_dir}")

    crop_x = (0.35, 1.02)
    crop_y = (0.33, 0.67)
    snaps: list[dict[str, object]] = []
    sigma_samples: list[np.ndarray] = []
    epspeq_samples: list[np.ndarray] = []
    column_titles: list[str] = []
    for milestone_path in selected_milestones:
        cycle = _extract_int_from_name(milestone_path, "N") or 0
        crack_extension = (_extract_int_from_name(milestone_path, "a") or 0) / 1000.0
        regular_path = _nearest_regular_path(regular_paths, cycle)
        milestone_mesh = meshio.read(milestone_path)
        milestone_points, _, tri = _triangulation(milestone_mesh, xlim=crop_x, ylim=crop_y)
        sigma_mesh = meshio.read(regular_path) if regular_path is not None else milestone_mesh
        sigma_points, _, _ = _triangulation(sigma_mesh)
        sigmaeq = _align_point_field_by_coordinates(sigma_points, _scalar_field(sigma_mesh, "sigmaeq"), milestone_points)
        alpha_bar = _scalar_field(milestone_mesh, "alpha_bar")
        epspeq = _scalar_field(milestone_mesh, "epspeq")
        snaps.append(
            {
                "tri": tri,
                "d": _scalar_field(milestone_mesh, "d"),
                "fatigue": _fatigue_degradation(alpha_bar, alpha_t),
                "epspeq": epspeq,
                "sigmaeq": sigmaeq,
                "note": f"N = {cycle}",
            }
        )
        sigma_samples.append(sigmaeq)
        epspeq_samples.append(epspeq)
        column_titles.append(rf"$\Delta a \approx {crack_extension:.2f}$ mm")

    epspeq_max = _rounded_percentile_max(np.concatenate(epspeq_samples), 99.0, floor=1.0e-6)
    sigma_max = _rounded_percentile_max(np.concatenate(sigma_samples), 99.0, floor=1.0e-6)
    outputs: dict[str, str] = {}
    if mesh_path is not None:
        outputs["mesh_overview"] = str(_export_geometry_gallery(output_dir / "sent_fatigue_mesh_overview.png", "SENT fatigue mesh overview", [("SENT", mesh_path)]))
    if cycle_csv is not None:
        rows = _read_csv_rows(cycle_csv)
        cycle_values = [float(row["N"]) for row in rows if row.get("N")]
        crack_values = [float(row["delta_a_mm"]) for row in rows if row.get("delta_a_mm")]
        outputs["crack_growth_curve"] = str(
            _export_line_chart(
                output_dir / "sent_fatigue_crack_growth.png",
                title="SENT fatigue crack growth",
                xlabel="Cycle N",
                ylabel="Crack extension Δa (mm)",
                series=[{"x": cycle_values, "y": crack_values, "color": CURVE_COLORS[0]}],
            )
        )
    outputs["main_panel"] = str(
        _export_sent_fatigue_main_panel(
            output_dir / "sent_fatigue_main_panel.png",
            snaps=snaps,
            column_titles=column_titles,
            row_specs=[
                ("d", "turbo", mpl.colors.Normalize(0.0, 1.0), "$d$", "$d$"),
                ("fatigue", "RdYlBu", mpl.colors.Normalize(0.0, 1.0), r"$f(\bar{\alpha})$", r"$f(\bar{\alpha})$"),
                ("epspeq", "plasma", mpl.colors.Normalize(0.0, epspeq_max), r"$\varepsilon^p_\mathrm{eq}$", r"$\varepsilon^p_\mathrm{eq}$"),
                ("sigmaeq", "viridis", mpl.colors.Normalize(0.0, sigma_max), r"$\sigma_\mathrm{eq}$", "MPa"),
            ],
            xlim=crop_x,
            ylim=crop_y,
        )
    )
    return outputs


def _central_rate(cycles: np.ndarray, crack_values: np.ndarray, cycle: int) -> tuple[float, float]:
    if len(cycles) == 0:
        return 0.0, 0.0
    index = int(np.argmin(np.abs(cycles - cycle)))
    crack_extension = float(crack_values[index])
    if 0 < index < len(cycles) - 1:
        rate = float((crack_values[index + 1] - crack_values[index - 1]) / (cycles[index + 1] - cycles[index - 1]))
    elif index == 0 and len(cycles) > 1:
        rate = float((crack_values[1] - crack_values[0]) / (cycles[1] - cycles[0]))
    elif len(cycles) > 1:
        rate = float((crack_values[-1] - crack_values[-2]) / (cycles[-1] - cycles[-2]))
    else:
        rate = 0.0
    return crack_extension, rate


def export_ct_fatigue_panels(
    native_output_dir: Path,
    output_dir: Path,
    runtime_params_path: Path | None = None,
) -> dict[str, str]:
    del runtime_params_path
    mesh_path = _first_existing(native_output_dir, "CT_mesh.msh")
    cycle_csv = _first_existing(native_output_dir, "cycle_summary.csv")
    milestone_paths = sorted((path for path in native_output_dir.glob("result_da*_cycle*.vtu") if path.is_file()), key=_natural_sort_key)
    selected_milestones = _select_evenly_spaced(milestone_paths, 4)
    if not selected_milestones:
        raise FileNotFoundError(f"Missing CT fatigue milestone VTK files in {native_output_dir}")

    cycle_rows = _read_csv_rows(cycle_csv) if cycle_csv is not None else []
    cycles = np.array([int(float(row["cycle"])) for row in cycle_rows if row.get("cycle")], dtype=int) if cycle_rows else np.array([], dtype=int)
    crack_values = np.array([float(row["delta_a_mm"]) for row in cycle_rows if row.get("delta_a_mm")], dtype=float) if cycle_rows else np.array([], dtype=float)

    sample_mesh = meshio.read(selected_milestones[0])
    sample_points = np.asarray(sample_mesh.points[:, :2], dtype=float)
    y_mid = 0.5 * (float(np.min(sample_points[:, 1])) + float(np.max(sample_points[:, 1])))
    xlim = (float(np.min(sample_points[:, 0])), float(np.max(sample_points[:, 0])))
    ylim = (y_mid, float(np.max(sample_points[:, 1])))

    def upper_half_filter(points: np.ndarray, cells: np.ndarray):
        return np.all(points[cells, 1] >= y_mid - 1.0e-10, axis=1)

    snaps: list[dict[str, object]] = []
    for path in selected_milestones:
        mesh = meshio.read(path)
        _, _, tri = _triangulation(mesh, triangle_filter=upper_half_filter)
        cycle = _extract_int_from_name(path, "cycle") or 0
        crack_extension, rate = _central_rate(cycles, crack_values, cycle)
        damage = _scalar_field(mesh, "s")
        snaps.append(
            {
                "tri": tri,
                "damage": damage,
                "note": rf"$\Delta a={crack_extension:.2f}$ mm" + "\n" + rf"$\mathrm{{d}}a/\mathrm{{d}}N={rate:.4f}$ mm/cycle",
            }
        )

    outputs: dict[str, str] = {}
    if mesh_path is not None:
        outputs["mesh_overview"] = str(_export_geometry_gallery(output_dir / "ct_mesh_overview.png", "CT mesh overview", [("CT", mesh_path)]))
    if cycle_csv is not None:
        outputs["crack_growth_curve"] = str(
            _export_line_chart(
                output_dir / "ct_crack_growth.png",
                title="CT crack growth",
                xlabel="Cycle N",
                ylabel="Crack extension Δa (mm)",
                series=[{"x": cycles, "y": crack_values, "color": CURVE_COLORS[0]}],
            )
        )
    outputs["damage_panel"] = str(
        _export_square_panel_2x2(
            output_dir / "ct_damage_panel.png",
            snaps=snaps,
            field_key="damage",
            cmap_name="turbo",
            norm=mpl.colors.Normalize(0.0, 1.0),
            cbar_title="$d$",
            title="CT upper-half damage snapshots",
            xlim=xlim,
            ylim=ylim,
        )
    )
    return outputs
