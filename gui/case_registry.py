from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Mapping, Tuple


REPO_ROOT = Path(__file__).resolve().parent.parent
GUI_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: str
    cases: frozenset[str]
    input_type: str = "float"


@dataclass(frozen=True)
class ScanColumnSpec:
    key: str
    label: str
    input_type: str = "float"


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
    curve_columns: Tuple[str, str] = ()
    comparison_curve_columns: Tuple[str, str] = ()
    comparison_curve_kind: str = ""
    default_run_profile: str = "full"
    scan_editor_kind: str = ""

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
RUN_PROFILE_DEFINITIONS: Tuple[Tuple[str, str], ...] = (
    ("preview", "Preview"),
    ("full", "Full"),
    ("debug", "Debug"),
)
RUN_PROFILE_LABELS: Dict[str, str] = dict(RUN_PROFILE_DEFINITIONS)
RUN_PROFILE_ORDER: Tuple[str, ...] = tuple(profile_id for profile_id, _ in RUN_PROFILE_DEFINITIONS)


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

TPB_FIELDS = (
    "E_mat",
    "nu_mat",
    "Gc",
    "ls",
    "U_MAX",
    "N_CYCLES",
    "N_STEPS_PER_CYCLE",
    "SAVE_CYCLE_INTERVAL",
    "hfc",
    "hf",
    "h",
)

OFFSET_FIELDS = (
    "E_mat",
    "nu_mat",
    "Gc",
    "ls",
    "U_MAX",
    "R_RATIO",
    "MAX_CYCLES",
    "N_STEPS_PER_CYCLE",
    "h_coarse",
    "h_band",
    "BAND_MARGIN_Y",
)

FANG_FIELDS = (
    "E",
    "nu",
    "sigma_y0",
    "lc",
    "Gc",
    "u_total",
    "N_STEPS",
    "h_coarse",
)

DOUBLE_NOTCHED_FIELDS = (
    "E",
    "nu",
    "sigma_y0",
    "H_hard",
    "lc",
    "Gc",
    "N_STEPS",
    "h_fine",
    "h_coarse",
)

PLASTIC_SENT_FIELDS = (
    "E",
    "nu",
    "sigma_y0",
    "n",
    "l0",
    "Gc",
    "alpha_T",
    "eta_plastic",
    "u_max",
    "R_load",
    "N_CYCLES",
    "N_STEPS_PER_CYCLE",
    "h_fine",
    "h_coarse",
    "ENABLE_PNG",
    "SAVE_PNG_EVERY",
)

