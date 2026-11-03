"""Unit tests for TideTrace M1 vision status function (Stage 4, Step 6).

Verifies:
1. vision_status() return structure and completeness.
2. vision_status() works cleanly without raising when PyTorch is not available.
3. Accurate reporting of cached scenes.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app import config
from app.vision import ADAPTER_VERSION, cache, status


def test_vision_status_keys():
    st = status.vision_status()
    assert isinstance(st, dict)

    expected_keys = {
        "model_loaded",
        "method_available",
        "checkpoint_present",
        "checkpoint_sha256",
        "torch_available",
        "device",
        "cache_dir",
        "cached_scenes",
        "adapter_version",
        "last_error",
    }
    assert expected_keys.issubset(st.keys()), f"Missing keys in vision_status(): {expected_keys - set(st.keys())}"
    assert st["adapter_version"] == ADAPTER_VERSION
    assert isinstance(st["model_loaded"], bool)
    assert st["method_available"] in ("unet", "baseline")
    assert isinstance(st["checkpoint_present"], bool)
    assert isinstance(st["torch_available"], bool)
    assert isinstance(st["cached_scenes"], list)


def test_vision_status_when_torch_unavailable(monkeypatch):
    """vision_status must function cleanly without raising if torch is unavailable."""
    # Monkeypatch torch_available in status module
    monkeypatch.setattr(status.model_mod, "torch_available", lambda: False)

    st = status.vision_status()
    assert st["torch_available"] is False
    assert st["method_available"] == "baseline"
    assert st["device"] == "cpu"
    assert isinstance(st["cached_scenes"], list)


def test_vision_status_tracks_cached_scenes(selftest_scene, tmp_path, monkeypatch):
    test_c_dir = tmp_path / "m1_status_cache"
    test_c_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(cache, "CACHE_DIR", test_c_dir)

    # Empty cache initially
    st1 = status.vision_status()
    assert len(st1["cached_scenes"]) == 0

    # Cache one scene
    _ = cache.get_detection(
        scene=selftest_scene,
        use_cache=True,
        force=True,
        cache_dir=test_c_dir,
    )

    st2 = status.vision_status()
    assert selftest_scene.id in st2["cached_scenes"]
