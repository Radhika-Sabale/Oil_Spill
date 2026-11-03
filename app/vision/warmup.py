"""Model pre-warming for TideTrace M1 vision (Stage 4, Step 3).

Loads the PyTorch U-Net checkpoint into memory ahead of first inference
and runs a single forward pass to prime PyTorch internal thread pools and kernels.
"""
from __future__ import annotations

import time
from typing import Optional

from .. import config
from ..ml import infer, model as model_mod


def warmup() -> float:
    """Load model weights and execute one small forward pass.

    Returns:
        Elapsed time in seconds taken to warm up. Safe to call multiple times.
    """
    t0 = time.perf_counter()

    if not model_mod.torch_available():
        return round(time.perf_counter() - t0, 4)

    import torch

    loaded = infer.get_model()
    if loaded is None or "model" not in loaded:
        return round(time.perf_counter() - t0, 4)

    net = loaded["model"]
    device = loaded.get("device", "cpu")

    # Run one tiny forward pass through the model to prime JIT / GEMM kernels
    # Tile size 512x512 matches the operational tile dimension
    tile_size = int(config.TILE)
    dummy_input = torch.zeros((1, 3, tile_size, tile_size), dtype=torch.float32, device=device)
    with torch.no_grad():
        _ = net(dummy_input)

    return round(time.perf_counter() - t0, 4)