PLASTIC_CT_FIELDS = (
    "E",
    "nu",
    "sigma_y0",
    "Q_inf",
    "b",
    "C",
    "gamma",
    "l0",
    "GcI",
    "GcII",
    "alpha_T",
    "F_MAX_3D",
    "R_LOAD",
    "N_CYCLES_TOTAL",
    "N_STEPS_PER_CYCLE",
    "CYCLE_JUMP",
    "h_fine",
    "h_coarse",
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
        visual_exporter="sent_panel",
        status="ready",
        protocol_case_name="SENT",
        mesh_stage_enabled=True,
        editable_field_keys=COMMON_PROTOCOL_FIELDS + ("N_steps_coarse", "du_coarse", "du_fine", "u_end"),
        curve_columns=("u_mm", "F_kN"),
        default_run_profile="full",
    ),
    CaseDefinition(
        category_id="elastic_fracture",
        category_label=CATEGORY_LABELS["elastic_fracture"],
        case_id="sens_shear",
        display_name="SENS shear",
        backend_mode="protocol_julia",
        curve_kind="force_displacement",
        result_profile="protocol_sens",
        visual_exporter="sens_panel",
        status="ready",
        protocol_case_name="SENS",
        mesh_stage_enabled=True,
        editable_field_keys=COMMON_PROTOCOL_FIELDS + ("du_shear", "u_end"),
        curve_columns=("u_mm", "F_kN"),
        default_run_profile="full",
    ),
    CaseDefinition(
        category_id="elastic_fatigue",
        category_label=CATEGORY_LABELS["elastic_fatigue"],
        case_id="tpb_fatigue",
        display_name="TPB fatigue",
        backend_mode="batch_script",
        curve_kind="crack_growth",
        result_profile="elastic_fatigue_tpb",
        visual_exporter="",
        status="ready",
        script_path="BenchmarkCases_Organized/ElasticFatigue/ElasticFatigue_TPB_AT1.jl",
        native_output_dir="results_ElasticFatigue_TPB_AT1",
        mesh_stage_enabled=True,
        editable_field_keys=TPB_FIELDS,
        curve_columns=("cycle", "delta_a"),
        default_run_profile="preview",
    ),
    CaseDefinition(
        category_id="elastic_fatigue",
        category_label=CATEGORY_LABELS["elastic_fatigue"],
        case_id="offset_double_notch_fatigue",
        display_name="Offset double-notch fatigue",
        backend_mode="batch_script",
        curve_kind="crack_growth",
        result_profile="elastic_fatigue_offset_scan",
        visual_exporter="",
        status="ready",
        script_path="BenchmarkCases_Organized/ElasticFatigue/ElasticFatigue_OffsetDoubleNotch.jl",
        native_output_dir="results_ElasticFatigue_OffsetDoubleNotch",
        mesh_stage_enabled=True,
        editable_field_keys=OFFSET_FIELDS,
        curve_columns=(),
        comparison_curve_columns=("cycle", "gap_mm"),
        comparison_curve_kind="cycle_gap",
        default_run_profile="preview",
        scan_editor_kind="offset_notch_scan",
    ),
    CaseDefinition(
        category_id="plastic_fracture",
        category_label=CATEGORY_LABELS["plastic_fracture"],
        case_id="fang_flat_grooved_scan",
        display_name="Flat grooved scan",
        backend_mode="batch_script",
        curve_kind="force_displacement",
        result_profile="plastic_fracture_flat_grooved_scan",
        visual_exporter="fang2019_panel",
        status="ready",
        script_path="BenchmarkCases_Organized/PlasticFracture/PlasticFracture_FlatGrooved.jl",
        native_output_dir="results_PlasticFracture_FlatGrooved",
        mesh_stage_enabled=True,
        editable_field_keys=FANG_FIELDS,
        curve_columns=(),
        comparison_curve_columns=("u_mm", "F_kN"),
        comparison_curve_kind="force_displacement",
        default_run_profile="preview",
        scan_editor_kind="fang_h_ratio_scan",
    ),
    CaseDefinition(
        category_id="plastic_fracture",
        category_label=CATEGORY_LABELS["plastic_fracture"],
        case_id="double_notched_monotonic",
        display_name="Double-notched monotonic",
        backend_mode="batch_script",
        curve_kind="force_displacement",
        result_profile="plastic_fracture_double_notched_scan",
        visual_exporter="",
        status="ready",
        script_path="BenchmarkCases_Organized/PlasticFracture/PlasticFracture_DoubleNotched.jl",
        native_output_dir="results_PlasticFracture_DoubleNotched",
        mesh_stage_enabled=True,
        editable_field_keys=DOUBLE_NOTCHED_FIELDS,
        curve_columns=(),
        comparison_curve_columns=("u_mm", "F_kN"),
        comparison_curve_kind="force_displacement",
        default_run_profile="preview",
        scan_editor_kind="double_notched_scan",
    ),
    CaseDefinition(
        category_id="plastic_fatigue",
        category_label=CATEGORY_LABELS["plastic_fatigue"],
        case_id="sent_elasto_plastic_fatigue",
        display_name="SENT elasto-plastic fatigue",
        backend_mode="batch_script",
        curve_kind="crack_growth",
        result_profile="plastic_fatigue_sent",
        visual_exporter="",
        status="ready",
        script_path="BenchmarkCases_Organized/PlasticFatigue/PlasticFatigue_SENT.jl",
        native_output_dir="results_PlasticFatigue_SENT",
        mesh_stage_enabled=True,
        editable_field_keys=PLASTIC_SENT_FIELDS,
        curve_columns=("N", "delta_a_mm"),
        default_run_profile="preview",
    ),
    CaseDefinition(
        category_id="plastic_fatigue",
        category_label=CATEGORY_LABELS["plastic_fatigue"],
        case_id="ct_elasto_plastic_fatigue",
        display_name="CT elasto-plastic fatigue",
        backend_mode="batch_script",
        curve_kind="crack_growth",
        result_profile="plastic_fatigue_ct",
        visual_exporter="",
        status="ready",
        script_path="BenchmarkCases_Organized/PlasticFatigue/PlasticFatigue_CT.jl",
        native_output_dir="results_PlasticFatigue_CT",
        mesh_stage_enabled=True,
        editable_field_keys=PLASTIC_CT_FIELDS,
        curve_columns=("cycle", "delta_a_mm"),
        default_run_profile="preview",
    ),
)


CASE_DEFINITIONS: Dict[str, CaseDefinition] = {case.case_id: case for case in CASE_REGISTRY}


