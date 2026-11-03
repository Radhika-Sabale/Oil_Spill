"""Demo Day Simulation Drill for TideTrace M1 Vision (Stage 4, Step 5).

Executes a 6-phase resilience and speed drill on the Golden Case (gom_mc20_chronic_slick):
1. Cold start, empty cache, network blocked -> result produced, cached
2. Warm start -> returned from cache in < 1s, flagged replayed_from_cache
3. Temporary checkpoint removal -> gracefully returns baseline or cache
4. Corrupted cache entry -> recovers and recomputes cleanly
5. Concurrency -> 4 simultaneous calls on cold cache give identical geometry
6. Determinism -> two consecutive runs from cleared cache produce identical geometry

All modified files (cache, checkpoint, sockets) are guaranteed restored via try/finally.
"""
from __future__ import annotations

import concurrent.futures
import json
import os
import shutil
import socket
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import config, scenes as scenes_mod
from app.ml import infer
from app.vision import cache


def _block_sockets():
    """Block socket connections to guarantee 100% offline execution."""
    real_connect = socket.socket.connect

    def guarded_connect(self, address):
        raise RuntimeError(f"Network violation: socket.connect to {address} blocked during drill")

    socket.socket.connect = guarded_connect
    return real_connect


def _restore_sockets(real_connect):
    socket.socket.connect = real_connect


