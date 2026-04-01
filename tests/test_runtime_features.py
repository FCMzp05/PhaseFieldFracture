import unittest

from gui.case_registry import SCAN_EDITOR_SPECS
from gui.gui_main import apply_run_profile_overrides, normalize_run_profile, serialize_scan_cases


class RunProfileLogicTests(unittest.TestCase):
    def test_full_profile_keeps_base_params(self):
        base_params = {"N_STEPS": 100, "SAVE_PNG_EVERY": 20}
        overrides = {
            "preview": {"N_STEPS": 2},
            "debug": {"N_STEPS": 2, "SAVE_PNG_EVERY": 1},
        }

        effective = apply_run_profile_overrides(base_params, overrides, "full")

        self.assertEqual(effective, base_params)
        self.assertIsNot(effective, base_params)

    def test_debug_profile_applies_overrides_without_mutating_base(self):
        base_params = {"N_STEPS": 100, "SAVE_PNG_EVERY": 20}
        overrides = {
            "preview": {"N_STEPS": 2},
            "debug": {"N_STEPS": 2, "SAVE_PNG_EVERY": 1},
        }

        effective = apply_run_profile_overrides(base_params, overrides, "debug")

        self.assertEqual(effective["N_STEPS"], 2)
        self.assertEqual(effective["SAVE_PNG_EVERY"], 1)
        self.assertEqual(base_params, {"N_STEPS": 100, "SAVE_PNG_EVERY": 20})

    def test_normalize_run_profile_falls_back_to_full(self):
        self.assertEqual(normalize_run_profile("preview"), "preview")
        self.assertEqual(normalize_run_profile("DEBUG"), "debug")
        self.assertEqual(normalize_run_profile("unexpected"), "full")


class ScanSerializationTests(unittest.TestCase):
    def test_offset_scan_rows_serialize(self):
        rows = [
            {"label": "aligned", "y_left_mm": "25.0", "y_right_mm": "25.0"},
            {"label": "offset_mid", "y_left_mm": "27.0", "y_right_mm": "23.0"},
        ]

        payload = serialize_scan_cases(rows, SCAN_EDITOR_SPECS["offset_notch_scan"])

        self.assertEqual(payload[0]["label"], "aligned")
        self.assertEqual(payload[1]["y_left_mm"], 27.0)
        self.assertEqual(payload[1]["y_right_mm"], 23.0)

    def test_fang_scan_rows_serialize(self):
        rows = [
            {"label": "H01E", "h_ratio": "0.1"},
            {"label": "H02E", "h_ratio": "0.2"},
        ]

        payload = serialize_scan_cases(rows, SCAN_EDITOR_SPECS["fang_h_ratio_scan"])

        self.assertEqual(payload, [{"label": "H01E", "h_ratio": 0.1}, {"label": "H02E", "h_ratio": 0.2}])

    def test_double_notched_scan_rows_serialize(self):
        rows = [
            {
                "tag": "paper",
                "title": "Paper baseline",
                "bl_radius_mm": "2.5",
                "tr_radius_mm": "2.0",
                "u_total_mm": "0.4",
                "left_scale": "1.0",
            }
        ]

        payload = serialize_scan_cases(rows, SCAN_EDITOR_SPECS["double_notched_scan"])

        self.assertEqual(payload[0]["tag"], "paper")
        self.assertEqual(payload[0]["title"], "Paper baseline")
        self.assertEqual(payload[0]["bl_radius_mm"], 2.5)
        self.assertEqual(payload[0]["left_scale"], 1.0)

    def test_scan_rows_must_not_be_empty(self):
        with self.assertRaisesRegex(ValueError, "At least one scan case is required"):
            serialize_scan_cases([], SCAN_EDITOR_SPECS["fang_h_ratio_scan"])


if __name__ == "__main__":
    unittest.main()
