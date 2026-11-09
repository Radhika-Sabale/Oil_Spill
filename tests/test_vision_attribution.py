"""Verify provenance fields pass through without requiring real SAR data."""
from __future__ import annotations

from dataclasses import replace

import pytest


@pytest.mark.synthetic_data
def test_scene_source_and_license_attribution(selftest_scene):
    """Attribution serialization is a metadata contract, tested on a fixture."""
    from app.vision import predict, schema, vectorize

    source = "fixture source record"
    license_text = "fixture attribution notice"
    scene = replace(selftest_scene, source=source, license=license_text)
    prediction = predict.predict_scene(scene, prefer_model=False)
    document = vectorize.to_contract_a(prediction, scene, prediction["raster"])

    schema.ContractADocument.model_validate(document)
    scene_metadata = document["scene"]
    assert scene_metadata["source"] == source
    assert scene_metadata["license"] == license_text
