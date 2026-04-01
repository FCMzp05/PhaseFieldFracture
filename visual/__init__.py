from __future__ import annotations

from pathlib import Path
from typing import Callable

from .gui_case_exporters import (
    export_ct_fatigue_panels,
    export_double_notched_panels,
    export_fang2019_panels,
    export_offset_double_notch_panels,
    export_sens_panels,
    export_sent_fatigue_panels,
    export_sent_panels,
    export_tpb_panels,
)


ExporterFn = Callable[[Path, Path, Path | None], dict[str, str]]


VISUAL_EXPORTERS: dict[str, ExporterFn] = {
    "ct_fatigue_panel": export_ct_fatigue_panels,
    "double_notched_panel": export_double_notched_panels,
    "fang2019_panel": export_fang2019_panels,
    "offset_double_notch_panel": export_offset_double_notch_panels,
    "sent_panel": export_sent_panels,
    "sent_fatigue_panel": export_sent_fatigue_panels,
    "sens_panel": export_sens_panels,
    "tpb_panel": export_tpb_panels,
}


def get_visual_exporter(name: str) -> ExporterFn:
    try:
        return VISUAL_EXPORTERS[name]
    except KeyError as exc:
        raise KeyError(f"Unknown visual exporter: {name}") from exc


def export_visuals(
    name: str,
    native_output_dir: Path,
    output_dir: Path,
    runtime_params_path: Path | None = None,
) -> dict[str, str]:
    exporter = get_visual_exporter(name)
    return exporter(native_output_dir, output_dir, runtime_params_path)
