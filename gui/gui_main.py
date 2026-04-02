from __future__ import annotations

import csv
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import matplotlib as mpl
from PyQt5.QtCore import (
    QEasingCurve,
    QEvent,
    QParallelAnimationGroup,
    QPropertyAnimation,
    QRect,
    QSequentialAnimationGroup,
    QThread,
    QTimer,
    Qt,
    pyqtSignal,
)
from PyQt5.QtGui import QColor, QFont, QFontDatabase, QKeySequence, QPixmap
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QBoxLayout,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGraphicsOpacityEffect,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QMenu,
    QShortcut,
    QScrollArea,
    QSlider,
    QSizePolicy,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure


GUI_DIR = Path(__file__).resolve().parent
REPO_ROOT = GUI_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from visual import export_visuals

if __package__ in (None, ""):
    from case_registry import (
        BOOL_FIELDS,
        CASE_DEFINITIONS,
        CASE_REGISTRY,
        CATEGORY_LABELS,
        CATEGORY_ORDER,
        COMPUTE_FIELD_SPECS,
        CURVE_AXIS_LABELS,
        INT_FIELDS,
        MESH_FIELD_SPECS,
        POSTPROCESS_VIEWS,
        RUN_PROFILE_LABELS,
        RUN_PROFILE_ORDER,
        SCAN_EDITOR_SPECS,
        first_case_for_category,
        iter_cases_for_category,
    )
    from run_manifest import RunManifest, dedupe_existing_paths, load_manifest, make_run_id, manifest_file_payloads, write_manifest
else:
    from .case_registry import (
        BOOL_FIELDS,
        CASE_DEFINITIONS,
        CASE_REGISTRY,
        CATEGORY_LABELS,
        CATEGORY_ORDER,
        COMPUTE_FIELD_SPECS,
        CURVE_AXIS_LABELS,
        INT_FIELDS,
        MESH_FIELD_SPECS,
        POSTPROCESS_VIEWS,
        RUN_PROFILE_LABELS,
        RUN_PROFILE_ORDER,
        SCAN_EDITOR_SPECS,
        first_case_for_category,
        iter_cases_for_category,
    )
    from .run_manifest import RunManifest, dedupe_existing_paths, load_manifest, make_run_id, manifest_file_payloads, write_manifest


RESULTS_DIR = GUI_DIR / "gui_results"
MANIFEST_DIR = RESULTS_DIR / "manifests"
RUNS_DIR = RESULTS_DIR / "runs"
VISUAL_EXPORT_DIR = RESULTS_DIR / "visual_exports"
STOP_FLAG = GUI_DIR / "gui_stop.flag"
TRANSIENT_CACHE_PREF_PATH = GUI_DIR / ".gui_cache_pref.json"
DEFAULT_PARAMS_PATH = GUI_DIR / "params_default.json"
PREFERRED_SERIF_FONT_FAMILY = "Times"
SERIF_FONT_FAMILY_CANDIDATES = (
    PREFERRED_SERIF_FONT_FAMILY,
    "Times New Roman",
    "Nimbus Roman No9 L",
    "TeX Gyre Termes",
    "Liberation Serif",
    "DejaVu Serif",
)
APP_FONT_FAMILY = PREFERRED_SERIF_FONT_FAMILY
APP_FONT_SIZE = 17
TITLE_FONT_SIZE = 40
PLOT_FONT_SIZE = 16
CURVE_AXIS_FONT_SIZE = 13
CURVE_TICK_FONT_SIZE = 11
CURVE_LEGEND_FONT_SIZE = 11
ANIMATION_FAST_MS = 150
ANIMATION_MEDIUM_MS = 220
ANIMATION_SLOW_MS = 320
ANIMATION_TOAST_STAY_MS = 2200
JULIA_COMMAND = "julia"
SUBTITLE_FONT_SIZE = 18
TOP_LEVEL_RESULT_PATTERNS = (
    "mesh_*.msh",
    "mesh_*.png",
    "F_u_curve*.csv",
    "F_u_curve*.png",
    "d_final*.png",
    "u_mag_final*.png",
    "u_mag_*.png",
    "result*.vtu",
    "snap*.png",
)
CASE_HEADER_SUMMARIES = {
    "sent_tension": "Single-edge notched tension benchmark for elastic phase-field fracture under monotonic tensile loading.",
    "sens_shear": "Single-edge notched shear benchmark for elastic phase-field fracture under in-plane shear loading.",
    "tpb_fatigue": "Three-point bending fatigue benchmark for phase-field crack initiation and growth under cyclic loading.",
    "offset_double_notch_fatigue": "Offset double-notch fatigue benchmark for competing crack-path evolution under cyclic loading.",
    "fang_flat_grooved_scan": "Flat grooved scan benchmark for elasto-plastic phase-field fracture with geometry-parameter comparison.",
    "double_notched_monotonic": "Double-notched monotonic benchmark for elasto-plastic fracture response and crack-path competition.",
    "sent_elasto_plastic_fatigue": "Single-edge notched tension fatigue benchmark for elasto-plastic phase-field crack-growth assessment.",
    "ct_elasto_plastic_fatigue": "Compact tension fatigue benchmark for elasto-plastic phase-field crack-growth assessment.",
}
CASE_BADGE_LABELS = {
    "sent_tension": "Single-Edge Notch · Monotonic Tension",
    "sens_shear": "Single-Edge Notch · In-Plane Shear",
    "tpb_fatigue": "Three-Point Bending · Fatigue",
    "offset_double_notch_fatigue": "Offset Double-Notch · Fatigue",
    "fang_flat_grooved_scan": "Flat Grooved · Parameter Scan",
    "double_notched_monotonic": "Double-Notched · Monotonic",
    "sent_elasto_plastic_fatigue": "SENT · Elasto-Plastic Fatigue",
    "ct_elasto_plastic_fatigue": "CT · Elasto-Plastic Fatigue",
}

mpl.rcParams.update(
    {
        "font.family": "serif",
        "font.serif": list(SERIF_FONT_FAMILY_CANDIDATES),
        "font.size": PLOT_FONT_SIZE,
        "axes.titlesize": PLOT_FONT_SIZE,
        "axes.labelsize": PLOT_FONT_SIZE,
        "xtick.labelsize": PLOT_FONT_SIZE,
        "ytick.labelsize": PLOT_FONT_SIZE,
        "legend.fontsize": PLOT_FONT_SIZE,
        "xtick.direction": "in",
        "ytick.direction": "in",
    }
)


def resolve_qt_serif_font_family() -> str:
    available_families = {family.casefold(): family for family in QFontDatabase().families()}
    for family in SERIF_FONT_FAMILY_CANDIDATES:
        matched_family = available_families.get(family.casefold())
        if matched_family is not None:
            return matched_family
    return APP_FONT_FAMILY


def mesh_file_name(protocol_case_name: str) -> str:
    return f"mesh_{protocol_case_name}.msh"


def mesh_png_name(protocol_case_name: str) -> str:
    return f"mesh_{protocol_case_name}.png"


def curve_csv_name(protocol_case_name: str) -> str:
    return f"F_u_curve_{protocol_case_name}.csv"


def curve_png_name(protocol_case_name: str) -> str:
    return f"F_u_curve_{protocol_case_name}.png"


def damage_final_name(protocol_case_name: str) -> str:
    return f"d_final_{protocol_case_name}.png"


def displacement_final_name(protocol_case_name: str) -> str:
    return f"u_mag_final_{protocol_case_name}.png"


def result_prefix(protocol_case_name: str) -> str:
    return f"result_{protocol_case_name}_"


def latest_manifest_path(case_id: str) -> Path:
    return MANIFEST_DIR / f"{case_id}_latest.json"


def case_runs_dir(case_id: str) -> Path:
    return RUNS_DIR / case_id


def run_dir(case_id: str, run_id: str) -> Path:
    return case_runs_dir(case_id) / run_id


def run_native_dir(case_id: str, run_id: str) -> Path:
    return run_dir(case_id, run_id) / "native"


def run_manifest_path(case_id: str, run_id: str) -> Path:
    return run_dir(case_id, run_id) / "manifest.json"


def run_runtime_params_path(case_id: str, run_id: str) -> Path:
    return run_dir(case_id, run_id) / "runtime_params.json"


def latest_archived_manifest_path(case_id: str) -> Path | None:
    manifest_paths = sorted(
        path for path in case_runs_dir(case_id).glob("*/manifest.json") if path.is_file()
    )
    return manifest_paths[-1] if manifest_paths else None


def first_existing(*paths: Path) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def extract_numeric_suffix(path_like: str | Path) -> int | None:
    match = re.search(r"(\d+)(?=\.[^.]+$)", Path(path_like).name)
    return int(match.group(1)) if match else None


def sorted_existing(paths):
    return [path for path in sorted(paths) if path.exists()]


def is_visual_export_view(view_name: str | None) -> bool:
    return (view_name or "") == "Visual Export"


def active_conda_prefix() -> Path | None:
    raw_prefix = os.environ.get("CONDA_PREFIX")
    if not raw_prefix:
        return None
    return Path(raw_prefix)


def active_conda_env_name() -> str | None:
    raw_name = os.environ.get("CONDA_DEFAULT_ENV")
    if raw_name:
        return raw_name
    prefix = active_conda_prefix()
    if prefix is None:
        return None
    return prefix.name


def repo_julia_project_dir() -> Path | None:
    project_file = REPO_ROOT / "Project.toml"
    if project_file.is_file():
        return REPO_ROOT
    return None


def resolved_julia_project() -> str | None:
    explicit_project = os.environ.get("JULIA_PROJECT")
    if explicit_project:
        return explicit_project
    repo_project = repo_julia_project_dir()
    if repo_project is not None:
        return str(repo_project)
    prefix = active_conda_prefix()
    env_name = active_conda_env_name()
    if prefix is None or not env_name:
        return None
    return str(prefix / "share" / "julia" / "environments" / env_name)


def resolved_julia_depot() -> str | None:
    explicit_depot = os.environ.get("JULIA_DEPOT_PATH")
    if explicit_depot:
        return explicit_depot
    prefix = active_conda_prefix()
    if prefix is None:
        return None
    return str(prefix / "share" / "julia")


def julia_env_prefix() -> str:
    exports: list[str] = []
    project = resolved_julia_project()
    depot = resolved_julia_depot()
    if project:
        exports.append(f"export JULIA_PROJECT={shlex.quote(project)}")
    if depot:
        exports.append(f"export JULIA_DEPOT_PATH={shlex.quote(depot)}")
    if not exports:
        return ""
    return " && ".join(exports) + " && "


def julia_subprocess_env():
    env = dict(os.environ)
    project = resolved_julia_project()
    depot = resolved_julia_depot()
    if project:
        env["JULIA_PROJECT"] = project
    if depot:
        env["JULIA_DEPOT_PATH"] = depot
    env["GKS_WSTYPE"] = "100"
    for key in (
        "DISPLAY",
        "WAYLAND_DISPLAY",
        "QT_QPA_PLATFORM",
        "QT_PLUGIN_PATH",
        "QML2_IMPORT_PATH",
        "XDG_RUNTIME_DIR",
    ):
        env.pop(key, None)
    return env


def purge_transient_gui_results() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    for directory in (MANIFEST_DIR, RUNS_DIR, VISUAL_EXPORT_DIR):
        if directory.exists():
            shutil.rmtree(directory)

    for pattern in TOP_LEVEL_RESULT_PATTERNS:
        for path in RESULTS_DIR.glob(pattern):
            if path.is_file():
                path.unlink()

    if STOP_FLAG.exists():
        STOP_FLAG.unlink()


def load_transient_cache_preference() -> bool:
    if not TRANSIENT_CACHE_PREF_PATH.exists():
        return False
    try:
        payload = json.loads(TRANSIENT_CACHE_PREF_PATH.read_text(encoding="utf-8"))
    except Exception:
        return False
    return bool(payload.get("keep_transient_results", False))


def write_transient_cache_preference(enabled: bool) -> None:
    payload = {"keep_transient_results": bool(enabled)}
    TRANSIENT_CACHE_PREF_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def normalize_run_profile(raw_profile: str | None, fallback: str = "full") -> str:
    profile = (raw_profile or "").strip().lower()
    if profile in RUN_PROFILE_ORDER:
        return profile
    return fallback if fallback in RUN_PROFILE_ORDER else "full"


def apply_run_profile_overrides(base_params: dict[str, object], profile_overrides: dict[str, dict[str, object]], run_profile: str):
    effective_params = dict(base_params)
    normalized_profile = normalize_run_profile(run_profile)
    if normalized_profile == "full":
        return effective_params
    for key, value in profile_overrides.get(normalized_profile, {}).items():
        effective_params[key] = value
    return effective_params


def parse_scan_value(raw_value: str, input_type: str, label: str):
    text = raw_value.strip()
    if input_type == "str":
        if not text:
            raise ValueError(f"{label} cannot be empty.")
        return text
    if not text:
        raise ValueError(f"{label} cannot be empty.")
    if input_type == "int":
        return int(text)
    if input_type == "bool":
        lowered = text.lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
        raise ValueError(f"{label} must be a boolean value.")
    return float(text)


def serialize_scan_cases(scan_rows, scan_columns):
    if not scan_columns:
        return []
    if not scan_rows:
        raise ValueError("At least one scan case is required.")
    serialized_rows = []
    for row_index, row in enumerate(scan_rows, start=1):
        payload = {}
        for column in scan_columns:
            label = f"Scan row {row_index} / {column.label}"
            payload[column.key] = parse_scan_value(str(row.get(column.key, "")), column.input_type, label)
        serialized_rows.append(payload)
    return serialized_rows


class CurveCanvas(FigureCanvas):
    def __init__(self):
        self.figure = Figure(figsize=(5, 4))
        self.axes = self.figure.add_subplot(111)
        self._x_label = "u (mm)"
        self._y_label = "F (kN)"
        super().__init__(self.figure)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(250)
        self.figure.patch.set_facecolor("#ffffff")
        self.axes.set_facecolor("#ffffff")
        self.setStyleSheet("background: transparent;")
        self.update_curve([], [])

    def set_curve_kind(self, curve_kind: str):
        self._x_label, self._y_label = CURVE_AXIS_LABELS.get(curve_kind, ("x", "y"))
        self.update_curve([], [])

    def update_curve(self, x_values, y_values):
        self.update_curves([{"x": x_values, "y": y_values, "label": ""}])

    def update_curves(self, series):
        self.axes.clear()
        self.figure.patch.set_facecolor("#ffffff")
        self.axes.set_facecolor("#ffffff")
        if not series:
            series = [{"x": [], "y": [], "label": ""}]
        for index, item in enumerate(series):
            x_values = item.get("x", [])
            y_values = item.get("y", [])
            label = item.get("label", "")
            color = item.get("color")
            line_kwargs = {"linewidth": 2.0}
            if color:
                line_kwargs["color"] = color
            if label:
                line_kwargs["label"] = label
            elif len(series) == 1 and index == 0:
                line_kwargs["color"] = "#1f77b4"
            self.axes.plot(x_values, y_values, **line_kwargs)
        self.axes.set_xlabel(self._x_label, fontsize=CURVE_AXIS_FONT_SIZE)
        self.axes.set_ylabel(self._y_label, fontsize=CURVE_AXIS_FONT_SIZE)
        self.axes.tick_params(direction="in", colors="#203247", labelsize=CURVE_TICK_FONT_SIZE)
        self.axes.grid(True, color="#b9cbdd", linewidth=1.0)
        for spine in self.axes.spines.values():
            spine.set_visible(True)
            spine.set_color("#2f4258")
            spine.set_linewidth(1.1)
        if len(series) > 1 and any(item.get("label") for item in series):
            legend = self.axes.legend(fontsize=CURVE_LEGEND_FONT_SIZE)
            if legend is not None:
                legend.get_frame().set_facecolor("#ffffff")
                legend.get_frame().set_edgecolor("#c2cfdb")
        self.figure.subplots_adjust(left=0.16, right=0.97, bottom=0.18, top=0.95)
        self.draw_idle()


