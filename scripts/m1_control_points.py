"""Generate ground-truth control points for M2 verification in QGIS / rasterio.

Writes data/m1_out/<scene>.control_points.csv with columns:
row,col,lon,lat,source
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

# Ensure repo root is on sys.path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rasterio.transform import Affine
from pyproj import Transformer

from app import config, scenes as scenes_mod
from app.geo import raster as raster_mod


def generate_control_points_for_scene(
    scene_or_id: scenes_mod.Scene | str,
    out_dir: Path,
) -> Path:
    """Generate control points CSV for a single scene."""
    if hasattr(scene_or_id, "sar_path") and hasattr(scene_or_id, "id"):
        scene = scene_or_id
        sar_p = Path(scene.sar_path)
        if not sar_p.exists() and (config.SAR_DIR / sar_p.name).exists():
            sar_p = config.SAR_DIR / sar_p.name
        incident_id = scene.id
    else:
        sc = scenes_mod.get(str(scene_or_id))
        if sc is not None:
            scene = sc
            sar_p = Path(scene.sar_path)
            if not sar_p.exists() and (config.SAR_DIR / sar_p.name).exists():
                sar_p = config.SAR_DIR / sar_p.name
            incident_id = scene.id
        else:
            sar_p = Path(str(scene_or_id))
            incident_id = sar_p.stem

    if not sar_p.exists():
        raise FileNotFoundError(f"SAR raster not found: {sar_p}")

    raster = raster_mod.load_sar(sar_p)
    w = raster.width
    h = raster.height

    points = []

    # 1. Four corners
    corners = [
        ("top_left", 0.0, 0.0),
        ("top_right", 0.0, float(w - 1)),
        ("bottom_left", float(h - 1), 0.0),
        ("bottom_right", float(h - 1), float(w - 1)),
    ]
    for _name, r, c in corners:
        lon, lat = raster.lonlat(c, r)
        points.append((round(r, 4), round(c, 4), round(float(lon), 6), round(float(lat), 6), "affine"))

    # 2. Centre
    cr, cc = float(h - 1) / 2.0, float(w - 1) / 2.0
    lon, lat = raster.lonlat(cc, cr)
    points.append((round(cr, 4), round(cc, 4), round(float(lon), 6), round(float(lat), 6), "affine"))

    # 3. Centroid of the largest polygon (from Contract A JSON if present)
    json_path = out_dir / f"{incident_id}.slick_detection.json"
    if json_path.exists():
        try:
            doc = json.loads(json_path.read_text(encoding="utf-8"))
            polys = doc.get("slick", {}).get("polygons", [])
            if polys:
                # Find polygon with largest area
                largest = max(polys, key=lambda p: p.get("properties", {}).get("area_km2", 0.0) or 0.0)
                props = largest.get("properties", {})
                clon = props.get("centroid_lon")
                clat = props.get("centroid_lat")
                if clon is not None and clat is not None:
                    # Invert affine to find pixel row, col
                    tr = Transformer.from_crs("EPSG:4326", raster.crs, always_xy=True)
                    x, y = tr.transform(clon, clat)
                    inv = ~Affine(*raster.transform)
                    c_recomp, r_recomp = inv * (x, y)
                    r_pix = float(r_recomp - 0.5)
                    c_pix = float(c_recomp - 0.5)
                    points.append((round(r_pix, 4), round(c_pix, 4), round(float(clon), 6), round(float(clat), 6), "affine"))
        except Exception as exc:
            print(f"Warning: could not extract largest polygon centroid from {json_path}: {exc}", file=sys.stderr)

    # Write CSV
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"{incident_id}.control_points.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["row", "col", "lon", "lat", "source"])
        for row, col, lon, lat, src in points:
            writer.writerow([row, col, lon, lat, src])

    return csv_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate control points for M2 verification.")
    parser.add_argument("--scene", help="Scene ID to process")
    parser.add_argument("--all", action="store_true", help="Process every available scene")
    parser.add_argument("--out", default="data/m1_out", help="Output directory (default: data/m1_out)")
    args = parser.parse_args()

    if not args.scene and not args.all:
        parser.error("Either --scene <id> or --all must be specified.")

    out_dir = Path(args.out).resolve()

    scenes_to_run = []
    if args.all:
        for s in scenes_mod.all_scenes():
            sar_p = Path(s.sar_path)
            if sar_p.exists() or (config.SAR_DIR / sar_p.name).exists():
                scenes_to_run.append(s)
    else:
        sc = scenes_mod.get(args.scene)
        scenes_to_run.append(sc if sc is not None else args.scene)

    for s in scenes_to_run:
        csv_p = generate_control_points_for_scene(s, out_dir=out_dir)
        print(f"Wrote control points to {csv_p}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

