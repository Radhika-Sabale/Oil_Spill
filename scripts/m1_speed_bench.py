"""M1 Vision Speed Benchmark (Stage 4, Step 3).

Measures inference levers on the Golden Case (gom_mc20_chronic_slick):
- Baseline (cold load, default threads, batch_size=4, torch.no_grad)
- Lever 1: torch.set_num_threads (physical core count vs default)
- Lever 2: batch_size in run_unet (batch_size=1, 2, 4, 8)
- Lever 3: torch.inference_mode instead of torch.no_grad
- Lever 4: warmup() ahead of request
"""
from __future__ import annotations

import hashlib
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import torch

from app import config, scenes as scenes_mod
from app.geo import raster as raster_mod
from app.ml import infer
from app.vision import predict, warmup


def compute_mask_sha256(mask: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(mask)).hexdigest()


def compute_iou(mask_a: np.ndarray, mask_b: np.ndarray, oil_class: int = 2) -> float:
    a = (mask_a == oil_class)
    b = (mask_b == oil_class)
    intersection = np.logical_and(a, b).sum()
    union = np.logical_or(a, b).sum()
    if union == 0:
        return 1.0 if intersection == 0 else 0.0
    return float(intersection) / float(union)


def run_benchmark():
    scene_id = "gom_mc20_chronic_slick"
    scene_record = scenes_mod.get(scene_id)
    sar_path = config.SAR_DIR / f"{scene_id}.tif"
    raster = raster_mod.load_sar(sar_path)
    sigma0_db = raster_mod.to_db(raster.array)

    print(f"=== Speed Benchmarking on Golden Case: {scene_id} ===")
    print(f"Raster shape: {raster.array.shape}, PyTorch default threads: {torch.get_num_threads()}\n")

    # 1. Baseline: Cold Load + Default Settings
    infer.reset_model_cache()
    tracemalloc.start()
    t_load_0 = time.perf_counter()
    loaded = infer.get_model()
    load_time = time.perf_counter() - t_load_0

    t_infer_0 = time.perf_counter()
    out_baseline = infer.run_unet(sigma0_db, loaded, batch_size=4)
    infer_time = time.perf_counter() - t_infer_0
    current_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    n_tiles = out_baseline["n_tiles"]
    per_tile_time = infer_time / max(1, n_tiles)
    total_time = load_time + infer_time
    baseline_probs = out_baseline["probs"]
    baseline_mask = np.argmax(baseline_probs, axis=0).astype(np.uint8)
    baseline_mask = infer._clean(baseline_mask)
    baseline_sha = compute_mask_sha256(baseline_mask)

    print("--- 1. Baseline ---")
    print(f"Model Load Time:   {load_time:.4f} s")
    print(f"Inference Time:    {infer_time:.4f} s ({n_tiles} tiles, {per_tile_time*1000:.2f} ms/tile)")
    print(f"Total Time:        {total_time:.4f} s")
    print(f"Peak Memory:       {peak_mem / (1024*1024):.2f} MB")
    print(f"Mask SHA-256:      {baseline_sha}\n")

    results = {
        "baseline": {
            "load_time": load_time,
            "infer_time": infer_time,
            "total_time": total_time,
            "per_tile_ms": per_tile_time * 1000,
            "peak_mem_mb": peak_mem / (1024 * 1024),
            "sha": baseline_sha,
            "iou": 1.0,
        }
    }

    # 2. Lever A: Thread tuning (test threads=4, 6, 8, 12)
    print("--- 2. Lever A: torch.set_num_threads ---")
    for th in [4, 6, 8, 12]:
        torch.set_num_threads(th)
        t0 = time.perf_counter()
        out = infer.run_unet(sigma0_db, loaded, batch_size=4)
        elapsed = time.perf_counter() - t0
        mask = infer._clean(np.argmax(out["probs"], axis=0).astype(np.uint8))
        sha = compute_mask_sha256(mask)
        iou = compute_iou(baseline_mask, mask)
        print(f"Threads={th:2d}: time={elapsed:.4f} s ({elapsed/n_tiles*1000:.2f} ms/tile) | SHA matches: {sha==baseline_sha} | IoU: {iou:.6f}")
        results[f"threads_{th}"] = {
            "infer_time": elapsed,
            "per_tile_ms": elapsed / n_tiles * 1000,
            "sha": sha,
            "iou": iou,
        }
    # Reset threads to 8
    torch.set_num_threads(8)
    print()

    # 3. Lever B: Batch size in run_unet (1, 2, 4, 8)
    print("--- 3. Lever B: batch_size in run_unet ---")
    for bs in [1, 2, 4, 8]:
        tracemalloc.start()
        t0 = time.perf_counter()
        out = infer.run_unet(sigma0_db, loaded, batch_size=bs)
        elapsed = time.perf_counter() - t0
        _, pk = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        mask = infer._clean(np.argmax(out["probs"], axis=0).astype(np.uint8))
        sha = compute_mask_sha256(mask)
        iou = compute_iou(baseline_mask, mask)
        print(f"Batch={bs}: time={elapsed:.4f} s ({elapsed/n_tiles*1000:.2f} ms/tile) | Peak Mem: {pk/(1024*1024):.2f} MB | SHA matches: {sha==baseline_sha} | IoU: {iou:.6f}")
        results[f"batch_{bs}"] = {
            "infer_time": elapsed,
            "per_tile_ms": elapsed / n_tiles * 1000,
            "peak_mem_mb": pk / (1024 * 1024),
            "sha": sha,
            "iou": iou,
        }
    print()

    # 4. Lever C: torch.inference_mode
    print("--- 4. Lever C: torch.inference_mode vs torch.no_grad ---")
    with torch.inference_mode():
        t0 = time.perf_counter()
        out = infer.run_unet(sigma0_db, loaded, batch_size=4)
        elapsed = time.perf_counter() - t0
    mask = infer._clean(np.argmax(out["probs"], axis=0).astype(np.uint8))
    sha = compute_mask_sha256(mask)
    iou = compute_iou(baseline_mask, mask)
    print(f"inference_mode: time={elapsed:.4f} s ({elapsed/n_tiles*1000:.2f} ms/tile) | SHA matches: {sha==baseline_sha} | IoU: {iou:.6f}\n")
    results["inference_mode"] = {
        "infer_time": elapsed,
        "per_tile_ms": elapsed / n_tiles * 1000,
        "sha": sha,
        "iou": iou,
    }

    # 5. Lever D: Warmup before request
    print("--- 5. Lever D: warmup() ahead of request ---")
    infer.reset_model_cache()
    w_time = warmup.warmup()
    t0 = time.perf_counter()
    # Now model is already loaded and primed
    loaded_warm = infer.get_model()
    out = infer.run_unet(sigma0_db, loaded_warm, batch_size=4)
    elapsed_w = time.perf_counter() - t0
    mask = infer._clean(np.argmax(out["probs"], axis=0).astype(np.uint8))
    sha = compute_mask_sha256(mask)
    iou = compute_iou(baseline_mask, mask)
    print(f"Warmup time:     {w_time:.4f} s")
    print(f"Subsequent call: {elapsed_w:.4f} s (vs cold baseline total {total_time:.4f} s)")
    print(f"SHA matches: {sha==baseline_sha} | IoU: {iou:.6f}\n")
    results["warmup"] = {
        "warmup_time": w_time,
        "subsequent_time": elapsed_w,
        "sha": sha,
        "iou": iou,
    }

    return results


if __name__ == "__main__":
    run_benchmark()