COMMON_FIELD_CASES = frozenset({"sent_tension", "sens_shear"})
TPB_CASES = frozenset({"tpb_fatigue"})
OFFSET_CASES = frozenset({"offset_double_notch_fatigue"})
FANG_CASES = frozenset({"fang_flat_grooved_scan"})
DOUBLE_NOTCHED_CASES = frozenset({"double_notched_monotonic"})
PLASTIC_SENT_CASES = frozenset({"sent_elasto_plastic_fatigue"})
PLASTIC_CT_CASES = frozenset({"ct_elasto_plastic_fatigue"})


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
            FieldSpec("h_fine", "Fine mesh size h_fine (mm)", COMMON_FIELD_CASES | DOUBLE_NOTCHED_CASES | PLASTIC_SENT_CASES | PLASTIC_CT_CASES),
            FieldSpec("h_coarse", "Coarse mesh size h_coarse (mm)", COMMON_FIELD_CASES | OFFSET_CASES | FANG_CASES | DOUBLE_NOTCHED_CASES | PLASTIC_SENT_CASES | PLASTIC_CT_CASES),
            FieldSpec("hfc", "Tip mesh size h_tip (mm)", TPB_CASES),
            FieldSpec("hf", "Refined mesh size h_refined (mm)", TPB_CASES),
            FieldSpec("h", "Far-field mesh size h_far (mm)", TPB_CASES),
            FieldSpec("h_band", "Band mesh size h_band (mm)", OFFSET_CASES),
            FieldSpec("BAND_MARGIN_Y", "Refinement band margin Y (mm)", OFFSET_CASES),
        ),
    ),
)

COMPUTE_FIELD_SPECS: Tuple[Tuple[str, Tuple[FieldSpec, ...]], ...] = (
    (
        "Material",
        (
            FieldSpec("E", "Young's modulus E (MPa)", COMMON_FIELD_CASES | FANG_CASES | DOUBLE_NOTCHED_CASES | PLASTIC_SENT_CASES | PLASTIC_CT_CASES),
            FieldSpec("nu", "Poisson ratio nu", COMMON_FIELD_CASES | FANG_CASES | DOUBLE_NOTCHED_CASES | PLASTIC_SENT_CASES | PLASTIC_CT_CASES),
            FieldSpec("E_mat", "Young's modulus E_mat", TPB_CASES | OFFSET_CASES),
            FieldSpec("nu_mat", "Poisson ratio nu_mat", TPB_CASES | OFFSET_CASES),
            FieldSpec("sigma_y0", "Yield stress sigma_y0 (MPa)", FANG_CASES | DOUBLE_NOTCHED_CASES | PLASTIC_SENT_CASES | PLASTIC_CT_CASES),
            FieldSpec("H_hard", "Hardening H_hard (MPa)", DOUBLE_NOTCHED_CASES),
            FieldSpec("n", "Hardening exponent n", PLASTIC_SENT_CASES),
            FieldSpec("Q_inf", "Voce Q_inf (MPa)", PLASTIC_CT_CASES),
            FieldSpec("b", "Voce b", PLASTIC_CT_CASES),
            FieldSpec("C", "Backstress C (MPa)", PLASTIC_CT_CASES),
            FieldSpec("gamma", "Backstress gamma", PLASTIC_CT_CASES),
        ),
    ),
    (
        "Phase Field",
        (
            FieldSpec("Gc", "Gc (N/mm)", COMMON_FIELD_CASES | TPB_CASES | OFFSET_CASES | FANG_CASES | DOUBLE_NOTCHED_CASES | PLASTIC_SENT_CASES),
            FieldSpec("GcI", "GcI (N/mm)", PLASTIC_CT_CASES),
            FieldSpec("GcII", "GcII (N/mm)", PLASTIC_CT_CASES),
            FieldSpec("l0", "Length scale l0 (mm)", COMMON_FIELD_CASES | PLASTIC_SENT_CASES | PLASTIC_CT_CASES),
            FieldSpec("ls", "Length scale ls (mm)", TPB_CASES | OFFSET_CASES),
            FieldSpec("lc", "Length scale lc (mm)", FANG_CASES | DOUBLE_NOTCHED_CASES),
            FieldSpec("eta_k", "Residual stiffness eta_k", COMMON_FIELD_CASES),
            FieldSpec("alpha_T", "Fatigue threshold alpha_T", PLASTIC_SENT_CASES | PLASTIC_CT_CASES),
            FieldSpec("eta_plastic", "Plastic weight eta_plastic", PLASTIC_SENT_CASES),
        ),
    ),
    (
        "Loading",
        (
            FieldSpec("N_steps_coarse", "Coarse steps", frozenset({"sent_tension"}), input_type="int"),
            FieldSpec("du_coarse", "du coarse (mm)", frozenset({"sent_tension"})),
            FieldSpec("du_fine", "du fine (mm)", frozenset({"sent_tension"})),
            FieldSpec("du_shear", "du shear (mm)", frozenset({"sens_shear"})),
            FieldSpec("u_end", "Max displacement u_end (mm)", COMMON_FIELD_CASES),
            FieldSpec("U_MAX", "Peak displacement U_MAX (mm)", TPB_CASES | OFFSET_CASES),
            FieldSpec("u_total", "Total displacement u_total (mm)", FANG_CASES),
            FieldSpec("u_max", "Peak displacement u_max (mm)", PLASTIC_SENT_CASES),
            FieldSpec("F_MAX_3D", "Peak load F_MAX_3D", PLASTIC_CT_CASES),
            FieldSpec("R_RATIO", "Load ratio R_RATIO", OFFSET_CASES),
            FieldSpec("R_load", "Load ratio R_load", PLASTIC_SENT_CASES),
            FieldSpec("R_LOAD", "Load ratio R_LOAD", PLASTIC_CT_CASES),
            FieldSpec("snapshot_every", "Snapshot every N steps", COMMON_FIELD_CASES, input_type="int"),
        ),
    ),
    (
        "Smoke",
        (
            FieldSpec("N_CYCLES", "Cycles N_CYCLES", TPB_CASES | PLASTIC_SENT_CASES, input_type="int"),
            FieldSpec("MAX_CYCLES", "Cycles MAX_CYCLES", OFFSET_CASES, input_type="int"),
            FieldSpec("N_CYCLES_TOTAL", "Cycles N_CYCLES_TOTAL", PLASTIC_CT_CASES, input_type="int"),
            FieldSpec("N_STEPS", "Steps N_STEPS", FANG_CASES | DOUBLE_NOTCHED_CASES, input_type="int"),
            FieldSpec("N_STEPS_PER_CYCLE", "Steps per cycle", TPB_CASES | OFFSET_CASES | PLASTIC_SENT_CASES | PLASTIC_CT_CASES, input_type="int"),
            FieldSpec("SAVE_CYCLE_INTERVAL", "Save cycle interval", TPB_CASES, input_type="int"),
            FieldSpec("SAVE_PNG_EVERY", "Save PNG every", PLASTIC_SENT_CASES, input_type="int"),
            FieldSpec("CYCLE_JUMP", "Cycle jump", PLASTIC_CT_CASES, input_type="int"),
            FieldSpec("ENABLE_PNG", "Enable PNG output", PLASTIC_SENT_CASES, input_type="bool"),
        ),
    ),
)

