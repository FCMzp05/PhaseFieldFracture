from __future__ import annotations

import argparse
from pathlib import Path

if __package__ in (None, ""):
    from _protocol_case_export import export_protocol_case_panels
else:
    from ._protocol_case_export import export_protocol_case_panels


def export_sens_panels(native_output_dir: Path, output_dir: Path) -> dict[str, str]:
    return export_protocol_case_panels(
        native_output_dir,
        output_dir,
        case_prefix="sens",
        display_name="SENS shear",
        mesh_png_name="mesh_SENS.png",
        mesh_msh_name="mesh_SENS.msh",
        curve_png_names=["F_u_curve_SENS.png"],
        curve_csv_names=["F_u_curve_SENS.csv"],
        snapshot_patterns=["snap_SENS_*.png"],
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export SENS visual panels.")
    parser.add_argument("native_output_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    outputs = export_sens_panels(args.native_output_dir, args.output_dir)
    for key, value in outputs.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
