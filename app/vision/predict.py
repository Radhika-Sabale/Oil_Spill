"""Prediction adapter for TideTrace M1 vision.

Loads a SAR chip, runs single-pass segmentation (U-Net or baseline), exports the
georeferenced raster mask files, and returns the intermediate prediction packet.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Union

import numpy as np

from .. import config, scenes as scenes_mod
from ..geo import raster as raster_mod
from ..ml import infer


def predict_scene(
    scene_id_or_path: Union[str, Path, scenes_mod.Scene],
    out_dir: Optional[Union[str, Path]] = None,
    prefer_model: bool = True,
    threshold_db: Optional[float] = None,
    exclude: Optional[np.ndarray] = None,
) -> Dict[str, Any]:
    """Execute single-pass segmentation for a SAR scene.

    Args:
        scene_id_or_path: Scene instance, scene ID string, or path to GeoTIFF.
        out_dir: Optional directory where .npy and .tif mask files are saved.
        prefer_model: True to use U-Net checkpoint, False for threshold baseline.
        threshold_db: Optional threshold override for baseline detector.
        exclude: Optional boolean mask (e.g. land mask) to exclude from detection.

    Returns:
        Intermediate prediction dict containing scene_record, raster, seg,
        mask_npy_path, and mask_tif_path.
    """
    # 1. Resolve scene record and load georeferenced SAR raster
    if hasattr(scene_id_or_path, "sar_path") and hasattr(scene_id_or_path, "id"):
        scene_record = scene_id_or_path
        p = Path(scene_record.sar_path)
        if not p.exists():
            if (config.SAR_DIR / p.name).exists():
                p = config.SAR_DIR / p.name
            elif (config.DATA_DIR / p.name).exists():
                p = config.DATA_DIR / p.name
        raster = raster_mod.load_sar(p)
    else:
        scene_str = str(scene_id_or_path)
        scene_record = scenes_mod.get(scene_str)
        if scene_record is not None:
            p = Path(scene_record.sar_path)
            if not p.exists():
                if (config.SAR_DIR / p.name).exists():
                    p = config.SAR_DIR / p.name
                elif (config.DATA_DIR / p.name).exists():
                    p = config.DATA_DIR / p.name
            if p.exists():
                raster = raster_mod.load_sar(p)
            else:
                scene_record = None

        if scene_record is None:
            p = Path(scene_str)
            candidates = [p]
            if not p.suffix:
                candidates.extend([p.with_suffix(".tif"), p.with_suffix(".tiff")])

            found_path = None
            for cand in candidates:
                if cand.is_absolute() and cand.exists():
                    found_path = cand
                    break
                for base in (config.SAR_DIR, config.DATA_DIR, config.ROOT_DIR):
                    if (base / cand.name).exists():
                        found_path = base / cand.name
                        break
                    elif (base / cand).exists():
                        found_path = base / cand
                        break
                if found_path is not None:
                    break

            if found_path is None or not found_path.exists():
                raise FileNotFoundError(f"Scene or raster file not found: {scene_id_or_path}")

            p = found_path
            raster = raster_mod.load_sar(p)
            scene_record = scenes_mod.describe_geotiff(p, scene_id=p.stem)

    # 2. Convert to dB and call segment_scene (once only)
    sigma0_db = raster_mod.to_db(raster.array)
    seg = infer.segment_scene(
        sigma0_db,
        prefer_model=prefer_model,
        threshold_db=threshold_db,
        exclude=exclude,
    )

    # 3. Export mask files if out_dir specified
    mask_npy_path: Optional[str] = None
    mask_tif_path: Optional[str] = None
    if out_dir is not None:
        out_p = Path(out_dir).resolve()
        out_p.mkdir(parents=True, exist_ok=True)

        npy_dest = out_p / f"{scene_record.id}_mask.npy"
        np.save(npy_dest, seg["mask"])
        mask_npy_path = str(npy_dest)

        tif_dest = out_p / f"{scene_record.id}_mask.tif"
        raster_mod.write_geotiff(
            tif_dest,
            seg["mask"],
            raster.transform,
            crs=raster.crs,
        )
        mask_tif_path = str(tif_dest)

    return {
        "scene_record": scene_record,
        "raster": raster,
        "seg": seg,
        "mask_npy_path": mask_npy_path,
        "mask_tif_path": mask_tif_path,
    }
