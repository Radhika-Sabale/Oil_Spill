"""Robustness and edge-case input tests for M1 vision adapter (Stage 3 Step 2)."""
from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest

from app import config, scenes as scenes_mod
from app.geo import raster as raster_mod, tiffio
from app.vision.predict import predict_scene
from app.vision.schema import ContractADocument
from app.vision.vectorize import to_contract_a


@pytest.fixture
def temp_dir(tmp_path):
    return tmp_path


def test_scattered_nan_pixels(temp_dir):
    """1. Raster with NaN / nodata pixels scattered through it returns valid Contract A."""
    arr = np.random.uniform(0.001, 0.1, (2, 256, 256)).astype(np.float32)
    # Scatter NaNs randomly
    nan_mask = np.random.rand(256, 256) < 0.05
    arr[0, nan_mask] = np.nan
    arr[1, nan_mask] = np.nan

    p = temp_dir / "scattered_nan.tif"
    raster_mod.write_geotiff(p, arr, (10.0, 0.0, 500000.0, 0.0, -10.0, 3000000.0), crs="EPSG:32616")

    res = predict_scene(p, prefer_model=False)
    doc = to_contract_a(res)
    validated = ContractADocument.model_validate(doc)
    assert validated.incident_id == "scattered_nan"


def test_entirely_nan_raster(temp_dir):
    """2. Raster that is entirely NaN returns valid Contract A document."""
    arr = np.full((2, 256, 256), np.nan, dtype=np.float32)
    p = temp_dir / "entirely_nan.tif"
    raster_mod.write_geotiff(p, arr, (10.0, 0.0, 500000.0, 0.0, -10.0, 3000000.0), crs="EPSG:32616")

    res = predict_scene(p, prefer_model=False)
    doc = to_contract_a(res)
    validated = ContractADocument.model_validate(doc)
    assert validated.slick.polygon_count == 0
    assert validated.slick.geometry is None
    assert "no_slick_detected" in validated.quality_flags


def test_single_band_raster(temp_dir):
    """3. Single-band raster (instead of VV and VH) returns valid Contract A."""
    arr = np.random.uniform(0.001, 0.1, (1, 256, 256)).astype(np.float32)
    p = temp_dir / "single_band.tif"
    raster_mod.write_geotiff(p, arr, (10.0, 0.0, 500000.0, 0.0, -10.0, 3000000.0), crs="EPSG:32616")

    res = predict_scene(p, prefer_model=False)
    doc = to_contract_a(res)
    validated = ContractADocument.model_validate(doc)
    assert validated.incident_id == "single_band"


def test_smaller_than_512_tile(temp_dir):
    """4. Raster smaller than one 512 tile (e.g. 128x128) returns valid Contract A."""
    arr = np.random.uniform(0.001, 0.1, (2, 128, 128)).astype(np.float32)
    p = temp_dir / "small_tile.tif"
    raster_mod.write_geotiff(p, arr, (10.0, 0.0, 500000.0, 0.0, -10.0, 3000000.0), crs="EPSG:32616")

    res = predict_scene(p, prefer_model=False)
    doc = to_contract_a(res)
    validated = ContractADocument.model_validate(doc)
    assert validated.incident_id == "small_tile"
    assert validated.mask.shape == [128, 128]


def test_non_square_raster(temp_dir):
    """5. Non-square raster (e.g. 200 x 500) returns valid Contract A."""
    arr = np.random.uniform(0.001, 0.1, (2, 200, 500)).astype(np.float32)
    p = temp_dir / "non_square.tif"
    raster_mod.write_geotiff(p, arr, (10.0, 0.0, 500000.0, 0.0, -10.0, 3000000.0), crs="EPSG:32616")

    res = predict_scene(p, prefer_model=False)
    doc = to_contract_a(res)
    validated = ContractADocument.model_validate(doc)
    assert validated.incident_id == "non_square"
    assert validated.mask.shape == [200, 500]


