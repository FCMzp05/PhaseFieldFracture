import tempfile
import unittest
from pathlib import Path

import meshio
import numpy as np

from gui.live_preview_renderer import render_previews


class LivePreviewRendererTests(unittest.TestCase):
    def test_render_previews_writes_multiple_outputs_from_single_vtu(self):
        points = np.array(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
            ],
            dtype=float,
        )
        cells = [("triangle", np.array([[0, 1, 2]], dtype=int))]
        point_data = {
            "d": np.array([0.0, 0.4, 0.9], dtype=float),
            "uh": np.array(
                [
                    [0.0, 0.0],
                    [0.02, 0.0],
                    [0.0, 0.03],
                ],
                dtype=float,
            ),
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            input_path = tmp_path / "preview.vtu"
            meshio.write(input_path, meshio.Mesh(points=points, cells=cells, point_data=point_data))

            outputs = {
                "damage": tmp_path / "damage.png",
                "displacement": tmp_path / "displacement.png",
                "von_mises": tmp_path / "von_mises.png",
            }
            render_previews(input_path, outputs, young_modulus=210950.0, poisson_ratio=0.3)

            for output_path in outputs.values():
                self.assertTrue(output_path.exists())
                self.assertGreater(output_path.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
