import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QPoint, QPointF, Qt
from PyQt5.QtGui import QColor, QImage
from PyQt5.QtGui import QWheelEvent
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QGraphicsOpacityEffect
from PyQt5.QtWidgets import QApplication

import gui.gui_main as gui_main
from gui.run_manifest import RunManifest, write_manifest
from visual import gui_case_exporters


class GuiPostprocessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.tempdir.name)
        self.results_dir = self.temp_path / "gui_results"
        self.manifest_dir = self.results_dir / "manifests"
        self.runs_dir = self.results_dir / "runs"
        self.visual_export_dir = self.results_dir / "visual_exports"
        self.cache_pref_path = self.temp_path / "gui_cache_pref.json"
        for directory in (self.results_dir, self.manifest_dir, self.runs_dir, self.visual_export_dir):
            directory.mkdir(parents=True, exist_ok=True)

        self.patchers = [
            mock.patch.object(gui_main, "RESULTS_DIR", self.results_dir),
            mock.patch.object(gui_main, "MANIFEST_DIR", self.manifest_dir),
            mock.patch.object(gui_main, "RUNS_DIR", self.runs_dir),
            mock.patch.object(gui_main, "VISUAL_EXPORT_DIR", self.visual_export_dir),
            mock.patch.object(gui_main, "STOP_FLAG", self.temp_path / "gui_stop.flag"),
            mock.patch.object(gui_main, "TRANSIENT_CACHE_PREF_PATH", self.cache_pref_path),
        ]
        for patcher in self.patchers:
            patcher.start()
        self.window = None

    def tearDown(self):
        if self.window is not None:
            self.window.close()
            self.app.processEvents()
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.tempdir.cleanup()

    def _open_window(self):
        self.window = gui_main.MainWindow()
        self.app.processEvents()

    def _flush_events(self):
        self.app.processEvents()
        QApplication.sendPostedEvents()
        self.app.processEvents()

    def _select_case(self, case_id: str):
        case = gui_main.CASE_DEFINITIONS[case_id]
        self.window.current_category = case.category_id
        self.window._refresh_case_combo(case.category_id, preferred_case_id=case_id)
        self.window.current_case = case_id
        self.window._apply_case_params_to_inputs(case_id)
        self.window._apply_case_state_to_ui()
        self.window._set_idle_state()
        self.app.processEvents()

    def _view_names(self):
        return [self.window.postprocess_view_combo.itemText(index) for index in range(self.window.postprocess_view_combo.count())]

    def _set_postprocess_view(self, view_key: str):
        index = self.window.postprocess_view_combo.findData(view_key)
        self.assertGreaterEqual(index, 0)
        self.window.postprocess_view_combo.setCurrentIndex(index)
        self.app.processEvents()

    def _write_postprocess_manifest(self, case_id: str, *, damage_frames: int = 0, displacement_frames: int = 0, vtk_frames: int = 0):
        native_dir = self.temp_path / f"{case_id}_native"
        native_dir.mkdir(parents=True, exist_ok=True)

        mesh_msh = native_dir / "mesh_SENT.msh"
        mesh_png = native_dir / "mesh_SENT.png"
        damage_png = native_dir / "d_final_SENT.png"
        displacement_png = native_dir / "u_mag_final_SENT.png"
        curve_csv = native_dir / "F_u_curve_SENT.csv"
        mesh_msh.write_text("mesh", encoding="utf-8")
        curve_csv.write_text("u_mm,F_kN\n0.0,0.0\n0.1,2.0\n", encoding="utf-8")

        snapshot_paths = []
        for frame_index in range(1, damage_frames + 1):
            snapshot_path = native_dir / f"snap_SENT_{frame_index:04d}.png"
            image = QImage(640, 480, QImage.Format_RGB32)
            image.fill(QColor("#f6d9d6"))
            self.assertTrue(image.save(str(snapshot_path)))
            snapshot_paths.append(str(snapshot_path))

        displacement_paths = []
        for frame_index in range(1, displacement_frames + 1):
            displacement_frame_path = native_dir / f"u_mag_SENT_{frame_index:04d}.png"
            image = QImage(640, 480, QImage.Format_RGB32)
            image.fill(QColor("#d6e6f6"))
            self.assertTrue(image.save(str(displacement_frame_path)))
            displacement_paths.append(str(displacement_frame_path))

        vtk_paths = []
        for frame_index in range(1, vtk_frames + 1):
            vtk_path = native_dir / f"result_SENT_{frame_index:04d}.vtu"
            vtk_path.write_text("vtk", encoding="utf-8")
            vtk_paths.append(str(vtk_path))

        for image_path, color in (
            (mesh_png, QColor("#e2ebf4")),
            (damage_png, QColor("#f6d9d6")),
            (displacement_png, QColor("#d6e6f6")),
        ):
            image = QImage(640, 480, QImage.Format_RGB32)
            image.fill(color)
            self.assertTrue(image.save(str(image_path)))

        manifest = RunManifest(
            category_id=gui_main.CASE_DEFINITIONS[case_id].category_id,
            case_id=case_id,
            run_id=f"{case_id}_20260402_000000",
            status="completed",
            backend_mode="protocol_julia",
            curve_kind="force_displacement",
            run_profile="preview",
            source_script="",
            run_dir=str(self.runs_dir / case_id / f"{case_id}_20260402_000000"),
            runtime_params_path="",
            native_output_dir=str(native_dir),
            mesh_paths=[str(mesh_msh), str(mesh_png)],
            snapshot_paths=snapshot_paths,
            vtk_paths=vtk_paths,
            curve_csv_paths=[str(curve_csv)],
            damage_paths=[str(damage_png)],
            displacement_paths=displacement_paths + [str(displacement_png)],
        )
        write_manifest(self.manifest_dir / f"{case_id}_latest.json", manifest)

    def test_protocol_case_exposes_von_mises_view_when_vtk_exists(self):
        self._write_postprocess_manifest("sent_tension", vtk_frames=2)
        self._open_window()
        self._select_case("sent_tension")
        self.assertEqual(self._view_names(), ["Mesh", "Damage", "Displacement", "Von Mises", "Force-Displacement Curve", "Results Summary"])

    def test_julia_env_resolution_follows_active_conda_env(self):
        fake_prefix = self.temp_path / "envs" / "gui_envs"
        expected_project = fake_prefix / "share" / "julia" / "environments" / "gui_envs"
        expected_depot = fake_prefix / "share" / "julia"

        with mock.patch.object(gui_main, "repo_julia_project_dir", return_value=None), mock.patch.dict(
            os.environ,
            {
                "CONDA_PREFIX": str(fake_prefix),
                "CONDA_DEFAULT_ENV": "gui_envs",
            },
            clear=True,
        ):
            self.assertEqual(gui_main.resolved_julia_project(), str(expected_project))
            self.assertEqual(gui_main.resolved_julia_depot(), str(expected_depot))

    def test_julia_env_resolution_respects_explicit_env_vars(self):
        with mock.patch.object(gui_main, "repo_julia_project_dir", return_value=self.temp_path / "repo"), mock.patch.dict(
            os.environ,
            {
                "JULIA_PROJECT": "@custom_project",
                "JULIA_DEPOT_PATH": "/tmp/custom_depot:/tmp/fallback_depot",
                "CONDA_PREFIX": str(self.temp_path / "ignored"),
                "CONDA_DEFAULT_ENV": "ignored",
            },
            clear=True,
        ):
            self.assertEqual(gui_main.resolved_julia_project(), "@custom_project")
            self.assertEqual(gui_main.resolved_julia_depot(), "/tmp/custom_depot:/tmp/fallback_depot")

    def test_julia_env_resolution_prefers_repo_project_when_present(self):
        repo_dir = self.temp_path / "repo"
        with mock.patch.object(gui_main, "repo_julia_project_dir", return_value=repo_dir), mock.patch.dict(
            os.environ,
            {
                "CONDA_PREFIX": str(self.temp_path / "envs" / "gui_envs"),
                "CONDA_DEFAULT_ENV": "gui_envs",
            },
            clear=True,
        ):
            self.assertEqual(gui_main.resolved_julia_project(), str(repo_dir))

    def test_fatigue_case_exposes_curve_view(self):
        self._open_window()
        self._select_case("sent_elasto_plastic_fatigue")
        self.assertEqual(self._view_names(), ["Mesh", "Damage", "Crack Growth Curve", "Results Summary"])

    def test_scan_case_hides_curve_and_displacement_views(self):
        self._open_window()
        self._select_case("offset_double_notch_fatigue")
        self.assertEqual(self._view_names(), ["Mesh", "Damage", "Summary Table", "Comparison Curve", "Results Summary"])

    def test_visual_export_view_is_enabled_for_newly_supported_cases(self):
        self._open_window()
        supported_cases = {
            "tpb_fatigue": ["Mesh", "Damage", "Crack Growth Curve", "Results Summary"],
            "double_notched_monotonic": ["Mesh", "Damage", "Summary Table", "Comparison Curve", "Results Summary"],
            "ct_elasto_plastic_fatigue": ["Mesh", "Damage", "Crack Growth Curve", "Results Summary"],
        }
        for case_id, expected_views in supported_cases.items():
            self._select_case(case_id)
            self.assertEqual(self._view_names(), expected_views)

    def test_curve_view_loads_manifest_csv_history(self):
        case_id = "sent_elasto_plastic_fatigue"
        native_dir = self.temp_path / "native"
        native_dir.mkdir(parents=True, exist_ok=True)

        mesh_msh = native_dir / "mesh.msh"
        mesh_png = native_dir / "mesh.png"
        curve_csv = native_dir / "cycle_summary.csv"
        mesh_msh.write_text("mesh", encoding="utf-8")
        mesh_png.write_text("", encoding="utf-8")
        curve_csv.write_text("N,delta_a_mm\n1,0.05\n2,0.12\n3,0.18\n", encoding="utf-8")

        manifest = RunManifest(
            category_id=gui_main.CASE_DEFINITIONS[case_id].category_id,
            case_id=case_id,
            run_id="sent_elasto_plastic_fatigue_20260401_000000",
            status="completed",
            backend_mode="batch_script",
            curve_kind="crack_growth",
            run_profile="preview",
            source_script="",
            run_dir=str(self.runs_dir / case_id / "sent_elasto_plastic_fatigue_20260401_000000"),
            runtime_params_path="",
            native_output_dir=str(native_dir),
            mesh_paths=[str(mesh_msh), str(mesh_png)],
            curve_csv_paths=[str(curve_csv)],
        )
        write_manifest(self.manifest_dir / f"{case_id}_latest.json", manifest)

        self._open_window()
        self._select_case(case_id)
        self._set_postprocess_view("Curve")

        line = self.window.postprocess_curve_canvas.axes.lines[0]
        self.assertEqual(list(line.get_xdata()), [1.0, 2.0, 3.0])
        self.assertEqual(list(line.get_ydata()), [0.05, 0.12, 0.18])
        self.assertEqual(self.window.history_combo.count(), 1)
        self.assertEqual(self.window.history_combo.itemData(0), str(curve_csv))
        self.assertIn(str(curve_csv), self.window.postprocess_detail_label.text())

    def test_mesh_preview_widget_supports_zoom_and_vertical_scroll(self):
        self._open_window()
        self.window.resize(1280, 900)
        self.window.show()
        self.window.tabs.setCurrentIndex(self.window.mesh_tab_index)
        self._flush_events()

        image_path = self.temp_path / "mesh_preview.png"
        image = QImage(320, 1400, QImage.Format_RGB32)
        image.fill(QColor("#ffffff"))
        self.assertTrue(image.save(str(image_path)))

        viewer = self.window.mesh_preview_label
        self.window._set_label_image(viewer, image_path, "Mesh preview will appear here.", animate=False)
        viewer.show_actual_size()
        self._flush_events()

        scrollbar = viewer.scroll_area.verticalScrollBar()
        self.assertGreater(scrollbar.maximum(), 0)

        start_value = scrollbar.value()
        viewer.scroll_down()
        self.app.processEvents()
        self.assertGreater(scrollbar.value(), start_value)

        viewer.scroll_up()
        self.app.processEvents()
        self.assertLessEqual(scrollbar.value(), start_value)

    def test_mesh_preview_ctrl_wheel_works_when_cursor_is_on_image_label(self):
        self._open_window()
        self.window.resize(1280, 900)
        self.window.show()
        self.window.tabs.setCurrentIndex(self.window.mesh_tab_index)
        self._flush_events()

        image_path = self.temp_path / "mesh_preview_ctrl_zoom.png"
        image = QImage(640, 960, QImage.Format_RGB32)
        image.fill(QColor("#dce8f5"))
        self.assertTrue(image.save(str(image_path)))

        viewer = self.window.mesh_preview_label
        self.window._set_label_image(viewer, image_path, "Mesh preview will appear here.", animate=False)
        viewer.show_actual_size()
        self._flush_events()

        start_scale = viewer._current_scale_factor()
        wheel_event = QWheelEvent(
            QPointF(100, 100),
            QPointF(100, 100),
            QPoint(0, 0),
            QPoint(0, 120),
            Qt.NoButton,
            Qt.ControlModifier,
            Qt.NoScrollPhase,
            False,
        )
        QApplication.sendEvent(viewer.image_label, wheel_event)
        self.app.processEvents()

        self.assertGreater(viewer._current_scale_factor(), start_scale)

    def test_mesh_preview_widget_is_not_wrapped_by_opacity_animation(self):
        self._open_window()
        self.window.resize(1280, 900)
        self.window.show()
        self.window.tabs.setCurrentIndex(self.window.mesh_tab_index)
        self._flush_events()

        image_path = self.temp_path / "mesh_preview_effect.png"
        image = QImage(640, 960, QImage.Format_RGB32)
        image.fill(QColor("#2f6fb2"))
        self.assertTrue(image.save(str(image_path)))

        viewer = self.window.mesh_preview_label
        with mock.patch.object(self.window, "_animations_enabled", return_value=True):
            self.window._set_label_image(viewer, image_path, "Mesh preview will appear here.", animate=True)
            self._flush_events()

        self.assertFalse(isinstance(viewer.graphicsEffect(), QGraphicsOpacityEffect))
        self.assertIsNotNone(viewer.image_label.pixmap())
        viewer.zoom_in()
        self.app.processEvents()
        self.assertIsNotNone(viewer.image_label.pixmap())

    def test_postprocess_stack_does_not_use_opacity_animation_on_view_change(self):
        case_id = "sent_tension"
        self._write_postprocess_manifest(case_id)

        self._open_window()
        self._select_case(case_id)
        self.window.tabs.setTabEnabled(self.window.post_tab_index, True)
        self.window.tabs.setCurrentIndex(self.window.post_tab_index)
        self._flush_events()

        with mock.patch.object(self.window, "_animations_enabled", return_value=True):
            self._set_postprocess_view("Curve")

        self.assertFalse(isinstance(self.window.postprocess_stack.graphicsEffect(), QGraphicsOpacityEffect))
        self.assertIs(self.window.postprocess_stack.currentWidget(), self.window.postprocess_curve_canvas)

    def test_postprocess_image_viewer_hides_internal_scrollbars_and_ignores_ctrl_wheel(self):
        self._write_postprocess_manifest("sent_tension")
        self._open_window()
        self.window.resize(1280, 900)
        self.window.show()
        self.window.tabs.setTabEnabled(self.window.post_tab_index, True)
        self.window.tabs.setCurrentIndex(self.window.post_tab_index)
        self._set_postprocess_view("Damage")
        self._flush_events()

        viewer = self.window.postprocess_label
        self.assertTrue(viewer.has_image())
        self._flush_events()
        self.assertEqual(viewer.scroll_area.horizontalScrollBarPolicy(), Qt.ScrollBarAlwaysOff)
        self.assertEqual(viewer.scroll_area.verticalScrollBarPolicy(), Qt.ScrollBarAlwaysOff)
        self.assertFalse(viewer.scroll_area.horizontalScrollBar().isVisible())
        self.assertFalse(viewer.scroll_area.verticalScrollBar().isVisible())

        start_scale = viewer._current_scale_factor()
        wheel_event = QWheelEvent(
            QPointF(100, 100),
            QPointF(100, 100),
            QPoint(0, 0),
            QPoint(0, 120),
            Qt.NoButton,
            Qt.ControlModifier,
            Qt.NoScrollPhase,
            False,
        )
        QApplication.sendEvent(viewer.scroll_area.viewport(), wheel_event)
        self._flush_events()

        self.assertEqual(viewer._current_scale_factor(), start_scale)

    def test_postprocess_image_viewer_ignores_keyboard_zoom_shortcuts(self):
        self._write_postprocess_manifest("sent_tension")
        self._open_window()
        self.window.resize(1280, 900)
        self.window.show()
        self.window.tabs.setTabEnabled(self.window.post_tab_index, True)
        self.window.tabs.setCurrentIndex(self.window.post_tab_index)
        self._set_postprocess_view("Damage")
        self._flush_events()

        viewer = self.window.postprocess_label
        self.assertTrue(viewer.has_image())
        viewer.setFocus()
        self._flush_events()

        fit_scale = viewer._current_scale_factor()
        QTest.keyClick(viewer, Qt.Key_Equal, Qt.ControlModifier)
        self._flush_events()
        self.assertEqual(viewer._current_scale_factor(), fit_scale)

        QTest.keyClick(viewer, Qt.Key_0, Qt.ControlModifier)
        self._flush_events()
        self.assertEqual(viewer._current_scale_factor(), fit_scale)

        QTest.keyClick(viewer, Qt.Key_1, Qt.ControlModifier)
        self._flush_events()
        self.assertEqual(viewer._current_scale_factor(), fit_scale)

    def test_postprocess_damage_timeline_slider_tracks_history_frames(self):
        self._write_postprocess_manifest("sent_tension", damage_frames=3)
        self._open_window()
        self.window.resize(1280, 900)
        self.window.show()
        self.window.tabs.setTabEnabled(self.window.post_tab_index, True)
        self.window.tabs.setCurrentIndex(self.window.post_tab_index)
        self._set_postprocess_view("Damage")
        self._flush_events()

        self.assertTrue(self.window.postprocess_timeline_stack.isVisible())
        self.assertEqual(self.window.postprocess_timeline_slider.maximum(), 3)
        self.assertIn("Frame 4/4", self.window.postprocess_timeline_value_label.text())

        self.window.postprocess_timeline_slider.setValue(1)
        self._flush_events()

        self.assertEqual(self.window.history_combo.currentIndex(), 1)
        self.assertTrue(str(self.window.history_combo.currentData()).endswith("snap_SENT_0002.png"))
        self.assertIn("snap_SENT_0002.png", self.window.postprocess_detail_label.text())

    def test_postprocess_von_mises_timeline_slider_tracks_generated_frames(self):
        self._write_postprocess_manifest("sent_tension", vtk_frames=3)
        self._open_window()
        self.window.resize(1280, 900)
        self.window.show()
        self.window.tabs.setTabEnabled(self.window.post_tab_index, True)
        self.window.tabs.setCurrentIndex(self.window.post_tab_index)

        vm_paths = []
        for frame_index in range(1, 4):
            image_path = self.temp_path / f"von_mises_{frame_index:04d}.png"
            image = QImage(640, 480, QImage.Format_RGB32)
            image.fill(QColor("#f7e2cc"))
            self.assertTrue(image.save(str(image_path)))
            vm_paths.append(image_path)

        with mock.patch.object(self.window, "_ensure_von_mises_history", return_value=vm_paths):
            self._set_postprocess_view("Von Mises")
            self._flush_events()

            self.assertTrue(self.window.postprocess_timeline_stack.isVisible())
            self.assertEqual(self.window.postprocess_timeline_slider.maximum(), 2)
            self.assertIn("Frame 3/3", self.window.postprocess_timeline_value_label.text())

            self.window.postprocess_timeline_slider.setValue(1)
            self._flush_events()

            self.assertEqual(self.window.history_combo.currentIndex(), 1)
            self.assertTrue(str(self.window.history_combo.currentData()).endswith("von_mises_0002.png"))
            self.assertIn("von_mises_0002.png", self.window.postprocess_detail_label.text())

    def test_mesh_view_does_not_show_postprocess_timeline(self):
        self._write_postprocess_manifest("sent_tension")
        self._open_window()
        self.window.resize(1280, 900)
        self.window.show()
        self.window.tabs.setTabEnabled(self.window.post_tab_index, True)
        self.window.tabs.setCurrentIndex(self.window.post_tab_index)
        self._set_postprocess_view("Mesh")
        self._flush_events()

        self.assertFalse(self.window.postprocess_timeline_stack.isVisible())

    def test_postprocess_tab_stays_scrollable_in_compact_window(self):
        self._open_window()
        self.window.resize(760, 680)
        self.window.show()
        self.window.tabs.setTabEnabled(self.window.post_tab_index, True)
        self.window.tabs.setCurrentIndex(self.window.post_tab_index)
        self.app.processEvents()

        scrollbar = self.window.postprocess_scroll.verticalScrollBar()
        self.assertGreater(scrollbar.maximum(), 0)
        self.assertTrue(self.window.export_results_button.isVisible())

    def test_visual_export_view_uses_more_compact_postprocess_layout(self):
        self._open_window()
        self.window.resize(1280, 900)
        self.window.show()

        case_id = "sent_tension"
        export_path = self.temp_path / "sent_visual_export.png"
        image = QImage(1600, 900, QImage.Format_RGB32)
        image.fill(QColor("#f0f4f8"))
        self.assertTrue(image.save(str(export_path)))

        vtk_path = self.temp_path / "latest_result.vtu"
        vtk_path.write_text("vtk", encoding="utf-8")

        state = self.window.case_states[case_id]
        state["latest_vtk_path"] = str(vtk_path)
        state["visual_export_paths"] = {"field_panel": str(export_path)}
        state["history_selection"]["Visual Export"] = str(export_path)

        self._select_case(case_id)
        self.window.tabs.setTabEnabled(self.window.post_tab_index, True)
        self.window.tabs.setCurrentIndex(self.window.post_tab_index)

        self._set_postprocess_view("Damage")
        self._flush_events()
        damage_min_height = self.window.postprocess_label.minimumHeight()
        self.assertTrue(self.window.vtk_label.isVisible())

        self._set_postprocess_view("Visual Export")
        self._flush_events()

        self.assertLess(self.window.postprocess_label.minimumHeight(), damage_min_height)
        self.assertFalse(self.window.vtk_label.isVisible())
        self.assertEqual(self.window.postprocess_detail_label.text(), f"Results Summary: {export_path.name}")
        self.assertFalse(self.window.postprocess_timeline_stack.isVisible())

    def test_protocol_visual_export_adds_displacement_panel(self):
        native_dir = self.temp_path / "sent_native"
        output_dir = self.temp_path / "visual_out"
        mesh_path = native_dir / "mesh_SENT.msh"
        curve_path = native_dir / "F_u_curve_SENT.csv"
        onset_path = native_dir / "result_onset_step0001.vtu"
        drop_path = native_dir / "result_drop_step0002.vtu"
        final_path = native_dir / "result_final_step0003.vtu"
        native_dir.mkdir(parents=True, exist_ok=True)

        captured = {}

        def fake_export_protocol_panel(output_path, **kwargs):
            captured["row_specs"] = kwargs["row_specs"]
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text("panel", encoding="utf-8")
            return output_path

        with mock.patch.object(gui_case_exporters, "_load_runtime_params", return_value={}), mock.patch.object(
            gui_case_exporters,
            "_first_existing",
            side_effect=[mesh_path, curve_path, onset_path, final_path],
        ), mock.patch.object(gui_case_exporters, "_sorted_matches", return_value=[drop_path]), mock.patch.object(
            gui_case_exporters, "meshio"
        ) as meshio_mock, mock.patch.object(
            gui_case_exporters,
            "_triangulation",
            return_value=(None, None, "tri"),
        ), mock.patch.object(
            gui_case_exporters,
            "_scalar_field",
            return_value=[0.0, 0.5, 1.0],
        ), mock.patch.object(
            gui_case_exporters,
            "_vector_field",
            return_value=gui_case_exporters.np.array([[0.0, 0.0], [0.01, 0.02], [0.02, 0.03]]),
        ), mock.patch.object(
            gui_case_exporters,
            "_compute_protocol_von_mises",
            return_value=gui_case_exporters.np.array([10.0, 20.0, 30.0]),
        ), mock.patch.object(
            gui_case_exporters,
            "_extract_int_from_name",
            side_effect=[1, 2, 3],
        ), mock.patch.object(
            gui_case_exporters,
            "_rounded_percentile_max",
            side_effect=[0.05, 40.0],
        ), mock.patch.object(
            gui_case_exporters,
            "_export_protocol_panel",
            side_effect=fake_export_protocol_panel,
        ), mock.patch.object(
            gui_case_exporters,
            "_export_geometry_gallery",
            return_value=output_dir / "sent_mesh_overview.png",
        ), mock.patch.object(
            gui_case_exporters,
            "_protocol_curve_points",
            return_value=([0.0, 1.0], [0.0, 2.0], []),
        ), mock.patch.object(
            gui_case_exporters,
            "_export_line_chart",
            return_value=output_dir / "sent_force_curve.png",
        ):
            meshio_mock.read.return_value = object()
            outputs = gui_case_exporters.export_sent_panels(native_dir, output_dir)

        self.assertEqual([spec[0] for spec in captured["row_specs"]], ["d", "umag", "svm"])
        self.assertTrue(outputs["field_panel"].endswith("sent_field_panel.png"))

    def test_live_curve_card_can_collapse_and_restore(self):
        self._open_window()
        self.window.resize(1280, 900)
        self.window.show()
        self.app.processEvents()

        self.assertFalse(self.window._compute_curve_collapsed)
        self.assertFalse(self.window.curve_surface.isHidden())
        self.assertEqual(self.window.curve_toggle_button.text(), "▾")
        self.assertFalse(self.window.keep_cache_action.isChecked())
        self.assertEqual(self.window.keep_cache_action.text(), "Keep Temp Cache Off")
        self.assertEqual(self.window.more_button.text(), "More")
        self.assertEqual(self.window.more_button.minimumWidth(), 64)

    def test_default_close_purges_transient_results(self):
        run_dir = self.runs_dir / "sent_tension" / "sent_tension_20260402_000000"
        run_dir.mkdir(parents=True, exist_ok=True)
        payload_path = run_dir / "snap_SENT_0001.png"
        payload_path.write_text("cached", encoding="utf-8")

        self._open_window()
        self.window.close()
        self.app.processEvents()
        self.window = None

        self.assertFalse(run_dir.exists())

    def test_keep_temp_cache_menu_action_preserves_results_across_reopen(self):
        run_dir = self.runs_dir / "sent_tension" / "sent_tension_20260402_000000"
        run_dir.mkdir(parents=True, exist_ok=True)
        payload_path = run_dir / "snap_SENT_0001.png"
        payload_path.write_text("cached", encoding="utf-8")

        self._open_window()
        self.window.show()
        self._flush_events()
        self.window.keep_cache_action.trigger()
        self._flush_events()

        self.assertTrue(self.window.keep_transient_results)
        self.assertTrue(gui_main.load_transient_cache_preference())
        self.assertTrue(self.window.keep_cache_action.isChecked())
        self.assertEqual(self.window.keep_cache_action.text(), "Keep Temp Cache On")
        self.assertEqual(self.window.more_button.text(), "More")

        self.window.close()
        self.app.processEvents()
        self.window = None

        self.assertTrue(run_dir.exists())
        self.assertTrue(payload_path.exists())

        self._open_window()
        self.assertTrue(self.window.keep_transient_results)
        self.assertTrue(self.window.keep_cache_action.isChecked())
        self.assertEqual(self.window.keep_cache_action.text(), "Keep Temp Cache On")

    def test_compute_live_preview_panel_shows_damage_and_displacement(self):
        self._open_window()
        self.window.resize(1280, 900)
        self.window.show()
        self.window.tabs.setCurrentIndex(self.window.compute_tab_index)
        self.app.processEvents()

        damage_path = self.temp_path / "snap_SENT_0001.png"
        von_mises_path = self.temp_path / "von_mises_SENT_0001.png"
        damage_image = QImage(320, 240, QImage.Format_RGB32)
        damage_image.fill(QColor("#dce8f5"))
        von_mises_image = QImage(320, 240, QImage.Format_RGB32)
        von_mises_image.fill(QColor("#ffffff"))
        self.assertTrue(damage_image.save(str(damage_path)))
        self.assertTrue(von_mises_image.save(str(von_mises_path)))

        self.window.current_case = "sent_tension"
        self.window.active_case_id = "sent_tension"
        self.window.active_run_mode = "compute"
        self.window.update_snapshot(str(damage_path))
        self.window.update_von_mises_path(str(von_mises_path))
        self.app.processEvents()

        self.assertIsNotNone(self.window.damage_label.image_label.pixmap())
        self.assertFalse(self.window.damage_label.image_label.pixmap().isNull())
        self.assertIsNotNone(self.window.displacement_label.image_label.pixmap())
        self.assertFalse(self.window.displacement_label.image_label.pixmap().isNull())
        self.assertFalse(self.window.compute_damage_card.isHidden())
        self.assertFalse(self.window.compute_displacement_card.isHidden())
        self.assertEqual(self.window.damage_label.scroll_area.horizontalScrollBarPolicy(), Qt.ScrollBarAlwaysOff)
        self.assertEqual(self.window.damage_label.scroll_area.verticalScrollBarPolicy(), Qt.ScrollBarAlwaysOff)
        self.assertEqual(self.window.displacement_label.scroll_area.horizontalScrollBarPolicy(), Qt.ScrollBarAlwaysOff)
        self.assertEqual(self.window.displacement_label.scroll_area.verticalScrollBarPolicy(), Qt.ScrollBarAlwaysOff)
        self.assertFalse(self.window.damage_label.scroll_area.horizontalScrollBar().isVisible())
        self.assertFalse(self.window.damage_label.scroll_area.verticalScrollBar().isVisible())
        self.assertFalse(self.window.displacement_label.scroll_area.horizontalScrollBar().isVisible())
        self.assertFalse(self.window.displacement_label.scroll_area.verticalScrollBar().isVisible())

        self.window.toggle_compute_curve_card()
        self.app.processEvents()
        self.assertTrue(self.window._compute_curve_collapsed)
        self.assertTrue(self.window.curve_surface.isHidden())
        self.assertEqual(self.window.curve_toggle_button.text(), "▴")

        self.window.toggle_compute_curve_card()
        self.app.processEvents()
        self.assertFalse(self.window._compute_curve_collapsed)
        self.assertFalse(self.window.curve_surface.isHidden())
        self.assertEqual(self.window.curve_toggle_button.text(), "▾")


if __name__ == "__main__":
    unittest.main()
