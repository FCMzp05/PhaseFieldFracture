import tempfile
import unittest
from pathlib import Path

from gui.run_manifest import RunManifest, load_manifest, write_manifest


class RunManifestTests(unittest.TestCase):
    def test_old_payload_defaults_run_profile_to_full(self):
        payload = {
            "category_id": "elastic_fracture",
            "case_id": "sent_tension",
            "run_id": "sent_tension_20260401_000000",
            "status": "completed",
            "backend_mode": "protocol_julia",
            "curve_kind": "force_displacement",
            "source_script": "/tmp/gui_solver.jl",
            "run_dir": "/tmp/run",
            "runtime_params_path": "/tmp/run/runtime_params.json",
            "native_output_dir": "/tmp/run/native",
            "mesh_paths": [],
            "snapshot_paths": [],
            "vtk_paths": [],
            "curve_csv_paths": [],
            "exported_visual_paths": {},
            "damage_paths": [],
            "displacement_paths": [],
            "notes": [],
        }

        manifest = RunManifest.from_dict(payload)

        self.assertEqual(manifest.run_profile, "full")

    def test_roundtrip_preserves_run_profile(self):
        manifest = RunManifest(
            category_id="plastic_fracture",
            case_id="fang_flat_grooved_scan",
            run_id="fang_flat_grooved_scan_20260401_000000",
            status="completed",
            backend_mode="batch_script",
            curve_kind="force_displacement",
            run_profile="preview",
            source_script="/tmp/fang.jl",
            run_dir="/tmp/run",
            runtime_params_path="/tmp/run/runtime_params.json",
            native_output_dir="/tmp/run/native",
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            manifest_path = Path(tmp_dir) / "manifest.json"
            write_manifest(manifest_path, manifest)
            loaded = load_manifest(manifest_path)

        self.assertEqual(loaded.run_profile, "preview")
        self.assertEqual(loaded.case_id, "fang_flat_grooved_scan")


if __name__ == "__main__":
    unittest.main()
