from __future__ import annotations

from pathlib import Path
from typing import Callable

from .SENS_panel import export_sens_panels
from .SENT_panel import export_sent_panels
from .export_fang2019_panels import export_fang2019_panels


ExporterFn = Callable[[Path, Path], dict[str, str]]


VISUAL_EXPORTERS: dict[str, ExporterFn] = {
    "fang2019_panel": export_fang2019_panels,
    "sent_panel": export_sent_panels,
    "sens_panel": export_sens_panels,
}


def get_visual_exporter(name: str) -> ExporterFn:
    try:
        return VISUAL_EXPORTERS[name]
    except KeyError as exc:
        raise KeyError(f"Unknown visual exporter: {name}") from exc


def export_visuals(name: str, native_output_dir: Path, output_dir: Path) -> dict[str, str]:
    exporter = get_visual_exporter(name)
    return exporter(native_output_dir, output_dir)