class ImagePreviewWidget(QWidget):
    def __init__(self, placeholder_text: str, *, surface_variant: str = "framed", fixed_fit: bool = False):
        super().__init__()
        self._placeholder_text = placeholder_text
        self._base_pixmap = QPixmap()
        self._scale_factor = 1.0
        self._fit_to_view = True
        self._fixed_fit = fixed_fit
        self._last_render_signature = None
        self._render_pending = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.image_label = QLabel(placeholder_text)
        self.image_label.setObjectName("PreviewContentLabel")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setWordWrap(True)

        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("PreviewImageArea")
        self.scroll_area.setProperty("surface_variant", surface_variant)
        self.scroll_area.setWidget(self.image_label)
        self.scroll_area.setWidgetResizable(False)
        self.scroll_area.setAlignment(Qt.AlignCenter)
        self.scroll_area.setFrameShape(QScrollArea.NoFrame)
        if self._fixed_fit:
            self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        else:
            self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setFocusPolicy(Qt.StrongFocus)
        self.scroll_area.viewport().setFocusPolicy(Qt.StrongFocus)
        self.scroll_area.installEventFilter(self)
        self.scroll_area.viewport().installEventFilter(self)
        self.image_label.installEventFilter(self)
        layout.addWidget(self.scroll_area, stretch=1)

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(420)
        self.setFocusPolicy(Qt.StrongFocus)
        self._zoom_shortcuts = []
        if not self._fixed_fit:
            self._install_zoom_shortcuts()
        self._update_controls()

    def has_image(self) -> bool:
        return not self._base_pixmap.isNull()

    def _install_zoom_shortcuts(self):
        shortcut_bindings = (
            ("Ctrl+=", self.zoom_in),
            ("Ctrl++", self.zoom_in),
            ("Ctrl+-", self.zoom_out),
            ("Ctrl+0", self.fit_to_view),
            ("Ctrl+1", self.show_actual_size),
        )
        for sequence_text, handler in shortcut_bindings:
            shortcut = QShortcut(QKeySequence(sequence_text), self)
            shortcut.setContext(Qt.WidgetWithChildrenShortcut)
            shortcut.activated.connect(handler)
            self._zoom_shortcuts.append(shortcut)

    def _schedule_render_pixmap(self):
        if self._render_pending:
            return
        self._render_pending = True
        QTimer.singleShot(0, self._flush_scheduled_render)

    def _flush_scheduled_render(self):
        self._render_pending = False
        self._render_pixmap()

    def clear_image(self, placeholder_text: str):
        self._placeholder_text = placeholder_text
        self._base_pixmap = QPixmap()
        self._scale_factor = 1.0
        self._fit_to_view = True
        self._last_render_signature = None
        self._render_pending = False
        self.image_label.setPixmap(QPixmap())
        self.image_label.setText(placeholder_text)
        self.image_label.adjustSize()
        self._update_controls()

    def set_image(self, image_path: Path | None, placeholder_text: str):
        self._placeholder_text = placeholder_text
        if image_path is None or not image_path.exists():
            self.clear_image(placeholder_text)
            return

        pixmap = QPixmap(str(image_path))
        if pixmap.isNull():
            self.clear_image(placeholder_text)
            return

        self._base_pixmap = pixmap
        self._scale_factor = 1.0
        self._fit_to_view = True
        self._last_render_signature = None
        self._render_pixmap()
        self._update_controls()

    def fit_to_view(self):
        if not self.has_image():
            return
        self._fit_to_view = True
        self._render_pixmap()

    def show_actual_size(self):
        if not self.has_image() or self._fixed_fit:
            return
        self._fit_to_view = False
        self._scale_factor = 1.0
        self._render_pixmap()

    def zoom_in(self):
        if self._fixed_fit:
            return
        self._set_manual_scale(self._current_scale_factor() * 1.2)

    def zoom_out(self):
        if self._fixed_fit:
            return
        self._set_manual_scale(self._current_scale_factor() / 1.2)

    def scroll_up(self):
        self._scroll_vertically(-1)

    def scroll_down(self):
        self._scroll_vertically(1)

    def _set_manual_scale(self, scale_factor: float):
        if not self.has_image() or self._fixed_fit:
            return
        self._fit_to_view = False
        self._scale_factor = max(0.2, min(scale_factor, 6.0))
        self._render_pixmap()

    def _current_scale_factor(self) -> float:
        if not self.has_image():
            return 1.0
        if not self._fit_to_view:
            return self._scale_factor

        viewport = self.scroll_area.viewport().size()
        if viewport.width() <= 0 or viewport.height() <= 0:
            return 1.0
        return min(viewport.width() / self._base_pixmap.width(), viewport.height() / self._base_pixmap.height())

    def _render_pixmap(self):
        if not self.has_image():
            self.clear_image(self._placeholder_text)
            return

        if self._fit_to_view:
            viewport = self.scroll_area.viewport().size()
            target_width = max(1, viewport.width() - 4)
            target_height = max(1, viewport.height() - 4)
            render_signature = ("fit", target_width, target_height, self._base_pixmap.cacheKey())
            if render_signature == self._last_render_signature:
                self._update_controls()
                return
            scaled = self._base_pixmap.scaled(target_width, target_height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            scale_text = "Fit"
        else:
            target_width = max(1, int(round(self._base_pixmap.width() * self._scale_factor)))
            target_height = max(1, int(round(self._base_pixmap.height() * self._scale_factor)))
            render_signature = ("manual", target_width, target_height, self._base_pixmap.cacheKey())
            if render_signature == self._last_render_signature:
                self._update_controls()
                return
            scaled = self._base_pixmap.scaled(target_width, target_height, Qt.KeepAspectRatio, Qt.FastTransformation)
            scale_text = f"{int(round(self._scale_factor * 100))}%"

        self._last_render_signature = render_signature
        self.image_label.setText("")
        self.image_label.setPixmap(scaled)
        self.image_label.resize(scaled.size())
        self.image_label.adjustSize()
        self._update_controls(scale_text=scale_text)

    def _handle_ctrl_wheel_zoom(self, event, cursor_pos=None):
        if not self.isVisible() or not self.scroll_area.isVisible():
            return
        delta = event.angleDelta().y() or event.angleDelta().x()
        if delta == 0:
            return

        if cursor_pos is None:
            cursor_pos = self.scroll_area.viewport().rect().center()
        h_bar = self.scroll_area.horizontalScrollBar()
        v_bar = self.scroll_area.verticalScrollBar()
        old_scale = max(self._current_scale_factor(), 1.0e-6)
        old_h = h_bar.value()
        old_v = v_bar.value()

        scale_factor = old_scale * (1.15 if delta > 0 else 1.0 / 1.15)
        self._set_manual_scale(scale_factor)
        new_scale = max(self._current_scale_factor(), 1.0e-6)
        scale_ratio = new_scale / old_scale

        h_bar.setValue(int(round((old_h + cursor_pos.x()) * scale_ratio - cursor_pos.x())))
        v_bar.setValue(int(round((old_v + cursor_pos.y()) * scale_ratio - cursor_pos.y())))

    def _scroll_vertically(self, direction: int):
        scrollbar = self.scroll_area.verticalScrollBar()
        step = max(60, int(round(self.scroll_area.viewport().height() * 0.18)))
        scrollbar.setValue(scrollbar.value() + direction * step)

    def _update_controls(self, scale_text: str | None = None):
        if self._fixed_fit:
            tooltip = "Fixed fit preview"
        else:
            tooltip = "Ctrl+Wheel: zoom\nCtrl+=/-: zoom\nCtrl+0: fit\nCtrl+1: actual size\nDouble-click: fit / actual size"
        if scale_text is not None:
            tooltip = f"{tooltip}\nCurrent Scale: {scale_text}"
        self.scroll_area.viewport().setToolTip(tooltip)

    def eventFilter(self, watched, event):
        if watched in {self.scroll_area, self.scroll_area.viewport(), self.image_label} and self.isVisible():
            if self._fixed_fit and event.type() == QEvent.Wheel and (event.modifiers() & Qt.ControlModifier):
                return True
            if not self._fixed_fit and event.type() == QEvent.Wheel and self.has_image() and (event.modifiers() & Qt.ControlModifier):
                cursor_pos = event.pos()
                if watched is not self.scroll_area.viewport():
                    cursor_pos = watched.mapTo(self.scroll_area.viewport(), event.pos())
                self._handle_ctrl_wheel_zoom(event, cursor_pos)
                return True
            if not self._fixed_fit and event.type() == QEvent.MouseButtonDblClick and self.has_image():
                if self._fit_to_view:
                    self.show_actual_size()
                else:
                    self.fit_to_view()
                return True
        return super().eventFilter(watched, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._fit_to_view and self.has_image():
            self._schedule_render_pixmap()


class ProtocolJuliaWorker(QThread):
    log_line = pyqtSignal(str)
    progress_update = pyqtSignal(float)
    step_update = pyqtSignal(float, float, float, int)
    snapshot_update = pyqtSignal(str)
    vtk_update = pyqtSignal(str)
    displacement_update = pyqtSignal(str)
    status_update = pyqtSignal(str)
    finished_state = pyqtSignal(bool, str, str, str)

    def __init__(self, case_id: str, protocol_case_name: str, params_path: Path, run_mode: str):
        super().__init__()
        self.case_id = case_id
        self.protocol_case_name = protocol_case_name
        self.params_path = params_path
        self.run_mode = run_mode
        self._process = None
        self._stop_requested = False

    def stop(self):
        self._stop_requested = True
        STOP_FLAG.write_text("stop\n", encoding="utf-8")
        self.status_update.emit("Stopping solver...")

    def run(self):
        solver_path = GUI_DIR / "gui_solver.jl"
        cmd = f'{julia_env_prefix()}{JULIA_COMMAND} "{solver_path}" "{self.params_path}"'
        stage_label = "mesh" if self.run_mode == "mesh" else "compute"
        self.status_update.emit(f"Launching Julia {self.protocol_case_name} {stage_label} stage...")
        self._process = subprocess.Popen(
            ["bash", "-lc", cmd],
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=julia_subprocess_env(),
        )

        success = False
        message = "Solver finished."
        try:
            assert self._process.stdout is not None
            for raw_line in self._process.stdout:
                line = raw_line.rstrip()
                if not line:
                    continue
                self.log_line.emit(line)
                self._handle_protocol(line)

            return_code = self._process.wait()
            if self._stop_requested:
                success = True
                message = "Stopped by user."
            elif return_code == 0:
                success = True
                message = "Mesh generated." if self.run_mode == "mesh" else "Run completed."
            else:
                message = f"Solver exited with code {return_code}."
        except Exception as exc:
            message = f"Worker error: {exc}"
            self.log_line.emit(message)
        finally:
            self.finished_state.emit(success, self.case_id, self.run_mode, message)

    def _handle_protocol(self, line: str):
        if line.startswith("INFO "):
            self.status_update.emit(line[5:])
            return
        if line.startswith("ERROR "):
            self.status_update.emit(line)
            return
        if line.startswith("PROGRESS "):
            try:
                self.progress_update.emit(float(line.split()[1]))
            except (IndexError, ValueError):
                pass
            return
        if line.startswith("SNAPSHOT "):
            self.snapshot_update.emit(line.split(" ", 1)[1])
            return
        if line.startswith("VTK "):
            self.vtk_update.emit(line.split(" ", 1)[1])
            return
        if line.startswith("DISPLACEMENT "):
            self.displacement_update.emit(line.split(" ", 1)[1])
            return
        if line.startswith("DONE"):
            self.status_update.emit("Solver finished.")
            if self.run_mode == "compute":
                self.progress_update.emit(100.0)
            return
        if not line.startswith("STEP "):
            return

        tokens = line.split()
        try:
            step = int(tokens[1])
            u_value = float(tokens[3])
            f_value = float(tokens[5])
            dmax = float(tokens[7])
        except (IndexError, ValueError):
            return
        self.step_update.emit(u_value, f_value * 1.0e-3, dmax, step)


class BatchJuliaWorker(QThread):
    log_line = pyqtSignal(str)
    progress_update = pyqtSignal(float)
    step_update = pyqtSignal(float, float, float, int)
    snapshot_update = pyqtSignal(str)
    vtk_update = pyqtSignal(str)
    displacement_update = pyqtSignal(str)
    status_update = pyqtSignal(str)
    finished_state = pyqtSignal(bool, str, str, str)

    def __init__(self, case_id: str, script_path: Path, params_path: Path, run_mode: str):
        super().__init__()
        self.case_id = case_id
        self.script_path = script_path
        self.params_path = params_path
        self.run_mode = run_mode
        self._process = None
        self._stop_requested = False

    def stop(self):
        self._stop_requested = True
        self.status_update.emit("Stopping benchmark...")
        if self._process is not None and self._process.poll() is None:
            self._process.terminate()

    def run(self):
        cmd = f'{julia_env_prefix()}{JULIA_COMMAND} "{self.script_path}" "{self.params_path}"'
        stage_label = "mesh" if self.run_mode == "mesh" else "compute"
        self.status_update.emit(f"Launching benchmark script: {self.script_path.name} [{stage_label}]")
        self._process = subprocess.Popen(
            ["bash", "-lc", cmd],
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=julia_subprocess_env(),
        )

        success = False
        message = "Benchmark finished."
        try:
            assert self._process.stdout is not None
            for raw_line in self._process.stdout:
                line = raw_line.rstrip()
                if not line:
                    continue
                self.log_line.emit(line)
                self.status_update.emit(line)
            return_code = self._process.wait()
            if self._stop_requested:
                success = True
                message = "Stopped by user."
            elif return_code == 0:
                success = True
                self.progress_update.emit(100.0)
                message = "Batch mesh completed." if self.run_mode == "mesh" else "Batch benchmark completed."
            else:
                message = f"Benchmark exited with code {return_code}."
        except Exception as exc:
            message = f"Worker error: {exc}"
            self.log_line.emit(message)
        finally:
            self.finished_state.emit(success, self.case_id, self.run_mode, message)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("")
        self.resize(1560, 940)

        self.worker = None
        self.active_run_mode = None
        self.active_case_id = None
        self.active_run_profile = None
        self.runtime_params_path = None
        self.active_run_id = None
        self.active_run_dir = None
        self.active_native_output_dir = None
        self.active_mesh_artifact_path = None
        self._syncing_inputs = False
        self._syncing_history = False
        self._syncing_selection = False
        self._syncing_run_profile = False
        self._syncing_scan_table = False
        self._syncing_postprocess_view = False
        self._syncing_postprocess_timeline = False
        self._postprocess_timeline_paths: list[str] = []
        self._entrance_animation_started = False
        self._progress_animation = None
        self._button_hover_animations = {}
        self._button_rest_geometries = {}
        self._section_animations = {}
        self._section_bindings_by_widget = {}
        self._toast_animation = None
        self._toast_hide_timer = QTimer(self)
        self._toast_hide_timer.setSingleShot(True)
        self._toast_hide_timer.timeout.connect(self._hide_toast)
        self._compute_curve_collapsed = False
        self.keep_transient_results = load_transient_cache_preference()

        self.run_profile_overrides = {}
        self.default_scan_cases = {}
        self.default_params = self._load_default_params()
        self.current_category = CATEGORY_ORDER[0]
        self.current_case = first_case_for_category(self.current_category).case_id
        self.case_states = {case.case_id: self._new_case_state(case.case_id) for case in CASE_REGISTRY}

        self.inputs = {}
        self.field_bindings = {}
        self.section_bindings = []

        self._build_ui()
        self._apply_theme()
        self.toast_label = self._build_toast_label(self.centralWidget())
        self._register_animated_buttons()
        self._sync_transient_cache_button()
        self._load_manifests_from_disk()
        self._sync_category_combo()
        self._refresh_case_combo(self.current_category, preferred_case_id=self.current_case)
        self._apply_case_params_to_inputs(self.current_case)
        self._apply_case_state_to_ui()
        self._set_idle_state()

    def _load_default_params(self):
        with DEFAULT_PARAMS_PATH.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)

        common = {key: self._format_value(value) for key, value in raw["common"].items()}
        case_defaults_raw = raw.get("case_defaults", {})
        self.run_profile_overrides = {
            case_id: {profile: dict(values) for profile, values in profile_map.items()}
            for case_id, profile_map in raw.get("run_profiles", {}).items()
        }
        self.default_scan_cases = {
            case_id: [
                {key: self._format_value(value) for key, value in row.items()}
                for row in rows
            ]
            for case_id, rows in raw.get("scan_defaults", {}).items()
        }
        defaults = {}
        for case in CASE_REGISTRY:
            merged = {}
            if case.protocol_case_name:
                merged.update(common)
                merged.update(
                    {
                        key: self._format_value(value)
                        for key, value in raw["cases"].get(case.protocol_case_name, {}).items()
                    }
                )
            merged.update(
                {
                    key: self._format_value(value)
                    for key, value in case_defaults_raw.get(case.case_id, {}).items()
                }
            )
            defaults[case.case_id] = merged
        return defaults

    def _format_value(self, value):
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, int):
            return str(value)
        if isinstance(value, float):
            return format(value, ".15g")
        return str(value)

    def _clone_default_scan_cases(self, case_id: str):
        return [dict(row) for row in self.default_scan_cases.get(case_id, [])]

    def _run_profile_overrides_for_case(self, case_id: str):
        return self.run_profile_overrides.get(case_id, {})

    def _scan_columns_for_case(self, case_id: str):
        case = CASE_DEFINITIONS[case_id]
        return SCAN_EDITOR_SPECS.get(case.scan_editor_kind, ())

    def _default_scan_row(self, case_id: str, row_index: int):
        row = {}
        for column_index, column in enumerate(self._scan_columns_for_case(case_id)):
            if column.input_type == "str":
                row[column.key] = f"case_{row_index + 1}" if column_index == 0 else ""
            else:
                row[column.key] = "0"
        return row

    def _collect_scan_cases(self, case):
        return serialize_scan_cases(self.case_states[case.case_id]["scan_cases"], self._scan_columns_for_case(case.case_id))

    def _new_case_state(self, case_id: str):
        case = CASE_DEFINITIONS[case_id]
        return {
            "params": dict(self.default_params.get(case_id, {})),
            "run_profile": normalize_run_profile(case.default_run_profile, fallback="full"),
            "scan_cases": self._clone_default_scan_cases(case_id),
            "mesh_ready": False,
            "mesh_artifact_path": None,
            "mesh_preview_path": None,
            "mesh_status": self._default_mesh_status(case),
            "compute_completed": False,
            "curve_x": [],
            "curve_y": [],
            "compute_status": self._default_compute_status(case),
            "progress": 0,
            "latest_damage_path": None,
            "latest_displacement_path": None,
            "latest_vtk_path": "",
            "visual_export_paths": {},
            "log_lines": [],
            "history_selection": {view_name: None for view_name in POSTPROCESS_VIEWS},
            "manifest_path": None,
            "manifest": None,
            "run_id": None,
            "run_dir": None,
            "runtime_params_path": None,
        }

    def _current_case_def(self):
        return CASE_DEFINITIONS[self.current_case]

    def _active_case_def(self):
        return CASE_DEFINITIONS[self.active_case_id or self.current_case]

    def _current_state(self):
        return self.case_states[self.current_case]

    def _active_state(self):
        return self.case_states[self.active_case_id or self.current_case]

    def _default_mesh_status(self, case):
        if not case.is_ready:
            return "Planned case. Compute is not available yet."
        if not case.mesh_stage_enabled:
            return "This benchmark builds its mesh during compute."
        return "Mesh not generated."

    def _default_compute_status(self, case):
        if not case.is_ready:
            return "Planned case. Waiting for future integration."
        return "Waiting for compute stage."

    def _case_header_summary(self, case):
        return CASE_HEADER_SUMMARIES.get(
            case.case_id,
            f"{case.display_name} benchmark in {case.category_label} with mesh, solve, and post-process workflow.",
        )

    def _case_badge_text(self, case):
        return CASE_BADGE_LABELS.get(case.case_id, f"{case.category_label} · {case.display_name}")

    def _build_ui(self):
        root = QWidget()
        root.setObjectName("AppRoot")
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(18, 18, 18, 18)
        root_layout.setSpacing(16)

        header_card = QWidget()
        header_card.setObjectName("HeaderCard")
        header_layout = QVBoxLayout(header_card)
        header_layout.setContentsMargins(24, 22, 24, 20)
        header_layout.setSpacing(14)

        top_row = QHBoxLayout()
        top_row.setSpacing(16)
        self.header_top_layout = top_row

        title_block = QWidget()
        title_block.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        title_layout = QVBoxLayout(title_block)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(8)
        self.window_title_label = QLabel("Phase-Field Fracture Workbench")
        self.window_title_label.setObjectName("WindowTitleLabel")
        self.window_title_label.setWordWrap(True)
        title_layout.addWidget(self.window_title_label)
        self.window_subtitle_label = QLabel("")
        self.window_subtitle_label.setObjectName("WindowSubtitleLabel")
        self.window_subtitle_label.setWordWrap(True)
        title_layout.addWidget(self.window_subtitle_label)
        top_row.addWidget(title_block, stretch=1)

        controls_card = QWidget()
        controls_card.setObjectName("ToolbarCard")
        controls_layout = QHBoxLayout(controls_card)
        controls_layout.setContentsMargins(14, 12, 14, 12)
        controls_layout.setSpacing(12)
        self.header_controls_layout = controls_layout

        self.category_combo = QComboBox()
        self.category_combo.currentIndexChanged.connect(self.on_category_combo_changed)
        controls_layout.addWidget(self._build_control_stack("Category", self.category_combo))

        self.case_combo = QComboBox()
        self.case_combo.currentIndexChanged.connect(self.on_case_combo_changed)
        controls_layout.addWidget(self._build_control_stack("Case", self.case_combo))
        top_row.addWidget(controls_card, stretch=0)
        header_layout.addLayout(top_row)

        self.case_status_badge = QLabel("")
        self.case_status_badge.setObjectName("CaseStatusBadge")
        self.case_status_badge.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.case_status_badge.setWordWrap(False)
        badge_row = QHBoxLayout()
        badge_row.setContentsMargins(0, 0, 0, 0)
        badge_row.setSpacing(12)
        badge_row.addWidget(self.case_status_badge)
        self.more_button = QToolButton()
        self.more_button.setText("More")
        self.more_button.setPopupMode(QToolButton.InstantPopup)
        self.more_button.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.more_button.setProperty("subtle_tool_button", True)
        self.more_menu = QMenu(self.more_button)
        self.more_menu.setObjectName("HeaderMenu")
        self.keep_cache_action = QAction("Keep Temp Cache", self)
        self.keep_cache_action.setCheckable(True)
        self.keep_cache_action.toggled.connect(self.on_keep_cache_toggled)
        self.more_menu.addAction(self.keep_cache_action)
        self.more_button.setMenu(self.more_menu)
        badge_row.addWidget(self.more_button, stretch=0)
        badge_row.addStretch(1)
        header_layout.addLayout(badge_row)
        root_layout.addWidget(header_card)
        self.header_card = header_card
        self.controls_card = controls_card

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.currentChanged.connect(self.on_tab_changed)
        self.mesh_tab_index = self.tabs.addTab(self._build_mesh_tab(), "Mesh")
        self.compute_tab_index = self.tabs.addTab(self._build_compute_tab(), "Compute")
        self.post_tab_index = self.tabs.addTab(self._build_postprocess_tab(), "Post-Process")
        root_layout.addWidget(self.tabs)
        self.setCentralWidget(root)

    def _build_mesh_tab(self):
        page = QWidget()
        page.setObjectName("TabPage")
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        self.mesh_main_layout = layout

        left_panel = QWidget()
        left_panel.setObjectName("PanelCard")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(18, 18, 18, 18)
        left_layout.setSpacing(12)

        self.mesh_intro_label = QLabel("")
        self.mesh_intro_label.setObjectName("IntroLabel")
        self.mesh_intro_label.setWordWrap(True)
        left_layout.addWidget(self.mesh_intro_label)

        for group_title, fields in MESH_FIELD_SPECS:
            section_binding = self._make_form_section(group_title)
            box = section_binding["section"]
            form = section_binding["form"]
            for field in fields:
                line_edit = QLineEdit(self._current_state()["params"].get(field.key, ""))
                line_edit.textChanged.connect(lambda _text, field_key=field.key, mesh_field=True: self.on_input_changed(field_key, mesh_field))
                form.addRow(field.label, line_edit)
                self.inputs[field.key] = line_edit
                self.field_bindings[field.key] = {"widget": line_edit, "form": form, "section": section_binding}
                section_binding["field_keys"].append(field.key)
            left_layout.addWidget(box)

        self.mesh_empty_label = QLabel("This case has no editable mesh parameters in the GUI.")
        self.mesh_empty_label.setObjectName("HintLabel")
        self.mesh_empty_label.setWordWrap(True)
        left_layout.addWidget(self.mesh_empty_label)

        self.generate_mesh_button = QPushButton("Generate Mesh")
        self.generate_mesh_button.setProperty("variant", "primary")
        self.generate_mesh_button.clicked.connect(self.start_mesh_generation)
        left_layout.addWidget(self.generate_mesh_button)

        self.mesh_status_label = QLabel("")
        self.mesh_status_label.setObjectName("StatusCard")
        self.mesh_status_label.setWordWrap(True)
        left_layout.addWidget(self.mesh_status_label)
        left_layout.addStretch(1)
        self.mesh_left_panel = left_panel
        self.mesh_left_scroll = self._wrap_panel_scroll(left_panel)

        self.mesh_preview_label = self._create_image_viewer("Mesh preview will appear here.")
        mesh_preview_card = QWidget()
        mesh_preview_card.setObjectName("PreviewCard")
        mesh_preview_layout = QVBoxLayout(mesh_preview_card)
        mesh_preview_layout.setContentsMargins(18, 16, 18, 18)
        mesh_preview_layout.setSpacing(10)
        mesh_preview_layout.addWidget(self._create_section_label("Mesh Preview"))
        mesh_preview_layout.addWidget(self.mesh_preview_label, stretch=1)
        self.mesh_preview_card = mesh_preview_card
        layout.addWidget(self.mesh_left_scroll, stretch=0)
        layout.addWidget(mesh_preview_card, stretch=1)
        return page

    def _make_form_section(self, group_title: str):
        box = QGroupBox(group_title)
        form = QFormLayout(box)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        binding = {
            "section": box,
            "form": form,
            "field_keys": [],
            "title": group_title,
            "expanded": True,
            "collapsed_height": 46,
        }
        box.setProperty("collapsible_section", True)
        box.setProperty("expanded", True)
        box.installEventFilter(self)
        self._set_section_title(binding)
        self.section_bindings.append(binding)
        self._section_bindings_by_widget[box] = binding
        return binding

    def _build_compute_tab(self):
        page = QWidget()
        page.setObjectName("TabPage")
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        self.compute_main_layout = layout

        left_panel = QWidget()
        left_panel.setObjectName("PanelCard")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(18, 18, 18, 18)
        left_layout.setSpacing(12)

        self.compute_intro_label = QLabel("")
        self.compute_intro_label.setObjectName("IntroLabel")
        self.compute_intro_label.setWordWrap(True)
        left_layout.addWidget(self.compute_intro_label)

        for group_title, fields in COMPUTE_FIELD_SPECS:
            section_binding = self._make_form_section(group_title)
            box = section_binding["section"]
            form = section_binding["form"]
            for field in fields:
                line_edit = QLineEdit(self._current_state()["params"].get(field.key, ""))
                line_edit.textChanged.connect(lambda _text, field_key=field.key, mesh_field=False: self.on_input_changed(field_key, mesh_field))
                form.addRow(field.label, line_edit)
                self.inputs[field.key] = line_edit
                self.field_bindings[field.key] = {"widget": line_edit, "form": form, "section": section_binding}
                section_binding["field_keys"].append(field.key)
            left_layout.addWidget(box)

        self.compute_empty_label = QLabel("This case currently runs with its benchmark defaults.")
        self.compute_empty_label.setObjectName("HintLabel")
        self.compute_empty_label.setWordWrap(True)
        left_layout.addWidget(self.compute_empty_label)

        self.run_profile_box = QGroupBox("Run Profile")
        run_profile_layout = QHBoxLayout(self.run_profile_box)
        run_profile_layout.addWidget(self._create_control_label("Profile"))
        self.run_profile_combo = QComboBox()
        for profile_id in RUN_PROFILE_ORDER:
            self.run_profile_combo.addItem(RUN_PROFILE_LABELS[profile_id], profile_id)
        self.run_profile_combo.currentIndexChanged.connect(self.on_run_profile_changed)
        run_profile_layout.addWidget(self.run_profile_combo, stretch=1)
        left_layout.addWidget(self.run_profile_box)

        self.scan_editor_box = QGroupBox("Scan Cases")
        scan_layout = QVBoxLayout(self.scan_editor_box)
        self.scan_editor_intro_label = QLabel("Edit the scan list for this benchmark.")
        self.scan_editor_intro_label.setWordWrap(True)
        scan_layout.addWidget(self.scan_editor_intro_label)
        self.scan_table = QTableWidget(0, 0)
        self.scan_table.verticalHeader().setVisible(False)
        self.scan_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.scan_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.scan_table.itemChanged.connect(self.on_scan_item_changed)
        self.scan_table.itemSelectionChanged.connect(self.on_scan_selection_changed)
        scan_layout.addWidget(self.scan_table)
        scan_button_row = QHBoxLayout()
        self.scan_button_layout = scan_button_row
        self.scan_add_button = QPushButton("Add")
        self.scan_remove_button = QPushButton("Remove")
        self.scan_reset_button = QPushButton("Reset Default")
        self.scan_add_button.setProperty("variant", "secondary")
        self.scan_remove_button.setProperty("variant", "secondary")
        self.scan_reset_button.setProperty("variant", "secondary")
        self.scan_add_button.clicked.connect(self.on_scan_add_row)
        self.scan_remove_button.clicked.connect(self.on_scan_remove_row)
        self.scan_reset_button.clicked.connect(self.on_scan_reset_default)
        scan_button_row.addWidget(self.scan_add_button)
        scan_button_row.addWidget(self.scan_remove_button)
        scan_button_row.addWidget(self.scan_reset_button)
        scan_layout.addLayout(scan_button_row)
        left_layout.addWidget(self.scan_editor_box)

        button_row = QHBoxLayout()
        self.compute_action_layout = button_row
        self.run_button = QPushButton("Run")
        self.stop_button = QPushButton("Stop")
        self.run_button.setProperty("variant", "primary")
        self.stop_button.setProperty("variant", "danger")
        self.run_button.clicked.connect(self.start_run)
        self.stop_button.clicked.connect(self.stop_run)
        button_row.addWidget(self.run_button)
        button_row.addWidget(self.stop_button)
        left_layout.addLayout(button_row)

        self.compute_status_label = QLabel("")
        self.compute_status_label.setObjectName("StatusCard")
        self.compute_status_label.setWordWrap(True)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        left_layout.addWidget(self.compute_status_label)
        left_layout.addWidget(self.progress_bar)

        self.log_box = QPlainTextEdit()
        self.log_box.setObjectName("LogPanel")
        self.log_box.setReadOnly(True)
        self.log_box.setMaximumBlockCount(500)
        left_layout.addWidget(self.log_box, stretch=1)
        self.compute_left_panel = left_panel
        self.compute_left_scroll = self._wrap_panel_scroll(left_panel)

        right_panel = QWidget()
        right_panel.setObjectName("PreviewCard")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(18, 18, 18, 18)
        right_layout.setSpacing(16)

        right_layout.addWidget(self._create_section_label("Live Preview"))
        preview_row = QWidget()
        preview_row_layout = QBoxLayout(QBoxLayout.LeftToRight, preview_row)
        preview_row_layout.setContentsMargins(0, 0, 0, 0)
        preview_row_layout.setSpacing(14)
        self.compute_top_preview_layout = preview_row_layout

        damage_card = QWidget()
        damage_card.setObjectName("NestedPreviewCard")
        damage_layout = QVBoxLayout(damage_card)
        damage_layout.setContentsMargins(16, 14, 16, 16)
        damage_layout.setSpacing(10)
        damage_layout.addWidget(self._create_section_label("Damage Contour"))
        self.damage_label = self._create_image_viewer(
            "Damage snapshot will appear here.",
            surface_variant="borderless",
            fixed_fit=True,
        )
        self.damage_label.setMinimumHeight(320)
        self.damage_surface = self._create_preview_surface(self.damage_label)
        damage_layout.addWidget(self.damage_surface, stretch=1)
        preview_row_layout.addWidget(damage_card, stretch=1)

        displacement_card = QWidget()
        displacement_card.setObjectName("NestedPreviewCard")
        displacement_layout = QVBoxLayout(displacement_card)
        displacement_layout.setContentsMargins(16, 14, 16, 16)
        displacement_layout.setSpacing(10)
        displacement_layout.addWidget(self._create_section_label("Displacement Contour"))
        self.displacement_label = self._create_image_viewer(
            "Displacement snapshot will appear here.",
            surface_variant="borderless",
            fixed_fit=True,
        )
        self.displacement_label.setMinimumHeight(320)
        self.displacement_surface = self._create_preview_surface(self.displacement_label)
        displacement_layout.addWidget(self.displacement_surface, stretch=1)
        preview_row_layout.addWidget(displacement_card, stretch=1)

        curve_card = QWidget()
        curve_card.setObjectName("NestedPreviewCard")
        curve_layout = QVBoxLayout(curve_card)
        curve_layout.setContentsMargins(16, 14, 16, 16)
        curve_layout.setSpacing(10)
        curve_header = QWidget()
        curve_header_layout = QHBoxLayout(curve_header)
        curve_header_layout.setContentsMargins(0, 0, 0, 0)
        curve_header_layout.setSpacing(10)
        curve_header_layout.addWidget(self._create_section_label("Live Curve"))
        curve_header_layout.addStretch(1)
        self.curve_toggle_button = QPushButton("▾")
        self.curve_toggle_button.setToolTip("Collapse live curve")
        self.curve_toggle_button.setProperty("icon_button", True)
        self.curve_toggle_button.setProperty("variant", "secondary")
        self.curve_toggle_button.clicked.connect(self.toggle_compute_curve_card)
        curve_header_layout.addWidget(self.curve_toggle_button, stretch=0)
        curve_layout.addWidget(curve_header)
        self.curve_canvas = CurveCanvas()
        self.curve_canvas.setObjectName("CurveCanvas")
        self.curve_surface = self._create_preview_surface(self.curve_canvas)
        curve_layout.addWidget(self.curve_surface, stretch=1)
        right_layout.addWidget(preview_row, stretch=3)
        right_layout.addWidget(curve_card, stretch=0)
        self.compute_preview_row = preview_row
        self.compute_damage_card = damage_card
        self.compute_displacement_card = displacement_card
        self.compute_curve_card = curve_card
        self.compute_preview_card = right_panel

        layout.addWidget(self.compute_left_scroll, stretch=0)
        layout.addWidget(right_panel, stretch=1)
        return page

    def _build_postprocess_tab(self):
        page = QWidget()
        page.setObjectName("TabPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        toolbar_card = QWidget()
        toolbar_card.setObjectName("PanelCard")
        toolbar_layout = QVBoxLayout(toolbar_card)
        toolbar_layout.setContentsMargins(18, 16, 18, 16)
        toolbar_layout.setSpacing(10)

        controls_row = QHBoxLayout()
        controls_row.setSpacing(12)
        self.postprocess_controls_layout = controls_row
        self.postprocess_view_combo = QComboBox()
        self.postprocess_view_combo.currentTextChanged.connect(self.on_postprocess_view_changed)
        self.postprocess_view_stack = self._build_control_stack("View", self.postprocess_view_combo)
        controls_row.addWidget(self.postprocess_view_stack)

        self.history_combo = QComboBox()
        self.history_combo.currentIndexChanged.connect(self.on_history_changed)
        self.postprocess_history_stack = self._build_control_stack("History", self.history_combo)
        controls_row.addWidget(self.postprocess_history_stack, stretch=1)
        toolbar_layout.addLayout(controls_row)

        action_row = QHBoxLayout()
        action_row.setSpacing(12)
        self.postprocess_action_layout = action_row
        self.export_results_button = QPushButton("Save Results")
        self.export_results_button.setProperty("variant", "primary")
        self.export_results_button.clicked.connect(self.export_results)
        action_row.addWidget(self.export_results_button)
        action_row.addStretch(1)
        toolbar_layout.addLayout(action_row)

        self.postprocess_stack = QStackedWidget()
        self.postprocess_stack.setObjectName("PreviewSurface")
        self.postprocess_stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.postprocess_image_panel = QWidget()
        self.postprocess_image_panel.setObjectName("PostprocessImagePanel")
        postprocess_image_layout = QVBoxLayout(self.postprocess_image_panel)
        postprocess_image_layout.setContentsMargins(0, 0, 0, 0)
        postprocess_image_layout.setSpacing(10)
        self.postprocess_label = self._create_image_viewer("Post-process output will appear here.", fixed_fit=True)
        postprocess_image_layout.addWidget(self.postprocess_label, stretch=1)
        self.postprocess_timeline_row = QWidget()
        postprocess_timeline_layout = QHBoxLayout(self.postprocess_timeline_row)
        postprocess_timeline_layout.setContentsMargins(0, 0, 0, 0)
        postprocess_timeline_layout.setSpacing(10)
        self.postprocess_timeline_title = QLabel("Timeline")
        self.postprocess_timeline_title.setObjectName("ControlLabel")
        self.postprocess_timeline_slider = QSlider(Qt.Horizontal)
        self.postprocess_timeline_slider.setMinimum(0)
        self.postprocess_timeline_slider.setMaximum(0)
        self.postprocess_timeline_slider.setSingleStep(1)
        self.postprocess_timeline_slider.setPageStep(1)
        self.postprocess_timeline_slider.setTracking(True)
        self.postprocess_timeline_slider.valueChanged.connect(self.on_postprocess_timeline_changed)
        self.postprocess_timeline_value_label = QLabel("Frame 1 / 1")
        self.postprocess_timeline_value_label.setObjectName("MetaCard")
        self.postprocess_timeline_value_label.setMinimumWidth(180)
        self.postprocess_timeline_value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        postprocess_timeline_layout.addWidget(self.postprocess_timeline_title)
        postprocess_timeline_layout.addWidget(self.postprocess_timeline_slider, stretch=1)
        postprocess_timeline_layout.addWidget(self.postprocess_timeline_value_label)
        self.postprocess_timeline_row.hide()
        postprocess_image_layout.addWidget(self.postprocess_timeline_row)
        self.postprocess_curve_canvas = CurveCanvas()
        self.postprocess_curve_canvas.setObjectName("CurveCanvas")
        self.postprocess_curve_canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.postprocess_table = QTableWidget(0, 0)
        self.postprocess_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.postprocess_table.setSelectionMode(QTableWidget.NoSelection)
        self.postprocess_table.verticalHeader().setVisible(False)
        self.postprocess_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.postprocess_stack.addWidget(self.postprocess_image_panel)
        self.postprocess_stack.addWidget(self.postprocess_curve_canvas)
        self.postprocess_stack.addWidget(self.postprocess_table)
        toolbar_layout.addWidget(self.postprocess_stack, stretch=1)

        self.vtk_label = QLabel("Latest VTK: None")
        self.vtk_label.setObjectName("MetaCard")
        self.vtk_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        toolbar_layout.addWidget(self.vtk_label)

        self.postprocess_detail_label = QLabel("")
        self.postprocess_detail_label.setObjectName("MetaCard")
        self.postprocess_detail_label.setWordWrap(True)
        self.postprocess_detail_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        toolbar_layout.addWidget(self.postprocess_detail_label)
        self.postprocess_scroll = self._wrap_panel_scroll(toolbar_card)
        layout.addWidget(self.postprocess_scroll)
        self.postprocess_toolbar_card = toolbar_card
        return page

    def _build_toast_label(self, parent: QWidget):
        label = QLabel(parent)
        label.setObjectName("ToastLabel")
        label.setWordWrap(True)
        label.hide()
        return label

    def _create_image_viewer(self, text: str, *, surface_variant: str = "framed", fixed_fit: bool = False):
        return ImagePreviewWidget(text, surface_variant=surface_variant, fixed_fit=fixed_fit)

    def _create_image_label(self, text: str):
        label = QLabel(text)
        label.setObjectName("PreviewLabel")
        label.setAlignment(Qt.AlignCenter)
        label.setMinimumHeight(420)
        label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        label.setWordWrap(True)
        return label

    def _build_control_stack(self, label_text: str, widget: QWidget):
        stack = QWidget()
        stack_layout = QVBoxLayout(stack)
        stack_layout.setContentsMargins(0, 0, 0, 0)
        stack_layout.setSpacing(6)
        stack_layout.addWidget(self._create_control_label(label_text))
        widget.setMinimumWidth(190)
        stack_layout.addWidget(widget)
        return stack

    def _wrap_panel_scroll(self, content: QWidget):
        scroll = QScrollArea()
        scroll.setObjectName("PanelScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        return scroll

    def _create_control_label(self, text: str):
        label = QLabel(text)
        label.setObjectName("ControlLabel")
        return label

    def _create_section_label(self, text: str):
        label = QLabel(text)
        label.setObjectName("SectionLabel")
        return label

    def _create_preview_surface(self, widget: QWidget):
        frame = QWidget()
        frame.setObjectName("PreviewInnerFrame")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(0)
        layout.addWidget(widget, stretch=1)
        return frame

    def _apply_theme(self):
        self.setStyleSheet(
            f"""
            QWidget#AppRoot {{
                background: #dbe3eb;
            }}
            QWidget#HeaderCard,
            QWidget#PanelCard,
            QWidget#PreviewCard,
            QWidget#ToolbarCard {{
                background: #edf3f8;
                border: 1px solid #bccbda;
                border-radius: 18px;
            }}
            QWidget#NestedPreviewCard {{
                background: #f4f7fa;
                border: 1px solid #cad4df;
                border-radius: 16px;
            }}
            QWidget#PreviewInnerFrame {{
                background: #ffffff;
                border: 1px solid #c5cfda;
                border-radius: 14px;
            }}
            QScrollArea#PreviewImageArea[surface_variant="borderless"] {{
                background: transparent;
                border: none;
                border-radius: 0px;
            }}
            QLabel#WindowTitleLabel {{
                color: #0e1b2a;
                font-size: {TITLE_FONT_SIZE}px;
                font-weight: 700;
            }}
            QLabel#WindowSubtitleLabel {{
                color: #4f5f73;
                font-size: {SUBTITLE_FONT_SIZE}px;
                font-weight: 600;
            }}
            QLabel#ControlLabel {{
                color: #4e5f73;
                font-size: 13px;
                font-weight: 600;
                letter-spacing: 0.08em;
                text-transform: uppercase;
            }}
            QLabel#SectionLabel {{
                color: #15273a;
                font-size: 20px;
                font-weight: 700;
            }}
            QLabel#CaseStatusBadge {{
                color: #17324f;
                background: #d7e3ef;
                border: 1px solid #aebfd3;
                border-radius: 12px;
                min-width: 470px;
                padding: 8px 18px;
                font-size: 18px;
                font-weight: 600;
            }}
            QLabel#IntroLabel,
            QLabel#HintLabel,
            QLabel#StatusCard,
            QLabel#MetaCard {{
                border-radius: 12px;
                padding: 12px 14px;
            }}
            QLabel#IntroLabel {{
                color: #24405d;
                background: #dde8f3;
                border: 1px solid #bfd0e1;
            }}
            QLabel#HintLabel {{
                color: #47596d;
                background: #ebf0f5;
                border: 1px dashed #c2cdda;
            }}
            QLabel#StatusCard {{
                color: #18314a;
                background: #dce8f5;
                border: 1px solid #b9ccde;
                font-weight: 600;
            }}
            QLabel#MetaCard {{
                color: #3f5166;
                background: #e7edf4;
                border: 1px solid #c2cdd8;
            }}
            QLabel#ToastLabel {{
                color: #ffffff;
                background: rgba(18, 34, 53, 232);
                border: 1px solid rgba(255, 255, 255, 24);
                border-radius: 14px;
                padding: 12px 14px;
                font-weight: 600;
            }}
            QLabel#ToastLabel[tone="success"] {{
                background: rgba(24, 82, 58, 232);
            }}
            QLabel#ToastLabel[tone="warning"] {{
                background: rgba(142, 82, 28, 234);
            }}
            QLabel#ToastLabel[tone="error"] {{
                background: rgba(128, 38, 40, 234);
            }}
            QLabel#PreviewLabel,
            QScrollArea#PreviewImageArea,
            QStackedWidget#PreviewSurface,
            QScrollArea#PanelScrollArea,
            QPlainTextEdit#LogPanel,
            QTableWidget {{
                background: #fdfefe;
                border: 1px solid #c5cfda;
                border-radius: 14px;
            }}
            QScrollArea#PanelScrollArea > QWidget > QWidget {{
                background: transparent;
            }}
            QLabel#PreviewLabel {{
                color: #57687d;
                padding: 14px;
                background: transparent;
            }}
            QLabel#PreviewContentLabel {{
                color: #57687d;
                padding: 14px;
                background: transparent;
            }}
            QTabWidget::pane {{
                border: none;
                top: 0;
            }}
            QTabBar::tab {{
                background: #c7d3df;
                color: #405062;
                border: none;
                border-top-left-radius: 14px;
                border-top-right-radius: 14px;
                min-width: 136px;
                min-height: 34px;
                padding: 11px 24px 12px 24px;
                margin-right: 8px;
                font-size: 17px;
                font-weight: 600;
            }}
            QTabBar::tab:selected {{
                background: #f4f8fc;
                color: #112235;
            }}
            QTabBar::tab:!selected:hover {{
                background: #d5dfeb;
            }}
            QGroupBox {{
                background: #f9fbfd;
                border: 1px solid #c6d1db;
                border-radius: 14px;
                margin-top: 14px;
                padding-top: 12px;
                font-weight: 700;
                color: #192c40;
            }}
            QGroupBox[collapsible_section="true"][expanded="false"] {{
                background: #edf2f7;
                border: 1px dashed #c2ccd6;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 14px;
                padding: 0 6px;
                color: #192c40;
            }}
            QGroupBox[collapsible_section="true"][expanded="false"]::title {{
                color: #4b5d72;
            }}
            QLineEdit,
            QComboBox,
            QPlainTextEdit,
            QTableWidget {{
                color: #112035;
                selection-background-color: #c5daf4;
                selection-color: #112035;
            }}
            QLineEdit,
            QComboBox {{
                min-height: 24px;
                padding: 8px 11px;
                border: 1px solid #b8c7d7;
                border-radius: 10px;
                background: #fbfdff;
            }}
            QLineEdit:focus,
            QComboBox:focus,
            QPlainTextEdit:focus,
            QTableWidget:focus {{
                border: 1px solid #4f84bb;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 28px;
            }}
            QPushButton {{
                min-height: 24px;
                padding: 9px 16px;
                border-radius: 11px;
                border: 1px solid #b7c5d4;
                background: #ebf1f7;
                color: #16293d;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: #dfe8f2;
            }}
            QPushButton[floating="true"] {{
                border-color: #7e9fbe;
            }}
            QPushButton[icon_button="true"] {{
                min-width: 34px;
                max-width: 34px;
                min-height: 30px;
                max-height: 30px;
                padding: 0px;
                font-size: 18px;
                font-weight: 700;
                border-radius: 15px;
            }}
            QPushButton[toggle_button="true"]:checked {{
                background: #d7e6f6;
                border: 1px solid #7f9fbf;
                color: #15324d;
            }}
            QPushButton[toggle_button="true"]:checked:hover {{
                background: #cfe0f2;
            }}
            QPushButton[variant="primary"] {{
                background: #1f5688;
                border: 1px solid #1a4d81;
                color: #ffffff;
            }}
            QPushButton[variant="primary"]:hover {{
                background: #174973;
            }}
            QPushButton[variant="secondary"] {{
                background: #e8eff6;
                color: #1c3a56;
            }}
            QPushButton[subtle_button="true"] {{
                min-height: 18px;
                padding: 4px 10px;
                border-radius: 9px;
                border: 1px solid #c6d2dd;
                background: #eef3f7;
                color: #607284;
                font-size: 13px;
                font-weight: 500;
            }}
            QPushButton[subtle_button="true"]:hover {{
                background: #e4ebf2;
                color: #4c6074;
            }}
            QPushButton[subtle_button="true"][toggle_button="true"]:checked {{
                background: #dce7f2;
                border: 1px solid #a8bfd6;
                color: #37526d;
            }}
            QPushButton[subtle_button="true"][toggle_button="true"]:checked:hover {{
                background: #d3e0ed;
            }}
            QToolButton[subtle_tool_button="true"] {{
                min-height: 18px;
                padding: 4px 10px;
                border-radius: 9px;
                border: 1px solid #c6d2dd;
                background: #eef3f7;
                color: #6c7d8f;
                font-size: 12px;
                font-weight: 500;
            }}
            QToolButton[subtle_tool_button="true"]:hover {{
                background: #e4ebf2;
                color: #55687c;
            }}
            QToolButton[subtle_tool_button="true"]::menu-indicator {{
                image: none;
                width: 0px;
            }}
            QMenu#HeaderMenu {{
                background: #f8fbfe;
                border: 1px solid #c2ced9;
                border-radius: 10px;
                padding: 6px;
            }}
            QMenu#HeaderMenu::item {{
                padding: 7px 24px 7px 12px;
                border-radius: 7px;
                color: #21384f;
            }}
            QMenu#HeaderMenu::item:selected {{
                background: #dde8f3;
            }}
            QMenu#HeaderMenu::indicator {{
                width: 14px;
                height: 14px;
            }}
            QPushButton[variant="danger"] {{
                background: #f8e7e4;
                border: 1px solid #d8a7a2;
                color: #8c2f26;
            }}
            QPushButton:disabled,
            QComboBox:disabled,
            QLineEdit:disabled {{
                color: #738296;
                background: #e4ebf1;
                border-color: #c7d1db;
            }}
            QProgressBar {{
                min-height: 12px;
                border: 1px solid #bfccd8;
                border-radius: 8px;
                background: #dee6ee;
                text-align: center;
                color: #233f5b;
            }}
            QProgressBar::chunk {{
                border-radius: 7px;
                background: #2f699e;
            }}
            QHeaderView::section {{
                background: #dfe7ef;
                color: #304258;
                border: none;
                border-bottom: 1px solid #c1ccd8;
                padding: 10px;
                font-weight: 700;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 12px;
                margin: 8px 2px 8px 0;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background: #8fa6bc;
                min-height: 52px;
                border-radius: 6px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: #748ca5;
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0px;
                border: none;
                background: transparent;
            }}
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {{
                border: none;
                background: transparent;
            }}
            QScrollBar:horizontal {{
                background: transparent;
                height: 12px;
                margin: 0 8px 2px 8px;
                border: none;
            }}
            QScrollBar::handle:horizontal {{
                background: #8fa6bc;
                min-width: 52px;
                border-radius: 6px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background: #748ca5;
            }}
            QScrollBar::add-line:horizontal,
            QScrollBar::sub-line:horizontal {{
                width: 0px;
                border: none;
                background: transparent;
            }}
            QScrollBar::add-page:horizontal,
            QScrollBar::sub-page:horizontal {{
                border: none;
                background: transparent;
            }}
            """
        )
        self._apply_responsive_layout()

    def _ensure_opacity_effect(self, widget: QWidget):
        effect = widget.graphicsEffect()
        if isinstance(effect, QGraphicsOpacityEffect):
            return effect
        effect = QGraphicsOpacityEffect(widget)
        effect.setOpacity(1.0)
        widget.setGraphicsEffect(effect)
        return effect

    def _animate_widget_opacity(self, widget: QWidget, *, start: float, end: float, duration: int):
        effect = self._ensure_opacity_effect(widget)
        current_animation = getattr(widget, "_opacity_animation", None)
        if current_animation is not None:
            current_animation.stop()

        effect.setOpacity(start)
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(duration)
        animation.setStartValue(start)
        animation.setEndValue(end)
        animation.setEasingCurve(QEasingCurve.InOutCubic)
        widget._opacity_animation = animation

        def _cleanup():
            if getattr(widget, "_opacity_animation", None) is animation:
                widget._opacity_animation = None
            effect.setOpacity(end)

        animation.finished.connect(_cleanup)
        animation.start()

    def _animate_content_swap(self, widget: QWidget, apply_content):
        effect = self._ensure_opacity_effect(widget)
        current_animation = getattr(widget, "_content_animation", None)
        if current_animation is not None:
            current_animation.stop()

        fade_out = QPropertyAnimation(effect, b"opacity", self)
        fade_out.setDuration(ANIMATION_FAST_MS)
        fade_out.setStartValue(float(effect.opacity()))
        fade_out.setEndValue(0.16)
        fade_out.setEasingCurve(QEasingCurve.OutCubic)

        fade_in = QPropertyAnimation(effect, b"opacity", self)
        fade_in.setDuration(ANIMATION_MEDIUM_MS)
        fade_in.setStartValue(0.16)
        fade_in.setEndValue(1.0)
        fade_in.setEasingCurve(QEasingCurve.InOutCubic)

        group = QSequentialAnimationGroup(self)
        group.addAnimation(fade_out)
        group.addAnimation(fade_in)
        fade_out.finished.connect(apply_content)
        widget._content_animation = group

        def _cleanup():
            if getattr(widget, "_content_animation", None) is group:
                widget._content_animation = None
            effect.setOpacity(1.0)

        group.finished.connect(_cleanup)
        group.start()

    def _set_progress_value(self, value: float, animate: bool):
        clamped = max(0, min(100, int(round(value))))
        if self._progress_animation is not None:
            self._progress_animation.stop()
            self._progress_animation = None
        if not animate:
            self.progress_bar.setValue(clamped)
            return

        animation = QPropertyAnimation(self.progress_bar, b"value", self)
        animation.setDuration(ANIMATION_MEDIUM_MS)
        animation.setStartValue(self.progress_bar.value())
        animation.setEndValue(clamped)
        animation.setEasingCurve(QEasingCurve.InOutCubic)
        self._progress_animation = animation

        def _cleanup():
            if self._progress_animation is animation:
                self._progress_animation = None

        animation.finished.connect(_cleanup)
        animation.start()

    def _register_animated_buttons(self):
        for button in (
            self.generate_mesh_button,
            self.run_button,
            self.stop_button,
            self.scan_add_button,
            self.scan_remove_button,
            self.scan_reset_button,
            self.export_results_button,
        ):
            button.installEventFilter(self)

    def _section_content_widgets(self, binding):
        content_widgets = []
        for field_key in binding["field_keys"]:
            field_binding = self.field_bindings[field_key]
            widget = field_binding["widget"]
            label_widget = field_binding["form"].labelForField(widget)
            content_widgets.append((field_key, label_widget, widget))
        return content_widgets

    def _set_section_title(self, binding):
        prefix = "▾" if binding["expanded"] else "▸"
        binding["section"].setTitle(f"{prefix} {binding['title']}")

    def _set_section_content_visibility(self, binding, expanded: bool):
        case_id = self.current_case
        for field_key, label_widget, widget in self._section_content_widgets(binding):
            visible = expanded and self._field_is_applicable(field_key, case_id)
            widget.setVisible(visible)
            if label_widget is not None:
                label_widget.setVisible(visible)

    def _set_section_expanded_state(self, binding, expanded: bool, animate: bool):
        section = binding["section"]
        current_animation = self._section_animations.get(section)
        if current_animation is not None:
            current_animation.stop()

        binding["expanded"] = expanded
        section.setProperty("expanded", expanded)
        self._set_section_title(binding)
        self.style().unpolish(section)
        self.style().polish(section)

        if expanded:
            self._set_section_content_visibility(binding, expanded=True)

        current_height = max(section.height(), binding["collapsed_height"])
        if expanded:
            section.setMaximumHeight(16777215)
            target_height = max(section.sizeHint().height(), current_height)
        else:
            target_height = binding["collapsed_height"]

        if not animate:
            section.setMaximumHeight(16777215 if expanded else binding["collapsed_height"])
            if not expanded:
                self._set_section_content_visibility(binding, expanded=False)
            return

        height_animation = QPropertyAnimation(section, b"maximumHeight", self)
        height_animation.setDuration(ANIMATION_MEDIUM_MS)
        height_animation.setStartValue(current_height)
        height_animation.setEndValue(target_height)
        height_animation.setEasingCurve(QEasingCurve.OutCubic if expanded else QEasingCurve.InOutCubic)
        self._section_animations[section] = height_animation

        def _cleanup():
            if self._section_animations.get(section) is height_animation:
                self._section_animations.pop(section, None)
            section.setMaximumHeight(16777215 if expanded else binding["collapsed_height"])
            if not expanded:
                self._set_section_content_visibility(binding, expanded=False)

        height_animation.finished.connect(_cleanup)
        height_animation.start()

    def _toggle_section(self, section: QGroupBox, expanded: bool, animate: bool = True):
        binding = self._section_bindings_by_widget.get(section)
        if binding is None or not section.isVisible():
            return
        self._set_section_expanded_state(binding, expanded=expanded, animate=animate)

    def _button_target_geometry(self, button: QPushButton, hovered: bool):
        rest_geometry = self._button_rest_geometries.get(button, button.geometry())
        return QRect(rest_geometry.x(), rest_geometry.y() - 3, rest_geometry.width(), rest_geometry.height()) if hovered else QRect(rest_geometry)

    def _animate_button_hover(self, button: QPushButton, hovered: bool):
        if not button.isEnabled() or not button.isVisible():
            return
        current_animation = self._button_hover_animations.get(button)
        if current_animation is not None:
            current_animation.stop()
        if hovered or button not in self._button_rest_geometries:
            self._button_rest_geometries[button] = QRect(button.geometry())

        target = self._button_target_geometry(button, hovered)
        button.setProperty("floating", hovered)
        self.style().unpolish(button)
        self.style().polish(button)

        animation = QPropertyAnimation(button, b"geometry", self)
        animation.setDuration(ANIMATION_FAST_MS if hovered else ANIMATION_MEDIUM_MS)
        animation.setStartValue(button.geometry())
        animation.setEndValue(target)
        animation.setEasingCurve(QEasingCurve.OutCubic if hovered else QEasingCurve.InOutCubic)
        self._button_hover_animations[button] = animation

        def _cleanup():
            if self._button_hover_animations.get(button) is animation:
                self._button_hover_animations.pop(button, None)

        animation.finished.connect(_cleanup)
        animation.start()

    def _visible_reveal_sections(self):
        sections = []
        for binding in self.section_bindings:
            section = binding["section"]
            if section.isVisible() and binding["expanded"]:
                sections.append(section)
        for section in (self.run_profile_box, self.scan_editor_box):
            if section.isVisible():
                sections.append(section)
        return sections

    def _pulse_status_card(self, label: QLabel):
        self._animate_widget_opacity(label, start=0.34, end=1.0, duration=ANIMATION_SLOW_MS)

    def _animations_enabled(self) -> bool:
        app = QApplication.instance()
        return bool(app is not None and app.platformName() != "offscreen" and self.isVisible())

    def _position_toast(self):
        if not hasattr(self, "toast_label"):
            return
        self.toast_label.adjustSize()
        width = min(max(self.toast_label.sizeHint().width(), 220), 360)
        self.toast_label.resize(width, self.toast_label.sizeHint().height())
        margin = 22
        x_pos = margin
        y_pos = self.centralWidget().height() - self.toast_label.height() - margin
        self.toast_label.move(x_pos, max(margin, y_pos))

    def _show_toast(self, text: str, tone: str):
        self._toast_hide_timer.stop()
        self.toast_label.setProperty("tone", tone)
        self.style().unpolish(self.toast_label)
        self.style().polish(self.toast_label)
        self.toast_label.setText(text)
        self._position_toast()
        self.toast_label.raise_()
        self.toast_label.show()

        current_animation = self._toast_animation
        if current_animation is not None:
            current_animation.stop()

        effect = self._ensure_opacity_effect(self.toast_label)
        end_rect = QRect(self.toast_label.geometry())
        start_rect = QRect(end_rect.x(), end_rect.y() - 14, end_rect.width(), end_rect.height())
        self.toast_label.setGeometry(start_rect)
        effect.setOpacity(0.0)

        geometry_animation = QPropertyAnimation(self.toast_label, b"geometry", self)
        geometry_animation.setDuration(ANIMATION_MEDIUM_MS)
        geometry_animation.setStartValue(start_rect)
        geometry_animation.setEndValue(end_rect)
        geometry_animation.setEasingCurve(QEasingCurve.OutCubic)

        opacity_animation = QPropertyAnimation(effect, b"opacity", self)
        opacity_animation.setDuration(ANIMATION_MEDIUM_MS)
        opacity_animation.setStartValue(0.0)
        opacity_animation.setEndValue(1.0)
        opacity_animation.setEasingCurve(QEasingCurve.InOutCubic)

        group = QParallelAnimationGroup(self)
        group.addAnimation(geometry_animation)
        group.addAnimation(opacity_animation)
        self._toast_animation = group
        group.start()
        self._toast_hide_timer.start(ANIMATION_TOAST_STAY_MS)

    def _hide_toast(self):
        if not hasattr(self, "toast_label") or not self.toast_label.isVisible():
            return
        current_animation = self._toast_animation
        if current_animation is not None:
            current_animation.stop()

        effect = self._ensure_opacity_effect(self.toast_label)
        start_rect = QRect(self.toast_label.geometry())
        end_rect = QRect(start_rect.x(), start_rect.y() - 12, start_rect.width(), start_rect.height())

        geometry_animation = QPropertyAnimation(self.toast_label, b"geometry", self)
        geometry_animation.setDuration(ANIMATION_FAST_MS)
        geometry_animation.setStartValue(start_rect)
        geometry_animation.setEndValue(end_rect)
        geometry_animation.setEasingCurve(QEasingCurve.InCubic)

        opacity_animation = QPropertyAnimation(effect, b"opacity", self)
        opacity_animation.setDuration(ANIMATION_FAST_MS)
        opacity_animation.setStartValue(float(effect.opacity()))
        opacity_animation.setEndValue(0.0)
        opacity_animation.setEasingCurve(QEasingCurve.InCubic)

        group = QParallelAnimationGroup(self)
        group.addAnimation(geometry_animation)
        group.addAnimation(opacity_animation)
        self._toast_animation = group

        def _cleanup():
            self.toast_label.hide()
            effect.setOpacity(1.0)

        group.finished.connect(_cleanup)
        group.start()

    def _show_run_feedback(self, run_mode: str, success: bool, was_stopped: bool, message: str):
        if success and not was_stopped:
            tone = "success"
            toast_text = f"{'Mesh' if run_mode == 'mesh' else 'Compute'} stage completed."
        elif was_stopped:
            tone = "warning"
            toast_text = f"{'Mesh' if run_mode == 'mesh' else 'Compute'} stage stopped."
        else:
            tone = "error"
            toast_text = message

        self._show_toast(toast_text, tone)
        target_label = self.mesh_status_label if run_mode == "mesh" else self.compute_status_label
        self._pulse_status_card(target_label)

    def _set_layout_direction(self, layout, horizontal: bool):
        layout.setDirection(QBoxLayout.LeftToRight if horizontal else QBoxLayout.TopToBottom)

    def _apply_responsive_layout(self):
        width = max(self.width(), self.minimumWidth())
        stacked_main = width < 1320
        compact_actions = width < 1040
        stacked_header = width < 1180

        self._set_layout_direction(self.header_top_layout, not stacked_header)
        self._set_layout_direction(self.header_controls_layout, not compact_actions)
        self._set_layout_direction(self.mesh_main_layout, not stacked_main)
        self._set_layout_direction(self.compute_main_layout, not stacked_main)
        self._set_layout_direction(self.compute_top_preview_layout, not stacked_main)
        self._set_layout_direction(self.scan_button_layout, not compact_actions)
        self._set_layout_direction(self.compute_action_layout, not compact_actions)
        self._set_layout_direction(self.postprocess_controls_layout, not compact_actions)
        self._set_layout_direction(self.postprocess_action_layout, not compact_actions)

        self.mesh_left_scroll.setMaximumWidth(640 if not stacked_main else 16777215)
        self.compute_left_scroll.setMaximumWidth(640 if not stacked_main else 16777215)
        self.mesh_left_scroll.setMinimumWidth(0 if stacked_main else 360)
        self.compute_left_scroll.setMinimumWidth(0 if stacked_main else 380)

        preview_min_height = 320 if stacked_main else 440
        compute_preview_min_height = 260 if stacked_main else 340
        curve_min_height = 180 if stacked_main else 210
        active_postprocess_view = self.postprocess_view_combo.currentText()
        if is_visual_export_view(active_postprocess_view):
            postprocess_surface_min_height = 180 if compact_actions else 230
        else:
            postprocess_surface_min_height = 260 if compact_actions else preview_min_height
        header_text_max_width = 16777215 if stacked_header else (880 if width < 1480 else 980)
        badge_min_width = 0 if stacked_header else (420 if width < 1480 else 470)
        self.mesh_preview_label.setMinimumHeight(preview_min_height)
        self.damage_label.setMinimumHeight(compute_preview_min_height)
        self.displacement_label.setMinimumHeight(compute_preview_min_height)
        self.curve_canvas.setMinimumHeight(curve_min_height)
        if self._compute_curve_collapsed:
            self.compute_curve_card.setMaximumHeight(82)
            self.curve_surface.setVisible(False)
        else:
            self.compute_curve_card.setMaximumHeight(300 if stacked_main else 340)
            self.curve_surface.setVisible(True)
        self.postprocess_stack.setMinimumHeight(postprocess_surface_min_height)
        self.postprocess_image_panel.setMinimumHeight(postprocess_surface_min_height)
        self.postprocess_label.setMinimumHeight(postprocess_surface_min_height)
        self.postprocess_curve_canvas.setMinimumHeight(max(curve_min_height, 200 if compact_actions else curve_min_height))
        self.postprocess_table.setMinimumHeight(220 if compact_actions else 340)
        self.window_title_label.setMaximumWidth(header_text_max_width)
        self.window_subtitle_label.setMaximumWidth(header_text_max_width)
        self.case_status_badge.setMinimumWidth(badge_min_width)
        self.case_status_badge.setMaximumWidth(header_text_max_width)

        self.scan_add_button.setMinimumWidth(0 if compact_actions else 90)
        self.scan_remove_button.setMinimumWidth(0 if compact_actions else 90)
        self.scan_reset_button.setMinimumWidth(0 if compact_actions else 120)
        self.run_button.setMinimumWidth(0 if compact_actions else 110)
        self.stop_button.setMinimumWidth(0 if compact_actions else 110)
        self.more_button.setMinimumWidth(0 if compact_actions else 64)
        self.export_results_button.setMinimumWidth(0 if compact_actions else 120)

    def toggle_compute_curve_card(self):
        self._compute_curve_collapsed = not self._compute_curve_collapsed
        self.curve_toggle_button.setText("▴" if self._compute_curve_collapsed else "▾")
        self.curve_toggle_button.setToolTip("Expand live curve" if self._compute_curve_collapsed else "Collapse live curve")
        self._apply_responsive_layout()

    def _sync_transient_cache_button(self):
        enabled = bool(self.keep_transient_results)
        self.keep_cache_action.blockSignals(True)
        self.keep_cache_action.setChecked(enabled)
        self.keep_cache_action.blockSignals(False)
        self.keep_cache_action.setText("Keep Temp Cache On" if enabled else "Keep Temp Cache Off")
        self.more_button.setToolTip(
            "Troubleshooting mode is on. Current mesh and compute cache will be kept after restart."
            if enabled
            else "Troubleshooting mode is off. Current mesh and compute cache will be purged on restart."
        )
        self.more_button.setText("More")
        self.style().unpolish(self.more_button)
        self.style().polish(self.more_button)

    def on_keep_cache_toggled(self, checked: bool):
        self.keep_transient_results = bool(checked)
        write_transient_cache_preference(self.keep_transient_results)
        self._sync_transient_cache_button()
        self._show_toast(
            "Temporary cache retention enabled." if self.keep_transient_results else "Temporary cache retention disabled.",
            "success" if self.keep_transient_results else "warning",
        )

    def _sync_category_combo(self):
        self._syncing_selection = True
        self.category_combo.clear()
        for category_id in CATEGORY_ORDER:
            self.category_combo.addItem(CATEGORY_LABELS[category_id], category_id)
        index = self.category_combo.findData(self.current_category)
        if index >= 0:
            self.category_combo.setCurrentIndex(index)
        self._syncing_selection = False

    def _refresh_case_combo(self, category_id: str, preferred_case_id: str | None = None):
        self._syncing_selection = True
        self.case_combo.clear()
        cases = iter_cases_for_category(category_id)
        for case in cases:
            self.case_combo.addItem(case.display_name, case.case_id)
        target_case = preferred_case_id or first_case_for_category(category_id).case_id
        index = self.case_combo.findData(target_case)
        if index < 0 and self.case_combo.count():
            index = 0
        if index >= 0:
            self.case_combo.setCurrentIndex(index)
            self.current_case = self.case_combo.currentData()
        self._syncing_selection = False

    def _load_manifest_file(self, manifest_path: Path | None):
        if manifest_path is None or not manifest_path.exists():
            return None
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            return None
        manifest = RunManifest.from_dict(payload)
        if "run_profile" not in payload:
            runtime_params_path = Path(manifest.runtime_params_path) if manifest.runtime_params_path else None
            inferred_profile = self._load_run_profile_from_runtime_params(runtime_params_path, fallback=None)
            manifest.run_profile = inferred_profile or CASE_DEFINITIONS.get(manifest.case_id, CASE_DEFINITIONS[self.current_case]).default_run_profile
        return manifest

    def _load_run_profile_from_runtime_params(self, runtime_params_path: Path | None, fallback: str | None = "full"):
        if runtime_params_path is None or not runtime_params_path.exists():
            return fallback
        try:
            payload = json.loads(runtime_params_path.read_text(encoding="utf-8"))
        except Exception:
            return fallback
        if "run_profile" not in payload:
            return fallback
        return normalize_run_profile(payload.get("run_profile"), fallback="full")

    def _load_saved_manifest_for_case(self, case):
        latest_path = latest_manifest_path(case.case_id)
        manifest = self._load_manifest_file(latest_path)
        if manifest is not None:
            return latest_path, manifest

        archived_path = latest_archived_manifest_path(case.case_id)
        manifest = self._load_manifest_file(archived_path)
        if manifest is not None:
            return archived_path, manifest

        return None, None

    def _load_manifests_from_disk(self):
        for case in CASE_REGISTRY:
            manifest_path, manifest = self._load_saved_manifest_for_case(case)
            if manifest is not None and manifest_path is not None:
                self._apply_manifest_to_state(case.case_id, manifest_path, manifest)

    def _make_manifest(
        self,
        case,
        native_output_dir: Path,
        *,
        run_profile: str | None = None,
        run_id: str | None = None,
        run_dir_path: Path | None = None,
        runtime_params_path: Path | None = None,
        mesh_paths=(),
        snapshot_paths=(),
        vtk_paths=(),
        curve_csv_paths=(),
        damage_paths=(),
        displacement_paths=(),
    ):
        mesh_paths = dedupe_existing_paths(mesh_paths)
        snapshot_paths = dedupe_existing_paths(snapshot_paths)
        vtk_paths = dedupe_existing_paths(vtk_paths)
        curve_csv_paths = dedupe_existing_paths(curve_csv_paths)
        damage_paths = dedupe_existing_paths(damage_paths)
        displacement_paths = dedupe_existing_paths(displacement_paths)
        if not any([mesh_paths, snapshot_paths, vtk_paths, curve_csv_paths, damage_paths, displacement_paths]):
            return None

        source_script = (
            str((GUI_DIR / "gui_solver.jl").resolve())
            if case.backend_mode == "protocol_julia"
            else str(case.script_abspath.resolve()) if case.script_abspath else ""
        )
        return RunManifest(
            category_id=case.category_id,
            case_id=case.case_id,
            run_id=run_id or make_run_id(case.case_id),
            status="completed",
            backend_mode=case.backend_mode,
            curve_kind=case.curve_kind,
            run_profile=normalize_run_profile(run_profile, fallback="full"),
            source_script=source_script,
            run_dir=str(run_dir_path.resolve()) if run_dir_path is not None else "",
            runtime_params_path=str(runtime_params_path.resolve()) if runtime_params_path is not None else "",
            native_output_dir=str(native_output_dir.resolve()),
            mesh_paths=mesh_paths,
            snapshot_paths=snapshot_paths,
            vtk_paths=vtk_paths,
            curve_csv_paths=curve_csv_paths,
            damage_paths=damage_paths,
            displacement_paths=displacement_paths,
        )

    def _build_manifest_from_disk(
        self,
        case,
        perform_export: bool,
        *,
        run_profile: str | None = None,
        run_id: str | None = None,
        run_dir_path: Path | None = None,
        runtime_params_path: Path | None = None,
    ):
        native_output_dir = run_dir_path / "native" if run_dir_path is not None else None
        resolved_run_profile = run_profile or self._load_run_profile_from_runtime_params(runtime_params_path)
        if case.result_profile.startswith("protocol_"):
            manifest = self._build_protocol_manifest(
                case,
                native_output_dir=native_output_dir,
                run_profile=resolved_run_profile,
                run_id=run_id,
                run_dir_path=run_dir_path,
                runtime_params_path=runtime_params_path,
            )
        elif case.result_profile == "elastic_fatigue_tpb":
            manifest = self._build_tpb_manifest(
                case,
                native_output_dir=native_output_dir,
                run_profile=resolved_run_profile,
                run_id=run_id,
                run_dir_path=run_dir_path,
                runtime_params_path=runtime_params_path,
            )
        elif case.result_profile == "elastic_fatigue_offset_scan":
            manifest = self._build_offset_scan_manifest(
                case,
                native_output_dir=native_output_dir,
                run_profile=resolved_run_profile,
                run_id=run_id,
                run_dir_path=run_dir_path,
                runtime_params_path=runtime_params_path,
            )
        elif case.result_profile == "plastic_fracture_flat_grooved_scan":
            manifest = self._build_fang_manifest(
                case,
                native_output_dir=native_output_dir,
                run_profile=resolved_run_profile,
                run_id=run_id,
                run_dir_path=run_dir_path,
                runtime_params_path=runtime_params_path,
            )
        elif case.result_profile == "plastic_fracture_double_notched_scan":
            manifest = self._build_double_notched_manifest(
                case,
                native_output_dir=native_output_dir,
                run_profile=resolved_run_profile,
                run_id=run_id,
                run_dir_path=run_dir_path,
                runtime_params_path=runtime_params_path,
            )
        elif case.result_profile == "plastic_fatigue_sent":
            manifest = self._build_plastic_fatigue_sent_manifest(
                case,
                native_output_dir=native_output_dir,
                run_profile=resolved_run_profile,
                run_id=run_id,
                run_dir_path=run_dir_path,
                runtime_params_path=runtime_params_path,
            )
        elif case.result_profile == "plastic_fatigue_ct":
            manifest = self._build_plastic_fatigue_ct_manifest(
                case,
                native_output_dir=native_output_dir,
                run_profile=resolved_run_profile,
                run_id=run_id,
                run_dir_path=run_dir_path,
                runtime_params_path=runtime_params_path,
            )
        else:
            manifest = None
        if manifest is None:
            return None
        if perform_export and case.visual_exporter:
            self._populate_visual_exports(case, manifest)
        return manifest

    def _build_protocol_manifest(
        self,
        case,
        native_output_dir: Path | None = None,
        *,
        run_profile: str | None = None,
        run_id: str | None = None,
        run_dir_path: Path | None = None,
        runtime_params_path: Path | None = None,
    ):
        case_name = case.protocol_case_name
        native_output_dir = native_output_dir or RESULTS_DIR
        if not native_output_dir.exists():
            return None

        mesh_msh = native_output_dir / mesh_file_name(case_name)
        mesh_png = native_output_dir / mesh_png_name(case_name)
        curve_candidates = [native_output_dir / curve_csv_name(case_name)]
        damage_candidates = [native_output_dir / damage_final_name(case_name)]
        displacement_candidates = [native_output_dir / displacement_final_name(case_name)]
        legacy_mode = run_dir_path is None
        if legacy_mode and case_name == "SENT":
            curve_candidates.append(native_output_dir / "F_u_curve.csv")
            damage_candidates.append(native_output_dir / "d_final.png")
            displacement_candidates.append(native_output_dir / "u_mag_final.png")
        curve_csv = first_existing(*curve_candidates)
        damage_final = first_existing(*damage_candidates)
        displacement_final = first_existing(*displacement_candidates)

        snapshot_paths = [path for path in native_output_dir.glob(f"snap_{case_name}_*.png") if path.is_file()]
        displacement_paths = [path for path in native_output_dir.glob(f"u_mag_{case_name}_*.png") if path.is_file()]
        vtk_paths = [path for path in native_output_dir.glob(f"{result_prefix(case_name)}*.vtu") if path.is_file()]
        if legacy_mode and case_name == "SENT":
            snapshot_paths.extend(
                path
                for path in native_output_dir.glob("snap_*.png")
                if path.is_file() and len(path.name) > 5 and path.name[5].isdigit()
            )
            displacement_paths.extend(path for path in native_output_dir.glob("u_mag_*.png") if path.is_file() and "final" not in path.name)
            legacy_final_vtk = native_output_dir / "result_final.vtu"
            if legacy_final_vtk.exists():
                vtk_paths.append(legacy_final_vtk)
        if displacement_final is not None:
            displacement_paths.append(displacement_final)

        return self._make_manifest(
            case,
            native_output_dir,
            run_profile=run_profile,
            run_id=run_id,
            run_dir_path=run_dir_path,
            runtime_params_path=runtime_params_path,
            mesh_paths=[mesh_msh, mesh_png],
            snapshot_paths=snapshot_paths,
            vtk_paths=vtk_paths,
            curve_csv_paths=[curve_csv] if curve_csv else [],
            damage_paths=[damage_final] if damage_final else [],
            displacement_paths=displacement_paths,
        )

    def _build_batch_manifest(
        self,
        case,
        native_output_dir: Path,
        *,
        run_profile: str | None = None,
        run_id: str | None = None,
        run_dir_path: Path | None = None,
        runtime_params_path: Path | None = None,
        mesh_paths=(),
        snapshot_paths=(),
        vtk_paths=(),
        curve_csv_paths=(),
        damage_paths=(),
        displacement_paths=(),
    ):
        return self._make_manifest(
            case,
            native_output_dir,
            run_profile=run_profile,
            run_id=run_id,
            run_dir_path=run_dir_path,
            runtime_params_path=runtime_params_path,
            mesh_paths=mesh_paths,
            snapshot_paths=snapshot_paths,
            vtk_paths=vtk_paths,
            curve_csv_paths=curve_csv_paths,
            damage_paths=damage_paths,
            displacement_paths=displacement_paths,
        )

    def _collect_files(self, base_dir: Path, patterns, recursive: bool = True):
        files = []
        for pattern in patterns:
            iterator = base_dir.rglob(pattern) if recursive else base_dir.glob(pattern)
            files.extend(path for path in iterator if path.is_file())
        return files

    def _build_tpb_manifest(
        self,
        case,
        native_output_dir: Path | None = None,
        *,
        run_profile: str | None = None,
        run_id: str | None = None,
        run_dir_path: Path | None = None,
        runtime_params_path: Path | None = None,
    ):
        native_output_dir = native_output_dir or case.native_output_abspath
        if native_output_dir is None or not native_output_dir.exists():
            return None

        case_dir = native_output_dir / "AT1"
        mesh_paths = self._collect_files(native_output_dir, ("BeamWithNotchSymThreePtBending.msh", "mesh.png"), recursive=False)
        vtk_paths = self._collect_files(case_dir, ("cycle_*.vtu",), recursive=False) if case_dir.exists() else []
        curve_csv_paths = self._collect_files(case_dir, ("history.csv",), recursive=False) if case_dir.exists() else []
        damage_paths = self._collect_files(case_dir, ("damage_final.png",), recursive=False) if case_dir.exists() else []
        return self._build_batch_manifest(
            case,
            native_output_dir,
            run_profile=run_profile,
            run_id=run_id,
            run_dir_path=run_dir_path,
            runtime_params_path=runtime_params_path,
            mesh_paths=mesh_paths,
            vtk_paths=vtk_paths,
            curve_csv_paths=curve_csv_paths,
            damage_paths=damage_paths,
        )

    def _build_fang_manifest(
        self,
        case,
        native_output_dir: Path | None = None,
        *,
        run_profile: str | None = None,
        run_id: str | None = None,
        run_dir_path: Path | None = None,
        runtime_params_path: Path | None = None,
    ):
        native_output_dir = native_output_dir or case.native_output_abspath
        if native_output_dir is None or not native_output_dir.exists():
            return None

        scan_summary = native_output_dir / "scan_summary.csv"

        return self._build_batch_manifest(
            case,
            native_output_dir,
            run_profile=run_profile,
            run_id=run_id,
            run_dir_path=run_dir_path,
            runtime_params_path=runtime_params_path,
            mesh_paths=self._collect_files(native_output_dir, ("*.msh", "geometry_mesh.png")),
            snapshot_paths=self._collect_files(native_output_dir, ("damage_*.png",)),
            vtk_paths=self._collect_files(native_output_dir, ("result_*.vtu",)),
            curve_csv_paths=([scan_summary] if scan_summary.exists() else []) + self._collect_files(native_output_dir, ("force_displacement_*.csv",)),
        )

    def _build_offset_scan_manifest(
        self,
        case,
        native_output_dir: Path | None = None,
        *,
        run_profile: str | None = None,
        run_id: str | None = None,
        run_dir_path: Path | None = None,
        runtime_params_path: Path | None = None,
    ):
        native_output_dir = native_output_dir or case.native_output_abspath
        if native_output_dir is None or not native_output_dir.exists():
            return None
        scan_summary = native_output_dir / "scan_summary.csv"
        return self._build_batch_manifest(
            case,
            native_output_dir,
            run_profile=run_profile,
            run_id=run_id,
            run_dir_path=run_dir_path,
            runtime_params_path=runtime_params_path,
            mesh_paths=self._collect_files(native_output_dir, ("mesh_offset_double_notch.msh", "mesh.png")),
            vtk_paths=self._collect_files(native_output_dir, ("result_*.vtu",)),
            damage_paths=self._collect_files(native_output_dir, ("damage_final.png",)),
            curve_csv_paths=([scan_summary] if scan_summary.exists() else []) + self._collect_files(native_output_dir, ("history.csv",)),
        )

    def _build_double_notched_manifest(
        self,
        case,
        native_output_dir: Path | None = None,
        *,
        run_profile: str | None = None,
        run_id: str | None = None,
        run_dir_path: Path | None = None,
        runtime_params_path: Path | None = None,
    ):
        native_output_dir = native_output_dir or case.native_output_abspath
        if native_output_dir is None or not native_output_dir.exists():
            return None
        scan_summary = native_output_dir / "scan_summary.csv"
        return self._build_batch_manifest(
            case,
            native_output_dir,
            run_profile=run_profile,
            run_id=run_id,
            run_dir_path=run_dir_path,
            runtime_params_path=runtime_params_path,
            mesh_paths=self._collect_files(native_output_dir, ("mesh_double_notched.msh", "mesh_double_notched.png")),
            snapshot_paths=self._collect_files(native_output_dir, ("damage_*.png",)),
            vtk_paths=self._collect_files(native_output_dir, ("result_*.vtu",)),
            curve_csv_paths=([scan_summary] if scan_summary.exists() else []) + self._collect_files(native_output_dir, ("force_displacement.csv",)),
        )

    def _build_plastic_fatigue_sent_manifest(
        self,
        case,
        native_output_dir: Path | None = None,
        *,
        run_profile: str | None = None,
        run_id: str | None = None,
        run_dir_path: Path | None = None,
        runtime_params_path: Path | None = None,
    ):
        native_output_dir = native_output_dir or case.native_output_abspath
        if native_output_dir is None or not native_output_dir.exists():
            return None
        return self._build_batch_manifest(
            case,
            native_output_dir,
            run_profile=run_profile,
            run_id=run_id,
            run_dir_path=run_dir_path,
            runtime_params_path=runtime_params_path,
            mesh_paths=self._collect_files(native_output_dir, ("mesh.msh", "mesh.png"), recursive=False),
            snapshot_paths=self._collect_files(native_output_dir, ("damage_N*.png",), recursive=False),
            vtk_paths=self._collect_files(native_output_dir, ("result_*.vtu",), recursive=False),
            curve_csv_paths=self._collect_files(native_output_dir, ("cycle_summary.csv",), recursive=False),
        )

    def _build_plastic_fatigue_ct_manifest(
        self,
        case,
        native_output_dir: Path | None = None,
        *,
        run_profile: str | None = None,
        run_id: str | None = None,
        run_dir_path: Path | None = None,
        runtime_params_path: Path | None = None,
    ):
        native_output_dir = native_output_dir or case.native_output_abspath
        if native_output_dir is None or not native_output_dir.exists():
            return None
        return self._build_batch_manifest(
            case,
            native_output_dir,
            run_profile=run_profile,
            run_id=run_id,
            run_dir_path=run_dir_path,
            runtime_params_path=runtime_params_path,
            mesh_paths=self._collect_files(native_output_dir, ("CT_mesh.msh", "mesh_CT.png"), recursive=False),
            vtk_paths=self._collect_files(native_output_dir, ("result*.vtu",), recursive=False),
            curve_csv_paths=self._collect_files(native_output_dir, ("cycle_summary.csv",), recursive=False),
            damage_paths=self._collect_files(native_output_dir, ("damage_final.png",), recursive=False),
        )

    def _populate_visual_exports(self, case, manifest: RunManifest):
        if not case.visual_exporter or not manifest.native_output_dir:
            return
        if not any([manifest.snapshot_paths, manifest.curve_csv_paths, manifest.damage_paths, manifest.vtk_paths]):
            return

        native_output_dir = Path(manifest.native_output_dir)
        if not native_output_dir.exists():
            manifest.notes.append(f"Visual export skipped: missing output dir {native_output_dir}")
            return

        try:
            export_dir = VISUAL_EXPORT_DIR / case.case_id / manifest.run_id
            runtime_params_path = Path(manifest.runtime_params_path) if manifest.runtime_params_path else None
            manifest.exported_visual_paths = export_visuals(
                case.visual_exporter,
                native_output_dir,
                export_dir,
                runtime_params_path,
            )
        except Exception as exc:
            manifest.exported_visual_paths = {}
            manifest.notes.append(f"Visual export failed: {exc}")

    def _apply_manifest_to_state(self, case_id: str, manifest_path: Path, manifest: RunManifest):
        state = self.case_states[case_id]
        case = CASE_DEFINITIONS[case_id]
        state["manifest_path"] = manifest_path
        state["manifest"] = manifest
        state["run_profile"] = normalize_run_profile(manifest.run_profile, fallback="full")
        state["run_id"] = manifest.run_id
        state["run_dir"] = manifest.run_dir or None
        state["runtime_params_path"] = manifest.runtime_params_path or None
        state["mesh_ready"] = bool(manifest.mesh_paths) or not case.mesh_stage_enabled
        state["mesh_artifact_path"] = self._first_file(manifest.mesh_paths, suffix=".msh")
        state["mesh_preview_path"] = self._first_file(manifest.mesh_paths, suffix=".png")
        state["latest_damage_path"] = self._last_file(manifest.damage_paths or manifest.snapshot_paths, suffix=".png")
        state["latest_displacement_path"] = self._last_file(manifest.displacement_paths, suffix=".png")
        state["latest_vtk_path"] = str(self._last_file(manifest.vtk_paths, suffix=".vtu") or "")
        state["visual_export_paths"] = dict(manifest.exported_visual_paths)
        state["compute_completed"] = bool(
            manifest.snapshot_paths or manifest.curve_csv_paths or manifest.vtk_paths or manifest.exported_visual_paths
        )
        if case.mesh_stage_enabled:
            state["mesh_status"] = "Mesh ready." if state["mesh_ready"] else "Mesh not generated."
        else:
            state["mesh_status"] = "Mesh generated inside benchmark run." if state["compute_completed"] else self._default_mesh_status(case)
        state["compute_status"] = "Latest results loaded from manifest." if state["compute_completed"] else self._default_compute_status(case)
        state["curve_x"], state["curve_y"] = self._load_curve_history(manifest, case)
        state["history_selection"]["Mesh"] = str(state["mesh_preview_path"]) if state["mesh_preview_path"] else None
        state["history_selection"]["Damage"] = str(state["latest_damage_path"]) if state["latest_damage_path"] else None
        state["history_selection"]["Displacement"] = (
            str(state["latest_displacement_path"]) if state["latest_displacement_path"] else None
        )
        summary_csv = self._summary_csv_path(case_id)
        state["history_selection"]["Summary Table"] = str(summary_csv) if summary_csv else None
        state["history_selection"]["Comparison Curve"] = None
        visual_history = list(manifest.exported_visual_paths.values())
        state["history_selection"]["Visual Export"] = visual_history[-1] if visual_history else None

    def _available_postprocess_views(self, case_id: str):
        case = CASE_DEFINITIONS[case_id]
        state = self.case_states[case_id]
        manifest = state["manifest"]
        views = ["Mesh", "Damage"]
        has_displacement = bool(state["latest_displacement_path"]) or bool(manifest and manifest.displacement_paths)
        if case.result_profile.startswith("protocol_") or has_displacement:
            views.append("Displacement")
        if len(case.curve_columns) == 2:
            views.append("Curve")
        if case.scan_editor_kind:
            views.append("Summary Table")
        if len(case.comparison_curve_columns) == 2:
            views.append("Comparison Curve")
        if case.visual_exporter:
            views.append("Visual Export")
        return [view_name for view_name in POSTPROCESS_VIEWS if view_name in views]

    def _sync_postprocess_view_combo(self, case_id: str):
        available_views = self._available_postprocess_views(case_id)
        current_view = self.postprocess_view_combo.currentText()
        if current_view not in available_views:
            current_view = available_views[0] if available_views else ""

        self._syncing_postprocess_view = True
        self.postprocess_view_combo.clear()
        self.postprocess_view_combo.addItems(available_views)
        if current_view:
            index = self.postprocess_view_combo.findText(current_view)
            if index >= 0:
                self.postprocess_view_combo.setCurrentIndex(index)
        self._syncing_postprocess_view = False

    def _first_file(self, paths, suffix=""):
        for raw_path in paths:
            path = Path(raw_path)
            if path.exists() and (not suffix or path.suffix == suffix):
                return path
        return None

    def _last_file(self, paths, suffix=""):
        for raw_path in reversed(list(paths)):
            path = Path(raw_path)
            if path.exists() and (not suffix or path.suffix == suffix):
                return path
        return None

    def _load_curve_csv(self, csv_path: Path, case) -> tuple[list[float], list[float]]:
        if len(case.curve_columns) != 2 or not csv_path.exists():
            return [], []

        x_column, y_column = case.curve_columns
        x_values = []
        y_values = []
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                try:
                    x_values.append(float(row[x_column]))
                    y_values.append(float(row[y_column]))
                except (KeyError, TypeError, ValueError):
                    continue
        return x_values, y_values

    def _load_curve_history(self, manifest: RunManifest, case) -> tuple[list[float], list[float]]:
        if not manifest.curve_csv_paths:
            return [], []
        return self._load_curve_csv(Path(manifest.curve_csv_paths[0]), case)

    def _summary_csv_path(self, case_id: str) -> Path | None:
        manifest = self.case_states[case_id]["manifest"]
        if manifest is None:
            return None
        for raw_path in manifest.curve_csv_paths:
            path = Path(raw_path)
            if path.exists() and path.name == "scan_summary.csv":
                return path
        return None

    def _comparison_curve_paths(self, case_id: str):
        case = CASE_DEFINITIONS[case_id]
        manifest = self.case_states[case_id]["manifest"]
        if manifest is None or len(case.comparison_curve_columns) != 2:
            return []
        result = []
        for raw_path in manifest.curve_csv_paths:
            path = Path(raw_path)
            if not path.exists() or path.name == "scan_summary.csv":
                continue
            result.append(path)
        return result

    def _series_label_for_path(self, case_id: str, path: Path) -> str:
        manifest = self.case_states[case_id]["manifest"]
        native_output_dir = Path(manifest.native_output_dir) if manifest is not None and manifest.native_output_dir else None
        if native_output_dir is not None and path.parent != native_output_dir:
            return path.parent.name
        stem = path.stem
        for prefix in ("force_displacement_", "history_"):
            if stem.startswith(prefix):
                stem = stem[len(prefix):]
        return stem

    def _load_xy_from_csv(self, csv_path: Path, x_column: str, y_column: str) -> tuple[list[float], list[float]]:
        if not csv_path.exists():
            return [], []
        x_values = []
        y_values = []
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                try:
                    x_values.append(float(row[x_column]))
                    y_values.append(float(row[y_column]))
                except (KeyError, TypeError, ValueError):
                    continue
        return x_values, y_values

    def _comparison_curve_series(self, case_id: str):
        case = CASE_DEFINITIONS[case_id]
        if len(case.comparison_curve_columns) != 2:
            return []
        x_column, y_column = case.comparison_curve_columns
        series = []
        for path in self._comparison_curve_paths(case_id):
            x_values, y_values = self._load_xy_from_csv(path, x_column, y_column)
            if not x_values or not y_values:
                continue
            series.append(
                {
                    "x": x_values,
                    "y": y_values,
                    "label": self._series_label_for_path(case_id, path),
                }
            )
        return series

    def _populate_summary_table(self, csv_path: Path | None):
        self.postprocess_table.clear()
        if csv_path is None or not csv_path.exists():
            self.postprocess_table.setRowCount(0)
            self.postprocess_table.setColumnCount(0)
            return
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            rows = list(reader)
        if not rows:
            self.postprocess_table.setRowCount(0)
            self.postprocess_table.setColumnCount(0)
            return
        headers = rows[0]
        body = rows[1:]
        self.postprocess_table.setColumnCount(len(headers))
        self.postprocess_table.setRowCount(len(body))
        self.postprocess_table.setHorizontalHeaderLabels(headers)
        for row_index, row in enumerate(body):
            for column_index, value in enumerate(row):
                self.postprocess_table.setItem(row_index, column_index, QTableWidgetItem(value))

    def _active_field_keys(self, case_id: str):
        return CASE_DEFINITIONS[case_id].editable_field_keys

    def _field_is_applicable(self, field_key: str, case_id: str) -> bool:
        return field_key in CASE_DEFINITIONS[case_id].editable_field_keys

    def _sync_visible_fields(self, animate_sections: bool = False):
        case = self._current_case_def()
        visible_mesh_fields = 0
        visible_compute_fields = 0
        scan_visible = bool(case.scan_editor_kind)

        for field_key, binding in self.field_bindings.items():
            widget = binding["widget"]
            form = binding["form"]
            section_binding = binding["section"]
            section = section_binding["section"]
            label_widget = form.labelForField(widget)
            visible = self._field_is_applicable(field_key, case.case_id)
            expanded = section_binding["expanded"]
            widget.setVisible(visible and expanded)
            if label_widget is not None:
                label_widget.setVisible(visible and expanded)
            if visible:
                parent_title = section_binding["title"]
                if parent_title in {"Geometry", "Mesh"}:
                    visible_mesh_fields += 1
                else:
                    visible_compute_fields += 1

        for section_binding in self.section_bindings:
            section = section_binding["section"]
            section_visible = any(self._field_is_applicable(key, case.case_id) for key in section_binding["field_keys"])
            section.setVisible(section_visible)
            if section_visible:
                self._set_section_title(section_binding)
                if section_binding["expanded"]:
                    section.setMaximumHeight(16777215)
                    self._set_section_content_visibility(section_binding, expanded=True)
                else:
                    section.setMaximumHeight(section_binding["collapsed_height"])
                    self._set_section_content_visibility(section_binding, expanded=False)

        self.mesh_empty_label.setVisible(visible_mesh_fields == 0)
        self.compute_empty_label.setVisible(visible_compute_fields == 0 and not scan_visible)
        self.scan_editor_box.setVisible(scan_visible)

    def _sync_run_profile_ui(self, case_id: str):
        case = CASE_DEFINITIONS[case_id]
        state = self.case_states[case_id]
        self._syncing_run_profile = True
        index = self.run_profile_combo.findData(normalize_run_profile(state["run_profile"], fallback=case.default_run_profile))
        if index < 0:
            index = self.run_profile_combo.findData(case.default_run_profile)
        if index >= 0:
            self.run_profile_combo.setCurrentIndex(index)
        self._syncing_run_profile = False

    def _sync_scan_editor(self, case_id: str):
        case = CASE_DEFINITIONS[case_id]
        columns = self._scan_columns_for_case(case_id)
        rows = self.case_states[case_id]["scan_cases"]
        self._syncing_scan_table = True
        self.scan_table.clear()
        self.scan_table.setRowCount(len(rows))
        self.scan_table.setColumnCount(len(columns))
        self.scan_table.setHorizontalHeaderLabels([column.label for column in columns])
        for row_index, row in enumerate(rows):
            for column_index, column in enumerate(columns):
                item = QTableWidgetItem(row.get(column.key, ""))
                self.scan_table.setItem(row_index, column_index, item)
        self._syncing_scan_table = False
        self.scan_editor_intro_label.setText(
            "Edit the scan list for this benchmark." if case.scan_editor_kind else "This benchmark does not use a scan list."
        )
        self._update_scan_editor_enabled_state()

    def _update_scan_editor_enabled_state(self):
        case = self._current_case_def()
        enabled = self.active_run_mode is None and case.is_ready and bool(case.scan_editor_kind)
        self.run_profile_box.setEnabled(self.active_run_mode is None and case.is_ready)
        self.run_profile_combo.setEnabled(self.active_run_mode is None and case.is_ready)
        self.scan_table.setEnabled(enabled)
        self.scan_add_button.setEnabled(enabled)
        self.scan_reset_button.setEnabled(enabled)
        self.scan_remove_button.setEnabled(enabled and self.scan_table.currentRow() >= 0)

    def _apply_case_params_to_inputs(self, case_id: str, animate_sections: bool = False):
        self._syncing_inputs = True
        params = self.case_states[case_id]["params"]
        for key, widget in self.inputs.items():
            widget.setText(params.get(key, ""))
        self._syncing_inputs = False
        self._sync_run_profile_ui(case_id)
        self._sync_scan_editor(case_id)
        self._sync_visible_fields()
        self._update_input_enabled_state()

    def _apply_case_state_to_ui(self):
        state = self._current_state()
        case = self._current_case_def()
        if hasattr(self, "case_status_badge"):
            self.case_status_badge.setText(self._case_badge_text(case))
        self.window_subtitle_label.setText(self._case_header_summary(case))

        self.mesh_intro_label.setText(
            "Generate mesh first, then run compute." if case.mesh_stage_enabled else "This benchmark creates its mesh during compute."
        )
        self.compute_intro_label.setText(
            "Protocol cases stream solver updates in real time." if case.backend_mode == "protocol_julia" else "Batch benchmark runs stream logs and refresh results after completion."
        )

        self.mesh_status_label.setText(state["mesh_status"])
        self.compute_status_label.setText(state["compute_status"])
        self._set_progress_value(state["progress"], animate=False)
        self.curve_canvas.set_curve_kind(case.curve_kind)
        self.curve_canvas.update_curve(state["curve_x"], state["curve_y"])
        self.log_box.setPlainText("\n".join(state["log_lines"]))
        self._scroll_log_to_end()
        self._set_label_image(self.mesh_preview_label, state["mesh_preview_path"], self._mesh_placeholder())
        self._refresh_compute_live_previews()
        self.vtk_label.setText(f"Latest VTK: {state['latest_vtk_path'] or 'None'}")
        self._sync_postprocess_view_combo(case.case_id)
        self.refresh_postprocess_view(prefer_latest=False, animate=False)
        self._sync_run_profile_ui(case.case_id)
        self._sync_scan_editor(case.case_id)
        self._sync_visible_fields()
        self._update_input_enabled_state()
        self._update_tab_availability()

    def _update_input_enabled_state(self):
        case = self._current_case_def()
        inputs_enabled = self.active_run_mode is None and case.is_ready
        self.category_combo.setEnabled(self.active_run_mode is None)
        self.case_combo.setEnabled(self.active_run_mode is None)
        for key, widget in self.inputs.items():
            widget.setEnabled(inputs_enabled and self._field_is_applicable(key, case.case_id))
        self._update_scan_editor_enabled_state()

    def _update_tab_availability(self):
        case = self._current_case_def()
        state = self._current_state()
        mesh_ready = state["mesh_ready"]

        self.tabs.setTabEnabled(self.mesh_tab_index, True)
        if not case.is_ready:
            self.tabs.setTabEnabled(self.compute_tab_index, True)
            self.tabs.setTabEnabled(self.post_tab_index, state["compute_completed"])
            return

        if case.mesh_stage_enabled:
            self.tabs.setTabEnabled(self.compute_tab_index, mesh_ready or self.active_run_mode == "compute")
            self.tabs.setTabEnabled(self.post_tab_index, mesh_ready)
            if not mesh_ready and self.tabs.currentIndex() != self.mesh_tab_index and self.active_run_mode is None:
                self.tabs.setCurrentIndex(self.mesh_tab_index)
        else:
            self.tabs.setTabEnabled(self.compute_tab_index, True)
            self.tabs.setTabEnabled(self.post_tab_index, state["compute_completed"])

    def _set_idle_state(self):
        case = self._current_case_def()
        state = self._current_state()
        self.active_run_mode = None
        self.active_case_id = None
        self._update_input_enabled_state()
        self.generate_mesh_button.setEnabled(case.is_ready and case.mesh_stage_enabled)
        self.run_button.setEnabled(case.is_ready and (not case.mesh_stage_enabled or state["mesh_ready"]))
        self.stop_button.setEnabled(False)
        self._update_tab_availability()

    def _set_busy_state(self, run_mode: str, case_id: str):
        self.active_run_mode = run_mode
        self.active_case_id = case_id
        self._update_input_enabled_state()
        self.generate_mesh_button.setEnabled(False)
        self.run_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.tabs.setTabEnabled(self.post_tab_index, False)
        self.tabs.setCurrentIndex(self.mesh_tab_index if run_mode == "mesh" else self.compute_tab_index)

    def _mesh_placeholder(self):
        return "Generate mesh to view the mesh preview."

    def _damage_placeholder(self):
        return "Run compute to view the damage contour."

    def _displacement_placeholder(self):
        return "Run compute to view the displacement contour."

    def _visual_placeholder(self):
        return "Exported visual panels will appear here."

    def _reset_widget_animations(self, widget: QWidget):
        content_animation = getattr(widget, "_content_animation", None)
        if content_animation is not None:
            content_animation.stop()
            widget._content_animation = None
        opacity_animation = getattr(widget, "_opacity_animation", None)
        if opacity_animation is not None:
            opacity_animation.stop()
            widget._opacity_animation = None
        effect = widget.graphicsEffect()
        if isinstance(effect, QGraphicsOpacityEffect):
            widget.setGraphicsEffect(None)

    def _clear_label_image(self, label: QWidget, placeholder: str):
        if isinstance(label, ImagePreviewWidget):
            self._reset_widget_animations(label)
            label.clear_image(placeholder)
            return
        label.setPixmap(QPixmap())
        label.setText(placeholder)

    def _render_label_image(self, label: QWidget, image_path: Path | None, placeholder: str):
        if isinstance(label, ImagePreviewWidget):
            self._reset_widget_animations(label)
            label.set_image(image_path, placeholder)
            return
        if image_path is None or not image_path.exists():
            self._clear_label_image(label, placeholder)
            return
        pixmap = QPixmap(str(image_path))
        if pixmap.isNull():
            self._clear_label_image(label, placeholder)
            return
        scaled = pixmap.scaled(label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        label.setPixmap(scaled)
        label.setText("")

    def _set_label_image(self, label: QWidget, image_path: Path | None, placeholder: str, animate: bool = True):
        apply_content = lambda: self._render_label_image(label, image_path, placeholder)
        if isinstance(label, ImagePreviewWidget):
            apply_content()
            return
        if not animate or not self._animations_enabled():
            apply_content()
            effect = self._ensure_opacity_effect(label)
            effect.setOpacity(1.0)
            return
        self._animate_content_swap(label, apply_content)

    def _refresh_compute_live_previews(self):
        state = self._current_state()
        self._set_label_image(self.damage_label, state["latest_damage_path"], self._damage_placeholder(), animate=False)
        self._set_label_image(
            self.displacement_label,
            state["latest_displacement_path"],
            "Run compute to view the displacement contour.",
            animate=False,
        )

    def _timeline_views(self):
        return {"Damage", "Displacement"}

    def _timeline_label_text(self, path: Path, frame_index: int, frame_count: int):
        step_value = extract_numeric_suffix(path)
        if step_value is None:
            return f"Frame {frame_index + 1}/{frame_count} | {path.name}"
        return f"Frame {frame_index + 1}/{frame_count} | Step {step_value}"

    def _sync_postprocess_timeline(self, view_name: str, paths, selected_path: Path | None):
        timeline_enabled = view_name in self._timeline_views() and len(paths) > 1
        self._postprocess_timeline_paths = [str(path) for path in paths]
        if not timeline_enabled:
            self._syncing_postprocess_timeline = True
            self.postprocess_timeline_slider.setMinimum(0)
            self.postprocess_timeline_slider.setMaximum(0)
            self.postprocess_timeline_slider.setValue(0)
            self._syncing_postprocess_timeline = False
            self.postprocess_timeline_value_label.setText("Frame 1 / 1")
            self.postprocess_timeline_row.hide()
            return

        selected_path_str = str(selected_path) if selected_path is not None else self._postprocess_timeline_paths[-1]
        try:
            selected_index = self._postprocess_timeline_paths.index(selected_path_str)
        except ValueError:
            selected_index = len(self._postprocess_timeline_paths) - 1

        self._syncing_postprocess_timeline = True
        self.postprocess_timeline_title.setText(f"{view_name} Timeline")
        self.postprocess_timeline_slider.setRange(0, len(self._postprocess_timeline_paths) - 1)
        self.postprocess_timeline_slider.setPageStep(max(1, len(self._postprocess_timeline_paths) // 8))
        self.postprocess_timeline_slider.setValue(selected_index)
        self._syncing_postprocess_timeline = False
        self.postprocess_timeline_value_label.setText(
            self._timeline_label_text(Path(self._postprocess_timeline_paths[selected_index]), selected_index, len(self._postprocess_timeline_paths))
        )
        self.postprocess_timeline_row.show()

    def _render_postprocess_view(self, view_name: str, selected_path: str | None):
        if view_name == "Curve":
            self.postprocess_stack.setCurrentWidget(self.postprocess_curve_canvas)
            self.postprocess_curve_canvas.set_curve_kind(self._current_case_def().curve_kind)
            if selected_path:
                x_values, y_values = self._load_curve_csv(Path(selected_path), self._current_case_def())
            else:
                x_values, y_values = [], []
            self.postprocess_curve_canvas.update_curve(x_values, y_values)
            self._sync_postprocess_timeline(view_name, [], None)
        elif view_name == "Summary Table":
            self.postprocess_stack.setCurrentWidget(self.postprocess_table)
            if selected_path:
                self._populate_summary_table(Path(selected_path))
            else:
                self._populate_summary_table(None)
            self._sync_postprocess_timeline(view_name, [], None)
        elif view_name == "Comparison Curve":
            self.postprocess_stack.setCurrentWidget(self.postprocess_curve_canvas)
            comparison_curve_kind = self._current_case_def().comparison_curve_kind or self._current_case_def().curve_kind
            self.postprocess_curve_canvas.set_curve_kind(comparison_curve_kind)
            self.postprocess_curve_canvas.update_curves(self._comparison_curve_series(self.current_case))
            self._sync_postprocess_timeline(view_name, [], None)
        else:
            image_path, placeholder = self._visible_image_path(view_name)
            timeline_paths = self._history_paths_for_case(self.current_case, view_name)
            selected_image_path = Path(selected_path) if selected_path else image_path
            self.postprocess_stack.setCurrentWidget(self.postprocess_image_panel)
            self._set_label_image(self.postprocess_label, image_path, placeholder, animate=False)
            self._sync_postprocess_timeline(view_name, timeline_paths, selected_image_path)
        detail_text = self._postprocess_detail_text(view_name, selected_path)
        self.postprocess_detail_label.setText(detail_text)
        self.postprocess_detail_label.setToolTip(selected_path or detail_text)
        self._update_postprocess_meta_cards(view_name)
        self._apply_responsive_layout()

    def _visible_image_path(self, view_name: str):
        state = self._current_state()
        if view_name == "Mesh":
            return state["mesh_preview_path"], self._mesh_placeholder()
        if view_name == "Damage":
            path = self.history_combo.currentData()
            return (Path(path), self._damage_placeholder()) if path else (state["latest_damage_path"], self._damage_placeholder())
        if view_name == "Displacement":
            path = self.history_combo.currentData()
            return (Path(path), self._displacement_placeholder()) if path else (state["latest_displacement_path"], self._displacement_placeholder())
        if view_name == "Visual Export":
            path = self.history_combo.currentData()
            return (Path(path), self._visual_placeholder()) if path else (None, self._visual_placeholder())
        return None, "Post-process output will appear here."

    def _postprocess_detail_text(self, view_name: str, selected_path: str | None):
        if view_name == "Summary Table":
            return f"Summary Table: {selected_path}" if selected_path else "Scan summary table will appear here."
        if view_name == "Comparison Curve":
            series = self._comparison_curve_series(self.current_case)
            if series:
                labels = ", ".join(item["label"] for item in series)
                return f"Comparison Curve: {len(series)} Series [{labels}]"
            return "Comparison curves will appear here."
        if view_name == "Visual Export" and selected_path:
            return f"Visual Export: {Path(selected_path).name}"
        if selected_path:
            return f"{view_name}: {selected_path}"
        placeholders = {
            "Mesh": self._mesh_placeholder(),
            "Damage": self._damage_placeholder(),
            "Displacement": self._displacement_placeholder(),
            "Curve": "Curve data will appear here.",
            "Summary Table": "Scan summary table will appear here.",
            "Comparison Curve": "Comparison curves will appear here.",
            "Visual Export": self._visual_placeholder(),
        }
        return placeholders.get(view_name, "Post-process output will appear here.")

    def _history_paths_for_case(self, case_id: str, view_name: str):
        state = self.case_states[case_id]
        manifest = state["manifest"]
        if manifest is None:
            return []
        if view_name == "Mesh":
            return [state["mesh_preview_path"]] if state["mesh_preview_path"] else []
        if view_name == "Damage":
            paths = [Path(path) for path in manifest.snapshot_paths]
            final_damage = state["latest_damage_path"]
            if final_damage and final_damage not in paths:
                paths.append(final_damage)
            return [path for path in paths if path.exists()]
        if view_name == "Displacement":
            paths = [Path(path) for path in manifest.displacement_paths]
            latest_displacement = state["latest_displacement_path"]
            if latest_displacement and latest_displacement not in paths:
                paths.append(latest_displacement)
            return [path for path in paths if path.exists()]
        if view_name == "Curve":
            return [Path(path) for path in manifest.curve_csv_paths if Path(path).exists()]
        if view_name == "Summary Table":
            summary_csv = self._summary_csv_path(case_id)
            return [summary_csv] if summary_csv is not None else []
        if view_name == "Visual Export":
            return [Path(path) for path in state["visual_export_paths"].values() if Path(path).exists()]
        return []

    def _update_postprocess_meta_cards(self, view_name: str):
        latest_vtk = self._current_state()["latest_vtk_path"]
        show_vtk = bool(latest_vtk) and not is_visual_export_view(view_name)
        self.vtk_label.setVisible(show_vtk)

    def _refresh_history_combo(self, prefer_latest: bool):
        view_name = self.postprocess_view_combo.currentText()
        state = self._current_state()
        paths = self._history_paths_for_case(self.current_case, view_name)
        selected_path = state["history_selection"].get(view_name)
        if prefer_latest and paths:
            selected_path = str(paths[-1])
        elif selected_path is None and paths:
            selected_path = str(paths[-1])

        self._syncing_history = True
        self.history_combo.clear()
        for path in paths:
            self.history_combo.addItem(path.name, str(path))
        if paths:
            index = self.history_combo.findData(selected_path)
            if index < 0:
                index = len(paths) - 1
            self.history_combo.setCurrentIndex(index)
            state["history_selection"][view_name] = self.history_combo.currentData()
        else:
            state["history_selection"][view_name] = None
        self.history_combo.setEnabled(bool(paths))
        self._syncing_history = False

    def _scroll_log_to_end(self):
        bar = self.log_box.verticalScrollBar()
        bar.setValue(bar.maximum())

    def on_category_combo_changed(self, _index: int):
        if self._syncing_selection:
            return
        category_id = self.category_combo.currentData()
        if not category_id or category_id == self.current_category:
            return
        self.current_category = category_id
        preferred_case = first_case_for_category(category_id).case_id
        self._refresh_case_combo(category_id, preferred_case_id=preferred_case)
        self.current_case = self.case_combo.currentData()
        self._apply_case_params_to_inputs(self.current_case)
        self._apply_case_state_to_ui()
        self._set_idle_state()

    def on_case_combo_changed(self, _index: int):
        if self._syncing_selection:
            return
        case_id = self.case_combo.currentData()
        if not case_id or case_id == self.current_case:
            return
        self.current_case = case_id
        self.current_category = CASE_DEFINITIONS[case_id].category_id
        self._apply_case_params_to_inputs(case_id)
        self._apply_case_state_to_ui()
        self._set_idle_state()

    def on_input_changed(self, field_key: str, mesh_field: bool):
        if self._syncing_inputs:
            return
        state = self._current_state()
        state["params"][field_key] = self.inputs[field_key].text().strip()
        if mesh_field and self._current_case_def().mesh_stage_enabled:
            self._invalidate_case_mesh_state(self.current_case, clear_log=False)
            self._apply_case_state_to_ui()
            if self.active_run_mode is None:
                self._set_idle_state()

    def on_run_profile_changed(self, _index: int):
        if self._syncing_run_profile:
            return
        profile = self.run_profile_combo.currentData()
        self._current_state()["run_profile"] = normalize_run_profile(profile, fallback=self._current_case_def().default_run_profile)

    def on_scan_item_changed(self, item: QTableWidgetItem):
        if self._syncing_scan_table:
            return
        columns = self._scan_columns_for_case(self.current_case)
        if not columns:
            return
        row_index = item.row()
        column = columns[item.column()]
        rows = self._current_state()["scan_cases"]
        while row_index >= len(rows):
            rows.append(self._default_scan_row(self.current_case, len(rows)))
        rows[row_index][column.key] = item.text().strip()

    def on_scan_selection_changed(self):
        self._update_scan_editor_enabled_state()

    def on_scan_add_row(self):
        case = self._current_case_def()
        if not case.scan_editor_kind:
            return
        rows = self._current_state()["scan_cases"]
        rows.append(self._default_scan_row(case.case_id, len(rows)))
        self._sync_scan_editor(case.case_id)
        last_row = self.scan_table.rowCount() - 1
        if last_row >= 0:
            self.scan_table.selectRow(last_row)

    def on_scan_remove_row(self):
        case = self._current_case_def()
        if not case.scan_editor_kind:
            return
        row_index = self.scan_table.currentRow()
        if row_index < 0:
            return
        rows = self._current_state()["scan_cases"]
        if 0 <= row_index < len(rows):
            del rows[row_index]
        self._sync_scan_editor(case.case_id)
        if self.scan_table.rowCount():
            self.scan_table.selectRow(min(row_index, self.scan_table.rowCount() - 1))

    def on_scan_reset_default(self):
        case = self._current_case_def()
        self._current_state()["scan_cases"] = self._clone_default_scan_cases(case.case_id)
        self._sync_scan_editor(case.case_id)

    def on_postprocess_view_changed(self, _view_name: str):
        if self._syncing_postprocess_view:
            return
        self.refresh_postprocess_view(prefer_latest=False, animate=True)

    def on_history_changed(self, _index: int):
        if self._syncing_history:
            return
        view_name = self.postprocess_view_combo.currentText()
        self._current_state()["history_selection"][view_name] = self.history_combo.currentData()
        self.refresh_postprocess_view(prefer_latest=False, animate=True)

    def on_postprocess_timeline_changed(self, frame_index: int):
        if self._syncing_postprocess_timeline:
            return
        if frame_index < 0 or frame_index >= self.history_combo.count():
            return
        if self.history_combo.currentIndex() != frame_index:
            self.history_combo.setCurrentIndex(frame_index)
            return
        if 0 <= frame_index < len(self._postprocess_timeline_paths):
            self.postprocess_timeline_value_label.setText(
                self._timeline_label_text(Path(self._postprocess_timeline_paths[frame_index]), frame_index, len(self._postprocess_timeline_paths))
            )

    def append_log(self, text: str):
        state = self._active_state()
        state["log_lines"].append(text)
        if len(state["log_lines"]) > 500:
            state["log_lines"] = state["log_lines"][-500:]
        if self.active_case_id == self.current_case:
            self.log_box.appendPlainText(text)
            self._scroll_log_to_end()

    def set_status(self, text: str):
        state = self._active_state()
        if self.active_run_mode == "mesh":
            state["mesh_status"] = text
            if self.active_case_id == self.current_case:
                self.mesh_status_label.setText(text)
        else:
            state["compute_status"] = text
            if self.active_case_id == self.current_case:
                self.compute_status_label.setText(text)

    def update_progress(self, value: float):
        state = self._active_state()
        state["progress"] = value
        if self.active_case_id == self.current_case:
            self._set_progress_value(value, animate=True)

    def update_step(self, x_value: float, y_value: float, marker_value: float, step: int):
        state = self._active_state()
        state["curve_x"].append(x_value)
        state["curve_y"].append(y_value)
        state["compute_status"] = f"Step {step} | x={x_value:.4e} | y={y_value:.4e} | marker={marker_value:.4f}"
        if self.active_case_id == self.current_case:
            self.curve_canvas.update_curve(state["curve_x"], state["curve_y"])
            self.compute_status_label.setText(state["compute_status"])

    def update_snapshot(self, image_path: str):
        path = Path(image_path)
        if not path.exists() or path.suffix.lower() != ".png":
            return
        state = self._active_state()
        if self.active_run_mode == "mesh":
            state["mesh_preview_path"] = path
            state["history_selection"]["Mesh"] = str(path)
            if self.active_case_id == self.current_case:
                self._set_label_image(self.mesh_preview_label, path, self._mesh_placeholder())
        else:
            state["latest_damage_path"] = path
            state["history_selection"]["Damage"] = str(path)
            if self.active_case_id == self.current_case:
                self._refresh_compute_live_previews()
        if self.active_case_id == self.current_case:
            self.refresh_postprocess_view(prefer_latest=True, animate=self.tabs.currentIndex() == self.post_tab_index)

    def update_vtk_path(self, vtk_path: str):
        state = self._active_state()
        state["latest_vtk_path"] = vtk_path
        if self.active_case_id == self.current_case:
            self.vtk_label.setText(f"Latest VTK: {vtk_path}")

    def update_displacement_path(self, image_path: str):
        path = Path(image_path)
        if not path.exists():
            return
        state = self._active_state()
        state["latest_displacement_path"] = path
        state["history_selection"]["Displacement"] = str(path)
        if self.active_case_id == self.current_case:
            self._refresh_compute_live_previews()
            self.refresh_postprocess_view(prefer_latest=True, animate=self.tabs.currentIndex() == self.post_tab_index)

    def collect_params(self):
        params = {}
        for key in self._active_field_keys(self.current_case):
            raw = self.inputs[key].text().strip()
            if key in INT_FIELDS:
                params[key] = int(raw)
            elif key in BOOL_FIELDS:
                params[key] = raw.lower() in {"1", "true", "yes", "on"}
            else:
                params[key] = float(raw)
        return params

    def _effective_params_for_run(self, case, params, run_profile: str):
        return apply_run_profile_overrides(params, self._run_profile_overrides_for_case(case.case_id), run_profile)

    def _seed_run_with_mesh_assets(self, case):
        self.active_mesh_artifact_path = None
        if self.active_native_output_dir is None or not case.mesh_stage_enabled:
            return

        state = self.case_states[case.case_id]
        mesh_artifact_path = state["mesh_artifact_path"]
        mesh_preview_path = state["mesh_preview_path"]
        for source_path in (mesh_artifact_path, mesh_preview_path):
            if source_path is None or not Path(source_path).exists():
                continue
            destination = self.active_native_output_dir / Path(source_path).name
            if Path(source_path).resolve() != destination.resolve():
                shutil.copy2(source_path, destination)
            if Path(source_path).suffix == ".msh":
                self.active_mesh_artifact_path = destination

    def write_runtime_params(self, case, payload):
        params_path = run_runtime_params_path(case.case_id, self.active_run_id)
        params_path.parent.mkdir(parents=True, exist_ok=True)
        params_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self.runtime_params_path = params_path
        return self.runtime_params_path

    def _build_protocol_runtime_payload(self, case, params, run_mode: str, run_profile: str):
        payload = dict(params)
        payload["run_id"] = self.active_run_id
        payload["run_dir"] = str(self.active_run_dir.resolve())
        payload["output_dir"] = str(self.active_native_output_dir.resolve())
        payload["python_executable"] = sys.executable
        payload["case_name"] = case.protocol_case_name
        payload["run_mode"] = run_mode
        payload["run_profile"] = normalize_run_profile(run_profile, fallback=case.default_run_profile)
        payload["mesh_file"] = str(self.active_mesh_artifact_path or self._current_state()["mesh_artifact_path"] or "")
        return payload

    def _build_batch_runtime_payload(self, case, params, run_mode: str, run_profile: str, scan_cases):
        return {
            "run_id": self.active_run_id,
            "run_dir": str(self.active_run_dir.resolve()),
            "output_dir": str(self.active_native_output_dir.resolve()),
            "case_id": case.case_id,
            "run_mode": run_mode,
            "run_profile": normalize_run_profile(run_profile, fallback=case.default_run_profile),
            "scan_cases": scan_cases,
            "params": params,
        }

    def cleanup_runtime_params(self):
        self.runtime_params_path = None
        self.active_run_dir = None
        self.active_native_output_dir = None
        self.active_mesh_artifact_path = None
        self.active_run_profile = None

    def _clear_case_compute_outputs(self, case_id: str, clear_log: bool):
        case = CASE_DEFINITIONS[case_id]
        state = self.case_states[case_id]
        state["compute_completed"] = False
        state["curve_x"] = []
        state["curve_y"] = []
        state["progress"] = 0
        if clear_log:
            state["log_lines"] = []
        state["compute_status"] = self._default_compute_status(case)
        state["latest_damage_path"] = None
        state["latest_displacement_path"] = None
        state["latest_vtk_path"] = ""
        state["visual_export_paths"] = {}
        state["manifest"] = None
        state["manifest_path"] = None
        state["run_id"] = None
        state["run_dir"] = None
        state["runtime_params_path"] = None
        state["history_selection"]["Damage"] = None
        state["history_selection"]["Displacement"] = None
        state["history_selection"]["Summary Table"] = None
        state["history_selection"]["Comparison Curve"] = None
        state["history_selection"]["Visual Export"] = None

    def _invalidate_case_mesh_state(self, case_id: str, clear_log: bool):
        case = CASE_DEFINITIONS[case_id]
        state = self.case_states[case_id]
        state["mesh_ready"] = False
        state["mesh_artifact_path"] = None
        state["mesh_preview_path"] = None
        state["mesh_status"] = self._default_mesh_status(case)
        state["history_selection"]["Mesh"] = None
        self._clear_case_compute_outputs(case_id, clear_log=clear_log)

    def _start_worker(self, run_mode: str, params, case, run_profile: str, scan_cases):
        self.cleanup_runtime_params()
        if STOP_FLAG.exists():
            STOP_FLAG.unlink()

        self.active_run_id = make_run_id(case.case_id)
        self.active_run_profile = normalize_run_profile(run_profile, fallback=case.default_run_profile)
        self.active_run_dir = run_dir(case.case_id, self.active_run_id)
        self.active_native_output_dir = run_native_dir(case.case_id, self.active_run_id)
        self.active_native_output_dir.mkdir(parents=True, exist_ok=True)
        if run_mode == "compute":
            self._seed_run_with_mesh_assets(case)
        if case.backend_mode == "protocol_julia":
            params_path = self.write_runtime_params(case, self._build_protocol_runtime_payload(case, params, run_mode, self.active_run_profile))
            self.worker = ProtocolJuliaWorker(case.case_id, case.protocol_case_name, params_path, run_mode)
        else:
            assert case.script_abspath is not None
            params_path = self.write_runtime_params(
                case,
                self._build_batch_runtime_payload(case, params, run_mode, self.active_run_profile, scan_cases),
            )
            self.worker = BatchJuliaWorker(case.case_id, case.script_abspath, params_path, run_mode)

        self.worker.log_line.connect(self.append_log)
        self.worker.progress_update.connect(self.update_progress)
        self.worker.step_update.connect(self.update_step)
        self.worker.snapshot_update.connect(self.update_snapshot)
        self.worker.vtk_update.connect(self.update_vtk_path)
        self.worker.displacement_update.connect(self.update_displacement_path)
        self.worker.status_update.connect(self.set_status)
        self.worker.finished_state.connect(self.on_worker_finished)
        self._set_busy_state(run_mode, case.case_id)
        self.worker.start()

    def start_mesh_generation(self):
        case = self._current_case_def()
        if not case.is_ready:
            QMessageBox.warning(self, "Planned Case", "This benchmark is listed but not integrated yet.")
            return
        if not case.mesh_stage_enabled:
            QMessageBox.warning(self, "Mesh Unavailable", "This benchmark builds its mesh during the compute stage.")
            return
        try:
            params = self.collect_params()
            scan_cases = self._collect_scan_cases(case)
        except ValueError as exc:
            QMessageBox.critical(self, "Invalid Input", str(exc))
            return
        run_profile = self._current_state()["run_profile"]
        effective_params = self._effective_params_for_run(case, params, run_profile)

        self._invalidate_case_mesh_state(self.current_case, clear_log=True)
        self._apply_case_state_to_ui()
        self._current_state()["mesh_status"] = f"Generating {case.display_name} mesh..."
        self.mesh_status_label.setText(self._current_state()["mesh_status"])
        self.log_box.clear()
        self._clear_label_image(self.mesh_preview_label, "Waiting for mesh preview...")
        self._start_worker("mesh", effective_params, case, run_profile, scan_cases)

    def start_run(self):
        case = self._current_case_def()
        state = self._current_state()
        if not case.is_ready:
            QMessageBox.warning(self, "Planned Case", "This benchmark is listed but not integrated yet.")
            return
        if case.mesh_stage_enabled and (not state["mesh_ready"] or state["mesh_artifact_path"] is None):
            QMessageBox.warning(self, "Mesh Required", "Generate mesh first before running compute.")
            return
        try:
            params = self.collect_params()
            scan_cases = self._collect_scan_cases(case)
        except ValueError as exc:
            QMessageBox.critical(self, "Invalid Input", str(exc))
            return
        run_profile = self._current_state()["run_profile"]
        effective_params = self._effective_params_for_run(case, params, run_profile)

        self._clear_case_compute_outputs(self.current_case, clear_log=True)
        self._apply_case_state_to_ui()
        state = self._current_state()
        state["compute_status"] = f"Starting {case.display_name} compute stage..."
        self.compute_status_label.setText(state["compute_status"])
        self.log_box.clear()
        self._start_worker("compute", effective_params, case, run_profile, scan_cases)

    def stop_run(self):
        if self.worker is None:
            return
        self.worker.stop()
        self.stop_button.setEnabled(False)

    def refresh_postprocess_view(self, prefer_latest: bool, animate: bool = True):
        self._refresh_history_combo(prefer_latest=prefer_latest)
        view_name = self.postprocess_view_combo.currentText()
        selected_path = self.history_combo.currentData()
        apply_content = lambda: self._render_postprocess_view(view_name, selected_path)
        apply_content()
        if animate and self._animations_enabled():
            self._animate_widget_opacity(self.postprocess_detail_label, start=0.36, end=1.0, duration=ANIMATION_MEDIUM_MS)

    def export_results(self):
        state = self._current_state()
        manifest = state["manifest"]
        if manifest is None:
            QMessageBox.warning(self, "No Results", "No result files are available to export for the current case.")
            return

        target_dir = QFileDialog.getExistingDirectory(self, "Select Output Folder", str(REPO_ROOT))
        if not target_dir:
            return

        target_path = Path(target_dir)
        archived_run_dir = Path(manifest.run_dir) if manifest.run_dir else None
        if archived_run_dir is not None and archived_run_dir.exists():
            destination = target_path / archived_run_dir.name
            shutil.copytree(archived_run_dir, destination, dirs_exist_ok=True)
            visual_paths = [Path(path) for path in manifest.exported_visual_paths.values()]
            if visual_paths:
                export_root = destination / "visual_exports"
                export_root.mkdir(parents=True, exist_ok=True)
                for path in visual_paths:
                    if path.exists():
                        shutil.copy2(path, export_root / path.name)
            QMessageBox.information(self, "Results Saved", f"Saved run bundle to {destination}.")
            return

        copied_count = 0
        for source_path in manifest_file_payloads(manifest):
            shutil.copy2(source_path, target_path / source_path.name)
            copied_count += 1

        if state["manifest_path"] is not None and Path(state["manifest_path"]).exists():
            shutil.copy2(state["manifest_path"], target_path / Path(state["manifest_path"]).name)
            copied_count += 1

        QMessageBox.information(self, "Results Saved", f"Saved {copied_count} payload(s) to {target_path}.")

    def _build_manifest_after_run(self, case):
        perform_export = bool(case.visual_exporter)
        manifest = self._build_manifest_from_disk(
            case,
            perform_export=perform_export,
            run_profile=self.active_run_profile,
            run_id=self.active_run_id,
            run_dir_path=self.active_run_dir,
            runtime_params_path=self.runtime_params_path,
        )
        if manifest is None:
            return None, None
        archived_manifest = run_manifest_path(case.case_id, self.active_run_id)
        write_manifest(archived_manifest, manifest)
        write_manifest(latest_manifest_path(case.case_id), manifest)
        return archived_manifest, manifest

    def on_worker_finished(self, success: bool, case_id: str, run_mode: str, message: str):
        if STOP_FLAG.exists():
            STOP_FLAG.unlink()

        was_stopped = message == "Stopped by user."
        case = CASE_DEFINITIONS[case_id]
        state = self.case_states[case_id]

        if success and not was_stopped:
            manifest_path, manifest = self._build_manifest_after_run(case)
            if manifest is not None and manifest_path is not None:
                self._apply_manifest_to_state(case_id, manifest_path, manifest)
            if run_mode == "mesh":
                state["mesh_status"] = "Mesh ready."
            else:
                state["compute_completed"] = True
                state["compute_status"] = message
        else:
            if run_mode == "mesh":
                state["mesh_status"] = message
            else:
                state["compute_status"] = message

        self.worker = None
        self.active_case_id = None
        self.active_run_mode = None
        self.active_run_id = None
        self.cleanup_runtime_params()

        if self.current_case == case_id:
            self._apply_case_state_to_ui()
            self._set_idle_state()
            self._show_run_feedback(run_mode, success, was_stopped, message)

        if not success:
            QMessageBox.warning(self, "Run Finished", message)

    def eventFilter(self, watched, event):
        if isinstance(watched, QPushButton):
            if event.type() == QEvent.Enter:
                self._animate_button_hover(watched, hovered=True)
            elif event.type() == QEvent.Leave:
                self._animate_button_hover(watched, hovered=False)
            elif event.type() in {QEvent.EnabledChange, QEvent.Hide}:
                watched.setProperty("floating", False)
                self.style().unpolish(watched)
                self.style().polish(watched)
                self._button_rest_geometries[watched] = QRect(watched.geometry())
            elif event.type() in {QEvent.Show, QEvent.Move, QEvent.Resize} and not watched.property("floating"):
                self._button_rest_geometries[watched] = QRect(watched.geometry())
        elif isinstance(watched, QGroupBox) and watched.property("collapsible_section"):
            if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton and event.pos().y() <= 34:
                binding = self._section_bindings_by_widget.get(watched)
                if binding is not None:
                    self._toggle_section(watched, expanded=not binding["expanded"], animate=True)
                    return True
        return super().eventFilter(watched, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_responsive_layout()
        self._position_toast()
        for button in (
            self.generate_mesh_button,
            self.run_button,
            self.stop_button,
            self.scan_add_button,
            self.scan_remove_button,
            self.scan_reset_button,
            self.export_results_button,
        ):
            if not button.property("floating"):
                self._button_rest_geometries[button] = QRect(button.geometry())

    def closeEvent(self, event):
        if self.worker is not None and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(5000)
        self.cleanup_runtime_params()
        if not self.keep_transient_results:
            purge_transient_gui_results()
        super().closeEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        if self._entrance_animation_started:
            return
        self._entrance_animation_started = True
        self._position_toast()
        self._animate_widget_opacity(self.case_status_badge, start=0.0, end=1.0, duration=ANIMATION_MEDIUM_MS)

    def on_tab_changed(self, index: int):
        page = self.tabs.widget(index)
        if page is not None and self.isVisible():
            self._animate_widget_opacity(self.case_status_badge, start=0.52, end=1.0, duration=ANIMATION_FAST_MS)


def main():
    if not load_transient_cache_preference():
        purge_transient_gui_results()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    app = QApplication(sys.argv)
    app_font = QFont(resolve_qt_serif_font_family(), APP_FONT_SIZE)
    app_font.setStyleHint(QFont.Serif)
    app.setFont(app_font)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
