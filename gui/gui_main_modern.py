import sys
from pathlib import Path

import matplotlib as mpl
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QFontDatabase
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

if __package__ in (None, ""):
    from gui_main import (
        CASE_NAMES,
        COMPUTE_FIELD_SPECS,
        GUI_DIR,
        MainWindow as BaseMainWindow,
        MESH_FIELD_SPECS,
        POSTPROCESS_VIEWS,
        RESULTS_DIR,
    )
else:
    from .gui_main import (
        CASE_NAMES,
        COMPUTE_FIELD_SPECS,
        GUI_DIR,
        MainWindow as BaseMainWindow,
        MESH_FIELD_SPECS,
        POSTPROCESS_VIEWS,
        RESULTS_DIR,
    )


THEME_PATH = GUI_DIR / "gui_main_modern.qss"
FONT_CANDIDATES = ("Ubuntu", "DejaVu Sans", "Sans Serif")

mpl.rcParams["font.family"] = list(FONT_CANDIDATES[:2])
mpl.rcParams["axes.titlesize"] = 12
mpl.rcParams["axes.labelsize"] = 10


def pick_app_font() -> QFont:
    families = set(QFontDatabase().families())
    for family in FONT_CANDIDATES:
        if family in families:
            return QFont(family, 11)
    return QFont()


def load_theme() -> str:
    if not THEME_PATH.exists():
        return ""
    return THEME_PATH.read_text(encoding="utf-8")


class ModernCurveCanvas(FigureCanvas):
    def __init__(self):
        self.figure = Figure(figsize=(5, 4), tight_layout=True)
        self.axes = self.figure.add_subplot(111)
        self.figure.patch.set_facecolor("#f6f8fb")
        super().__init__(self.figure)
        self.setStyleSheet("background: transparent;")
        self.update_curve([], [])

    def update_curve(self, u_values, f_values_kn):
        self.axes.clear()
        self.axes.set_facecolor("#f6f8fb")
        self.axes.grid(True, color="#d7deea", linewidth=0.8, alpha=0.85)
        self.axes.tick_params(colors="#526173", labelsize=9)
        self.axes.set_xlabel("u (mm)", color="#526173")
        self.axes.set_ylabel("F (kN)", color="#526173")
        self.axes.plot(u_values, f_values_kn, color="#335f8a", linewidth=2.2)
        for spine in self.axes.spines.values():
            spine.set_color("#cfd8e3")
            spine.set_linewidth(1.0)
        self.draw_idle()


