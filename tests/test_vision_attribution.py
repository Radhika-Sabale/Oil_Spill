"""Verification test for data attribution pass-through (Stage 5, Step 3).

Verifies that the scene output JSON carries both the scene.source and
scene.license string from data/sar/scenes.json.
"""
from __future__ import annotations

import pytest

from app import scenes as scenes_mod
from app.vision import predict, schema, vectorize


def test_scene_source_and_license_attribution(selftest_scene):
    # Set license on scene record if not present
    sc = scenes_mod.get("gom_mc20_chronic_slick")
    if sc is None or not (sc.sar_path and sc.license):
        pytest.skip("gom_mc20_chronic_slick not found in scenes index")

    pred = predict.predict_scene(sc, prefer_model=False)
    doc = vectorize.to_contract_a(pred, sc, pred["raster"])

    # Must validate schema
    schema.ContractADocument.model_validate(doc)

    scene_meta = doc.get("scene", {})
    assert "source" in scene_meta
    assert scene_meta["source"] == sc.source

    assert "license" in scene_meta, "license was dropped from scene metadata"
    assert scene_meta["license"] == sc.license

