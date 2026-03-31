from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Tuple


REPO_ROOT = Path(__file__).resolve().parent.parent
GUI_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: str
    cases: frozenset[str]


@dataclass(frozen=True)
class CaseDefinition:
    category_id: str
    category_label: str
    case_id: str
    display_name: str
    backend_mode: str
    curve_kind: str
    result_profile: str
    visual_exporter: str
    status: str
    protocol_case_name: str = ""
    script_path: str = ""
    native_output_dir: str = ""
    mesh_stage_enabled: bool = True
    editable_field_keys: Tuple[str, ...] = ()

    @property
    def is_ready(self) -> bool:
        return self.status == "ready"

    @property
    def script_abspath(self) -> Path | None:
        if not self.script_path:
            return None
        return REPO_ROOT / self.script_path

    @property
    def native_output_abspath(self) -> Path | None:
        if not self.native_output_dir:
            return None
        return REPO_ROOT / self.native_output_dir


CATEGORY_DEFINITIONS: Tuple[Tuple[str, str], ...] = (
    ("elastic_fracture", "Elastic Fracture"),
    ("elastic_fatigue", "Elastic Fatigue"),
    ("plastic_fracture", "Plastic Fracture"),
    ("plastic_fatigue", "Plastic Fatigue"),
)

CATEGORY_LABELS: Dict[str, str] = dict(CATEGORY_DEFINITIONS)
CATEGORY_ORDER: Tuple[str, ...] = tuple(category_id for category_id, _ in CATEGORY_DEFINITIONS)


COMMON_PROTOCOL_FIELDS = (
    "W",
    "H",
    "a0",
    "E",
    "nu",
    "Gc",
    "l0",
    "eta_k",
    "h_fine",
    "h_coarse",
    "snapshot_every",
)


CASE_REGISTRY: Tuple[CaseDefinition, ...] = (
    CaseDefinition(
        category_id="elastic_fracture",
        category_label=CATEGORY_LABELS["elastic_fracture"],
        case_id="sent_tension",
        display_name="SENT tension",
        backend_mode="protocol_julia",
        curve_kind="force_displacement",
        result_profile="protocol_sent",
        visual_exporter="",
        status="ready",
        protocol_case_name="SENT",
        mesh_stage_enabled=True,
        editable_field_keys=COMMON_PROTOCOL_FIELDS + ("N_steps_coarse", "du_coarse", "du_fine", "u_end"),
    ),
    CaseDefinition(
        category_id="elastic_fracture",
        category_label=CATEGORY_LABELS["elastic_fracture"],
        case_id="sens_shear",
        display_name="SENS shear",
        backend_mode="protocol_julia",
        curve_kind="force_displacement",
        result_profile="protocol_sens",
        visual_exporter="",
        status="ready",
        protocol_case_name="SENS",
        mesh_stage_enabled=True,
        editable_field_keys=COMMON_PROTOCOL_FIELDS + ("du_shear", "u_end"),
    ),
    CaseDefinition(
        category_id="elastic_fatigue",
        category_label=CATEGORY_LABELS["elastic_fatigue"],
        case_id="tpb_fatigue",
        display_name="TPB fatigue",
        backend_mode="batch_script",
        curve_kind="crack_growth",
        result_profile="planned",
        visual_exporter="",
        status="planned",
        script_path="BenchmarkCases_Organized/ElasticFatigue/ElasticFatigue_TPB_AT1.jl",
        native_output_dir="results_ElasticFatigue_TPB_AT1",
        mesh_stage_enabled=False,
    ),
    CaseDefinition(
        category_id="elastic_fatigue",
        category_label=CATEGORY_LABELS["elastic_fatigue"],
        case_id="offset_double_notch_fatigue",
        display_name="Offset double-notch fatigue",
        backend_mode="batch_script",
        curve_kind="crack_growth",
        result_profile="planned",
        visual_exporter="",
        status="planned",
        script_path="BenchmarkCases_Organized/ElasticFatigue/ElasticFatigue_OffsetDoubleNotch.jl",
        native_output_dir="results_ElasticFatigue_OffsetDoubleNotch",
        mesh_stage_enabled=False,
    ),
    CaseDefinition(
        category_id="plastic_fracture",
        category_label=CATEGORY_LABELS["plastic_fracture"],
        case_id="fang_flat_grooved_scan",
        display_name="Fang flat grooved scan",
        backend_mode="batch_script",
        curve_kind="force_displacement",
        result_profile="fang_flat_grooved_scan",
        visual_exporter="fang2019_panel",
        status="ready",
        script_path="BenchmarkCases_Organized/PlasticFracture/PlasticFracture_FlatGrooved.jl",
        native_output_dir="results_PlasticFracture_FlatGrooved",
        mesh_stage_enabled=False,
    ),
    CaseDefinition(
        category_id="plastic_fracture",
        category_label=CATEGORY_LABELS["plastic_fracture"],
        case_id="double_notched_monotonic",
        display_name="Double-notched monotonic",
        backend_mode="batch_script",
        curve_kind="force_displacement",
        result_profile="planned",
        visual_exporter="",
        status="planned",
        script_path="BenchmarkCases_Organized/PlasticFracture/PlasticFracture_DoubleNotched.jl",
        native_output_dir="results_PlasticFracture_DoubleNotched",
        mesh_stage_enabled=False,
    ),
    CaseDefinition(
        category_id="plastic_fatigue",
        category_label=CATEGORY_LABELS["plastic_fatigue"],
        case_id="sent_elasto_plastic_fatigue",
        display_name="SENT elasto-plastic fatigue",
        backend_mode="batch_script",
        curve_kind="crack_growth",
        result_profile="planned",
        visual_exporter="",
        status="planned",
        script_path="BenchmarkCases_Organized/PlasticFatigue/PlasticFatigue_SENT.jl",
        native_output_dir="results_PlasticFatigue_SENT",
        mesh_stage_enabled=False,
    ),
    CaseDefinition(
        category_id="plastic_fatigue",
        category_label=CATEGORY_LABELS["plastic_fatigue"],
        case_id="ct_elasto_plastic_fatigue",
        display_name="CT elasto-plastic fatigue",
        backend_mode="batch_script",
        curve_kind="crack_growth",
        result_profile="planned",
        visual_exporter="",
        status="planned",
        script_path="BenchmarkCases_Organized/PlasticFatigue/PlasticFatigue_CT.jl",
        native_output_dir="results_PlasticFatigue_CT",
        mesh_stage_enabled=False,
    ),
)


