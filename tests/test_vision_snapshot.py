"""Regression snapshot tests for TideTrace M1 vision (Stage 3 Step 4)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.vision.predict import predict_scene
from app.vision.vectorize import to_contract_a


def test_selftest_regression_snapshot(selftest_scene):
    """Synthetic selftest scene regression snapshot check."""
    fixture_path = Path(__file__).resolve().parent / "fixtures" / "selftest_snapshot.json"
    assert fixture_path.exists(), f"Snapshot fixture not found: {fixture_path}"
    snapshot = json.loads(fixture_path.read_text(encoding="utf-8"))

    pred = predict_scene(selftest_scene, prefer_model=False)
    doc = to_contract_a(pred)

    mask = pred["seg"]["mask"]
    mask_sha = hashlib.sha256(mask.tobytes()).hexdigest()
    assert mask_sha == snapshot["mask_sha256"], (
        f"Mask SHA-256 mismatch: {mask_sha} vs expected {snapshot['mask_sha256']}"
    )

    polys = doc["slick"]["polygons"]
    assert len(polys) == snapshot["polygon_count"], (
        f"Polygon count mismatch: {len(polys)} vs expected {snapshot['polygon_count']}"
    )

    coords = []
    for p in polys:
        ring = [[round(float(pt[0]), 6), round(float(pt[1]), 6)] for pt in p["geometry"]["coordinates"][0]]
        coords.append(ring)

    assert coords == snapshot["polygons_coordinates_rounded_6dec"], (
        "Polygon coordinates deviated from regression snapshot"
    )
    assert doc["slick"]["area_km2"] == snapshot["area_km2"]
    assert doc["slick"]["confidence"] == snapshot["confidence"]

