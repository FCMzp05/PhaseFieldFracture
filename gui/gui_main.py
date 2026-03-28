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


REPO_ROOT = Path(__file__).resolve().parent.parent
GUI_DIR = Path(__file__).resolve().parent
RESULTS_DIR = GUI_DIR / "gui_results"
STOP_FLAG = GUI_DIR / "gui_stop.flag"
DEFAULT_PARAMS_PATH = GUI_DIR / "params_default.json"
CONDA_HOOK = "/home/dazhi_zhao/miniforge3/bin/conda"

CASE_NAMES = ("SENT", "SENS")
POSTPROCESS_VIEWS = ("Mesh", "Damage", "Displacement")
APP_FONT_FAMILY = "Times New Roman"

COMMON_FIELDS = (
    "W",
    "H",
    "a0",
    "E",
    "nu",
    "Gc",
    "l0",
    "eta_k",
    "h_fine",
    "h_coarse",
    "snapshot_every",
)
CASE_FIELDS = {
    "SENT": ("N_steps_coarse", "du_coarse", "du_fine", "u_end"),
    "SENS": ("du_shear", "u_end"),
}
FIELD_CASES = {
    "W": set(CASE_NAMES),
    "H": set(CASE_NAMES),
    "a0": set(CASE_NAMES),
    "h_fine": set(CASE_NAMES),
    "h_coarse": set(CASE_NAMES),
    "E": set(CASE_NAMES),
    "nu": set(CASE_NAMES),
    "Gc": set(CASE_NAMES),
    "l0": set(CASE_NAMES),
    "eta_k": set(CASE_NAMES),
    "N_steps_coarse": {"SENT"},
    "du_coarse": {"SENT"},
    "du_fine": {"SENT"},
    "du_shear": {"SENS"},
    "u_end": set(CASE_NAMES),
    "snapshot_every": set(CASE_NAMES),
}
MESH_FIELD_SPECS = [
    ("Geometry", [
        ("W", "Width W (mm)", set(CASE_NAMES)),
        ("H", "Height H (mm)", set(CASE_NAMES)),
        ("a0", "Pre-crack a0 (mm)", set(CASE_NAMES)),
    ]),
    ("Mesh", [
        ("h_fine", "Fine mesh h_fine (mm)", set(CASE_NAMES)),
        ("h_coarse", "Coarse mesh h_coarse (mm)", set(CASE_NAMES)),
    ]),
]
COMPUTE_FIELD_SPECS = [
    ("Material", [
        ("E", "Young's modulus E (MPa)", set(CASE_NAMES)),
        ("nu", "Poisson ratio nu", set(CASE_NAMES)),
    ]),
    ("Phase Field", [
        ("Gc", "Gc (N/mm)", set(CASE_NAMES)),
        ("l0", "Length scale l0 (mm)", set(CASE_NAMES)),
        ("eta_k", "Residual stiffness eta_k", set(CASE_NAMES)),
    ]),
    ("Loading", [
        ("N_steps_coarse", "Coarse steps", {"SENT"}),
        ("du_coarse", "du coarse (mm)", {"SENT"}),
        ("du_fine", "du fine (mm)", {"SENT"}),
        ("du_shear", "du shear (mm)", {"SENS"}),
        ("u_end", "Max displacement u_end (mm)", set(CASE_NAMES)),
        ("snapshot_every", "Snapshot every N steps", set(CASE_NAMES)),
    ]),
]
INT_FIELDS = {"N_steps_coarse", "snapshot_every"}

mpl.rcParams["font.family"] = APP_FONT_FAMILY


def mesh_file_name(case_name: str) -> str:
    return f"mesh_{case_name}.msh"


def mesh_png_name(case_name: str) -> str:
    return f"mesh_{case_name}.png"


def curve_csv_name(case_name: str) -> str:
    return f"F_u_curve_{case_name}.csv"


def curve_png_name(case_name: str) -> str:
    return f"F_u_curve_{case_name}.png"


def damage_final_name(case_name: str) -> str:
    return f"d_final_{case_name}.png"


def displacement_final_name(case_name: str) -> str:
    return f"u_mag_final_{case_name}.png"


