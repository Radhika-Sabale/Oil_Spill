"""M1 Scene Evidence Report (Stage 4, Step 1).

Evaluates the M1 vision adapter on every scene whose SAR file exists,
prints an evidence table to stdout, and writes data/m1_out/scene_report.csv.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Any, Dict, List

# Ensure repository root is on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import config, scenes as scenes_mod
from app.vision import predict, vectorize


def run_scene_report(out_csv_path: Path = None) -> List[Dict[str, Any]]:
    if out_csv_path is None:
        out_csv_path = config.DATA_DIR / "m1_out" / "scene_report.csv"

    index = scenes_mod.load_index()
    if not index:
        print("Warning: no scenes loaded from index.")
        return []

    rows: List[Dict[str, Any]] = []

    for sc in index:
        sar_path = Path(sc.sar_path)
        if not sar_path.exists():
            # Check config.SAR_DIR as well
            if (config.SAR_DIR / sar_path.name).exists():
                sar_path = config.SAR_DIR / sar_path.name
            else:
                # Scene SAR file does not exist on disk; skip
                continue

        # Run vision adapter (prefer_model=True)
        pred = predict.predict_scene(sc, prefer_model=True)
        doc = vectorize.to_contract_a(pred, sc, pred["raster"])

        seg = pred["seg"]
        radiometry = seg.get("radiometry") or {}
        slick = doc["slick"]

        row = {
            "scene_id": sc.id,
            "ais_mode": getattr(sc, "ais_mode", "unknown"),
            "method": slick["method"],
            "polygon_count": slick["polygon_count"],
            "total_oil_area_km2": slick["area_km2"] if slick["area_km2"] is not None else "null",
            "lookalike_polygon_count": len(slick.get("polygons_lookalike", [])),
            "sea_level_db": radiometry.get("sea_level_db"),
            "offset_from_reference_db": radiometry.get("offset_from_reference_db"),
            "dynamic_range_db": radiometry.get("dynamic_range_db"),
            "clean_water": radiometry.get("clean_water", False),
            "outside_training_range": radiometry.get("outside_training_range", False),
            "elapsed_s": doc.get("elapsed_s", 0.0),
        }
        rows.append(row)

    # Write CSV
    out_csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "scene_id",
        "ais_mode",
        "method",
        "polygon_count",
        "total_oil_area_km2",
        "lookalike_polygon_count",
        "sea_level_db",
        "offset_from_reference_db",
        "dynamic_range_db",
        "clean_water",
        "outside_training_range",
        "elapsed_s",
    ]
    with open(out_csv_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return rows


def format_table(rows: List[Dict[str, Any]]) -> str:
    headers = [
        "Scene ID",
        "AIS Mode",
        "Method",
        "Polys",
        "Area (km2)",
        "Lookalikes",
        "Sea Level (dB)",
        "Offset (dB)",
        "Dyn Range (dB)",
        "Clean Water",
        "Out of Range",
        "Elapsed (s)",
    ]
    keys = [
        "scene_id",
        "ais_mode",
        "method",
        "polygon_count",
        "total_oil_area_km2",
        "lookalike_polygon_count",
        "sea_level_db",
        "offset_from_reference_db",
        "dynamic_range_db",
        "clean_water",
        "outside_training_range",
        "elapsed_s",
    ]

    table_lines = []
    header_line = " | ".join(headers)
    table_lines.append(header_line)
    table_lines.append("-" * len(header_line))

    for r in rows:
        vals = [str(r.get(k, "")) for k in keys]
        table_lines.append(" | ".join(vals))

    return "\n".join(table_lines)


def main():
    csv_dest = config.DATA_DIR / "m1_out" / "scene_report.csv"
    print(f"Generating scene report across existing SAR scenes...")
    rows = run_scene_report(csv_dest)
    print("\n" + format_table(rows) + "\n")
    print(f"Report written to: {csv_dest}")


if __name__ == "__main__":
    main()

