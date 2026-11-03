"""Tests for Contract A adapter (M1 vision output).

Verifies the Contract A specification, schema conformance, coordinate ordering,
mask geometry, baseline fallback, empty water handling, and determinism.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pytest

from app import config, scenes as scenes_mod
from app.geo import raster as raster_mod
from app.vision.predict import predict_scene
from app.vision.schema import ContractADocument
from app.vision.vectorize import to_contract_a

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def clean_water_scene(tmp_path):
    """Synthetic uniform-water scene with zero slicks."""
    h, w = 256, 256
    arr = np.full((2, h, w), -18.0, dtype=np.float32)
    # Affine transform for Arabian Sea region: lon ~ 71.5, lat ~ 19.0
    # transform: (a, b, c, d, e, f)
    # col: dx=0.0002 deg, row: dy=-0.0002 deg
    transform = (0.0002, 0.0, 71.5, 0.0, -0.0002, 19.0)
    sar_path = Path(tmp_path) / "clean_water.tif"
    raster_mod.write_geotiff(sar_path, arr, transform, crs="EPSG:4326")

    scene = scenes_mod.describe_geotiff(
        sar_path,
        scene_id="clean_water_test",
        title="Clean water uniform test",
        t_sat="2024-03-13T00:00:00Z",
        source="synthetic",
        selftest=True,
    )
    return scene


@pytest.fixture
def prepared_checkpoint():
    """Ensure the shipped checkpoint is accessible inside the test sandbox."""
    real_chk = ROOT / "models" / "oil_unet_best.pt"
    if not real_chk.exists():
        pytest.skip("models/oil_unet_best.pt not found on disk")

    dest_dir = Path(config.MODELS_DIR).resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_chk = dest_dir / "oil_unet_best.pt"
    if real_chk.resolve() != dest_chk.resolve() and not dest_chk.exists():
        shutil.copy2(real_chk, dest_chk)

    # Also copy SHA and report files if they exist
    for name in ("CHECKPOINT_SHA256.txt", "oil_unet_best.report.json"):
        src = (ROOT / "models" / name).resolve()
        dst = (dest_dir / name).resolve()
        if src.exists() and src != dst and not dst.exists():
            shutil.copy2(src, dst)

    from app.ml import infer
    infer.reset_model_cache()
    return dest_chk


# ---------------------------------------------------------------------------
# Test 1: Pydantic v2 schema validation
# ---------------------------------------------------------------------------

def test_contract_a_schema_validation(selftest_scene, tmp_path):
    pred = predict_scene(selftest_scene, out_dir=tmp_path, prefer_model=False)
    doc = to_contract_a(pred)

    validated = ContractADocument.model_validate(doc)
    assert validated.incident_id == selftest_scene.id
    assert validated.case_type == "synthetic_demo"
    assert validated.scene.bounds_lonlat == doc["scene"]["bounds_lonlat"]
    assert validated.slick.method in ("model", "baseline")


# ---------------------------------------------------------------------------
# Test 2: Mask properties
# ---------------------------------------------------------------------------

def test_mask_properties(selftest_scene, tmp_path):
    pred = predict_scene(selftest_scene, out_dir=tmp_path, prefer_model=False)
    doc = to_contract_a(pred)

    raster = pred["raster"]
    mask = pred["seg"]["mask"]

    assert doc["mask"]["shape"] == [raster.height, raster.width]
    assert doc["mask"]["dtype"] == "uint8"
    assert mask.shape == (raster.height, raster.width)
    assert mask.dtype == np.uint8

    unique_vals = set(np.unique(mask).tolist())
    assert unique_vals.issubset({0, 1, 2})

    # Verify saved files
    npy_path = Path(doc["mask"]["path"])
    assert npy_path.exists()
    loaded_npy = np.load(npy_path)
    assert np.array_equal(loaded_npy, mask)

    tif_path = Path(doc["mask"]["georeferenced_tif"])
    assert tif_path.exists()


# ---------------------------------------------------------------------------
# Test 3: Every polygon vertex lies within bounds_lonlat
# ---------------------------------------------------------------------------

def test_polygon_vertices_within_bounds(selftest_scene):
    pred = predict_scene(selftest_scene, prefer_model=False)
    doc = to_contract_a(pred)

    west, south, east, north = doc["scene"]["bounds_lonlat"]
    tol = 0.005  # half pixel margin

    polys = doc["slick"]["polygons"]
    assert len(polys) > 0, "selftest_scene should produce at least one polygon"

    for feature in polys:
        coords = feature["geometry"]["coordinates"]
        for ring in coords:
            for pt in ring:
                lon, lat = pt[0], pt[1]
                assert west - tol <= lon <= east + tol, f"lon {lon} outside bounds [{west}, {east}]"
                assert south - tol <= lat <= north + tol, f"lat {lat} outside bounds [{south}, {north}]"


# ---------------------------------------------------------------------------
# Test 4: Coordinate order is [lon, lat]
# ---------------------------------------------------------------------------

def test_coordinates_lon_lat_order(selftest_scene):
    """Ensure coordinates are [lon, lat] and not inverted."""
    pred = predict_scene(selftest_scene, prefer_model=False)
    doc = to_contract_a(pred)

    west, south, east, north = doc["scene"]["bounds_lonlat"]
    # For selftest_scene, longitude is ~71.6 and latitude is ~19.0 (strictly disjoint)
    assert abs(west - south) > 20.0, "Longitude and latitude ranges must not overlap for this check"

    polys = doc["slick"]["polygons"]
    assert len(polys) > 0

    first_pt = polys[0]["geometry"]["coordinates"][0][0]
    x, y = first_pt[0], first_pt[1]

    # x must be longitude, y must be latitude
    assert west <= x <= east, f"Coordinate x ({x}) is outside longitude bounds [{west}, {east}]"
    assert south <= y <= north, f"Coordinate y ({y}) is outside latitude bounds [{south}, {north}]"
    assert not (south <= x <= north), f"Coordinate x ({x}) appears to be latitude!"


# ---------------------------------------------------------------------------
# Test 5: Baseline path forced
# ---------------------------------------------------------------------------

def test_baseline_path_fallback(selftest_scene):
    pred = predict_scene(selftest_scene, prefer_model=False)
    doc = to_contract_a(pred)

    assert doc["slick"]["method"] == "baseline"
    assert "baseline_used" in doc["quality_flags"]
    assert any("fallback_reason" in f for f in doc["quality_flags"])
    # In baseline mode, model architecture fields must be null (not invented)
    assert doc["model"]["arch"] is None
    assert doc["model"]["checkpoint_sha256"] is None


# ---------------------------------------------------------------------------
# Test 6: Empty result on uniform water
# ---------------------------------------------------------------------------

def test_empty_result_uniform_water(clean_water_scene):
    pred = predict_scene(clean_water_scene, prefer_model=False)
    doc = to_contract_a(pred)

    assert doc["slick"]["polygon_count"] == 0
    assert doc["slick"]["geometry"] is None
    assert doc["slick"]["area_km2"] is None
    assert doc["slick"]["confidence"] is None
    assert "no_slick_detected" in doc["quality_flags"]
    assert "clean_water" in doc["quality_flags"]
    assert doc["slick"]["polygons"] == []


# ---------------------------------------------------------------------------
# Test 7: Determinism
# ---------------------------------------------------------------------------

def test_determinism(selftest_scene, tmp_path):
    pred1 = predict_scene(selftest_scene, out_dir=tmp_path / "run1", prefer_model=False)
    doc1 = to_contract_a(pred1)

    pred2 = predict_scene(selftest_scene, out_dir=tmp_path / "run2", prefer_model=False)
    doc2 = to_contract_a(pred2)

    assert doc1["slick"]["polygon_count"] == doc2["slick"]["polygon_count"]
    assert doc1["slick"]["area_km2"] == doc2["slick"]["area_km2"]
    assert doc1["slick"]["geometry"] == doc2["slick"]["geometry"]
    assert np.array_equal(pred1["seg"]["mask"], pred2["seg"]["mask"])


# ---------------------------------------------------------------------------
# Test 8: No invented numbers (null when uncomputable)
# ---------------------------------------------------------------------------

def test_no_invented_numbers(clean_water_scene):
    pred = predict_scene(clean_water_scene, prefer_model=False)
    doc = to_contract_a(pred)

    # When no slick is detected, confidence and area must be null, never 0.0
    assert doc["slick"]["confidence"] is None
    assert doc["slick"]["confidence"] is not 0.0
    assert doc["slick"]["area_km2"] is None
    assert doc["slick"]["area_km2"] is not 0.0


# ---------------------------------------------------------------------------
# Test 9: U-Net model path execution (with checkpoint)
# ---------------------------------------------------------------------------

def test_model_path_execution(selftest_scene, prepared_checkpoint):
    from app.ml import model as model_mod

    if not (model_mod.torch_available() and model_mod.smp_available()):
        pytest.skip("torch or segmentation_models_pytorch not installed")

    pred = predict_scene(selftest_scene, prefer_model=True)
    doc = to_contract_a(pred)

    assert doc["slick"]["method"] == "model"
    assert doc["model"]["arch"] == "UnetPlusPlus"
    assert doc["model"]["encoder"] == "timm-efficientnet-b0"

    sha_path = ROOT / "models" / "CHECKPOINT_SHA256.txt"
    if sha_path.exists():
        expected_sha = sha_path.read_text(encoding="utf-8").strip()
        assert doc["model"]["checkpoint_sha256"] == expected_sha