def result_prefix(case_name: str) -> str:
    return f"result_{case_name}_"


class JuliaWorker(QThread):
    log_line = pyqtSignal(str)
    progress_update = pyqtSignal(float)
    step_update = pyqtSignal(int, float, float, float)
    snapshot_update = pyqtSignal(str)
    vtk_update = pyqtSignal(str)
    displacement_update = pyqtSignal(str)
    status_update = pyqtSignal(str)
    finished_state = pyqtSignal(bool, str, str, str)

    def __init__(self, params_path: Path, run_mode: str, case_name: str):
        super().__init__()
        self.params_path = params_path
        self.run_mode = run_mode
        self.case_name = case_name
        self._process = None
        self._stop_requested = False

    def stop(self):
        self._stop_requested = True
        STOP_FLAG.write_text("stop\n", encoding="utf-8")
        self.status_update.emit("Stopping solver...")

    def run(self):
        solver_path = GUI_DIR / "gui_solver.jl"
        cmd = (
            f'eval "$({CONDA_HOOK} shell.bash hook)" && '
            f"conda activate pf_env && "
            f'julia "{solver_path}" "{self.params_path}"'
        )
        stage_label = "mesh" if self.run_mode == "mesh" else "compute"
        self.status_update.emit(f"Launching Julia {self.case_name} {stage_label} stage...")
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
            self.finished_state.emit(success, self.case_name, self.run_mode, message)

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
        self.step_update.emit(step, u_value, f_value, dmax)


