import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

import gui.gui_main as gui_main
from gui.run_manifest import RunManifest, write_manifest


class GuiScanPostprocessTests(unittest.TestCase):
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
        self.window = gui_main.MainWindow()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.app.processEvents()
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.tempdir.cleanup()

    def _select_case(self, case_id: str):
        case = gui_main.CASE_DEFINITIONS[case_id]
        self.window.current_category = case.category_id
        self.window._refresh_case_combo(case.category_id, preferred_case_id=case_id)
        self.window.current_case = case_id
        self.window._apply_case_params_to_inputs(case_id)
        self.window._apply_case_state_to_ui()
        self.window._set_idle_state()
        self.app.processEvents()

    def _write_manifest(self, case_id: str, native_dir: Path, curve_csv_paths):
        manifest = RunManifest(
            category_id=gui_main.CASE_DEFINITIONS[case_id].category_id,
            case_id=case_id,
            run_id=f"{case_id}_20260401_000000",
            status="completed",
            backend_mode="batch_script",
            curve_kind=gui_main.CASE_DEFINITIONS[case_id].curve_kind,
            run_profile="preview",
            source_script="",
            run_dir=str(self.runs_dir / case_id / f"{case_id}_20260401_000000"),
            runtime_params_path="",
            native_output_dir=str(native_dir),
            curve_csv_paths=[str(path) for path in curve_csv_paths],
        )
        write_manifest(self.manifest_dir / f"{case_id}_latest.json", manifest)

    def test_fang_manifest_collects_summary_and_force_displacement_csvs(self):
        native_dir = self.temp_path / "fang_native"
        (native_dir / "H01E").mkdir(parents=True, exist_ok=True)
        (native_dir / "H02E").mkdir(parents=True, exist_ok=True)
        (native_dir / "scan_summary.csv").write_text("label,H_ratio\nH01E,0.1\nH02E,0.2\n", encoding="utf-8")
        (native_dir / "H01E" / "force_displacement_H01E.csv").write_text("u_mm,F_kN\n0,0\n1,2\n", encoding="utf-8")
        (native_dir / "H02E" / "force_displacement_H02E.csv").write_text("u_mm,F_kN\n0,0\n1,3\n", encoding="utf-8")

        case = gui_main.CASE_DEFINITIONS["fang_flat_grooved_scan"]
        manifest = self.window._build_fang_manifest(case, native_output_dir=native_dir, run_profile="preview")

        self.assertIsNotNone(manifest)
        self.assertEqual(
            {Path(path).name for path in manifest.curve_csv_paths},
            {"scan_summary.csv", "force_displacement_H01E.csv", "force_displacement_H02E.csv"},
        )

    def test_offset_manifest_collects_summary_and_history_csvs(self):
        native_dir = self.temp_path / "offset_native"
        (native_dir / "aligned").mkdir(parents=True, exist_ok=True)
        (native_dir / "offset_mid").mkdir(parents=True, exist_ok=True)
        (native_dir / "scan_summary.csv").write_text("case_label,cycle_coalescence\naligned,100\noffset_mid,120\n", encoding="utf-8")
        (native_dir / "aligned" / "history.csv").write_text("cycle,gap_mm\n1,0.1\n2,0.2\n", encoding="utf-8")
        (native_dir / "offset_mid" / "history.csv").write_text("cycle,gap_mm\n1,0.15\n2,0.25\n", encoding="utf-8")

        case = gui_main.CASE_DEFINITIONS["offset_double_notch_fatigue"]
        manifest = self.window._build_offset_scan_manifest(case, native_output_dir=native_dir, run_profile="preview")

        self.assertIsNotNone(manifest)
        self.assertEqual(
            {str(Path(path).relative_to(native_dir)) for path in manifest.curve_csv_paths},
            {"scan_summary.csv", "aligned/history.csv", "offset_mid/history.csv"},
        )

    def test_summary_table_and_comparison_curve_views_render_scan_results(self):
        case_id = "fang_flat_grooved_scan"
        native_dir = self.temp_path / "fang_view_native"
        case_a_dir = native_dir / "H01E"
        case_b_dir = native_dir / "H02E"
        case_a_dir.mkdir(parents=True, exist_ok=True)
        case_b_dir.mkdir(parents=True, exist_ok=True)
        summary_csv = native_dir / "scan_summary.csv"
        curve_a = case_a_dir / "force_displacement_H01E.csv"
        curve_b = case_b_dir / "force_displacement_H02E.csv"
        summary_csv.write_text(
            "label,H_ratio,runtime_s,n_steps,u_final_mm,f_peak_kN,d_final\nH01E,0.10,1.0,10,0.20,5.00,0.95\nH02E,0.20,1.2,11,0.25,6.50,0.98\n",
            encoding="utf-8",
        )
        curve_a.write_text("u_mm,F_kN\n0.0,0.0\n0.1,2.0\n0.2,5.0\n", encoding="utf-8")
        curve_b.write_text("u_mm,F_kN\n0.0,0.0\n0.1,2.5\n0.2,6.5\n", encoding="utf-8")
        self._write_manifest(case_id, native_dir, [summary_csv, curve_a, curve_b])

        self.window._load_manifests_from_disk()
        self._select_case(case_id)

        view_names = [self.window.postprocess_view_combo.itemText(index) for index in range(self.window.postprocess_view_combo.count())]
        self.assertEqual(view_names, ["Mesh", "Damage", "Summary Table", "Comparison Curve", "Visual Export"])

        self.window.postprocess_view_combo.setCurrentText("Summary Table")
        self.app.processEvents()
        self.assertEqual(self.window.postprocess_table.columnCount(), 7)
        self.assertEqual(self.window.postprocess_table.rowCount(), 2)
        self.assertEqual(self.window.postprocess_table.horizontalHeaderItem(0).text(), "label")
        self.assertEqual(self.window.postprocess_table.item(1, 5).text(), "6.50")

        self.window.postprocess_view_combo.setCurrentText("Comparison Curve")
        self.app.processEvents()
        lines = self.window.postprocess_curve_canvas.axes.lines
        self.assertEqual(len(lines), 2)
        self.assertEqual([line.get_label() for line in lines], ["H01E", "H02E"])
        self.assertEqual(list(lines[0].get_xdata()), [0.0, 0.1, 0.2])
        self.assertEqual(list(lines[1].get_ydata()), [0.0, 2.5, 6.5])
        self.assertIn("2 Series [H01E, H02E]", self.window.postprocess_detail_label.text())


if __name__ == "__main__":
    unittest.main()
