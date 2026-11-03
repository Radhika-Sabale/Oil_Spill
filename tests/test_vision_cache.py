"""Unit tests for TideTrace M1 vision result cache (Stage 4, Step 6).

Verifies:
1. Cache key sensitivity: changing any input/setting produces a different key.
2. Atomic writes: no half-written or dangling temporary files.
3. Corrupt entry recovery: invalid JSON or missing npy is caught, discarded, and recomputed with flag.
4. Provenance flag correctness: served_from_cache and replayed_from_cache behavior.
5. Byte-identical replay: fresh and replayed results match exactly except for provenance.
"""
from __future__ import annotations

import copy
import json
import shutil
import tempfile
from pathlib import Path

import numpy as np
import pytest

from app import config
from app.geo import raster as raster_mod
from app.vision import cache, schema


@pytest.fixture
def temp_cache_dir(tmp_path):
    cdir = tmp_path / "m1_test_cache"
    cdir.mkdir(parents=True, exist_ok=True)
    yield cdir
    shutil.rmtree(cdir, ignore_errors=True)


def test_cache_key_sensitivity(selftest_scene, tmp_path):
    sar_path = Path(selftest_scene.sar_path)
    base_key = cache.compute_cache_key(
        sar_path=sar_path,
        checkpoint_sha256="test_chk_123",
        tile=512,
        tile_overlap=64,
        radiometric_align=False,
        baseline_threshold_db=-22.0,
        baseline_relative_only=True,
        adapter_version="1.0.0",
    )

    # 1. Changing checkpoint SHA-256
    key_diff_chk = cache.compute_cache_key(
        sar_path=sar_path,
        checkpoint_sha256="test_chk_999",
        tile=512,
        tile_overlap=64,
        radiometric_align=False,
        baseline_threshold_db=-22.0,
        baseline_relative_only=True,
        adapter_version="1.0.0",
    )
    assert base_key != key_diff_chk

    # 2. Changing tile
    key_diff_tile = cache.compute_cache_key(
        sar_path=sar_path,
        checkpoint_sha256="test_chk_123",
        tile=256,
        tile_overlap=64,
        radiometric_align=False,
        baseline_threshold_db=-22.0,
        baseline_relative_only=True,
        adapter_version="1.0.0",
    )
    assert base_key != key_diff_tile

    # 3. Changing tile overlap
    key_diff_ov = cache.compute_cache_key(
        sar_path=sar_path,
        checkpoint_sha256="test_chk_123",
        tile=512,
        tile_overlap=32,
        radiometric_align=False,
        baseline_threshold_db=-22.0,
        baseline_relative_only=True,
        adapter_version="1.0.0",
    )
    assert base_key != key_diff_ov

    # 4. Changing radiometric alignment flag
    key_diff_align = cache.compute_cache_key(
        sar_path=sar_path,
        checkpoint_sha256="test_chk_123",
        tile=512,
        tile_overlap=64,
        radiometric_align=True,
        baseline_threshold_db=-22.0,
        baseline_relative_only=True,
        adapter_version="1.0.0",
    )
    assert base_key != key_diff_align

    # 5. Changing baseline threshold settings
    key_diff_thresh = cache.compute_cache_key(
        sar_path=sar_path,
        checkpoint_sha256="test_chk_123",
        tile=512,
        tile_overlap=64,
        radiometric_align=False,
        baseline_threshold_db=-20.0,
        baseline_relative_only=True,
        adapter_version="1.0.0",
    )
    assert base_key != key_diff_thresh

    key_diff_rel = cache.compute_cache_key(
        sar_path=sar_path,
        checkpoint_sha256="test_chk_123",
        tile=512,
        tile_overlap=64,
        radiometric_align=False,
        baseline_threshold_db=-22.0,
        baseline_relative_only=False,
        adapter_version="1.0.0",
    )
    assert base_key != key_diff_rel

    # 6. Changing ADAPTER_VERSION
    key_diff_ver = cache.compute_cache_key(
        sar_path=sar_path,
        checkpoint_sha256="test_chk_123",
        tile=512,
        tile_overlap=64,
        radiometric_align=False,
        baseline_threshold_db=-22.0,
        baseline_relative_only=True,
        adapter_version="1.0.1",
    )
    assert base_key != key_diff_ver

    # 7. Changing SAR file bytes
    alt_sar = tmp_path / "alt_sar.tif"
    alt_sar.write_bytes(sar_path.read_bytes() + b"\x00\x00")
    key_diff_bytes = cache.compute_cache_key(
        sar_path=alt_sar,
        checkpoint_sha256="test_chk_123",
        tile=512,
        tile_overlap=64,
        radiometric_align=False,
        baseline_threshold_db=-22.0,
        baseline_relative_only=True,
        adapter_version="1.0.0",
    )
    assert base_key != key_diff_bytes


