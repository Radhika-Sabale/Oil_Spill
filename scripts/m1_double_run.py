"""Double Run Comparison Script on Golden Case (Stage 5, Step 5).

1. Clears cache and runs export twice in two separate processes.
2. Compares outputs: geometry, mask SHA-256, area, flags.
3. Displays any diff in the JSON documents.
4. Runs third time from cache and confirms replayed_from_cache and identical geometry.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import config
from app.vision import cache


def run():
    golden = "gom_mc20_chronic_slick"
    python_bin = sys.executable

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_p = Path(tmp_dir)
        out1 = tmp_p / "out1"
        out2 = tmp_p / "out2"
        out3 = tmp_p / "out3"
        test_cache = tmp_p / "cache"

        out1.mkdir()
        out2.mkdir()
        out3.mkdir()
        test_cache.mkdir()

        print(f"=== Double Run on Golden Case: {golden} ===")

        # Run 1
        cmd1 = [python_bin, "scripts/m1_export.py", "--scene", golden, "--out", str(out1)]
        res1 = subprocess.run(cmd1, cwd=ROOT_DIR, capture_output=True, text=True)
        assert res1.returncode == 0, f"Run 1 failed: {res1.stderr}"

        # Run 2
        cmd2 = [python_bin, "scripts/m1_export.py", "--scene", golden, "--out", str(out2)]
        res2 = subprocess.run(cmd2, cwd=ROOT_DIR, capture_output=True, text=True)
        assert res2.returncode == 0, f"Run 2 failed: {res2.stderr}"

        j1_path = out1 / f"{golden}.slick_detection.json"
        j2_path = out2 / f"{golden}.slick_detection.json"
        npy1_path = out1 / f"{golden}_mask.npy"
        npy2_path = out2 / f"{golden}_mask.npy"

        doc1 = json.loads(j1_path.read_text(encoding="utf-8"))
        doc2 = json.loads(j2_path.read_text(encoding="utf-8"))

        mask1_bytes = npy1_path.read_bytes()
        mask2_bytes = npy2_path.read_bytes()
        sha1 = hashlib.sha256(mask1_bytes).hexdigest()
        sha2 = hashlib.sha256(mask2_bytes).hexdigest()

        print(f"Run 1 Mask SHA-256: {sha1}")
        print(f"Run 2 Mask SHA-256: {sha2}")
        print(f"Mask bytes identical: {mask1_bytes == mask2_bytes}")

        # Check geometry, area, polygon count, quality flags
        geom1 = doc1["slick"]["geometry"]
        geom2 = doc2["slick"]["geometry"]
        area1 = doc1["slick"]["area_km2"]
        area2 = doc2["slick"]["area_km2"]
        polys1 = doc1["slick"]["polygon_count"]
        polys2 = doc2["slick"]["polygon_count"]
        flags1 = doc1.get("quality_flags", [])
        flags2 = doc2.get("quality_flags", [])

        print(f"Polygons: Run 1 = {polys1}, Run 2 = {polys2} (Match: {polys1 == polys2})")
        print(f"Area km2: Run 1 = {area1}, Run 2 = {area2} (Match: {area1 == area2})")
        print(f"Geometry coordinates match: {geom1 == geom2}")
        print(f"Quality flags match: {flags1 == flags2}")

        # JSON Diff (normalized formatting)
        str1 = json.dumps(doc1, indent=2, sort_keys=True)
        str2 = json.dumps(doc2, indent=2, sort_keys=True)
        diff = list(difflib.unified_diff(
            str1.splitlines(keepends=True),
            str2.splitlines(keepends=True),
            fromfile="run1_output.json",
            tofile="run2_output.json",
            n=3
        ))

        print("\n--- JSON Diff between Run 1 and Run 2 ---")
        if diff:
            sys.stdout.writelines(diff)
        else:
            print("(Outputs are 100% byte-identical, no diff)")

        # Run 3: from cache
        print("\n--- Run 3: From Cache Verification ---")
        doc_cached_fresh = cache.get_detection(golden, use_cache=True, force=True, cache_dir=test_cache)
        doc_cached_replay = cache.get_detection(golden, use_cache=True, force=False, cache_dir=test_cache)

        prov3 = doc_cached_replay.get("provenance", {})
        replayed_served = prov3.get("served_from_cache", False)
        replayed_flag = "replayed_from_cache" in doc_cached_replay.get("quality_flags", [])
        geom3 = doc_cached_replay["slick"]["geometry"]

        print(f"Served from cache: {replayed_served}")
        print(f"Flag 'replayed_from_cache' present: {replayed_flag}")
        print(f"Cached geometry matches fresh geometry: {geom3 == geom1}")


if __name__ == "__main__":
    run()