def test_bright_land_patch_next_to_water(temp_dir):
    """6. Raster with a patch of very bright land next to water returns valid Contract A."""
    arr = np.random.uniform(0.001, 0.02, (2, 256, 256)).astype(np.float32)
    # Bright patch representing land (e.g. sigma0 > 1.0 or ~0 dB)
    arr[:, :100, :] = 2.0
    p = temp_dir / "bright_land.tif"
    raster_mod.write_geotiff(p, arr, (10.0, 0.0, 500000.0, 0.0, -10.0, 3000000.0), crs="EPSG:32616")

    res = predict_scene(p, prefer_model=False)
    doc = to_contract_a(res)
    validated = ContractADocument.model_validate(doc)
    assert validated.incident_id == "bright_land"


def test_no_georeference_clear_failure(temp_dir):
    """7. Raster with no georeference at all: expect clear failure naming missing CRS/transform."""
    arr = np.random.uniform(0.001, 0.1, (1, 128, 128)).astype(np.float32)
    p = temp_dir / "no_georef.tif"

    # Write raw un-georeferenced TIFF
    from PIL import Image
    im = Image.fromarray((arr[0] * 255).astype(np.uint8))
    im.save(p)

    with pytest.raises(raster_mod.GeorefError) as exc_info:
        predict_scene(p, prefer_model=False)

    err_msg = str(exc_info.value).lower()
    assert "no affine transform or crs" in err_msg or "transform" in err_msg
    assert "georeference" in err_msg


def test_missing_scene_file_raises():
    """Predicting a non-existent path or scene id raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        predict_scene("completely_fictional_scene_id_999")


def test_scene_id_string_resolution(selftest_scene):
    """Resolving scene by string id or path works identically to passing Scene object."""
    # Test 1: By string path
    res1 = predict_scene(str(selftest_scene.sar_path), prefer_model=False)
    doc1 = to_contract_a(res1)
    assert doc1["incident_id"] == selftest_scene.id

    # Test 2: By scene id string from real scenes if available
    real_sar = config.SAR_DIR / "arabian_sea_mumbai_offshore.tif"
    if real_sar.exists():
        res2 = predict_scene("arabian_sea_mumbai_offshore", prefer_model=False)
        doc2 = to_contract_a(res2)
        assert doc2["incident_id"] == "arabian_sea_mumbai_offshore"


def test_vectorize_requires_raster():
    """to_contract_a requires raster parameter if not in prediction packet."""
    with pytest.raises(ValueError, match="raster is required"):
        to_contract_a({"seg": {"mask": np.zeros((10, 10))}})


def test_manual_demo_and_synthetic_flags(temp_dir):
    """to_contract_a maps unexpected method strings to manual_demo and flags synthetic scenes."""
    arr = np.zeros((1, 64, 64), dtype=np.float32)
    p = temp_dir / "test_synth.tif"
    raster_mod.write_geotiff(p, arr, (10.0, 0.0, 0.0, 0.0, -10.0, 0.0), crs="EPSG:4326")
    sar = raster_mod.load_sar(p)

    fake_pred = {
        "seg": {
            "mask": np.zeros((64, 64), dtype=np.uint8),
            "oil_prob": np.zeros((64, 64), dtype=np.float32),
            "method": "manual_human_label",
            "model": {},
            "radiometry": {},
            "elapsed_s": 0.1,
            "fallback_reason": None,
        },
        "raster": sar,
    }
    # Pass a Scene with synthetic in source
    synth_scene = scenes_mod.Scene(
        id="manual_test_synth",
        title="Synth Test",
        sar_path=str(p),
        t_sat="2024-01-01T00:00:00Z",
        bounds=(0, 0, 1, 1),
        centroid=(0.5, 0.5),
        crs="EPSG:4326",
        source="synthetic benchmark",
    )
    doc = to_contract_a(fake_pred, scene_record=synth_scene)
    assert doc["slick"]["method"] == "manual_demo"
    assert doc["case_type"] == "synthetic_demo"