def test_atomic_write_and_no_half_files(selftest_scene, temp_cache_dir):
    doc = cache.get_detection(
        scene=selftest_scene,
        use_cache=True,
        force=True,
        cache_dir=temp_cache_dir,
    )
    assert doc is not None

    # Verify no dangling temporary files
    tmp_files = list(temp_cache_dir.glob("tmp_*"))
    assert len(tmp_files) == 0, f"Found dangling temporary files: {tmp_files}"

    # Verify both json and npy exist
    js_files = list(temp_cache_dir.glob("*.json"))
    npy_files = list(temp_cache_dir.glob("*.npy"))
    assert len(js_files) == 1
    assert len(npy_files) == 1


def test_corrupt_entry_recovery(selftest_scene, temp_cache_dir):
    # Prime cache first
    _ = cache.get_detection(
        scene=selftest_scene,
        use_cache=True,
        force=True,
        cache_dir=temp_cache_dir,
    )

    # Corrupt the JSON file with unparseable garbage
    js_files = list(temp_cache_dir.glob("*.json"))
    assert len(js_files) == 1
    js_files[0].write_text("CORRUPTED_JSON_NOT_VALID_SYNTAX", encoding="utf-8")

    # Call get_detection: must safely ignore corruption, recompute, and set flag
    recovered_doc = cache.get_detection(
        scene=selftest_scene,
        use_cache=True,
        force=False,
        cache_dir=temp_cache_dir,
    )

    prov = recovered_doc.get("provenance") or {}
    assert prov.get("served_from_cache") is False
    assert "corrupt_cache_ignored" in recovered_doc.get("quality_flags", [])

    # Next call without corruption should serve from cache cleanly
    cached_doc = cache.get_detection(
        scene=selftest_scene,
        use_cache=True,
        force=False,
        cache_dir=temp_cache_dir,
    )
    assert cached_doc["provenance"]["served_from_cache"] is True
    assert "replayed_from_cache" in cached_doc["quality_flags"]


def test_provenance_flag_correctness(selftest_scene, temp_cache_dir):
    # Cold computation
    cold_doc = cache.get_detection(
        scene=selftest_scene,
        use_cache=True,
        force=True,
        cache_dir=temp_cache_dir,
    )
    assert cold_doc["provenance"]["served_from_cache"] is False
    assert "replayed_from_cache" not in cold_doc["quality_flags"]
    assert cold_doc["provenance"]["cache_key"] is not None

    # Warm replay
    warm_doc = cache.get_detection(
        scene=selftest_scene,
        use_cache=True,
        force=False,
        cache_dir=temp_cache_dir,
    )
    assert warm_doc["provenance"]["served_from_cache"] is True
    assert "replayed_from_cache" in warm_doc["quality_flags"]


def test_byte_identical_replay(selftest_scene, temp_cache_dir):
    # Fresh compute
    fresh = cache.get_detection(
        scene=selftest_scene,
        use_cache=True,
        force=True,
        cache_dir=temp_cache_dir,
    )

    # Replayed from cache
    replayed = cache.get_detection(
        scene=selftest_scene,
        use_cache=True,
        force=False,
        cache_dir=temp_cache_dir,
    )

    # Validate both pass Pydantic schema
    schema.ContractADocument.model_validate(fresh)
    schema.ContractADocument.model_validate(replayed)

    # Normalize documents by removing provenance and cache quality flags
    doc_a = copy.deepcopy(fresh)
    doc_b = copy.deepcopy(replayed)

    doc_a.pop("provenance", None)
    doc_b.pop("provenance", None)

    doc_a["quality_flags"] = [f for f in doc_a.get("quality_flags", []) if f != "replayed_from_cache"]
    doc_b["quality_flags"] = [f for f in doc_b.get("quality_flags", []) if f != "replayed_from_cache"]

    str_a = json.dumps(doc_a, indent=2, sort_keys=True)
    str_b = json.dumps(doc_b, indent=2, sort_keys=True)

    assert str_a == str_b, "Replayed document differs from fresh document"

    # Compare mask arrays
    arr_a = np.load(fresh["mask"]["path"])
    arr_b = np.load(replayed["mask"]["path"])
    np.testing.assert_array_equal(arr_a, arr_b)

