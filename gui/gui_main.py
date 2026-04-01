from __future__ import annotations

import csv
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import matplotlib as mpl
from PyQt5.QtCore import QThread, Qt, pyqtSignal
from PyQt5.QtGui import QFont, QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QTabWidget,
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
        first_case_for_category,
        iter_cases_for_category,
        status_display,
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
        first_case_for_category,
        iter_cases_for_category,
        status_display,
    )
    from .run_manifest import RunManifest, dedupe_existing_paths, load_manifest, make_run_id, manifest_file_payloads, write_manifest


RESULTS_DIR = GUI_DIR / "gui_results"
MANIFEST_DIR = RESULTS_DIR / "manifests"
VISUAL_EXPORT_DIR = RESULTS_DIR / "visual_exports"
STOP_FLAG = GUI_DIR / "gui_stop.flag"
DEFAULT_PARAMS_PATH = GUI_DIR / "params_default.json"
APP_FONT_FAMILY = "Times New Roman"
JULIA_COMMAND = "julia"
GUI_ENVS_JULIA_PROJECT = "/home/dazhi_zhao/miniforge3/envs/gui_envs/share/julia/environments/gui_envs"
GUI_ENVS_JULIA_DEPOT = "/home/dazhi_zhao/miniforge3/envs/gui_envs/share/julia"

mpl.rcParams["font.family"] = APP_FONT_FAMILY


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


def first_existing(*paths: Path) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def sorted_existing(paths):
    return [path for path in sorted(paths) if path.exists()]


def julia_env_prefix() -> str:
    return (
        f'export JULIA_PROJECT="{GUI_ENVS_JULIA_PROJECT}" && '
        f'export JULIA_DEPOT_PATH="{GUI_ENVS_JULIA_DEPOT}" && '
    )