class CurveCanvas(FigureCanvas):
    def __init__(self):
        self.figure = Figure(figsize=(5, 4), tight_layout=True)
        self.axes = self.figure.add_subplot(111)
        super().__init__(self.figure)
        self.update_curve([], [])

    def update_curve(self, u_values, f_values_kn):
        self.axes.clear()
        self.axes.plot(u_values, f_values_kn, color="#1f77b4", linewidth=2.0)
        self.axes.set_xlabel("u (mm)")
        self.axes.set_ylabel("F (kN)")
        self.axes.grid(True)
        for spine in self.axes.spines.values():
            spine.set_visible(True)
        self.draw_idle()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("peng_pf_ui - SENT/SENS Three-Stage Workflow")
        self.resize(1520, 920)

        self.worker = None
        self.active_run_mode = None
        self.active_case_name = None
        self.runtime_params_path = None
        self.current_case = CASE_NAMES[0]
        self.paraview_executable = shutil.which("paraview")
        self._syncing_inputs = False
        self._syncing_history = False

        self.default_params = self._load_default_params()
        self.case_states = {case_name: self._new_case_state(case_name) for case_name in CASE_NAMES}

        self.inputs = {}
        self.mesh_input_widgets = []
        self.compute_input_widgets = []

        self._build_ui()
        self._apply_case_params_to_inputs(self.current_case)
        self._apply_case_state_to_ui()
        self._set_idle_state()

    def _format_value(self, value):
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, int):
            return str(value)
        if isinstance(value, float):
            return format(value, ".15g")
        return str(value)

    def _load_default_params(self):
        with DEFAULT_PARAMS_PATH.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)

        common = {key: self._format_value(value) for key, value in raw["common"].items()}
        case_defaults = {}
        all_case_values = {}
        for case_name in CASE_NAMES:
            case_payload = raw["cases"].get(case_name, {})
            for key, value in case_payload.items():
                all_case_values[key] = self._format_value(value)

        for case_name in CASE_NAMES:
            merged = dict(common)
            merged.update(all_case_values)
            merged.update({key: self._format_value(value) for key, value in raw["cases"].get(case_name, {}).items()})
            case_defaults[case_name] = merged
        return case_defaults

    def _new_case_state(self, case_name: str):
        return {
            "params": dict(self.default_params[case_name]),
            "mesh_ready": False,
            "mesh_artifact_path": None,
            "mesh_preview_path": None,
            "mesh_status": "Mesh not generated.",
            "compute_completed": False,
            "u_history": [],
            "f_history_kn": [],
            "compute_status": "Waiting for compute stage.",
            "progress": 0,
            "latest_damage_path": None,
            "latest_displacement_path": None,
            "latest_vtk_path": "",
            "log_lines": [],
            "history_selection": {view_name: None for view_name in POSTPROCESS_VIEWS},
        }

    def _current_state(self):
        return self.case_states[self.current_case]

    def _active_state(self):
        case_name = self.active_case_name or self.current_case
        return self.case_states[case_name]

    def _field_is_applicable(self, field_key: str, case_name: str) -> bool:
        return case_name in FIELD_CASES[field_key]

    def _active_field_keys(self, case_name: str):
        keys = list(COMMON_FIELDS)
        for field_key in CASE_FIELDS.get(case_name, ()):
            if field_key not in keys:
                keys.append(field_key)
        return keys

    def _case_result_files(self, case_name: str):
        files = []
        if not RESULTS_DIR.exists():
            return files
        for path in RESULTS_DIR.iterdir():
            if not path.is_file() or path.name.startswith("gui_params_"):
                continue
            name = path.name
            if name in {
                mesh_file_name(case_name),
                mesh_png_name(case_name),
                curve_csv_name(case_name),
                curve_png_name(case_name),
                damage_final_name(case_name),
                displacement_final_name(case_name),
            }:
                files.append(path)
                continue
            if name.startswith(f"snap_{case_name}_") or name.startswith(result_prefix(case_name)):
                files.append(path)
        return sorted(files)

    def _load_curve_history(self, csv_path: Path):
        u_values = []
        f_values_kn = []
        if not csv_path.exists():
            return u_values, f_values_kn

        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                try:
                    u_values.append(float(row["u_mm"]))
                    f_values_kn.append(float(row["F_kN"]))
                except (KeyError, TypeError, ValueError):
                    continue
        return u_values, f_values_kn

    def _sync_case_results_from_disk(self, case_name: str):
        state = self.case_states[case_name]
        mesh_path = RESULTS_DIR / mesh_file_name(case_name)
        mesh_png_path = RESULTS_DIR / mesh_png_name(case_name)
        damage_path = RESULTS_DIR / damage_final_name(case_name)
        displacement_path = RESULTS_DIR / displacement_final_name(case_name)
        curve_csv_path = RESULTS_DIR / curve_csv_name(case_name)
        vtk_paths = sorted(
            RESULTS_DIR.glob(f"{result_prefix(case_name)}*.vtu"),
            key=lambda path: path.stat().st_mtime,
        )
        snapshot_paths = sorted(RESULTS_DIR.glob(f"snap_{case_name}_*.png"))

        state["mesh_artifact_path"] = mesh_path if mesh_path.exists() else None
        state["mesh_preview_path"] = mesh_png_path if mesh_png_path.exists() else None
        state["mesh_ready"] = state["mesh_artifact_path"] is not None
        state["mesh_status"] = "Mesh ready." if state["mesh_ready"] else "Mesh not generated."

        state["latest_damage_path"] = damage_path if damage_path.exists() else (snapshot_paths[-1] if snapshot_paths else None)
        state["latest_displacement_path"] = displacement_path if displacement_path.exists() else None
        state["latest_vtk_path"] = str(vtk_paths[-1]) if vtk_paths else ""
        state["compute_completed"] = bool(
            snapshot_paths or damage_path.exists() or displacement_path.exists() or curve_csv_path.exists() or vtk_paths
        )
        if state["compute_completed"]:
            state["u_history"], state["f_history_kn"] = self._load_curve_history(curve_csv_path)
            if state["compute_status"] == "Waiting for compute stage.":
                state["compute_status"] = "Latest results loaded from disk."
        else:
            state["u_history"] = []
            state["f_history_kn"] = []
            state["compute_status"] = "Waiting for compute stage."
            state["progress"] = 0

    def _build_ui(self):
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(10)

        top_row = QHBoxLayout()
        title = QLabel("Phase 2 Workflow")
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        top_row.addWidget(title)
        top_row.addStretch(1)
        top_row.addWidget(QLabel("Case"))
        self.case_combo = QComboBox()
        self.case_combo.addItems(CASE_NAMES)
        self.case_combo.currentTextChanged.connect(self.on_case_changed)
        top_row.addWidget(self.case_combo)
        root_layout.addLayout(top_row)

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

        intro = QLabel("Stage 1: generate the case-specific mesh first, then unlock compute.")
        intro.setWordWrap(True)
        left_layout.addWidget(intro)

        for group_title, fields in MESH_FIELD_SPECS:
            box = QGroupBox(group_title)
            form = QFormLayout(box)
            for key, label, _cases in fields:
                line_edit = QLineEdit(self._current_state()["params"].get(key, ""))
                line_edit.textChanged.connect(
                    lambda _text, field_key=key, mesh_field=True: self.on_input_changed(field_key, mesh_field)
                )
                form.addRow(label, line_edit)
                self.inputs[key] = line_edit
                self.mesh_input_widgets.append(line_edit)
            left_layout.addWidget(box)

        self.generate_mesh_button = QPushButton("Generate Mesh")
        self.generate_mesh_button.clicked.connect(self.start_mesh_generation)
        left_layout.addWidget(self.generate_mesh_button)

        self.mesh_status_label = QLabel("Mesh not generated.")
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

        intro = QLabel("Stage 2: solve on the generated mesh and stream case-specific F-u and contour results.")
        intro.setWordWrap(True)
        left_layout.addWidget(intro)

        for group_title, fields in COMPUTE_FIELD_SPECS:
            box = QGroupBox(group_title)
            form = QFormLayout(box)
            for key, label, _cases in fields:
                line_edit = QLineEdit(self._current_state()["params"].get(key, ""))
                line_edit.textChanged.connect(
                    lambda _text, field_key=key, mesh_field=False: self.on_input_changed(field_key, mesh_field)
                )
                form.addRow(label, line_edit)
                self.inputs[key] = line_edit
                self.compute_input_widgets.append(line_edit)
            left_layout.addWidget(box)

        button_row = QHBoxLayout()
        self.run_button = QPushButton("Run")
        self.stop_button = QPushButton("Stop")
        self.run_button.clicked.connect(self.start_run)
        self.stop_button.clicked.connect(self.stop_run)
        button_row.addWidget(self.run_button)
        button_row.addWidget(self.stop_button)
        left_layout.addLayout(button_row)

        self.compute_status_label = QLabel("Waiting for compute stage.")
        self.compute_status_label.setWordWrap(True)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        left_layout.addWidget(self.compute_status_label)
        left_layout.addWidget(self.progress_bar)

        self.log_box = QPlainTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMaximumBlockCount(400)
        left_layout.addWidget(self.log_box, stretch=1)
        left_panel.setMaximumWidth(440)

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

    def _clear_label_image(self, label: QLabel, placeholder: str):
        label.setPixmap(QPixmap())
        label.setText(placeholder)

    def _set_label_image(self, label: QLabel, image_path: Path, placeholder: str):
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

    def _mesh_placeholder(self):
        return "Generate mesh to view the mesh preview."

    def _damage_placeholder(self):
        return "Run compute to view the damage contour."

    def _displacement_placeholder(self):
        return "Run compute to view the displacement contour."

    def _visible_image_path(self, view_name: str):
        state = self._current_state()
        if view_name == "Mesh":
            return state["mesh_preview_path"], self._mesh_placeholder()
        if view_name == "Damage":
            path = self.history_combo.currentData()
            if isinstance(path, str) and path:
                return Path(path), self._damage_placeholder()
            return state["latest_damage_path"], self._damage_placeholder()
        if view_name == "Displacement":
            path = self.history_combo.currentData()
            if isinstance(path, str) and path:
                return Path(path), self._displacement_placeholder()
            return state["latest_displacement_path"], self._displacement_placeholder()
        return None, "Post-process output will appear here."

    def _history_paths_for_case(self, case_name: str, view_name: str):
        state = self.case_states[case_name]
        if view_name == "Mesh":
            if state["mesh_ready"] and state["mesh_preview_path"] and state["mesh_preview_path"].exists():
                return [state["mesh_preview_path"]]
            return []
        if view_name == "Damage":
            if not state["compute_completed"] and state["latest_damage_path"] is None:
                return []
            paths = sorted(RESULTS_DIR.glob(f"snap_{case_name}_*.png"))
            final_path = RESULTS_DIR / damage_final_name(case_name)
            if final_path.exists():
                paths.append(final_path)
            elif state["latest_damage_path"] and state["latest_damage_path"].exists() and state["latest_damage_path"] not in paths:
                paths.append(state["latest_damage_path"])
            return paths
        if view_name == "Displacement":
            if state["latest_displacement_path"] and state["latest_displacement_path"].exists():
                return [state["latest_displacement_path"]]
            final_path = RESULTS_DIR / displacement_final_name(case_name)
            return [final_path] if final_path.exists() else []
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

    def _apply_case_params_to_inputs(self, case_name: str):
        self._syncing_inputs = True
        params = self.case_states[case_name]["params"]
        for key, widget in self.inputs.items():
            widget.setText(params.get(key, ""))
        self.case_combo.setCurrentText(case_name)
        self._syncing_inputs = False
        self._update_input_enabled_state()

    def _apply_case_state_to_ui(self):
        state = self._current_state()
        self.mesh_status_label.setText(state["mesh_status"])
        self.compute_status_label.setText(state["compute_status"])
        self.progress_bar.setValue(max(0, min(100, int(round(state["progress"])))))
        self.curve_canvas.update_curve(state["u_history"], state["f_history_kn"])
        self.log_box.setPlainText("\n".join(state["log_lines"]))
        self._scroll_log_to_end()
        self._set_label_image(self.mesh_preview_label, state["mesh_preview_path"], self._mesh_placeholder())
        self._set_label_image(self.damage_label, state["latest_damage_path"], "Damage snapshot will appear here.")
        self.vtk_label.setText(f"Latest VTK: {state['latest_vtk_path'] or 'none'}")
        self.refresh_postprocess_view(prefer_latest=False)
        self._update_input_enabled_state()
        self._update_tab_availability()
        self._update_paraview_button()

    def _update_input_enabled_state(self):
        inputs_enabled = self.active_run_mode is None
        self.case_combo.setEnabled(inputs_enabled)
        for key, widget in self.inputs.items():
            widget.setEnabled(inputs_enabled and self._field_is_applicable(key, self.current_case))

    def _update_tab_availability(self):
        mesh_ready = self._current_state()["mesh_ready"]
        self.tabs.setTabEnabled(self.mesh_tab_index, True)
        self.tabs.setTabEnabled(self.compute_tab_index, mesh_ready)
        self.tabs.setTabEnabled(self.post_tab_index, mesh_ready)
        if not mesh_ready and self.tabs.currentIndex() != self.mesh_tab_index:
            self.tabs.setCurrentIndex(self.mesh_tab_index)

    def _set_idle_state(self):
        self.active_run_mode = None
        self.active_case_name = None
        self._update_input_enabled_state()
        self.generate_mesh_button.setEnabled(True)
        self.run_button.setEnabled(self._current_state()["mesh_ready"])
        self.stop_button.setEnabled(False)
        self._update_tab_availability()
        self._update_paraview_button()

    def _set_busy_state(self, run_mode: str, case_name: str):
        self.active_run_mode = run_mode
        self.active_case_name = case_name
        self._update_input_enabled_state()
        self.generate_mesh_button.setEnabled(False)
        self.run_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.tabs.setTabEnabled(self.mesh_tab_index, run_mode == "mesh")
        self.tabs.setTabEnabled(self.compute_tab_index, run_mode == "compute")
        self.tabs.setTabEnabled(self.post_tab_index, False)
        self.tabs.setCurrentIndex(self.mesh_tab_index if run_mode == "mesh" else self.compute_tab_index)

    def _clear_case_compute_outputs(self, case_name: str, clear_log: bool):
        state = self.case_states[case_name]
        state["compute_completed"] = False
        state["u_history"] = []
        state["f_history_kn"] = []
        state["progress"] = 0
        if clear_log:
            state["log_lines"] = []
        state["compute_status"] = "Waiting for compute stage."
        state["latest_damage_path"] = None
        state["latest_displacement_path"] = None
        state["latest_vtk_path"] = ""
        state["history_selection"]["Damage"] = None
        state["history_selection"]["Displacement"] = None

    def _invalidate_case_mesh_state(self, case_name: str, clear_log: bool):
        state = self.case_states[case_name]
        state["mesh_ready"] = False
        state["mesh_artifact_path"] = None
        state["mesh_preview_path"] = None
        state["mesh_status"] = "Mesh not generated."
        state["history_selection"]["Mesh"] = None
        self._clear_case_compute_outputs(case_name, clear_log=clear_log)

    def on_input_changed(self, field_key: str, mesh_field: bool):
        if self._syncing_inputs:
            return

        state = self._current_state()
        state["params"][field_key] = self.inputs[field_key].text().strip()
        if mesh_field:
            self._invalidate_case_mesh_state(self.current_case, clear_log=False)
            self._apply_case_state_to_ui()
            if self.active_run_mode is None:
                self._set_idle_state()

    def on_case_changed(self, case_name: str):
        if self._syncing_inputs or case_name == self.current_case:
            return
        self.current_case = case_name
        self._apply_case_params_to_inputs(case_name)
        self._apply_case_state_to_ui()
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
        if len(state["log_lines"]) > 400:
            state["log_lines"] = state["log_lines"][-400:]
        if self.active_case_name == self.current_case:
            self.log_box.appendPlainText(text)
            self._scroll_log_to_end()

    def set_status(self, text: str):
        state = self._active_state()
        if self.active_run_mode == "mesh":
            state["mesh_status"] = text
            if self.active_case_name == self.current_case:
                self.mesh_status_label.setText(text)
        else:
            state["compute_status"] = text
            if self.active_case_name == self.current_case:
                self.compute_status_label.setText(text)

    def update_progress(self, value: float):
        state = self._active_state()
        state["progress"] = value
        if self.active_case_name == self.current_case:
            self.progress_bar.setValue(max(0, min(100, int(round(value)))))

    def update_step(self, step: int, u_value: float, f_value: float, dmax: float):
        state = self._active_state()
        state["u_history"].append(u_value)
        state["f_history_kn"].append(f_value * 1.0e-3)
        state["compute_status"] = f"Step {step} | u={u_value:.3e} mm | F={f_value * 1.0e-3:.4f} kN | dmax={dmax:.4f}"
        if self.active_case_name == self.current_case:
            self.curve_canvas.update_curve(state["u_history"], state["f_history_kn"])
            self.compute_status_label.setText(state["compute_status"])

    def update_snapshot(self, image_path: str):
        path = Path(image_path)
        if not path.exists() or path.suffix.lower() != ".png":
            return

        state = self._active_state()
        if self.active_run_mode == "mesh":
            state["mesh_preview_path"] = path
            state["history_selection"]["Mesh"] = str(path)
            if self.active_case_name == self.current_case:
                self._set_label_image(self.mesh_preview_label, path, self._mesh_placeholder())
        else:
            state["latest_damage_path"] = path
            state["history_selection"]["Damage"] = str(path)
            if self.active_case_name == self.current_case:
                self._set_label_image(self.damage_label, path, "Damage snapshot will appear here.")
        if self.active_case_name == self.current_case:
            self.refresh_postprocess_view(prefer_latest=True)

    def update_vtk_path(self, vtk_path: str):
        state = self._active_state()
        state["latest_vtk_path"] = vtk_path
        if self.active_case_name == self.current_case:
            self.vtk_label.setText(f"Latest VTK: {vtk_path}")
            self._update_paraview_button()

    def update_displacement_path(self, image_path: str):
        path = Path(image_path)
        if not path.exists():
            return
        state = self._active_state()
        state["latest_displacement_path"] = path
        state["history_selection"]["Displacement"] = str(path)
        if self.active_case_name == self.current_case:
            self.refresh_postprocess_view(prefer_latest=True)

    def collect_params(self):
        params = {}
        for key in self._active_field_keys(self.current_case):
            raw = self.inputs[key].text().strip()
            if key in INT_FIELDS:
                params[key] = int(raw)
            else:
                params[key] = float(raw)
        return params

    def write_runtime_params(self, params, run_mode: str, case_name: str, mesh_file: str = ""):
        payload = dict(params)
        payload["case_name"] = case_name
        payload["run_mode"] = run_mode
        payload["mesh_file"] = mesh_file

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

    def cleanup_runtime_params(self):
        if self.runtime_params_path and self.runtime_params_path.exists():
            self.runtime_params_path.unlink()
        self.runtime_params_path = None

    def _start_worker(self, run_mode: str, params, case_name: str, mesh_file: str = ""):
        self.cleanup_runtime_params()
        if STOP_FLAG.exists():
            STOP_FLAG.unlink()

        params_path = self.write_runtime_params(params, run_mode=run_mode, case_name=case_name, mesh_file=mesh_file)
        self.worker = JuliaWorker(params_path, run_mode, case_name)
        self.worker.log_line.connect(self.append_log)
        self.worker.progress_update.connect(self.update_progress)
        self.worker.step_update.connect(self.update_step)
        self.worker.snapshot_update.connect(self.update_snapshot)
        self.worker.vtk_update.connect(self.update_vtk_path)
        self.worker.displacement_update.connect(self.update_displacement_path)
        self.worker.status_update.connect(self.set_status)
        self.worker.finished_state.connect(self.on_worker_finished)
        self._set_busy_state(run_mode, case_name)
        self.worker.start()

    def start_mesh_generation(self):
        try:
            params = self.collect_params()
        except ValueError as exc:
            QMessageBox.critical(self, "Invalid input", str(exc))
            return

        self._invalidate_case_mesh_state(self.current_case, clear_log=True)
        self._apply_case_state_to_ui()
        self._current_state()["mesh_status"] = f"Generating {self.current_case} mesh..."
        self.mesh_status_label.setText(self._current_state()["mesh_status"])
        self._clear_label_image(self.mesh_preview_label, "Waiting for mesh preview...")
        self._start_worker("mesh", params, self.current_case)

    def start_run(self):
        state = self._current_state()
        if not state["mesh_ready"] or state["mesh_artifact_path"] is None:
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
        state["compute_status"] = f"Starting {self.current_case} compute stage..."
        self.compute_status_label.setText(state["compute_status"])
        self._start_worker("compute", params, self.current_case, mesh_file=str(state["mesh_artifact_path"]))

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
        files_to_copy = self._case_result_files(self.current_case)
        if not files_to_copy:
            QMessageBox.warning(self, "No results", "No result files are available to export for the current case.")
            return

        target_dir = QFileDialog.getExistingDirectory(self, "Select Output Folder", str(REPO_ROOT))
        if not target_dir:
            return

        target_path = Path(target_dir)
        copied_count = 0
        for source_path in files_to_copy:
            shutil.copy2(source_path, target_path / source_path.name)
            copied_count += 1

        QMessageBox.information(
            self,
            "Results saved",
            f"Saved {copied_count} files to {target_path}.",
        )

    def on_worker_finished(self, success: bool, case_name: str, run_mode: str, message: str):
        self.cleanup_runtime_params()
        if STOP_FLAG.exists():
            STOP_FLAG.unlink()

        was_stopped = message == "Stopped by user."
        state = self.case_states[case_name]

        if success and not was_stopped:
            self._sync_case_results_from_disk(case_name)
            if run_mode == "mesh":
                state["mesh_status"] = "Mesh ready."
                state["history_selection"]["Mesh"] = str(state["mesh_preview_path"]) if state["mesh_preview_path"] else None
            if run_mode == "compute":
                state["compute_completed"] = True
                state["compute_status"] = message
                if state["latest_damage_path"] is not None:
                    state["history_selection"]["Damage"] = str(state["latest_damage_path"])
                if state["latest_displacement_path"] is not None:
                    state["history_selection"]["Displacement"] = str(state["latest_displacement_path"])
        else:
            if run_mode == "mesh":
                state["mesh_status"] = message
            else:
                state["compute_status"] = message

        self.worker = None
        self.active_case_name = None
        self.active_run_mode = None

        if self.current_case == case_name:
            self._apply_case_state_to_ui()
            self._set_idle_state()

        if not success:
            QMessageBox.warning(self, "Run finished", message)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        state = self._current_state()
        self._set_label_image(self.mesh_preview_label, state["mesh_preview_path"], self._mesh_placeholder())
        self._set_label_image(self.damage_label, state["latest_damage_path"], "Damage snapshot will appear here.")
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
