"""Status query function for TideTrace M1 vision (Stage 4, Step 4).

Provides system and readiness status for consumption by M4, health endpoints,
and integration monitors.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .. import config
from ..ml import infer, model as model_mod
from . import ADAPTER_VERSION, cache


def vision_status() -> Dict[str, Any]:
    """Return diagnostic status dict for the M1 vision subsystem.

    This function is guaranteed never to raise an unhandled exception and
    functions correctly even when PyTorch is not installed.
    """
    try:
        # Check torch availability safely
        torch_ok = False
        device = "cpu"
        try:
            torch_ok = bool(model_mod.torch_available())
            if torch_ok:
                import torch
                device = "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            torch_ok = False
            device = "cpu"

        # Check checkpoint presence and SHA-256
        chk_present = False
        chk_sha: Optional[str] = None
        try:
            chk_present = bool(config.CHECKPOINT.is_file())
            chk_sha = cache.get_checkpoint_sha256() if chk_present else None
        except Exception:
            chk_present = False
            chk_sha = None

        # Check if model is loaded into memory
        loaded_in_mem = False
        try:
            loaded_in_mem = bool(infer.model_ready() and (infer.get_model() is not None))
        except Exception:
            loaded_in_mem = False

        # Determine method availability
        method_avail = "unet" if (torch_ok and chk_present) else "baseline"

        # Cached scenes check
        cached_scenes: List[str] = []
        try:
            cached_scenes = cache.list_cached_scenes()
        except Exception:
            cached_scenes = []

        # Last error from infer
        last_err: Optional[str] = None
        try:
            last_err = infer.model_error()
        except Exception:
            last_err = None

        return {
            "model_loaded": loaded_in_mem,
            "method_available": method_avail,
            "checkpoint_present": chk_present,
            "checkpoint_sha256": chk_sha,
            "torch_available": torch_ok,
            "device": device,
            "cache_dir": str(cache.CACHE_DIR),
            "cached_scenes": cached_scenes,
            "adapter_version": ADAPTER_VERSION,
            "last_error": last_err,
        }
    except Exception as exc:
        # Absolute safety net: never raise
        return {
            "model_loaded": False,
            "method_available": "baseline",
            "checkpoint_present": False,
            "checkpoint_sha256": None,
            "torch_available": False,
            "device": "cpu",
            "cache_dir": str(config.DATA_DIR / "m1_cache"),
            "cached_scenes": [],
            "adapter_version": ADAPTER_VERSION,
            "last_error": f"vision_status_error: {exc}",
        }

