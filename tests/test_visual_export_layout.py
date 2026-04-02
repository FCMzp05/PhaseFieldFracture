import tempfile
import unittest
from pathlib import Path

import matplotlib as mpl
import matplotlib.image as mpimg
import matplotlib.tri as mtri
import numpy as np

from visual.gui_case_exporters import _export_protocol_panel, _protocol_curve_points


class VisualExportLayoutTests(unittest.TestCase):
    def test_protocol_field_panel_is_landscape_1x2(self):
        tri = mtri.Triangulation(
            np.array([0.0, 1.0, 0.0], dtype=float),
            np.array([0.0, 0.0, 1.0], dtype=float),
            np.array([[0, 1, 2]], dtype=int),
        )
        snap = {
            "tri": tri,
            "d": np.array([0.0, 0.5, 1.0], dtype=float),
            "svm": np.array([10.0, 20.0, 30.0], dtype=float),
            "note": "final",
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "protocol_panel.png"
            _export_protocol_panel(
                output_path,
                snaps=[snap],
                col_titles=[],
                row_specs=[
                    ("d", "turbo", mpl.colors.Normalize(0.0, 1.0), "Damage field $d$", "$d$"),
                    ("svm", "plasma", mpl.colors.Normalize(0.0, 40.0), "Von Mises stress", "MPa"),
                ],
                note_key="note",
            )
            image = mpimg.imread(output_path)

        self.assertGreater(image.shape[1], image.shape[0])

    def test_protocol_curve_markers_do_not_include_abc_labels(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "curve.csv"
            csv_path.write_text(
                "step,u_mm,F_kN\n1,0.0,0.0\n2,0.1,1.0\n3,0.2,2.0\n",
                encoding="utf-8",
            )
            _, _, markers = _protocol_curve_points(csv_path, [1, 2, 3], x_scale=1.0)

        self.assertEqual(len(markers), 3)
        self.assertTrue(all("label" not in marker for marker in markers))


if __name__ == "__main__":
    unittest.main()
