import unittest

import meshio
import numpy as np

from visual.gui_case_exporters import _scalar_field, _triangulation, _vector_field


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

    def test_scalar_and_vector_fields_align_by_coordinate_after_merge(self):
        mesh = meshio.Mesh(
            points=np.array(
                [
                    [1.0, 0.0, 0.0],
                    [0.0, 0.0, 0.0],
                    [0.0, 1.0, 0.0],
                    [1.0, 0.0, 0.0],
                    [0.0, 0.0, 0.0],
                ],
                dtype=float,
            ),
            cells=[("triangle", np.array([[1, 0, 2], [4, 3, 2]], dtype=int))],
            point_data={
                "d": np.array([10.0, 20.0, 30.0, 10.0, 20.0], dtype=float),
                "uh": np.array(
                    [
                        [1.0, 10.0, 0.0],
                        [2.0, 20.0, 0.0],
                        [3.0, 30.0, 0.0],
                        [1.0, 10.0, 0.0],
                        [2.0, 20.0, 0.0],
                    ],
                    dtype=float,
                ),
            },
        )

        points, _, _ = _triangulation(mesh)
        damage = _scalar_field(mesh, "d")
        displacement = _vector_field(mesh, "uh")

        damage_by_coord = {tuple(np.round(point, 8)): float(value) for point, value in zip(points, damage)}
        displacement_by_coord = {
            tuple(np.round(point, 8)): tuple(np.round(value, 8)) for point, value in zip(points, displacement)
        }

        self.assertEqual(damage_by_coord[(0.0, 0.0)], 20.0)
        self.assertEqual(damage_by_coord[(1.0, 0.0)], 10.0)
        self.assertEqual(damage_by_coord[(0.0, 1.0)], 30.0)
        self.assertEqual(displacement_by_coord[(0.0, 0.0)], (2.0, 20.0))
        self.assertEqual(displacement_by_coord[(1.0, 0.0)], (1.0, 10.0))
        self.assertEqual(displacement_by_coord[(0.0, 1.0)], (3.0, 30.0))


if __name__ == "__main__":
    unittest.main()
