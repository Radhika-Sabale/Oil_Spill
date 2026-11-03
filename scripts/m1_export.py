"""CLI tool to export Contract A ('M1 vision output') JSON and mask files.

Usage:
    python scripts/m1_export.py --scene gom_mc20_chronic_slick --out data/m1_out
    python scripts/m1_export.py --all --out data/m1_out
    python scripts/m1_export.py --all --out data/m1_out --snapshot
    python scripts/m1_export.py --all --out data/m1_out --compare
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

# Ensure repo root is on sys.path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np

from app import config, scenes as scenes_mod              # noqa: E402
from app.vision.predict import predict_scene              # noqa: E402
from app.vision.schema import ContractADocument           # noqa: E402
from app.vision.vectorize import to_contract_a            # noqa: E402


def compute_snapshot_dict(doc: dict, mask_array: np.ndarray) -> dict:
    """Extract deterministic regression fields."""
    mask_sha = hashlib.sha256(mask_array.tobytes()).hexdigest()
    polys = doc.get("slick", {}).get("polygons", [])
    coords = []
    for p in polys:
        ring = [[round(float(pt[0]), 6), round(float(pt[1]), 6)] for pt in p.get("geometry", {}).get("coordinates", [[]])[0]]
        coords.append(ring)

    return {
        "incident_id": doc["incident_id"],
        "mask_sha256": mask_sha,
        "polygon_count": doc.get("slick", {}).get("polygon_count", 0),
        "polygons_coordinates_rounded": coords,
        "area_km2": doc.get("slick", {}).get("area_km2"),
        "confidence": doc.get("slick", {}).get("confidence"),
        "quality_flags": doc.get("quality_flags", []),
    }


def export_one_scene(
    scene_or_id: scenes_mod.Scene | str,
    out_dir: Path,
    prefer_model: bool = True,
) -> tuple[dict, np.ndarray]:
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

    return doc, prediction["seg"]["mask"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Export TideTrace M1 Contract A vision documents.")
    parser.add_argument("--scene", help="Scene ID to process")
    parser.add_argument("--all", action="store_true", help="Process every scene whose SAR TIFF exists")
    parser.add_argument("--out", default="data/m1_out", help="Output directory (default: data/m1_out)")
    parser.add_argument("--prefer-model", default=True, action=argparse.BooleanOptionalAction,
                        help="Whether to use U-Net (default: True)")
    parser.add_argument("--snapshot", action="store_true",
                        help="Save regression snapshot to data/m1_out/snapshots/<id>.snapshot.json")
    parser.add_argument("--compare", action="store_true",
                        help="Compare current output against existing snapshot in data/m1_out/snapshots/")
    args = parser.parse_args()

    if not args.scene and not args.all:
        parser.error("Either --scene <id> or --all must be specified.")

    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    snap_dir = out_dir / "snapshots"

    scenes_to_run: list[scenes_mod.Scene | str] = []
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
            scenes_to_run.append(args.scene)

    if not scenes_to_run:
        print("No matching scenes found with existing SAR imagery.", file=sys.stderr)
        return 1

    mode_label = "Comparing against" if args.compare else ("Saving snapshot to" if args.snapshot else "Exporting Contract A documents into")
    print(f"{mode_label} {out_dir} for {len(scenes_to_run)} scene(s)...\n")

    has_error = False
    for s in scenes_to_run:
        try:
            doc, mask = export_one_scene(s, out_dir=out_dir, prefer_model=args.prefer_model)
            slick = doc["slick"]
            incident_id = doc["incident_id"]

            print(
                f"[{incident_id}] method={slick['method']} "
                f"polygons={slick['polygon_count']} "
                f"area_km2={slick['area_km2']} "
                f"conf={slick['confidence']} "
                f"flags={doc['quality_flags']} "
                f"elapsed={doc['elapsed_s']}s"
            )

            current_snap = compute_snapshot_dict(doc, mask)

            if args.snapshot:
                snap_dir.mkdir(parents=True, exist_ok=True)
                snap_file = snap_dir / f"{incident_id}.snapshot.json"
                snap_file.write_text(json.dumps(current_snap, indent=2), encoding="utf-8")
                print(f"  -> Saved snapshot: {snap_file.name}")

            if args.compare:
                snap_file = snap_dir / f"{incident_id}.snapshot.json"
                if not snap_file.exists():
                    print(f"  [COMPARE FAIL] No snapshot found at {snap_file}", file=sys.stderr)
                    has_error = True
                    continue
                expected = json.loads(snap_file.read_text(encoding="utf-8"))

                # Check mask SHA256
                if current_snap["mask_sha256"] != expected["mask_sha256"]:
                    print(f"  [COMPARE FAIL] Mask SHA-256 mismatch: {current_snap['mask_sha256']} != {expected['mask_sha256']}", file=sys.stderr)
                    has_error = True
                elif current_snap["polygon_count"] != expected["polygon_count"]:
                    print(f"  [COMPARE FAIL] Polygon count mismatch: {current_snap['polygon_count']} != {expected['polygon_count']}", file=sys.stderr)
                    has_error = True
                elif current_snap["polygons_coordinates_rounded"] != expected["polygons_coordinates_rounded"]:
                    print(f"  [COMPARE FAIL] Coordinates mismatch", file=sys.stderr)
                    has_error = True
                else:
                    print(f"  [COMPARE OK] Matches snapshot {snap_file.name}")

        except Exception as exc:
            print(f"[{getattr(s, 'id', str(s))}] ERROR: {exc}", file=sys.stderr)
            return 1

    if has_error:
        print("\nSnapshot comparison failed for one or more scenes.", file=sys.stderr)
        return 1

    print(f"\nAll {len(scenes_to_run)} scene(s) processed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
