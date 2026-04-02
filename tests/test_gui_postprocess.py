import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QPoint, QPointF, Qt
from PyQt5.QtGui import QColor, QImage
from PyQt5.QtGui import QWheelEvent
from PyQt5.QtWidgets import QGraphicsOpacityEffect
from PyQt5.QtWidgets import QApplication

import gui.gui_main as gui_main
from gui.run_manifest import RunManifest, write_manifest


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
        for directory in (self.results_dir, self.manifest_dir, self.runs_dir, self.visual_export_dir):
            directory.mkdir(parents=True, exist_ok=True)

        self.patchers = [
            mock.patch.object(gui_main, "RESULTS_DIR", self.results_dir),
            mock.patch.object(gui_main, "MANIFEST_DIR", self.manifest_dir),
            mock.patch.object(gui_main, "RUNS_DIR", self.runs_dir),
            mock.patch.object(gui_main, "VISUAL_EXPORT_DIR", self.visual_export_dir),
            mock.patch.object(gui_main, "STOP_FLAG", self.temp_path / "gui_stop.flag"),
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

    def test_fatigue_case_exposes_curve_view(self):
        self._open_window()
        self._select_case("sent_elasto_plastic_fatigue")
        self.assertEqual(self._view_names(), ["Mesh", "Damage", "Curve", "Visual Export"])

    def test_scan_case_hides_curve_and_displacement_views(self):
        self._open_window()
        self._select_case("offset_double_notch_fatigue")
        self.assertEqual(self._view_names(), ["Mesh", "Damage", "Summary Table", "Comparison Curve", "Visual Export"])

    def test_visual_export_view_is_enabled_for_newly_supported_cases(self):
        self._open_window()
        supported_cases = {
            "tpb_fatigue": ["Mesh", "Damage", "Curve", "Visual Export"],
            "double_notched_monotonic": ["Mesh", "Damage", "Summary Table", "Comparison Curve", "Visual Export"],
            "ct_elasto_plastic_fatigue": ["Mesh", "Damage", "Curve", "Visual Export"],
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
        self.window.postprocess_view_combo.setCurrentText("Curve")
        self.app.processEvents()

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

    def test_postprocess_tab_stays_scrollable_in_compact_window(self):
        self._open_window()
        self.window.resize(760, 680)
        self.window.show()
        self.window.tabs.setTabEnabled(self.window.post_tab_index, True)
        self.window.tabs.setCurrentIndex(self.window.post_tab_index)
        self.app.processEvents()

        scrollbar = self.window.postprocess_scroll.verticalScrollBar()
        self.assertGreater(scrollbar.maximum(), 0)
        self.assertTrue(self.window.open_paraview_button.isVisible())
        self.assertTrue(self.window.export_results_button.isVisible())

    def test_live_curve_card_can_collapse_and_restore(self):
        self._open_window()
        self.window.resize(1280, 900)
        self.window.show()
        self.app.processEvents()

        self.assertFalse(self.window._compute_curve_collapsed)
        self.assertFalse(self.window.curve_surface.isHidden())
        self.assertEqual(self.window.curve_toggle_button.text(), "▾")

    def test_compute_live_preview_panel_shows_damage_and_displacement(self):
        self._open_window()
        self.window.resize(1280, 900)
        self.window.show()
        self.window.tabs.setCurrentIndex(self.window.compute_tab_index)
        self.app.processEvents()

        damage_path = self.temp_path / "snap_SENT_0001.png"
        displacement_path = self.temp_path / "u_mag_SENT_0001.png"
        damage_image = QImage(320, 240, QImage.Format_RGB32)
        damage_image.fill(QColor("#dce8f5"))
        displacement_image = QImage(320, 240, QImage.Format_RGB32)
        displacement_image.fill(QColor("#ffffff"))
        self.assertTrue(damage_image.save(str(damage_path)))
        self.assertTrue(displacement_image.save(str(displacement_path)))

        self.window.current_case = "sent_tension"
        self.window.active_case_id = "sent_tension"
        self.window.active_run_mode = "compute"
        self.window.update_snapshot(str(damage_path))
        self.window.update_displacement_path(str(displacement_path))
        self.app.processEvents()

        self.assertIsNotNone(self.window.damage_label.image_label.pixmap())
        self.assertFalse(self.window.damage_label.image_label.pixmap().isNull())
        self.assertIsNotNone(self.window.displacement_label.image_label.pixmap())
        self.assertFalse(self.window.displacement_label.image_label.pixmap().isNull())
        self.assertFalse(self.window.compute_damage_card.isHidden())
        self.assertFalse(self.window.compute_displacement_card.isHidden())

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