CASE_DEFINITIONS: Dict[str, CaseDefinition] = {case.case_id: case for case in CASE_REGISTRY}


COMMON_FIELD_CASES = frozenset({"sent_tension", "sens_shear"})
MESH_FIELD_SPECS: Tuple[Tuple[str, Tuple[FieldSpec, ...]], ...] = (
    (
        "Geometry",
        (
            FieldSpec("W", "Width W (mm)", COMMON_FIELD_CASES),
            FieldSpec("H", "Height H (mm)", COMMON_FIELD_CASES),
            FieldSpec("a0", "Pre-crack a0 (mm)", COMMON_FIELD_CASES),
        ),
    ),
    (
        "Mesh",
        (
            FieldSpec("h_fine", "Fine mesh h_fine (mm)", COMMON_FIELD_CASES),
            FieldSpec("h_coarse", "Coarse mesh h_coarse (mm)", COMMON_FIELD_CASES),
        ),
    ),
)

COMPUTE_FIELD_SPECS: Tuple[Tuple[str, Tuple[FieldSpec, ...]], ...] = (
    (
        "Material",
        (
            FieldSpec("E", "Young's modulus E (MPa)", COMMON_FIELD_CASES),
            FieldSpec("nu", "Poisson ratio nu", COMMON_FIELD_CASES),
        ),
    ),
    (
        "Phase Field",
        (
            FieldSpec("Gc", "Gc (N/mm)", COMMON_FIELD_CASES),
            FieldSpec("l0", "Length scale l0 (mm)", COMMON_FIELD_CASES),
            FieldSpec("eta_k", "Residual stiffness eta_k", COMMON_FIELD_CASES),
        ),
    ),
    (
        "Loading",
        (
            FieldSpec("N_steps_coarse", "Coarse steps", frozenset({"sent_tension"})),
            FieldSpec("du_coarse", "du coarse (mm)", frozenset({"sent_tension"})),
            FieldSpec("du_fine", "du fine (mm)", frozenset({"sent_tension"})),
            FieldSpec("du_shear", "du shear (mm)", frozenset({"sens_shear"})),
            FieldSpec("u_end", "Max displacement u_end (mm)", COMMON_FIELD_CASES),
            FieldSpec("snapshot_every", "Snapshot every N steps", COMMON_FIELD_CASES),
        ),
    ),
)

INT_FIELDS = frozenset({"N_steps_coarse", "snapshot_every"})
POSTPROCESS_VIEWS = ("Mesh", "Damage", "Displacement", "Visual Export")


def iter_cases_for_category(category_id: str) -> List[CaseDefinition]:
    return [case for case in CASE_REGISTRY if case.category_id == category_id]


def first_case_for_category(category_id: str) -> CaseDefinition:
    cases = iter_cases_for_category(category_id)
    if not cases:
        raise KeyError(f"Unknown category: {category_id}")
    ready_cases = [case for case in cases if case.is_ready]
    return ready_cases[0] if ready_cases else cases[0]


def status_display(case: CaseDefinition) -> str:
    return "Ready" if case.is_ready else "Planned"


CURVE_AXIS_LABELS: Mapping[str, Tuple[str, str]] = {
    "force_displacement": ("u (mm)", "F (kN)"),
    "crack_growth": ("N", "Δa (mm)"),
}