class ModernMainWindow(BaseMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("peng_pf_ui - Modern Scientific Workbench")
        self.resize(1600, 980)
        self.setMinimumSize(1220, 820)
        self._sync_header_state()

    def _build_ui(self):
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(20, 18, 20, 18)
        root_layout.setSpacing(16)

        root_layout.addWidget(self._build_top_bar())

        body_splitter = QSplitter(Qt.Vertical)
        body_splitter.setChildrenCollapsible(False)
        body_splitter.addWidget(self._build_content_panel())
        body_splitter.addWidget(self._build_bottom_panel())
        body_splitter.setStretchFactor(0, 4)
        body_splitter.setStretchFactor(1, 2)
        body_splitter.setSizes([620, 260])
        root_layout.addWidget(body_splitter, stretch=1)

        self.setCentralWidget(root)

    def _build_content_panel(self):
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([450, 980])
        return splitter

    def _build_top_bar(self):
        frame = QFrame()
        frame.setObjectName("topBar")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(18)

        title_block = QVBoxLayout()
        title_block.setSpacing(4)

        eyebrow = QLabel("Scientific Fracture Workflow")
        eyebrow.setObjectName("eyebrowLabel")
        title_block.addWidget(eyebrow)

        title = QLabel("Modern PyQt5 Workbench")
        title.setObjectName("windowTitleLabel")
        title_block.addWidget(title)

        self.header_status_label = QLabel("Mesh-first workflow for SENT / SENS studies.")
        self.header_status_label.setObjectName("headerStatusLabel")
        self.header_status_label.setWordWrap(True)
        title_block.addWidget(self.header_status_label)

        layout.addLayout(title_block, stretch=1)

        summary_block = QVBoxLayout()
        summary_block.setSpacing(6)

        badge_row = QHBoxLayout()
        badge_row.setSpacing(8)
        badge_row.addWidget(QLabel("Stage"))
        self.stage_badge = QLabel("Setup")
        self.stage_badge.setObjectName("stageBadge")
        badge_row.addWidget(self.stage_badge)
        badge_row.addStretch(1)
        summary_block.addLayout(badge_row)

        case_row = QHBoxLayout()
        case_row.setSpacing(8)
        case_row.addWidget(QLabel("Case"))
        self.case_combo = QComboBox()
        self.case_combo.addItems(CASE_NAMES)
        self.case_combo.currentTextChanged.connect(self.on_case_changed)
        self.case_combo.setMinimumWidth(140)
        case_row.addWidget(self.case_combo)
        summary_block.addLayout(case_row)

        self.header_meta_label = QLabel("Waiting for mesh generation.")
        self.header_meta_label.setObjectName("headerMetaLabel")
        summary_block.addWidget(self.header_meta_label)

        layout.addLayout(summary_block, stretch=0)
        return frame

    def _build_left_panel(self):
        scroll = QScrollArea()
        scroll.setObjectName("leftScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setMinimumWidth(420)
        scroll.setMaximumWidth(480)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(14)

        mesh_card, mesh_layout = self._create_card(
            "Mesh Setup",
            "Adjust geometry and mesh density, then generate the case-specific mesh preview.",
        )
        self._populate_field_sections(mesh_layout, MESH_FIELD_SPECS, self.mesh_input_widgets, mesh_only=True)
        self.generate_mesh_button = QPushButton("Generate Mesh")
        self.generate_mesh_button.setProperty("role", "primary")
        self.generate_mesh_button.clicked.connect(self.start_mesh_generation)
        mesh_layout.addWidget(self.generate_mesh_button)
        self.mesh_status_label = QLabel("Mesh not generated.")
        self.mesh_status_label.setObjectName("cardMetaLabel")
        self.mesh_status_label.setWordWrap(True)
        mesh_layout.addWidget(self.mesh_status_label)
        layout.addWidget(mesh_card)

        compute_card, compute_layout = self._create_card(
            "Compute",
            "Keep the parameter inputs close to the solver controls and monitor the latest run state.",
        )
        self._populate_field_sections(compute_layout, COMPUTE_FIELD_SPECS, self.compute_input_widgets, mesh_only=False)
        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        self.run_button = QPushButton("Run")
        self.run_button.setProperty("role", "primary")
        self.stop_button = QPushButton("Stop")
        self.stop_button.setProperty("role", "danger")
        self.run_button.clicked.connect(self.start_run)
        self.stop_button.clicked.connect(self.stop_run)
        button_row.addWidget(self.run_button)
        button_row.addWidget(self.stop_button)
        compute_layout.addLayout(button_row)
        self.compute_status_label = QLabel("Waiting for compute stage.")
        self.compute_status_label.setObjectName("cardMetaLabel")
        self.compute_status_label.setWordWrap(True)
        compute_layout.addWidget(self.compute_status_label)
        layout.addWidget(compute_card)

        post_card, post_layout = self._create_card(
            "Post-process",
            "Switch between mesh, damage, and displacement views without leaving the main workbench.",
        )
        view_form = QFormLayout()
        view_form.setSpacing(10)
        view_form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.postprocess_view_combo = QComboBox()
        self.postprocess_view_combo.addItems(POSTPROCESS_VIEWS)
        self.postprocess_view_combo.currentTextChanged.connect(self.on_postprocess_view_changed)
        self.history_combo = QComboBox()
        self.history_combo.currentIndexChanged.connect(self.on_history_changed)
        view_form.addRow("View", self.postprocess_view_combo)
        view_form.addRow("History", self.history_combo)
        post_layout.addLayout(view_form)

        post_button_row = QHBoxLayout()
        post_button_row.setSpacing(10)
        self.open_paraview_button = QPushButton("Open in ParaView")
        self.open_paraview_button.setProperty("role", "secondary")
        self.open_paraview_button.clicked.connect(self.open_in_paraview)
        self.export_results_button = QPushButton("Save Results")
        self.export_results_button.setProperty("role", "secondary")
        self.export_results_button.clicked.connect(self.export_results)
        post_button_row.addWidget(self.open_paraview_button)
        post_button_row.addWidget(self.export_results_button)
        post_layout.addLayout(post_button_row)
        layout.addWidget(post_card)

        layout.addStretch(1)
        scroll.setWidget(container)
        return scroll

    def _build_right_panel(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)

        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setSpacing(16)
        layout.setContentsMargins(0, 0, 0, 0)

        primary_card, primary_layout = self._create_card(
            "Primary View",
            "The main result area stays visually dominant throughout mesh, compute, and review stages.",
        )
        primary_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        primary_header = QHBoxLayout()
        primary_header.setSpacing(8)
        self.primary_title_label = QLabel("Mesh Preview")
        self.primary_title_label.setObjectName("sectionTitleLabel")
        primary_header.addWidget(self.primary_title_label)
        primary_header.addStretch(1)
        self.primary_hint_label = QLabel("Generate mesh to unlock the full workflow.")
        self.primary_hint_label.setObjectName("hintLabel")
        primary_header.addWidget(self.primary_hint_label)
        primary_layout.addLayout(primary_header)

        self.primary_view_label = self._create_image_label("Generate mesh to view the mesh preview.")
        self.mesh_preview_label = self.primary_view_label
        self.damage_label = self.primary_view_label
        self.postprocess_label = self.primary_view_label
        primary_layout.addWidget(self.primary_view_label, stretch=1)
        layout.addWidget(primary_card, stretch=3)

        curve_card, curve_layout = self._create_card(
            "Force-Displacement Curve",
            "The curve remains available as a secondary analysis view.",
        )
        curve_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.curve_canvas = ModernCurveCanvas()
        self.curve_canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.curve_canvas.setMinimumHeight(180)
        curve_layout.addWidget(self.curve_canvas, stretch=1)
        layout.addWidget(curve_card, stretch=2)
        layout.addStretch(1)

        scroll.setWidget(panel)
        return scroll

    def _build_bottom_panel(self):
        frame = QFrame()
        frame.setObjectName("bottomCard")
        frame.setMinimumHeight(220)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        status_row = QHBoxLayout()
        status_row.setSpacing(16)

        mesh_block = QVBoxLayout()
        mesh_block.setSpacing(4)
        mesh_caption = QLabel("Mesh Status")
        mesh_caption.setObjectName("miniCaptionLabel")
        mesh_block.addWidget(mesh_caption)
        self.bottom_mesh_status_label = QLabel("Mesh not generated.")
        self.bottom_mesh_status_label.setObjectName("bottomStatusLabel")
        self.bottom_mesh_status_label.setWordWrap(True)
        mesh_block.addWidget(self.bottom_mesh_status_label)
        status_row.addLayout(mesh_block, stretch=1)

        compute_block = QVBoxLayout()
        compute_block.setSpacing(4)
        compute_caption = QLabel("Compute Status")
        compute_caption.setObjectName("miniCaptionLabel")
        compute_block.addWidget(compute_caption)
        self.bottom_compute_status_label = QLabel("Waiting for compute stage.")
        self.bottom_compute_status_label.setObjectName("bottomStatusLabel")
        self.bottom_compute_status_label.setWordWrap(True)
        compute_block.addWidget(self.bottom_compute_status_label)
        status_row.addLayout(compute_block, stretch=2)

        layout.addLayout(status_row)

        progress_row = QHBoxLayout()
        progress_row.setSpacing(12)
        progress_row.addWidget(QLabel("Progress"))
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        progress_row.addWidget(self.progress_bar, stretch=1)
        layout.addLayout(progress_row)

        self.vtk_label = QLabel("Latest VTK: none")
        self.vtk_label.setObjectName("vtkLabel")
        self.vtk_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.vtk_label.setWordWrap(True)
        layout.addWidget(self.vtk_label)

        log_caption = QLabel("Run Log")
        log_caption.setObjectName("miniCaptionLabel")
        layout.addWidget(log_caption)

        self.log_box = QPlainTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMaximumBlockCount(400)
        self.log_box.setMinimumHeight(120)
        layout.addWidget(self.log_box)
        return frame

    def _create_card(self, title: str, subtitle: str):
        frame = QFrame()
        frame.setProperty("card", True)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        title_label = QLabel(title)
        title_label.setObjectName("cardTitleLabel")
        layout.addWidget(title_label)

        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("cardSubtitleLabel")
        subtitle_label.setWordWrap(True)
        layout.addWidget(subtitle_label)
        return frame, layout

    def _populate_field_sections(self, layout, specs, widget_bucket, mesh_only: bool):
        for section_title, fields in specs:
            section = QFrame()
            section.setProperty("section", True)
            section_layout = QVBoxLayout(section)
            section_layout.setContentsMargins(14, 12, 14, 12)
            section_layout.setSpacing(10)

            label = QLabel(section_title)
            label.setObjectName("sectionTitleLabel")
            section_layout.addWidget(label)

            form = QFormLayout()
            form.setSpacing(10)
            form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            for key, field_label, _cases in fields:
                line_edit = QLineEdit(self._current_state()["params"].get(key, ""))
                line_edit.textChanged.connect(
                    lambda _text, field_key=key, mesh_field=mesh_only: self.on_input_changed(field_key, mesh_field)
                )
                line_edit.setClearButtonEnabled(False)
                form.addRow(field_label, line_edit)
                self.inputs[key] = line_edit
                widget_bucket.append(line_edit)
            section_layout.addLayout(form)
            layout.addWidget(section)

    def _create_image_label(self, text: str):
        label = QLabel(text)
        label.setAlignment(Qt.AlignCenter)
        label.setWordWrap(True)
        label.setMinimumHeight(220)
        label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        label.setObjectName("primaryImageLabel")
        return label

    def _display_font_name(self):
        return QApplication.font().family()

    def _current_primary_view(self) -> str:
        state = self._current_state()
        if self.active_run_mode == "mesh":
            return "Mesh"
        if self.active_run_mode == "compute":
            return "Damage"
        if state["compute_completed"]:
            return self.postprocess_view_combo.currentText() or "Damage"
        return "Mesh"

    def _refresh_primary_view(self):
        view_name = self._current_primary_view()
        image_path, placeholder = self._visible_image_path(view_name)
        self._set_label_image(self.primary_view_label, image_path, placeholder)

        title_map = {
            "Mesh": "Mesh Preview",
            "Damage": "Damage Contour",
            "Displacement": "Displacement Contour",
        }
        hint_map = {
            "Mesh": "Geometry and discretization preview",
            "Damage": "Latest solver contour snapshot",
            "Displacement": "Final displacement magnitude view",
        }
        self.primary_title_label.setText(title_map.get(view_name, "Primary View"))
        self.primary_hint_label.setText(hint_map.get(view_name, "Current active visualization"))

    def _sync_header_state(self):
        state = self._current_state()
        if self.active_run_mode == "mesh":
            stage_text = "Meshing"
            summary_text = state["mesh_status"]
            meta_text = "Mesh generation is active."
        elif self.active_run_mode == "compute":
            stage_text = "Computing"
            summary_text = state["compute_status"]
            meta_text = f"Current view: {self._current_primary_view()}"
        elif state["compute_completed"]:
            stage_text = "Review"
            summary_text = state["compute_status"]
            meta_text = f"Viewing {self.postprocess_view_combo.currentText()} for {self.current_case}."
        elif state["mesh_ready"]:
            stage_text = "Ready"
            summary_text = state["mesh_status"]
            meta_text = "Mesh is ready. Compute can start."
        else:
            stage_text = "Setup"
            summary_text = state["mesh_status"]
            meta_text = "Mesh-first workflow. Generate mesh before compute."

        self.stage_badge.setText(stage_text)
        self.header_status_label.setText(summary_text)
        self.header_meta_label.setText(meta_text)

    def _update_tab_availability(self):
        return

    def _update_input_enabled_state(self):
        inputs_enabled = self.active_run_mode is None
        self.case_combo.setEnabled(inputs_enabled)
        for key, widget in self.inputs.items():
            widget.setEnabled(inputs_enabled and self._field_is_applicable(key, self.current_case))

    def _set_idle_state(self):
        self.active_run_mode = None
        self.active_case_name = None
        self._update_input_enabled_state()
        self.generate_mesh_button.setEnabled(True)
        self.run_button.setEnabled(self._current_state()["mesh_ready"])
        self.stop_button.setEnabled(False)
        self.postprocess_view_combo.setEnabled(True)
        self._update_paraview_button()
        self._refresh_history_combo(prefer_latest=False)
        self._refresh_primary_view()
        self._sync_header_state()

    def _set_busy_state(self, run_mode: str, case_name: str):
        self.active_run_mode = run_mode
        self.active_case_name = case_name
        self._update_input_enabled_state()
        self.generate_mesh_button.setEnabled(False)
        self.run_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.postprocess_view_combo.setEnabled(run_mode != "compute")
        self._refresh_primary_view()
        self._sync_header_state()

    def _apply_case_state_to_ui(self):
        state = self._current_state()
        self.mesh_status_label.setText(state["mesh_status"])
        self.compute_status_label.setText(state["compute_status"])
        self.bottom_mesh_status_label.setText(state["mesh_status"])
        self.bottom_compute_status_label.setText(state["compute_status"])
        self.progress_bar.setValue(max(0, min(100, int(round(state["progress"])))))
        self.curve_canvas.update_curve(state["u_history"], state["f_history_kn"])
        self.log_box.setPlainText("\n".join(state["log_lines"]))
        self._scroll_log_to_end()
        self.vtk_label.setText(f"Latest VTK: {state['latest_vtk_path'] or 'none'}")
        self._refresh_history_combo(prefer_latest=False)
        self._update_input_enabled_state()
        self._update_paraview_button()
        self._refresh_primary_view()
        self._sync_header_state()

    def refresh_postprocess_view(self, prefer_latest: bool):
        self._refresh_history_combo(prefer_latest=prefer_latest)
        self._refresh_primary_view()
        self._update_paraview_button()
        self._sync_header_state()

    def on_postprocess_view_changed(self, _view_name: str):
        self.refresh_postprocess_view(prefer_latest=False)

    def on_history_changed(self, _index: int):
        if self._syncing_history:
            return
        view_name = self.postprocess_view_combo.currentText()
        self._current_state()["history_selection"][view_name] = self.history_combo.currentData()
        self._refresh_primary_view()
        self._sync_header_state()

    def on_case_changed(self, case_name: str):
        super().on_case_changed(case_name)
        self._sync_header_state()

    def set_status(self, text: str):
        super().set_status(text)
        state = self._active_state()
        self.bottom_mesh_status_label.setText(state["mesh_status"])
        self.bottom_compute_status_label.setText(state["compute_status"])
        self._sync_header_state()

    def update_progress(self, value: float):
        super().update_progress(value)
        self._sync_header_state()

    def update_step(self, step: int, u_value: float, f_value: float, dmax: float):
        super().update_step(step, u_value, f_value, dmax)
        state = self._active_state()
        self.bottom_compute_status_label.setText(state["compute_status"])
        self._refresh_primary_view()
        self._sync_header_state()

    def update_snapshot(self, image_path: str):
        path = Path(image_path)
        if not path.exists() or path.suffix.lower() != ".png":
            return

        state = self._active_state()
        if self.active_run_mode == "mesh":
            state["mesh_preview_path"] = path
            state["history_selection"]["Mesh"] = str(path)
        else:
            state["latest_damage_path"] = path
            state["history_selection"]["Damage"] = str(path)

        if self.active_case_name == self.current_case:
            self.refresh_postprocess_view(prefer_latest=True)

    def update_displacement_path(self, image_path: str):
        super().update_displacement_path(image_path)
        self._refresh_primary_view()
        self._sync_header_state()

    def start_mesh_generation(self):
        try:
            params = self.collect_params()
        except ValueError as exc:
            QMessageBox.critical(self, "Invalid input", str(exc))
            return

        self._invalidate_case_mesh_state(self.current_case, clear_log=True)
        self._apply_case_state_to_ui()
        state = self._current_state()
        state["mesh_status"] = f"Generating {self.current_case} mesh..."
        self.mesh_status_label.setText(state["mesh_status"])
        self.bottom_mesh_status_label.setText(state["mesh_status"])
        self._clear_label_image(self.primary_view_label, "Waiting for mesh preview...")
        self._start_worker("mesh", params, self.current_case)

    def start_run(self):
        super().start_run()
        self._refresh_primary_view()
        self._sync_header_state()

    def on_worker_finished(self, success: bool, case_name: str, run_mode: str, message: str):
        super().on_worker_finished(success, case_name, run_mode, message)
        if self.current_case == case_name:
            self._apply_case_state_to_ui()

    def resizeEvent(self, event):
        QMainWindow.resizeEvent(self, event)
        self._refresh_primary_view()


def main():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    app = QApplication(sys.argv)
    app.setFont(pick_app_font())
    app.setStyleSheet(load_theme())
    window = ModernMainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
