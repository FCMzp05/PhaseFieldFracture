from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List


@dataclass
class RunManifest:
    category_id: str
    case_id: str
    run_id: str
    status: str
    backend_mode: str
    curve_kind: str
    run_profile: str
    source_script: str
    run_dir: str
    runtime_params_path: str
    native_output_dir: str
    mesh_paths: List[str] = field(default_factory=list)
    snapshot_paths: List[str] = field(default_factory=list)
    vtk_paths: List[str] = field(default_factory=list)
    curve_csv_paths: List[str] = field(default_factory=list)
    exported_visual_paths: Dict[str, str] = field(default_factory=dict)
    damage_paths: List[str] = field(default_factory=list)
    displacement_paths: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Dict[str, object]) -> "RunManifest":
        return cls(
            category_id=str(payload["category_id"]),
            case_id=str(payload["case_id"]),
            run_id=str(payload["run_id"]),
            status=str(payload["status"]),
            backend_mode=str(payload["backend_mode"]),
            curve_kind=str(payload["curve_kind"]),
            run_profile=str(payload.get("run_profile", "full")),
            source_script=str(payload.get("source_script", "")),
            run_dir=str(payload.get("run_dir", "")),
            runtime_params_path=str(payload.get("runtime_params_path", "")),
            native_output_dir=str(payload.get("native_output_dir", "")),
            mesh_paths=_string_list(payload.get("mesh_paths", [])),
            snapshot_paths=_string_list(payload.get("snapshot_paths", [])),
            vtk_paths=_string_list(payload.get("vtk_paths", [])),
            curve_csv_paths=_string_list(payload.get("curve_csv_paths", [])),
            exported_visual_paths={str(k): str(v) for k, v in dict(payload.get("exported_visual_paths", {})).items()},
            damage_paths=_string_list(payload.get("damage_paths", [])),
            displacement_paths=_string_list(payload.get("displacement_paths", [])),
            notes=_string_list(payload.get("notes", [])),
        )


def _string_list(values: object) -> List[str]:
    if not isinstance(values, list):
        return []
    return [str(value) for value in values]


def make_run_id(case_id: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{case_id}_{stamp}"


def write_manifest(path: Path, manifest: RunManifest) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest.to_dict(), indent=2), encoding="utf-8")


def load_manifest(path: Path) -> RunManifest:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return RunManifest.from_dict(payload)


def dedupe_existing_paths(paths: Iterable[Path]) -> List[str]:
    seen = set()
    result: List[str] = []
    for path in sorted({path.resolve() for path in paths if path.exists()}):
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        result.append(key)
    return result


def manifest_file_payloads(manifest: RunManifest) -> List[Path]:
    files: List[Path] = []
    if manifest.runtime_params_path:
        files.append(Path(manifest.runtime_params_path))
    for bucket in (
        manifest.mesh_paths,
        manifest.snapshot_paths,
        manifest.vtk_paths,
        manifest.curve_csv_paths,
        manifest.damage_paths,
        manifest.displacement_paths,
    ):
        files.extend(Path(path) for path in bucket)
    files.extend(Path(path) for path in manifest.exported_visual_paths.values())
    return [path for path in files if path.exists()]
