"""Vectorization and Contract A document assembly for TideTrace M1 vision.

Converts raster segmentation outputs into GeoJSON polygons, extracts slick
metrics, and formats the output into the standardised Contract A JSON specification.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .. import config, scenes as scenes_mod
from ..geo import geometry, raster as raster_mod


CONFIDENCE_DEFINITION = (
    "Area-weighted mean of per-polygon confidence scores, where each polygon's "
    "confidence is the mean pixel probability (U-Net mineral oil softmax probability "
    "for model, or sigmoid contrast score for baseline) over its connected component."
)


def _load_checkpoint_sha256() -> Optional[str]:
    sha_file = config.MODELS_DIR / "CHECKPOINT_SHA256.txt"
    if sha_file.exists():
        try:
            val = sha_file.read_text(encoding="utf-8").strip()
            return val if val else None
        except OSError:
            pass
    return None


def _load_reported_metrics() -> Optional[Dict[str, Any]]:
    rep_file = config.MODELS_DIR / "oil_unet_best.report.json"
    if rep_file.exists():
        try:
            data = json.loads(rep_file.read_text(encoding="utf-8"))
            return data.get("best", data)
        except Exception:
            pass
    return None


def to_contract_a(
    prediction: Dict[str, Any],
    scene_record: Optional[scenes_mod.Scene] = None,
    raster: Optional[raster_mod.Raster] = None,
) -> Dict[str, Any]:
    """Convert an intermediate prediction packet into a Contract A document.

    Args:
        prediction: Dict from predict_scene (or dict containing 'seg', 'raster', 'scene_record').
        scene_record: Optional override for the Scene instance.
        raster: Optional override for the Raster instance.

    Returns:
        Contract A document as a Python dictionary.
    """
    scene_record = scene_record or prediction.get("scene_record")
    raster = raster or prediction.get("raster")
    seg = prediction.get("seg") or prediction

    if raster is None:
        raise ValueError("raster is required to georeference slick polygons")

    mask = seg["mask"]
    oil_prob = seg.get("oil_prob")
    radiometry = seg.get("radiometry") or {}
    model_meta = seg.get("model") or {}
    method_raw = seg.get("method", "")
    fallback_reason = seg.get("fallback_reason")

    # 1. Determine method and case_type
    if method_raw == "unet":
        method = "model"
    elif "baseline" in method_raw.lower():
        method = "baseline"
    else:
        method = "manual_demo"

    is_synthetic = False
    if scene_record is not None:
        if getattr(scene_record, "selftest", False):
            is_synthetic = True
        elif "synthetic" in (getattr(scene_record, "source", "") or "").lower():
            is_synthetic = True
        elif "synthetic" in (getattr(scene_record, "id", "") or "").lower():
            is_synthetic = True

    case_type = "synthetic_demo" if is_synthetic else "real_historical"

    # 2. Extract polygons via geometry.polygons_from_mask
    sigma0_slice = raster.array[0] if raster.array.ndim == 3 else raster.array

    # Mineral oil (class 2)
    oil_polygons = geometry.polygons_from_mask(
        class_mask=mask,
        sar=raster,
        klass=2,
        prob=oil_prob,
        sigma0_db=sigma0_slice,
    )

    # Look-alikes (class 1) - kept separate per Contract A rules
    lookalike_polygons = geometry.polygons_from_mask(
        class_mask=mask,
        sar=raster,
        klass=1,
        prob=oil_prob,
        sigma0_db=sigma0_slice,
        prefix="LA",
    )

    # 3. Assemble Slick geometry and metrics
    quality_flags: List[str] = []
    if method == "baseline":
        quality_flags.append("baseline_used")
        if fallback_reason:
            quality_flags.append(f"fallback_reason: {fallback_reason}")

    if radiometry.get("outside_training_range"):
        quality_flags.append("outside_training_range")

    if radiometry.get("clean_water"):
        quality_flags.append("clean_water")

    if oil_polygons:
        polygon_count = len(oil_polygons)
        total_area = sum(p.area_km2 for p in oil_polygons)
        area_km2 = round(float(total_area), 4)

        # MultiPolygon coordinates: list of Polygon coordinates
        multipoly_coords: List[List[List[List[float]]]] = []
        for p in oil_polygons:
            ring = [[float(lon), float(lat)] for lon, lat in p.ring_lonlat]
            multipoly_coords.append([ring])

        slick_geometry: Optional[Dict[str, Any]] = {
            "type": "MultiPolygon",
            "coordinates": multipoly_coords,
        }

        # Area-weighted confidence
        if total_area > 0:
            weighted_conf = sum(p.confidence * p.area_km2 for p in oil_polygons) / total_area
            confidence: Optional[float] = round(float(weighted_conf), 4)
        else:
            confidence = round(float(oil_polygons[0].confidence), 4)

        conf_definition = CONFIDENCE_DEFINITION
    else:
        polygon_count = 0
        slick_geometry = None
        area_km2 = None
        confidence = None
        conf_definition = CONFIDENCE_DEFINITION
        quality_flags.append("no_slick_detected")

    # 4. Model metadata block
    if method == "model":
        chk_sha = _load_checkpoint_sha256()
        reported_m = _load_reported_metrics() or model_meta.get("metrics")
        model_block = {
            "arch": model_meta.get("arch") or "UnetPlusPlus",
            "encoder": model_meta.get("encoder") or "timm-efficientnet-b0",
            "checkpoint_sha256": chk_sha,
            "reported_metrics": reported_m,
            "reported_metrics_note": (
                "measured by the original authors on their own validation tiles, not on this scene"
            ),
        }
    else:
        model_block = {
            "arch": None,
            "encoder": None,
            "checkpoint_sha256": None,
            "reported_metrics": None,
            "reported_metrics_note": None,
        }

    # 5. Mask metadata block
    mask_block = {
        "path": prediction.get("mask_npy_path"),
        "shape": [int(mask.shape[0]), int(mask.shape[1])],
        "dtype": str(mask.dtype),
        "classes": {"0": "sea", "1": "look_alike", "2": "mineral_oil"},
        "georeferenced_tif": prediction.get("mask_tif_path"),
    }

    # 6. Scene metadata block
    w, s, e, n = raster.bounds_lonlat()
    acquired_at = (
        getattr(scene_record, "t_sat", None)
        or (raster.meta.get("datetime") if raster.meta else None)
        or ""
    )
    source_str = getattr(scene_record, "source", "") or ""
    raster_path = (
        getattr(scene_record, "sar_path", "")
        or (str(raster.path) if raster.path else "")
    )

    scene_block = {
        "source": str(source_str),
        "license": getattr(scene_record, "license", None),
        "acquired_at_utc": str(acquired_at),
        "crs": str(raster.crs),
        "raster_path": str(raster_path),
        "bounds_lonlat": [round(float(w), 6), round(float(s), 6), round(float(e), 6), round(float(n), 6)],
    }

    # 7. Assembled Contract A document
    incident_id = str(
        getattr(scene_record, "id", None)
        or (raster.path.stem if raster.path else "unknown_scene")
    )

    doc: Dict[str, Any] = {
        "incident_id": incident_id,
        "case_type": case_type,
        "scene": scene_block,
        "slick": {
            "geometry": slick_geometry,
            "polygon_count": polygon_count,
            "area_km2": area_km2,
            "confidence": confidence,
            "confidence_definition": conf_definition,
            "method": method,
            "polygons": [p.to_feature() for p in oil_polygons],
            "polygons_lookalike": [p.to_feature() for p in lookalike_polygons],
        },
        "mask": mask_block,
        "model": model_block,
        "quality_flags": quality_flags,
        "elapsed_s": round(float(seg.get("elapsed_s", 0.0)), 3),
    }

    return doc

