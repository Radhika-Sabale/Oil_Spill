"""Fallback and resilience verification tests for M1 vision adapter (Stage 3 Step 3)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from app import config
from app.geo import raster as raster_mod
from app.ml import infer, model as model_mod
from app.vision.predict import predict_scene
from app.vision.schema import ContractADocument
from app.vision.vectorize import to_contract_a


@pytest.fixture(autouse=True)
def clean_model_cache():
    """Ensure infer model cache is reset before and after every test."""
    infer.reset_model_cache()
    yield
    infer.reset_model_cache()


@pytest.fixture
def test_scene(tmp_path):
    """Small synthetic raster for fast fallback testing."""
    arr = np.random.uniform(0.001, 0.05, (2, 128, 128)).astype(np.float32)
    p = tmp_path / "fallback_test_scene.tif"
    raster_mod.write_geotiff(p, arr, (10.0, 0.0, 500000.0, 0.0, -10.0, 3000000.0), crs="EPSG:32616")
    return p


def test_missing_checkpoint_falls_back(monkeypatch, test_scene, tmp_path):
    """1. Missing checkpoint: method becomes 'baseline', flag 'baseline_used', non-empty reason."""
    missing_pt = tmp_path / "missing_checkpoint.pt"
    monkeypatch.setattr(config, "CHECKPOINT", missing_pt)

    pred = predict_scene(test_scene, prefer_model=True)
    doc = to_contract_a(pred)

    assert doc["slick"]["method"] == "baseline"
    assert "baseline_used" in doc["quality_flags"]
    reason_flag = [f for f in doc["quality_flags"] if f.startswith("fallback_reason:")]
    assert len(reason_flag) == 1
    assert "not found" in reason_flag[0] or "no checkpoint" in reason_flag[0]
    ContractADocument.model_validate(doc)


def test_corrupt_checkpoint_falls_back(monkeypatch, test_scene, tmp_path):
    """2. Corrupt checkpoint: plain garbage file falls back to baseline without crashing."""
    if not model_mod.torch_available():
        pytest.skip("torch not installed; corrupt checkpoint parsing requires torch")

    # SAFETY: Write plain garbage bytes, NOT a pickle payload
    corrupt_pt = tmp_path / "corrupt_garbage.pt"
    corrupt_pt.write_bytes(b"CORRUPT_HEADER_GARBAGE_DATA_1234567890_XYZ")

    monkeypatch.setattr(config, "CHECKPOINT", corrupt_pt)

    pred = predict_scene(test_scene, prefer_model=True)
    doc = to_contract_a(pred)

    assert doc["slick"]["method"] == "baseline"
    assert "baseline_used" in doc["quality_flags"]
    reason_flag = [f for f in doc["quality_flags"] if f.startswith("fallback_reason:")]
    assert len(reason_flag) == 1
    assert len(reason_flag[0]) > len("fallback_reason: ")
    ContractADocument.model_validate(doc)


def test_inference_exception_falls_back(monkeypatch, test_scene):
    """3. Model raises during inference: monkeypatch run_unet to raise, falls back to baseline."""
    if not (model_mod.torch_available() and config.CHECKPOINT.exists()):
        pytest.skip("torch or valid checkpoint not available for inference monkeypatch test")

    def raise_inference_error(*args, **kwargs):
        raise RuntimeError("Simulated matrix dimension or GPU memory failure")

    monkeypatch.setattr(infer, "run_unet", raise_inference_error)

    pred = predict_scene(test_scene, prefer_model=True)
    doc = to_contract_a(pred)

    assert doc["slick"]["method"] == "baseline"
    assert "baseline_used" in doc["quality_flags"]
    reason_flag = [f for f in doc["quality_flags"] if f.startswith("fallback_reason:")]
    assert len(reason_flag) == 1
    assert "Simulated matrix dimension or GPU memory failure" in reason_flag[0]
    ContractADocument.model_validate(doc)

