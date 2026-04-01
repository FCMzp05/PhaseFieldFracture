import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from gui.gui_main import MainWindow


class GuiMainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()

    def tearDown(self):
        self.window.close()

    def _switch_case(self, case_id: str):
        self.window.current_case = case_id
        self.window.current_category = self.window.case_states[case_id]["manifest"].category_id if self.window.case_states[case_id]["manifest"] else self.window._current_case_def().category_id
        self.window._apply_case_params_to_inputs(case_id)
        self.window._apply_case_state_to_ui()

    def test_non_scan_case_hides_scan_editor(self):
        self.window.current_case = "sent_tension"
        self.window.current_category = "elastic_fracture"
        self.window._apply_case_params_to_inputs("sent_tension")
        self.window._apply_case_state_to_ui()

        self.assertTrue(self.window.scan_editor_box.isHidden())
        self.assertEqual(self.window.case_states["sent_tension"]["run_profile"], "full")

    def test_scan_case_shows_expected_columns(self):
        self.window.current_case = "fang_flat_grooved_scan"
        self.window.current_category = "plastic_fracture"
        self.window._apply_case_params_to_inputs("fang_flat_grooved_scan")
        self.window._apply_case_state_to_ui()

        headers = [
            self.window.scan_table.horizontalHeaderItem(index).text()
            for index in range(self.window.scan_table.columnCount())
        ]
        self.assertFalse(self.window.scan_editor_box.isHidden())
        self.assertEqual(headers, ["Label", "h_ratio"])
        self.assertEqual(self.window.case_states["fang_flat_grooved_scan"]["run_profile"], "preview")

    def test_profile_and_scan_state_are_kept_per_case(self):
        self.window.current_case = "sent_tension"
        self.window.current_category = "elastic_fracture"
        self.window._apply_case_params_to_inputs("sent_tension")
        self.window.run_profile_combo.setCurrentIndex(self.window.run_profile_combo.findData("debug"))

        self.window.current_case = "fang_flat_grooved_scan"
        self.window.current_category = "plastic_fracture"
        self.window._apply_case_params_to_inputs("fang_flat_grooved_scan")
        self.window.run_profile_combo.setCurrentIndex(self.window.run_profile_combo.findData("full"))
        item = self.window.scan_table.item(0, 0)
        item.setText("custom_ratio")
        self.window.on_scan_item_changed(item)

        self.window.current_case = "sent_tension"
        self.window.current_category = "elastic_fracture"
        self.window._apply_case_params_to_inputs("sent_tension")
        self.assertEqual(self.window.case_states["sent_tension"]["run_profile"], "debug")

        self.window.current_case = "fang_flat_grooved_scan"
        self.window.current_category = "plastic_fracture"
        self.window._apply_case_params_to_inputs("fang_flat_grooved_scan")
        self.assertEqual(self.window.case_states["fang_flat_grooved_scan"]["run_profile"], "full")
        self.assertEqual(self.window.case_states["fang_flat_grooved_scan"]["scan_cases"][0]["label"], "custom_ratio")


if __name__ == "__main__":
    unittest.main()