def run_demo_drill(golden_case: str = "gom_mc20_chronic_slick") -> bool:
    print(f"======================================================================")
    print(f"STARTING DEMO DRILL ON GOLDEN CASE: {golden_case}")
    print(f"======================================================================\n")

    # Use an isolated drill cache directory
    drill_cache_dir = config.DATA_DIR / "m1_cache_drill"
    if drill_cache_dir.exists():
        shutil.rmtree(drill_cache_dir, ignore_errors=True)
    drill_cache_dir.mkdir(parents=True, exist_ok=True)

    passed_phases: List[Tuple[str, str]] = []
    failed_phases: List[Tuple[str, str]] = []

    real_connect = _block_sockets()
    chk_backup: Optional[Path] = None

    try:
        # ------------------------------------------------------------------
        # Phase 1: Cold start, empty cache, network blocked
        # ------------------------------------------------------------------
        t0 = time.perf_counter()
        infer.reset_model_cache()
        doc1 = cache.get_detection(
            scene=golden_case,
            use_cache=True,
            force=True,
            cache_dir=drill_cache_dir,
        )
        elapsed_cold = time.perf_counter() - t0

        polys1 = doc1["slick"]["polygon_count"]
        area1 = doc1["slick"]["area_km2"]
        prov1 = doc1.get("provenance") or {}
        served1 = prov1.get("served_from_cache", False)

        cached_files = list(drill_cache_dir.glob("*.json"))
        if not served1 and polys1 > 0 and len(cached_files) == 1:
            msg = f"cold start computed in {elapsed_cold:.2f}s, polys={polys1}, area={area1} km2, saved to cache"
            print(f"[PASS] Phase 1 - Cold Start (Offline): {msg}")
            passed_phases.append(("Phase 1: Cold Start (Offline)", msg))
        else:
            msg = f"served1={served1}, polys={polys1}, cached_files={len(cached_files)}"
            print(f"[FAIL] Phase 1 - Cold Start: {msg}")
            failed_phases.append(("Phase 1: Cold Start", msg))

        # ------------------------------------------------------------------
        # Phase 2: Warm start from cache (< 1.0 second)
        # ------------------------------------------------------------------
        t0 = time.perf_counter()
        doc2 = cache.get_detection(
            scene=golden_case,
            use_cache=True,
            force=False,
            cache_dir=drill_cache_dir,
        )
        elapsed_warm = time.perf_counter() - t0

        prov2 = doc2.get("provenance") or {}
        served2 = prov2.get("served_from_cache", False)
        flags2 = doc2.get("quality_flags", [])
        has_replayed_flag = "replayed_from_cache" in flags2

        if served2 and has_replayed_flag and elapsed_warm < 1.0:
            msg = f"replayed from cache in {elapsed_warm*1000:.2f}ms (<1s limit), flag 'replayed_from_cache' present"
            print(f"[PASS] Phase 2 - Warm Start: {msg}")
            passed_phases.append(("Phase 2: Warm Start", msg))
        else:
            msg = f"served2={served2}, has_flag={has_replayed_flag}, time={elapsed_warm:.4f}s"
            print(f"[FAIL] Phase 2 - Warm Start: {msg}")
            failed_phases.append(("Phase 2: Warm Start", msg))

        # ------------------------------------------------------------------
        # Phase 3: Temporary checkpoint deletion
        # ------------------------------------------------------------------
        chk_path = config.CHECKPOINT
        chk_backup = chk_path.with_suffix(".drill_bak")
        try:
            if chk_path.exists():
                shutil.move(chk_path, chk_backup)
            infer.reset_model_cache()

            # Calling get_detection with force=True will force computation without checkpoint
            doc3 = cache.get_detection(
                scene=golden_case,
                use_cache=True,
                force=True,
                cache_dir=drill_cache_dir,
            )
            method3 = doc3["slick"]["method"]
            if method3 in ("baseline", "model"):
                msg = f"handled missing checkpoint cleanly, method='{method3}', fallback flags={doc3.get('quality_flags')}"
                print(f"[PASS] Phase 3 - Checkpoint Resiliency: {msg}")
                passed_phases.append(("Phase 3: Checkpoint Resiliency", msg))
            else:
                msg = f"unexpected method: {method3}"
                print(f"[FAIL] Phase 3 - Checkpoint Resiliency: {msg}")
                failed_phases.append(("Phase 3: Checkpoint Resiliency", msg))
        finally:
            if chk_backup is not None and chk_backup.exists():
                shutil.move(chk_backup, chk_path)
                chk_backup = None
            infer.reset_model_cache()

        # ------------------------------------------------------------------
        # Phase 4: Corrupt cache entry recovery
        # ------------------------------------------------------------------
        # Corrupt the cached JSON entry in drill cache
        cached_jsons = list(drill_cache_dir.glob("*.json"))
        if cached_jsons:
            target_json = cached_jsons[0]
            target_json.write_text("{this is corrupted invalid JSON garbage", encoding="utf-8")

            doc4 = cache.get_detection(
                scene=golden_case,
                use_cache=True,
                force=False,
                cache_dir=drill_cache_dir,
            )
            prov4 = doc4.get("provenance") or {}
            recomputed = not prov4.get("served_from_cache", False)
            flags4 = doc4.get("quality_flags", [])
            has_corrupt_flag = "corrupt_cache_ignored" in flags4

            if recomputed and has_corrupt_flag:
                msg = f"detected corrupted cache entry, automatically recomputed fresh and set flag 'corrupt_cache_ignored'"
                print(f"[PASS] Phase 4 - Corrupt Entry Recovery: {msg}")
                passed_phases.append(("Phase 4: Corrupt Entry Recovery", msg))
            else:
                msg = f"recomputed={recomputed}, has_flag={has_corrupt_flag}"
                print(f"[FAIL] Phase 4 - Corrupt Entry Recovery: {msg}")
                failed_phases.append(("Phase 4: Corrupt Entry Recovery", msg))
        else:
            print("[FAIL] Phase 4 - Corrupt Entry Recovery: no cache file to corrupt")
            failed_phases.append(("Phase 4: Corrupt Entry Recovery", "no cache entry found"))

        # ------------------------------------------------------------------
        # Phase 5: Concurrency (4 simultaneous calls on cold cache)
        # ------------------------------------------------------------------
        shutil.rmtree(drill_cache_dir, ignore_errors=True)
        drill_cache_dir.mkdir(parents=True, exist_ok=True)
        infer.reset_model_cache()

        def worker(idx: int):
            return cache.get_detection(
                scene=golden_case,
                use_cache=True,
                force=False,
                cache_dir=drill_cache_dir,
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
            futures = [ex.submit(worker, i) for i in range(4)]
            results = [f.result() for f in futures]

        geom_matches = True
        base_coords = results[0]["slick"]["geometry"]
        for r in results[1:]:
            if r["slick"]["geometry"] != base_coords:
                geom_matches = False
                break

        # Check that cache files are valid and not corrupt
        cached_js = list(drill_cache_dir.glob("*.json"))
        cached_npy = list(drill_cache_dir.glob("*.npy"))
        all_valid = False
        if len(cached_js) == 1 and len(cached_npy) == 1:
            try:
                _ = json.loads(cached_js[0].read_text(encoding="utf-8"))
                all_valid = True
            except Exception:
                all_valid = False

        if geom_matches and all_valid:
            msg = f"4 concurrent threads finished with 100% identical geometry and clean atomic cache write"
            print(f"[PASS] Phase 5 - Concurrency: {msg}")
            passed_phases.append(("Phase 5: Concurrency", msg))
        else:
            msg = f"geom_matches={geom_matches}, valid_cache={all_valid}, jsons={len(cached_js)}"
            print(f"[FAIL] Phase 5 - Concurrency: {msg}")
            failed_phases.append(("Phase 5: Concurrency", msg))

        # ------------------------------------------------------------------
        # Phase 6: Determinism across cleared cache
        # ------------------------------------------------------------------
        shutil.rmtree(drill_cache_dir, ignore_errors=True)
        drill_cache_dir.mkdir(parents=True, exist_ok=True)
        infer.reset_model_cache()
        doc_run_a = cache.get_detection(golden_case, use_cache=True, cache_dir=drill_cache_dir)

        shutil.rmtree(drill_cache_dir, ignore_errors=True)
        drill_cache_dir.mkdir(parents=True, exist_ok=True)
        infer.reset_model_cache()
        doc_run_b = cache.get_detection(golden_case, use_cache=True, cache_dir=drill_cache_dir)

        geom_a = doc_run_a["slick"]["geometry"]
        geom_b = doc_run_b["slick"]["geometry"]
        poly_a = doc_run_a["slick"]["polygon_count"]
        poly_b = doc_run_b["slick"]["polygon_count"]

        if poly_a == poly_b and geom_a == geom_b:
            msg = f"both independent cold runs produced exactly {poly_a} polygons with identical GeoJSON coordinates"
            print(f"[PASS] Phase 6 - Determinism: {msg}")
            passed_phases.append(("Phase 6: Determinism", msg))
        else:
            msg = f"polygons run A: {poly_a}, run B: {poly_b}, geom_match={geom_a == geom_b}"
            print(f"[FAIL] Phase 6 - Determinism: {msg}")
            failed_phases.append(("Phase 6: Determinism", msg))

    finally:
        # GUARANTEED RESTORATION
        _restore_sockets(real_connect)
        if chk_backup is not None and chk_backup.exists():
            shutil.move(chk_backup, config.CHECKPOINT)
        if drill_cache_dir.exists():
            shutil.rmtree(drill_cache_dir, ignore_errors=True)
        infer.reset_model_cache()

    print(f"\n======================================================================")
    print(f"DEMO DRILL SUMMARY: {len(passed_phases)}/6 PASSED, {len(failed_phases)} FAILED")
    print(f"======================================================================")
    for name, note in passed_phases:
        print(f"  [PASS] {name}: {note}")
    for name, note in failed_phases:
        print(f"  [FAIL] {name}: {note}")
    print()

    return len(failed_phases) == 0


if __name__ == "__main__":
    success = run_demo_drill()
    sys.exit(0 if success else 1)

