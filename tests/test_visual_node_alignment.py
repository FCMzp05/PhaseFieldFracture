import unittest

import meshio
import numpy as np

from visual.gui_case_exporters import _scalar_field, _triangulation


class VisualNodeAlignmentTests(unittest.TestCase):
    def test_triangulation_and_point_field_share_merged_nodes(self):
        mesh = meshio.Mesh(
            points=np.array(
                [
                    [0.0, 0.0, 0.0],
                    [1.0, 0.0, 0.0],
                    [0.0, 1.0, 0.0],
                    [1.0, 0.0, 0.0],
                ],
                dtype=float,
            ),
            cells=[("triangle", np.array([[0, 1, 2], [0, 3, 2]], dtype=int))],
            point_data={"d": np.array([0.0, 0.4, 1.0, 0.6], dtype=float)},
        )

        points, cells, tri = _triangulation(mesh)
        damage = _scalar_field(mesh, "d")

        self.assertEqual(points.shape[0], 3)
        self.assertEqual(cells.shape, (2, 3))
        self.assertEqual(tri.triangles.shape, (2, 3))
        self.assertEqual(damage.shape[0], 3)
        self.assertAlmostEqual(float(damage[1]), 0.5)


if __name__ == "__main__":
    unittest.main()