INT_FIELDS = frozenset(
    {
        "N_steps_coarse",
        "snapshot_every",
        "N_CYCLES",
        "MAX_CYCLES",
        "N_CYCLES_TOTAL",
        "N_STEPS",
        "N_STEPS_PER_CYCLE",
        "SAVE_CYCLE_INTERVAL",
        "SAVE_PNG_EVERY",
        "CYCLE_JUMP",
    }
)
BOOL_FIELDS = frozenset({"ENABLE_PNG"})
POSTPROCESS_VIEWS = ("Mesh", "Damage", "Displacement", "Curve", "Summary Table", "Comparison Curve", "Visual Export")
SCAN_EDITOR_SPECS: Mapping[str, Tuple[ScanColumnSpec, ...]] = {
    "offset_notch_scan": (
        ScanColumnSpec("label", "Label", "str"),
        ScanColumnSpec("y_left_mm", "y_left_mm", "float"),
        ScanColumnSpec("y_right_mm", "y_right_mm", "float"),
    ),
    "fang_h_ratio_scan": (
        ScanColumnSpec("label", "Label", "str"),
        ScanColumnSpec("h_ratio", "h_ratio", "float"),
    ),
    "double_notched_scan": (
        ScanColumnSpec("tag", "Tag", "str"),
        ScanColumnSpec("title", "Title", "str"),
        ScanColumnSpec("bl_radius_mm", "bl_radius_mm", "float"),
        ScanColumnSpec("tr_radius_mm", "tr_radius_mm", "float"),
        ScanColumnSpec("u_total_mm", "u_total_mm", "float"),
        ScanColumnSpec("left_scale", "left_scale", "float"),
    ),
}


def iter_cases_for_category(category_id: str) -> List[CaseDefinition]:
    return [case for case in CASE_REGISTRY if case.category_id == category_id]


def first_case_for_category(category_id: str) -> CaseDefinition:
    cases = iter_cases_for_category(category_id)
    if not cases:
        raise KeyError(f"Unknown category: {category_id}")
    ready_cases = [case for case in cases if case.is_ready]
    return ready_cases[0] if ready_cases else cases[0]
CURVE_AXIS_LABELS: Mapping[str, Tuple[str, str]] = {
    "force_displacement": ("u (mm)", "F (kN)"),
    "crack_growth": ("N", "Δa (mm)"),
    "cycle_gap": ("N", "Gap (mm)"),
}
