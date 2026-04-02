import tempfile
import unittest
from pathlib import Path

import matplotlib as mpl
import matplotlib.image as mpimg
import matplotlib.tri as mtri
import numpy as np

from visual.gui_case_exporters import _export_protocol_panel


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


if __name__ == "__main__":
    unittest.main()
