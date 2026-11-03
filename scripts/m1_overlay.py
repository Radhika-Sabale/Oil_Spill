"""Generate human review overlay images and model vs baseline comparison (Stage 3 Step 5).

Outputs:
    data/m1_out/review/<scene>_overlay.png
    data/m1_out/review/<scene>_comparison.png (when both model & baseline run)
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

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from pyproj import Transformer
from rasterio.transform import Affine

from app import config, scenes as scenes_mod
from app.geo import raster as raster_mod
from app.vision.predict import predict_scene
from app.vision.vectorize import to_contract_a


def lonlat_to_pixel(lon: float, lat: float, raster: raster_mod.Raster) -> tuple[float, float]:
    """Convert lon/lat to image pixel (col, row)."""
    if raster.crs and not raster.crs.upper().endswith("4326"):
        tr = Transformer.from_crs("EPSG:4326", raster.crs, always_xy=True)
        x, y = tr.transform(lon, lat)
    else:
        x, y = lon, lat

    inv = ~Affine(*raster.transform)
    c, r = inv * (x, y)
    return float(c - 0.5), float(r - 0.5)


def draw_overlay_on_raster(
    raster: raster_mod.Raster,
    doc: dict,
    caption_title: str = "",
) -> Image.Image:
    """Render 8-bit stretched SAR raster with outlined polygons and text banner."""
    raw_arr = raster.array[0] if raster.array.ndim == 3 else raster.array
    u8_arr = raster_mod.stretch_to_uint8(raw_arr)
    base_img = Image.fromarray(u8_arr).convert("RGB")

    draw = ImageDraw.Draw(base_img)

    # 1. Draw look-alike polygons (amber/yellow: (255, 190, 0))
    for f in doc.get("slick", {}).get("polygons_lookalike", []):
        coords = f.get("geometry", {}).get("coordinates", [])
        if coords:
            for ring in coords:
                px_ring = [lonlat_to_pixel(pt[0], pt[1], raster) for pt in ring]
                if len(px_ring) >= 2:
                    draw.line(px_ring, fill=(255, 190, 0), width=2)

    # 2. Draw mineral oil polygons (bright red: (255, 40, 40))
    for f in doc.get("slick", {}).get("polygons", []):
        coords = f.get("geometry", {}).get("coordinates", [])
        if coords:
            for ring in coords:
                px_ring = [lonlat_to_pixel(pt[0], pt[1], raster) for pt in ring]
                if len(px_ring) >= 2:
                    draw.line(px_ring, fill=(255, 40, 40), width=2)

    # 3. Add top caption banner
    banner_h = 32
    w, h = base_img.size
    final_img = Image.new("RGB", (w, h + banner_h), color=(20, 24, 30))
    final_img.paste(base_img, (0, banner_h))

    banner_draw = ImageDraw.Draw(final_img)
    incident_id = doc.get("incident_id", "")
    method = doc.get("slick", {}).get("method", "")
    poly_count = doc.get("slick", {}).get("polygon_count", 0)
    area = doc.get("slick", {}).get("area_km2")
    conf = doc.get("slick", {}).get("confidence")

    title_part = f"[{caption_title}] " if caption_title else ""
    caption = (
        f"{title_part}{incident_id} | method: {method} | "
        f"polygons: {poly_count} | area: {area} km2 | conf: {conf}"
    )

    banner_draw.text((10, 8), caption, fill=(240, 240, 240))
    return final_img


def process_scene_overlays(
    scene_or_id: scenes_mod.Scene | str,
    out_dir: Path,
) -> dict:
    """Generate both standalone overlay and model-vs-baseline comparison for one scene."""
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

    review_dir = out_dir / "review"
    review_dir.mkdir(parents=True, exist_ok=True)

    # 1. Run model prediction (or load existing Contract A JSON)
    pred_model = predict_scene(sar_p, prefer_model=True)
    doc_model = to_contract_a(pred_model)
    raster = pred_model["raster"]

    # Standalone overlay
    overlay_img = draw_overlay_on_raster(raster, doc_model)
    overlay_path = review_dir / f"{incident_id}_overlay.png"
    overlay_img.save(overlay_path)

    # 2. Run baseline prediction for comparison
    pred_base = predict_scene(sar_p, prefer_model=False)
    doc_base = to_contract_a(pred_base)

    mask_m = pred_model["seg"]["mask"]
    mask_b = pred_base["seg"]["mask"]

    # Calculate agreement IoU between model and baseline oil masks (class 2)
    oil_m = (mask_m == 2)
    oil_b = (mask_b == 2)
    intersection = int((oil_m & oil_b).sum())
    union = int((oil_m | oil_b).sum())
    if union > 0:
        agreement_iou = round(float(intersection / union), 4)
    else:
        # Both predict no oil
        agreement_iou = 1.0 if not oil_m.any() and not oil_b.any() else 0.0

    # Side-by-side comparison image
    left_im = draw_overlay_on_raster(raster, doc_model, caption_title="MODEL")
    right_im = draw_overlay_on_raster(raster, doc_base, caption_title="BASELINE")

    w1, h1 = left_im.size
    w2, h2 = right_im.size
    banner_top = 36
    comp_img = Image.new("RGB", (w1 + w2, max(h1, h2) + banner_top), color=(15, 18, 24))
    comp_img.paste(left_im, (0, banner_top))
    comp_img.paste(right_im, (w1, banner_top))

    draw_comp = ImageDraw.Draw(comp_img)
    comp_caption = (
        f"{incident_id} | Side-by-Side: Model (left) vs Baseline (right) | "
        f"Oil Mask Agreement (IoU): {agreement_iou:.4f} ({agreement_iou * 100:.1f}%)"
    )
    draw_comp.text((15, 10), comp_caption, fill=(255, 255, 255))

    comp_path = review_dir / f"{incident_id}_comparison.png"
    comp_img.save(comp_path)

    return {
        "incident_id": incident_id,
        "overlay_path": str(overlay_path),
        "comparison_path": str(comp_path),
        "agreement_iou": agreement_iou,
        "model_polygons": doc_model["slick"]["polygon_count"],
        "baseline_polygons": doc_base["slick"]["polygon_count"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate human review overlays and comparison images.")
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

    print(f"Generating review overlays for {len(scenes_to_run)} scene(s)...\n")

    for s in scenes_to_run:
        res = process_scene_overlays(s, out_dir=out_dir)
        print(
            f"[{res['incident_id']}] "
            f"Model polys: {res['model_polygons']} | "
            f"Baseline polys: {res['baseline_polygons']} | "
            f"Oil mask agreement (IoU): {res['agreement_iou']:.4f}\n"
            f"  Overlay:    {res['overlay_path']}\n"
            f"  Comparison: {res['comparison_path']}"
        )

    print("\nReview overlays completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

