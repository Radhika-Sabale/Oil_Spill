"""CLI tool to export Contract A ('M1 vision output') JSON and mask files.

Usage:
    python scripts/m1_export.py --scene gom_mc20_chronic_slick --out data/m1_out
    python scripts/m1_export.py --all --out data/m1_out
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure repo root is on sys.path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import config, scenes as scenes_mod              # noqa: E402
from app.vision.predict import predict_scene              # noqa: E402
from app.vision.schema import ContractADocument           # noqa: E402
from app.vision.vectorize import to_contract_a            # noqa: E402


def export_one_scene(
    scene_or_id: scenes_mod.Scene | str,
    out_dir: Path,
    prefer_model: bool = True,
) -> dict:
    """Run prediction, vectorize, validate against schema, and write output files."""
    # Run prediction and save masks into out_dir
    prediction = predict_scene(
        scene_or_id,
        out_dir=out_dir,
        prefer_model=prefer_model,
    )
    doc = to_contract_a(prediction)

    # Validate against Contract A Pydantic schema
    ContractADocument.model_validate(doc)

    # Write Contract A JSON
    incident_id = doc["incident_id"]
    json_path = out_dir / f"{incident_id}.slick_detection.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2)

    return doc


def main() -> int:
    parser = argparse.ArgumentParser(description="Export TideTrace M1 Contract A vision documents.")
    parser.add_argument("--scene", help="Scene ID to process")
    parser.add_argument("--all", action="store_true", help="Process every scene whose SAR TIFF exists")
    parser.add_argument("--out", default="data/m1_out", help="Output directory (default: data/m1_out)")
    parser.add_argument("--prefer-model", default=True, action=argparse.BooleanOptionalAction,
                        help="Whether to use U-Net (default: True)")
    args = parser.parse_args()

    if not args.scene and not args.all:
        parser.error("Either --scene <id> or --all must be specified.")

    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    scenes_to_run: list[scenes_mod.Scene] = []
    if args.all:
        for s in scenes_mod.all_scenes():
            sar_p = Path(s.sar_path)
            if sar_p.exists():
                scenes_to_run.append(s)
            elif (config.SAR_DIR / sar_p.name).exists():
                s.sar_path = str(config.SAR_DIR / sar_p.name)
                scenes_to_run.append(s)
    else:
        sc = scenes_mod.get(args.scene)
        if sc is not None:
            sar_p = Path(sc.sar_path)
            if not sar_p.exists() and (config.SAR_DIR / sar_p.name).exists():
                sc.sar_path = str(config.SAR_DIR / sar_p.name)
            scenes_to_run.append(sc)
        else:
            # Try as direct path
            scenes_to_run.append(args.scene)

    if not scenes_to_run:
        print("No matching scenes found with existing SAR imagery.", file=sys.stderr)
        return 1

    print(f"Exporting Contract A documents for {len(scenes_to_run)} scene(s) into {out_dir}...\n")

    for s in scenes_to_run:
        try:
            doc = export_one_scene(s, out_dir=out_dir, prefer_model=args.prefer_model)
            slick = doc["slick"]
            print(
                f"[{doc['incident_id']}] method={slick['method']} "
                f"polygons={slick['polygon_count']} "
                f"area_km2={slick['area_km2']} "
                f"conf={slick['confidence']} "
                f"flags={doc['quality_flags']} "
                f"elapsed={doc['elapsed_s']}s"
            )
        except Exception as exc:
            print(f"[{getattr(s, 'id', str(s))}] ERROR: {exc}", file=sys.stderr)
            return 1

    print(f"\nAll {len(scenes_to_run)} scene(s) exported successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