class CurveCanvas(FigureCanvas):
    def __init__(self):
        self.figure = Figure(figsize=(5, 4), tight_layout=True)
        self.axes = self.figure.add_subplot(111)
        self._x_label = "u (mm)"
        self._y_label = "F (kN)"
        super().__init__(self.figure)
        self.update_curve([], [])

    def set_curve_kind(self, curve_kind: str):
        self._x_label, self._y_label = CURVE_AXIS_LABELS.get(curve_kind, ("x", "y"))
        self.update_curve([], [])

    def update_curve(self, x_values, y_values):
        self.axes.clear()
        self.axes.plot(x_values, y_values, color="#1f77b4", linewidth=2.0)
        self.axes.set_xlabel(self._x_label)
        self.axes.set_ylabel(self._y_label)
        self.axes.grid(True)
        for spine in self.axes.spines.values():
            spine.set_visible(True)
        self.draw_idle()


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
        self.setWindowTitle("peng_pf_ui - Benchmark Workbench")
        self.resize(1560, 940)

        self.worker = None
        self.active_run_mode = None
        self.active_case_id = None
        self.runtime_params_path = None
        self.active_run_id = None
        self._syncing_inputs = False
        self._syncing_history = False
        self._syncing_selection = False

        self.paraview_executable = shutil.which("paraview")
        self.default_params = self._load_default_params()
        self.current_category = CATEGORY_ORDER[0]
        self.current_case = first_case_for_category(self.current_category).case_id
        self.case_states = {case.case_id: self._new_case_state(case.case_id) for case in CASE_REGISTRY}

        self.inputs = {}
        self.field_bindings = {}
        self.section_bindings = []

        self._build_ui()
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

    def _new_case_state(self, case_id: str):
        case = CASE_DEFINITIONS[case_id]
        return {
            "params": dict(self.default_params.get(case_id, {})),
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

    def _build_ui(self):
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(10)

        top_row = QHBoxLayout()
        title = QLabel("Benchmark Workbench")
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        top_row.addWidget(title)
        top_row.addStretch(1)

        top_row.addWidget(QLabel("Category"))
        self.category_combo = QComboBox()
        self.category_combo.currentIndexChanged.connect(self.on_category_combo_changed)
        top_row.addWidget(self.category_combo)

        top_row.addWidget(QLabel("Case"))
        self.case_combo = QComboBox()
        self.case_combo.currentIndexChanged.connect(self.on_case_combo_changed)
        top_row.addWidget(self.case_combo)
        root_layout.addLayout(top_row)

        self.case_status_badge = QLabel("")
        self.case_status_badge.setStyleSheet("color: #555555;")
        root_layout.addWidget(self.case_status_badge)

        self.tabs = QTabWidget()
        self.mesh_tab_index = self.tabs.addTab(self._build_mesh_tab(), "Mesh")
        self.compute_tab_index = self.tabs.addTab(self._build_compute_tab(), "Compute")
        self.post_tab_index = self.tabs.addTab(self._build_postprocess_tab(), "Post-process")
        root_layout.addWidget(self.tabs)
        self.setCentralWidget(root)

    def _build_mesh_tab(self):
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setSpacing(12)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setSpacing(10)

        self.mesh_intro_label = QLabel("")
        self.mesh_intro_label.setWordWrap(True)
        left_layout.addWidget(self.mesh_intro_label)

        for group_title, fields in MESH_FIELD_SPECS:
            box = QGroupBox(group_title)
            form = QFormLayout(box)
            form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            field_keys = []
            for field in fields:
                line_edit = QLineEdit(self._current_state()["params"].get(field.key, ""))
                line_edit.textChanged.connect(lambda _text, field_key=field.key, mesh_field=True: self.on_input_changed(field_key, mesh_field))
                form.addRow(field.label, line_edit)
                self.inputs[field.key] = line_edit
                self.field_bindings[field.key] = {"widget": line_edit, "form": form, "section": box}
                field_keys.append(field.key)
            self.section_bindings.append({"section": box, "field_keys": field_keys})
            left_layout.addWidget(box)

        self.mesh_empty_label = QLabel("This case has no editable mesh parameters in the GUI.")
        self.mesh_empty_label.setWordWrap(True)
        left_layout.addWidget(self.mesh_empty_label)

        self.generate_mesh_button = QPushButton("Generate Mesh")
        self.generate_mesh_button.clicked.connect(self.start_mesh_generation)
        left_layout.addWidget(self.generate_mesh_button)

        self.mesh_status_label = QLabel("")
        self.mesh_status_label.setWordWrap(True)
        left_layout.addWidget(self.mesh_status_label)
        left_layout.addStretch(1)

        self.mesh_preview_label = self._create_image_label("Mesh preview will appear here.")
        layout.addWidget(left_panel, stretch=0)
        layout.addWidget(self.mesh_preview_label, stretch=1)
        return page

    def _build_compute_tab(self):
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setSpacing(12)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setSpacing(10)

        self.compute_intro_label = QLabel("")
        self.compute_intro_label.setWordWrap(True)
        left_layout.addWidget(self.compute_intro_label)

        for group_title, fields in COMPUTE_FIELD_SPECS:
            box = QGroupBox(group_title)
            form = QFormLayout(box)
            form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            field_keys = []
            for field in fields:
                line_edit = QLineEdit(self._current_state()["params"].get(field.key, ""))
                line_edit.textChanged.connect(lambda _text, field_key=field.key, mesh_field=False: self.on_input_changed(field_key, mesh_field))
                form.addRow(field.label, line_edit)
                self.inputs[field.key] = line_edit
                self.field_bindings[field.key] = {"widget": line_edit, "form": form, "section": box}
                field_keys.append(field.key)
            self.section_bindings.append({"section": box, "field_keys": field_keys})
            left_layout.addWidget(box)

        self.compute_empty_label = QLabel("This case currently runs with its benchmark defaults.")
        self.compute_empty_label.setWordWrap(True)
        left_layout.addWidget(self.compute_empty_label)

        button_row = QHBoxLayout()
        self.run_button = QPushButton("Run")
        self.stop_button = QPushButton("Stop")
        self.run_button.clicked.connect(self.start_run)
        self.stop_button.clicked.connect(self.stop_run)
        button_row.addWidget(self.run_button)
        button_row.addWidget(self.stop_button)
        left_layout.addLayout(button_row)

        self.compute_status_label = QLabel("")
        self.compute_status_label.setWordWrap(True)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        left_layout.addWidget(self.compute_status_label)
        left_layout.addWidget(self.progress_bar)

        self.log_box = QPlainTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMaximumBlockCount(500)
        left_layout.addWidget(self.log_box, stretch=1)
        left_panel.setMaximumWidth(460)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setSpacing(10)

        self.damage_label = self._create_image_label("Damage snapshot will appear here.")
        self.curve_canvas = CurveCanvas()
        right_layout.addWidget(self.damage_label, stretch=3)
        right_layout.addWidget(self.curve_canvas, stretch=2)

        layout.addWidget(left_panel, stretch=0)
        layout.addWidget(right_panel, stretch=1)
        return page

    def _build_postprocess_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("View"))
        self.postprocess_view_combo = QComboBox()
        self.postprocess_view_combo.addItems(POSTPROCESS_VIEWS)
        self.postprocess_view_combo.currentTextChanged.connect(self.on_postprocess_view_changed)
        top_row.addWidget(self.postprocess_view_combo)

        top_row.addWidget(QLabel("History"))
        self.history_combo = QComboBox()
        self.history_combo.currentIndexChanged.connect(self.on_history_changed)
        top_row.addWidget(self.history_combo, stretch=1)

        self.open_paraview_button = QPushButton("Open in ParaView")
        self.open_paraview_button.clicked.connect(self.open_in_paraview)
        top_row.addWidget(self.open_paraview_button)

        self.export_results_button = QPushButton("Save Results")
        self.export_results_button.clicked.connect(self.export_results)
        top_row.addWidget(self.export_results_button)
        layout.addLayout(top_row)

        self.postprocess_label = self._create_image_label("Post-process output will appear here.")
        layout.addWidget(self.postprocess_label, stretch=1)

        self.vtk_label = QLabel("Latest VTK: none")
        self.vtk_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.vtk_label)
        return page

    def _create_image_label(self, text: str):
        label = QLabel(text)
        label.setAlignment(Qt.AlignCenter)
        label.setMinimumHeight(420)
        label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        label.setStyleSheet("border: 1px solid #b0b0b0; background: #fafafa;")
        label.setWordWrap(True)
        return label

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
            self.case_combo.addItem(f"{case.display_name} [{status_display(case)}]", case.case_id)
        target_case = preferred_case_id or first_case_for_category(category_id).case_id
        index = self.case_combo.findData(target_case)
        if index < 0 and self.case_combo.count():
            index = 0
        if index >= 0:
            self.case_combo.setCurrentIndex(index)
            self.current_case = self.case_combo.currentData()
        self._syncing_selection = False

    def _load_manifests_from_disk(self):
        for case in CASE_REGISTRY:
            manifest_path = latest_manifest_path(case.case_id)
            if manifest_path.exists():
                try:
                    manifest = load_manifest(manifest_path)
                except Exception:
                    manifest = None
                if manifest is not None:
                    self._apply_manifest_to_state(case.case_id, manifest_path, manifest)
                    continue
            manifest = self._build_manifest_from_disk(case, perform_export=bool(case.visual_exporter))
            if manifest is not None:
                manifest_path = latest_manifest_path(case.case_id)
                write_manifest(manifest_path, manifest)
                self._apply_manifest_to_state(case.case_id, manifest_path, manifest)

    def _build_manifest_from_disk(self, case, perform_export: bool):
        if case.result_profile.startswith("protocol_"):
            manifest = self._build_protocol_manifest(case)
        elif case.result_profile == "elastic_fatigue_tpb":
            manifest = self._build_tpb_manifest(case)
        elif case.result_profile == "elastic_fatigue_offset_scan":
            manifest = self._build_offset_scan_manifest(case)
        elif case.result_profile == "plastic_fracture_flat_grooved_scan":
            manifest = self._build_fang_manifest(case)
        elif case.result_profile == "plastic_fracture_double_notched_scan":
            manifest = self._build_double_notched_manifest(case)
        elif case.result_profile == "plastic_fatigue_sent":
            manifest = self._build_plastic_fatigue_sent_manifest(case)
        elif case.result_profile == "plastic_fatigue_ct":
            manifest = self._build_plastic_fatigue_ct_manifest(case)
        else:
            manifest = None
        if manifest is None:
            return None
        if self.active_run_id is not None:
            manifest.run_id = self.active_run_id
        if perform_export and case.visual_exporter:
            self._populate_visual_exports(case, manifest)
        return manifest

    def _build_protocol_manifest(self, case):
        case_name = case.protocol_case_name
        mesh_msh = RESULTS_DIR / mesh_file_name(case_name)
        mesh_png = RESULTS_DIR / mesh_png_name(case_name)
        curve_csv = first_existing(RESULTS_DIR / curve_csv_name(case_name), RESULTS_DIR / "F_u_curve.csv" if case_name == "SENT" else RESULTS_DIR / curve_csv_name(case_name))
        damage_final = first_existing(RESULTS_DIR / damage_final_name(case_name), RESULTS_DIR / "d_final.png" if case_name == "SENT" else RESULTS_DIR / damage_final_name(case_name))
        displacement = first_existing(RESULTS_DIR / displacement_final_name(case_name))

        snapshot_patterns = [f"snap_{case_name}_*.png"]
        vtk_patterns = [f"{result_prefix(case_name)}*.vtu"]
        if case_name == "SENT":
            snapshot_patterns.append("snap_*.png")
            vtk_patterns.append("result_final.vtu")

        snapshot_paths = []
        for pattern in snapshot_patterns:
            snapshot_paths.extend(path for path in RESULTS_DIR.glob(pattern) if path.is_file())
        vtk_paths = []
        for pattern in vtk_patterns:
            vtk_paths.extend(path for path in RESULTS_DIR.glob(pattern) if path.is_file())

        if not any([mesh_msh.exists(), mesh_png.exists(), curve_csv is not None, snapshot_paths, vtk_paths, damage_final, displacement]):
            return None

        return RunManifest(
            category_id=case.category_id,
            case_id=case.case_id,
            run_id=make_run_id(case.case_id),
            status="completed",
            backend_mode=case.backend_mode,
            curve_kind=case.curve_kind,
            source_script=str((GUI_DIR / "gui_solver.jl").resolve()),
            native_output_dir=str(RESULTS_DIR.resolve()),
            mesh_paths=dedupe_existing_paths([mesh_msh, mesh_png]),
            snapshot_paths=dedupe_existing_paths(snapshot_paths),
            vtk_paths=dedupe_existing_paths(vtk_paths),
            curve_csv_paths=dedupe_existing_paths([curve_csv] if curve_csv else []),
            damage_paths=dedupe_existing_paths([damage_final] if damage_final else []),
            displacement_paths=dedupe_existing_paths([displacement] if displacement else []),
        )

    def _build_batch_manifest(
        self,
        case,
        native_output_dir: Path,
        *,
        mesh_paths,
        snapshot_paths=(),
        vtk_paths=(),
        curve_csv_paths=(),
        damage_paths=(),
        displacement_paths=(),
    ):
        if not any([mesh_paths, snapshot_paths, vtk_paths, curve_csv_paths, damage_paths, displacement_paths]):
            return None

        return RunManifest(
            category_id=case.category_id,
            case_id=case.case_id,
            run_id=make_run_id(case.case_id),
            status="completed",
            backend_mode=case.backend_mode,
            curve_kind=case.curve_kind,
            source_script=str(case.script_abspath.resolve()) if case.script_abspath else "",
            native_output_dir=str(native_output_dir.resolve()),
            mesh_paths=dedupe_existing_paths(mesh_paths),
            snapshot_paths=dedupe_existing_paths(snapshot_paths),
            vtk_paths=dedupe_existing_paths(vtk_paths),
            curve_csv_paths=dedupe_existing_paths(curve_csv_paths),
            damage_paths=dedupe_existing_paths(damage_paths),
            displacement_paths=dedupe_existing_paths(displacement_paths),
        )

    def _collect_files(self, base_dir: Path, patterns, recursive: bool = True):
        files = []
        for pattern in patterns:
            iterator = base_dir.rglob(pattern) if recursive else base_dir.glob(pattern)
            files.extend(path for path in iterator if path.is_file())
        return files

    def _build_tpb_manifest(self, case):
        native_output_dir = case.native_output_abspath
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
            mesh_paths=mesh_paths,
            vtk_paths=vtk_paths,
            curve_csv_paths=curve_csv_paths,
            damage_paths=damage_paths,
        )

    def _build_fang_manifest(self, case):
        native_output_dir = case.native_output_abspath
        if native_output_dir is None or not native_output_dir.exists():
            return None

        scan_summary = native_output_dir / "scan_summary.csv"

        return self._build_batch_manifest(
            case,
            native_output_dir,
            mesh_paths=self._collect_files(native_output_dir, ("*.msh", "geometry_mesh.png")),
            snapshot_paths=self._collect_files(native_output_dir, ("damage_*.png",)),
            vtk_paths=self._collect_files(native_output_dir, ("result_*.vtu",)),
            curve_csv_paths=([scan_summary] if scan_summary.exists() else []) + self._collect_files(native_output_dir, ("force_displacement_*.csv",)),
        )

    def _build_offset_scan_manifest(self, case):
        native_output_dir = case.native_output_abspath
        if native_output_dir is None or not native_output_dir.exists():
            return None
        return self._build_batch_manifest(
            case,
            native_output_dir,
            mesh_paths=self._collect_files(native_output_dir, ("mesh_offset_double_notch.msh", "mesh.png")),
            vtk_paths=self._collect_files(native_output_dir, ("result_*.vtu",)),
            damage_paths=self._collect_files(native_output_dir, ("damage_final.png",)),
        )

    def _build_double_notched_manifest(self, case):
        native_output_dir = case.native_output_abspath
        if native_output_dir is None or not native_output_dir.exists():
            return None
        return self._build_batch_manifest(
            case,
            native_output_dir,
            mesh_paths=self._collect_files(native_output_dir, ("mesh_double_notched.msh", "mesh_double_notched.png")),
            snapshot_paths=self._collect_files(native_output_dir, ("damage_*.png",)),
            vtk_paths=self._collect_files(native_output_dir, ("result_*.vtu",)),
        )

    def _build_plastic_fatigue_sent_manifest(self, case):
        native_output_dir = case.native_output_abspath
        if native_output_dir is None or not native_output_dir.exists():
            return None
        return self._build_batch_manifest(
            case,
            native_output_dir,
            mesh_paths=self._collect_files(native_output_dir, ("mesh.msh", "mesh.png"), recursive=False),
            snapshot_paths=self._collect_files(native_output_dir, ("damage_N*.png",), recursive=False),
            vtk_paths=self._collect_files(native_output_dir, ("result_*.vtu",), recursive=False),
            curve_csv_paths=self._collect_files(native_output_dir, ("cycle_summary.csv",), recursive=False),
        )

    def _build_plastic_fatigue_ct_manifest(self, case):
        native_output_dir = case.native_output_abspath
        if native_output_dir is None or not native_output_dir.exists():
            return None
        return self._build_batch_manifest(
            case,
            native_output_dir,
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
            manifest.exported_visual_paths = export_visuals(case.visual_exporter, native_output_dir, export_dir)
        except Exception as exc:
            manifest.exported_visual_paths = {}
            manifest.notes.append(f"Visual export failed: {exc}")

    def _apply_manifest_to_state(self, case_id: str, manifest_path: Path, manifest: RunManifest):
        state = self.case_states[case_id]
        case = CASE_DEFINITIONS[case_id]
        state["manifest_path"] = manifest_path
        state["manifest"] = manifest
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
        visual_history = list(manifest.exported_visual_paths.values())
        state["history_selection"]["Visual Export"] = visual_history[-1] if visual_history else None

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

    def _load_curve_history(self, manifest: RunManifest, case) -> tuple[list[float], list[float]]:
        if len(case.curve_columns) != 2:
            return [], []
        if not manifest.curve_csv_paths:
            return [], []
        csv_path = Path(manifest.curve_csv_paths[0])
        if not csv_path.exists():
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

    def _active_field_keys(self, case_id: str):
        return CASE_DEFINITIONS[case_id].editable_field_keys

    def _field_is_applicable(self, field_key: str, case_id: str) -> bool:
        return field_key in CASE_DEFINITIONS[case_id].editable_field_keys

    def _sync_visible_fields(self):
        case = self._current_case_def()
        visible_mesh_fields = 0
        visible_compute_fields = 0

        for field_key, binding in self.field_bindings.items():
            widget = binding["widget"]
            form = binding["form"]
            section = binding["section"]
            label_widget = form.labelForField(widget)
            visible = self._field_is_applicable(field_key, case.case_id)
            widget.setVisible(visible)
            if label_widget is not None:
                label_widget.setVisible(visible)
            if visible:
                parent_title = section.title()
                if parent_title in {"Geometry", "Mesh"}:
                    visible_mesh_fields += 1
                else:
                    visible_compute_fields += 1

        for section_binding in self.section_bindings:
            section = section_binding["section"]
            section_visible = any(self._field_is_applicable(key, case.case_id) for key in section_binding["field_keys"])
            section.setVisible(section_visible)

        self.mesh_empty_label.setVisible(visible_mesh_fields == 0)
        self.compute_empty_label.setVisible(visible_compute_fields == 0)

    def _apply_case_params_to_inputs(self, case_id: str):
        self._syncing_inputs = True
        params = self.case_states[case_id]["params"]
        for key, widget in self.inputs.items():
            widget.setText(params.get(key, ""))
        self._syncing_inputs = False
        self._sync_visible_fields()
        self._update_input_enabled_state()

    def _apply_case_state_to_ui(self):
        state = self._current_state()
        case = self._current_case_def()
        if hasattr(self, "case_status_badge"):
            self.case_status_badge.setText(
                f"{case.category_label} / {case.display_name} | backend={case.backend_mode} | status={status_display(case)}"
            )

        self.mesh_intro_label.setText(
            "Generate mesh first, then run compute." if case.mesh_stage_enabled else "This benchmark creates its mesh during compute."
        )
        self.compute_intro_label.setText(
            "Protocol cases stream solver updates in real time." if case.backend_mode == "protocol_julia" else "Batch benchmark runs stream logs and refresh results after completion."
        )

        self.mesh_status_label.setText(state["mesh_status"])
        self.compute_status_label.setText(state["compute_status"])
        self.progress_bar.setValue(max(0, min(100, int(round(state["progress"])))))
        self.curve_canvas.set_curve_kind(case.curve_kind)
        self.curve_canvas.update_curve(state["curve_x"], state["curve_y"])
        self.log_box.setPlainText("\n".join(state["log_lines"]))
        self._scroll_log_to_end()
        self._set_label_image(self.mesh_preview_label, state["mesh_preview_path"], self._mesh_placeholder())
        self._set_label_image(self.damage_label, state["latest_damage_path"], self._damage_placeholder())
        self.vtk_label.setText(f"Latest VTK: {state['latest_vtk_path'] or 'none'}")
        self.refresh_postprocess_view(prefer_latest=False)
        self._sync_visible_fields()
        self._update_input_enabled_state()
        self._update_tab_availability()
        self._update_paraview_button()

    def _update_input_enabled_state(self):
        case = self._current_case_def()
        inputs_enabled = self.active_run_mode is None and case.is_ready
        self.category_combo.setEnabled(self.active_run_mode is None)
        self.case_combo.setEnabled(self.active_run_mode is None)
        for key, widget in self.inputs.items():
            widget.setEnabled(inputs_enabled and self._field_is_applicable(key, case.case_id))

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
        self._update_paraview_button()

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

    def _clear_label_image(self, label: QLabel, placeholder: str):
        label.setPixmap(QPixmap())
        label.setText(placeholder)

    def _set_label_image(self, label: QLabel, image_path: Path | None, placeholder: str):
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
            return [state["latest_displacement_path"]] if state["latest_displacement_path"] else []
        if view_name == "Visual Export":
            return [Path(path) for path in state["visual_export_paths"].values() if Path(path).exists()]
        return []

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

    def _update_paraview_button(self):
        latest_vtk = self._current_state()["latest_vtk_path"]
        enabled = bool(self.paraview_executable and latest_vtk and Path(latest_vtk).exists())
        self.open_paraview_button.setEnabled(enabled)

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

    def on_postprocess_view_changed(self, _view_name: str):
        self.refresh_postprocess_view(prefer_latest=False)

    def on_history_changed(self, _index: int):
        if self._syncing_history:
            return
        view_name = self.postprocess_view_combo.currentText()
        self._current_state()["history_selection"][view_name] = self.history_combo.currentData()
        image_path, placeholder = self._visible_image_path(view_name)
        self._set_label_image(self.postprocess_label, image_path, placeholder)

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
            self.progress_bar.setValue(max(0, min(100, int(round(value)))))

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
                self._set_label_image(self.damage_label, path, self._damage_placeholder())
        if self.active_case_id == self.current_case:
            self.refresh_postprocess_view(prefer_latest=True)

    def update_vtk_path(self, vtk_path: str):
        state = self._active_state()
        state["latest_vtk_path"] = vtk_path
        if self.active_case_id == self.current_case:
            self.vtk_label.setText(f"Latest VTK: {vtk_path}")
            self._update_paraview_button()

    def update_displacement_path(self, image_path: str):
        path = Path(image_path)
        if not path.exists():
            return
        state = self._active_state()
        state["latest_displacement_path"] = path
        state["history_selection"]["Displacement"] = str(path)
        if self.active_case_id == self.current_case:
            self.refresh_postprocess_view(prefer_latest=True)

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

    def write_runtime_params(self, payload):

        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            prefix="gui_params_",
            dir=str(RESULTS_DIR),
            delete=False,
            encoding="utf-8",
        )
        with handle:
            json.dump(payload, handle, indent=2)
        self.runtime_params_path = Path(handle.name)
        return self.runtime_params_path

    def _build_protocol_runtime_payload(self, case, params, run_mode: str):
        payload = dict(params)
        payload["case_name"] = case.protocol_case_name
        payload["run_mode"] = run_mode
        payload["mesh_file"] = str(self._current_state()["mesh_artifact_path"] or "")
        return payload

    def _build_batch_runtime_payload(self, case, params, run_mode: str):
        return {
            "case_id": case.case_id,
            "run_mode": run_mode,
            "smoke_mode": case.smoke_mode_default,
            "params": params,
        }

    def cleanup_runtime_params(self):
        if self.runtime_params_path and self.runtime_params_path.exists():
            self.runtime_params_path.unlink()
        self.runtime_params_path = None

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
        state["history_selection"]["Damage"] = None
        state["history_selection"]["Displacement"] = None
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

    def _start_worker(self, run_mode: str, params, case):
        self.cleanup_runtime_params()
        if STOP_FLAG.exists():
            STOP_FLAG.unlink()

        self.active_run_id = make_run_id(case.case_id)
        if case.backend_mode == "protocol_julia":
            params_path = self.write_runtime_params(self._build_protocol_runtime_payload(case, params, run_mode))
            self.worker = ProtocolJuliaWorker(case.case_id, case.protocol_case_name, params_path, run_mode)
        else:
            assert case.script_abspath is not None
            params_path = self.write_runtime_params(self._build_batch_runtime_payload(case, params, run_mode))
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
            QMessageBox.warning(self, "Planned case", "This benchmark is listed but not integrated yet.")
            return
        if not case.mesh_stage_enabled:
            QMessageBox.warning(self, "Mesh unavailable", "This benchmark builds its mesh during the compute stage.")
            return
        try:
            params = self.collect_params()
        except ValueError as exc:
            QMessageBox.critical(self, "Invalid input", str(exc))
            return

        self._invalidate_case_mesh_state(self.current_case, clear_log=True)
        self._apply_case_state_to_ui()
        self._current_state()["mesh_status"] = f"Generating {case.display_name} mesh..."
        self.mesh_status_label.setText(self._current_state()["mesh_status"])
        self._clear_label_image(self.mesh_preview_label, "Waiting for mesh preview...")
        self._start_worker("mesh", params, case)

    def start_run(self):
        case = self._current_case_def()
        state = self._current_state()
        if not case.is_ready:
            QMessageBox.warning(self, "Planned case", "This benchmark is listed but not integrated yet.")
            return
        if case.mesh_stage_enabled and (not state["mesh_ready"] or state["mesh_artifact_path"] is None):
            QMessageBox.warning(self, "Mesh required", "Generate mesh first before running compute.")
            return
        try:
            params = self.collect_params()
        except ValueError as exc:
            QMessageBox.critical(self, "Invalid input", str(exc))
            return

        self._clear_case_compute_outputs(self.current_case, clear_log=True)
        self._apply_case_state_to_ui()
        state = self._current_state()
        state["compute_status"] = f"Starting {case.display_name} compute stage..."
        self.compute_status_label.setText(state["compute_status"])
        self._start_worker("compute", params, case)

    def stop_run(self):
        if self.worker is None:
            return
        self.worker.stop()
        self.stop_button.setEnabled(False)

    def refresh_postprocess_view(self, prefer_latest: bool):
        self._refresh_history_combo(prefer_latest=prefer_latest)
        view_name = self.postprocess_view_combo.currentText()
        image_path, placeholder = self._visible_image_path(view_name)
        self._set_label_image(self.postprocess_label, image_path, placeholder)
        self._update_paraview_button()

    def open_in_paraview(self):
        latest_vtk = self._current_state()["latest_vtk_path"]
        if not self.paraview_executable:
            QMessageBox.warning(self, "ParaView unavailable", "The `paraview` executable was not found in PATH.")
            return
        if not latest_vtk or not Path(latest_vtk).exists():
            QMessageBox.warning(self, "VTK unavailable", "No VTK file is available for the current case.")
            return
        try:
            subprocess.Popen([self.paraview_executable, latest_vtk], cwd=str(REPO_ROOT))
        except Exception as exc:
            QMessageBox.critical(self, "ParaView launch failed", str(exc))

    def export_results(self):
        state = self._current_state()
        manifest = state["manifest"]
        if manifest is None:
            QMessageBox.warning(self, "No results", "No result files are available to export for the current case.")
            return

        target_dir = QFileDialog.getExistingDirectory(self, "Select Output Folder", str(REPO_ROOT))
        if not target_dir:
            return

        target_path = Path(target_dir)
        copied_count = 0

        if manifest.native_output_dir and self._current_case_def().backend_mode == "batch_script":
            native_output_dir = Path(manifest.native_output_dir)
            if native_output_dir.exists():
                destination = target_path / native_output_dir.name
                shutil.copytree(native_output_dir, destination, dirs_exist_ok=True)
                copied_count += 1
            visual_paths = [Path(path) for path in manifest.exported_visual_paths.values()]
            if visual_paths:
                export_root = target_path / f"{self.current_case}_visual_exports"
                export_root.mkdir(parents=True, exist_ok=True)
                for path in visual_paths:
                    shutil.copy2(path, export_root / path.name)
                    copied_count += 1
        else:
            for source_path in manifest_file_payloads(manifest):
                shutil.copy2(source_path, target_path / source_path.name)
                copied_count += 1

        if state["manifest_path"] is not None and Path(state["manifest_path"]).exists():
            shutil.copy2(state["manifest_path"], target_path / Path(state["manifest_path"]).name)
            copied_count += 1

        QMessageBox.information(self, "Results saved", f"Saved {copied_count} payload(s) to {target_path}.")

    def _build_manifest_after_run(self, case):
        perform_export = bool(case.visual_exporter)
        manifest = self._build_manifest_from_disk(case, perform_export=perform_export)
        if manifest is None:
            return None, None
        manifest_path = latest_manifest_path(case.case_id)
        write_manifest(manifest_path, manifest)
        return manifest_path, manifest

    def on_worker_finished(self, success: bool, case_id: str, run_mode: str, message: str):
        self.cleanup_runtime_params()
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

        if self.current_case == case_id:
            self._apply_case_state_to_ui()
            self._set_idle_state()

        if not success:
            QMessageBox.warning(self, "Run finished", message)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        state = self._current_state()
        self._set_label_image(self.mesh_preview_label, state["mesh_preview_path"], self._mesh_placeholder())
        self._set_label_image(self.damage_label, state["latest_damage_path"], self._damage_placeholder())
        self.refresh_postprocess_view(prefer_latest=False)

    def closeEvent(self, event):
        if self.worker is not None and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(5000)
        self.cleanup_runtime_params()
        if STOP_FLAG.exists():
            STOP_FLAG.unlink()
        super().closeEvent(event)


def main():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    app = QApplication(sys.argv)
    app.setFont(QFont(APP_FONT_FAMILY, 11))
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
