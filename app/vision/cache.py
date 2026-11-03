"""Result cache for TideTrace M1 vision output (Stage 4).

Provides deterministic, content-addressed caching for Contract A documents
and raster masks in data/m1_cache/.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

from .. import config, scenes as scenes_mod
from ..geo import raster as raster_mod
from ..ml import infer
from . import ADAPTER_VERSION, predict, vectorize

CACHE_DIR = config.DATA_DIR / "m1_cache"
_COMPUTE_LOCK = threading.Lock()


def get_checkpoint_sha256() -> Optional[str]:
    """Read checkpoint SHA-256 from text file or compute if available."""
    sha_file = config.MODELS_DIR / "CHECKPOINT_SHA256.txt"
    if sha_file.exists():
        try:
            val = sha_file.read_text(encoding="utf-8").strip()
            if val:
                return val
        except Exception:
            pass
    if config.CHECKPOINT.is_file():
        try:
            h = hashlib.sha256()
            with open(config.CHECKPOINT, "rb") as f:
                while chunk := f.read(65536):
                    h.update(chunk)
            return h.hexdigest()
        except Exception:
            pass
    return None


def compute_cache_key(
    sar_path: Union[str, Path],
    checkpoint_sha256: Optional[str] = None,
    tile: int = None,
    tile_overlap: int = None,
    radiometric_align: bool = None,
    baseline_threshold_db: float = None,
    baseline_relative_only: bool = None,
    adapter_version: str = ADAPTER_VERSION,
) -> str:
    """Compute deterministic SHA-256 cache key over all inputs and settings."""
    if tile is None:
        tile = config.TILE
    if tile_overlap is None:
        tile_overlap = config.TILE_OVERLAP
    if radiometric_align is None:
        radiometric_align = config.RADIOMETRIC_ALIGN
    if baseline_threshold_db is None:
        baseline_threshold_db = config.OIL_DB_THRESHOLD
    if baseline_relative_only is None:
        baseline_relative_only = config.BASELINE_RELATIVE_ONLY

    hasher = hashlib.sha256()

    # 1. SAR file bytes
    p = Path(sar_path)
    if not p.is_file():
        raise FileNotFoundError(f"SAR file not found for cache key: {sar_path}")
    with open(p, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)

    # 2. Checkpoint SHA-256 (or string "no-checkpoint")
    chk_str = str(checkpoint_sha256 or "no-checkpoint")
    hasher.update(chk_str.encode("utf-8"))

    # 3. TILE
    hasher.update(f"|tile:{tile}".encode("utf-8"))

    # 4. TILE_OVERLAP
    hasher.update(f"|overlap:{tile_overlap}".encode("utf-8"))

    # 5. Radiometric alignment flag
    hasher.update(f"|radiometric_align:{radiometric_align}".encode("utf-8"))

    # 6. Baseline threshold settings
    hasher.update(f"|threshold_db:{baseline_threshold_db}".encode("utf-8"))
    hasher.update(f"|relative_only:{baseline_relative_only}".encode("utf-8"))

    # 7. ADAPTER_VERSION
    hasher.update(f"|adapter_version:{adapter_version}".encode("utf-8"))

    return hasher.hexdigest()


def _atomic_write_bytes(dest_path: Path, data: bytes) -> None:
    """Atomic file write using temporary file in same directory."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = dest_path.parent
    fd, tmp_path = tempfile.mkstemp(dir=temp_dir, prefix="tmp_", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, dest_path)
    except Exception:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        raise


def _atomic_write_npy(dest_path: Path, array: np.ndarray) -> None:
    """Atomic numpy array write using temporary file in same directory."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = dest_path.parent
    fd, tmp_path = tempfile.mkstemp(dir=temp_dir, prefix="tmp_", suffix=".npy")
    os.close(fd)
    try:
        np.save(tmp_path, array)
        os.replace(tmp_path, dest_path)
    except Exception:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        raise


def _resolve_scene_and_sar(
    scene_id_or_path: Union[str, Path, scenes_mod.Scene],
) -> Tuple[str, Path, Optional[scenes_mod.Scene]]:
    """Resolve incident ID, SAR file path, and optional Scene record."""
    if hasattr(scene_id_or_path, "sar_path") and hasattr(scene_id_or_path, "id"):
        sc: scenes_mod.Scene = scene_id_or_path
        p = Path(sc.sar_path)
        if not p.is_file():
            if (config.SAR_DIR / p.name).is_file():
                p = config.SAR_DIR / p.name
            elif (config.DATA_DIR / p.name).is_file():
                p = config.DATA_DIR / p.name
        return sc.id, p, sc

    scene_str = str(scene_id_or_path)
    sc = scenes_mod.get(scene_str)
    if sc is not None:
        p = Path(sc.sar_path)
        if not p.is_file():
            if (config.SAR_DIR / p.name).is_file():
                p = config.SAR_DIR / p.name
            elif (config.DATA_DIR / p.name).is_file():
                p = config.DATA_DIR / p.name
        if p.is_file():
            return sc.id, p, sc

    # Search filesystem candidates
    cand_p = Path(scene_str)
    candidates = [cand_p]
    if not cand_p.suffix:
        candidates.extend([cand_p.with_suffix(".tif"), cand_p.with_suffix(".tiff")])

    for c in candidates:
        if c.is_file():
            return c.stem, c, None
        for base in (config.SAR_DIR, config.DATA_DIR, config.ROOT_DIR):
            if (base / c.name).is_file():
                return c.stem, base / c.name, None
            if (base / c).is_file():
                return c.stem, base / c, None

    raise FileNotFoundError(f"SAR raster not found: {scene_id_or_path}")


def get_detection(
    scene: Union[str, Path, scenes_mod.Scene],
    use_cache: bool = True,
    force: bool = False,
    cache_dir: Optional[Union[str, Path]] = None,
    prefer_model: bool = True,
    threshold_db: Optional[float] = None,
    exclude: Optional[np.ndarray] = None,
) -> Dict[str, Any]:
    """Retrieve Contract A detection document, using or updating cache as instructed.

    Args:
        scene: Scene instance, scene ID string, or path to GeoTIFF.
        use_cache: If True, read/write from cache. If False, neither read nor write.
        force: If True, recompute freshly and overwrite any cache entry.
        cache_dir: Target cache directory (defaults to data/m1_cache/).
        prefer_model: Prefer U-Net model over threshold baseline.
        threshold_db: Optional baseline threshold override.
        exclude: Optional exclusion mask.

    Returns:
        Contract A JSON document with provenance block.
    """
    c_dir = Path(cache_dir or CACHE_DIR).resolve()
    scene_id, sar_path, scene_record = _resolve_scene_and_sar(scene)

    chk_sha = get_checkpoint_sha256() if config.CHECKPOINT.is_file() else None

    # Compute content-addressed key
    key = compute_cache_key(
        sar_path=sar_path,
        checkpoint_sha256=chk_sha,
        tile=config.TILE,
        tile_overlap=config.TILE_OVERLAP,
        radiometric_align=config.RADIOMETRIC_ALIGN,
        baseline_threshold_db=config.OIL_DB_THRESHOLD,
        baseline_relative_only=config.BASELINE_RELATIVE_ONLY,
        adapter_version=ADAPTER_VERSION,
    )

    json_path = c_dir / f"{scene_id}.{key}.json"
    npy_path = c_dir / f"{scene_id}.{key}.npy"

    corrupted_found = False

    # Check cache if requested and not forced
    if use_cache and not force:
        with _COMPUTE_LOCK:
            if json_path.is_file() and npy_path.is_file():
                try:
                    # Validate JSON parse and NPY readability
                    raw_text = json_path.read_text(encoding="utf-8")
                    cached_doc = json.loads(raw_text)
                    # Verify numpy array loads cleanly
                    arr = np.load(npy_path)
                    if arr.size > 0:
                        doc = copy.deepcopy(cached_doc)
                        prov = doc.get("provenance") or {}
                        prov["served_from_cache"] = True
                        doc["provenance"] = prov
                        if "replayed_from_cache" not in doc.get("quality_flags", []):
                            doc["quality_flags"].append("replayed_from_cache")
                        return doc
                except Exception:
                    corrupted_found = True
                    # Corrupt cache entry is removed or ignored
                    try:
                        json_path.unlink(missing_ok=True)
                        npy_path.unlink(missing_ok=True)
                    except Exception:
                        pass
            elif json_path.is_file() and not npy_path.is_file():
                corrupted_found = True
                try:
                    json_path.unlink(missing_ok=True)
                except Exception:
                    pass

    # Compute freshly under lock to avoid racing compute
    with _COMPUTE_LOCK:
        # Check cache once more under lock (in case another thread just completed it)
        if use_cache and not force and not corrupted_found:
            if json_path.is_file() and npy_path.is_file():
                try:
                    raw_text = json_path.read_text(encoding="utf-8")
                    cached_doc = json.loads(raw_text)
                    _ = np.load(npy_path)
                    doc = copy.deepcopy(cached_doc)
                    prov = doc.get("provenance") or {}
                    prov["served_from_cache"] = True
                    doc["provenance"] = prov
                    if "replayed_from_cache" not in doc.get("quality_flags", []):
                        doc["quality_flags"].append("replayed_from_cache")
                    return doc
                except Exception:
                    corrupted_found = True

        # Fresh computation
        pred = predict.predict_scene(
            scene_id_or_path=sar_path,
            out_dir=None,
            prefer_model=prefer_model,
            threshold_db=threshold_db,
            exclude=exclude,
        )
        if scene_record is None:
            scene_record = pred["scene_record"]
        doc = vectorize.to_contract_a(pred, scene_record, pred["raster"])

        computed_at = datetime.now(timezone.utc).isoformat()
        prov_block = {
            "served_from_cache": False,
            "computed_at_utc": computed_at,
            "cache_key": key,
            "checkpoint_sha256": chk_sha,
        }
        doc["provenance"] = prov_block

        if corrupted_found and "corrupt_cache_ignored" not in doc["quality_flags"]:
            doc["quality_flags"].append("corrupt_cache_ignored")

        if use_cache:
            c_dir.mkdir(parents=True, exist_ok=True)
            # Write mask array atomically
            _atomic_write_npy(npy_path, pred["seg"]["mask"])
            doc["mask"]["path"] = str(npy_path)

            # Write document JSON atomically
            json_bytes = json.dumps(doc, indent=2, sort_keys=True).encode("utf-8")
            _atomic_write_bytes(json_path, json_bytes)

        return doc


def list_cached_scenes(cache_dir: Optional[Union[str, Path]] = None) -> List[str]:
    """Return sorted list of scene IDs with valid cache entries."""
    c_dir = Path(cache_dir or CACHE_DIR).resolve()
    if not c_dir.is_dir():
        return []

    valid_scenes: set[str] = set()
    for j_path in c_dir.glob("*.json"):
        # Format: <scene_id>.<key>.json
        parts = j_path.stem.split(".")
        if len(parts) >= 2:
            key = parts[-1]
            sc_id = ".".join(parts[:-1])
            npy_p = c_dir / f"{sc_id}.{key}.npy"
            if npy_p.is_file():
                try:
                    # quick sanity check
                    doc = json.loads(j_path.read_text(encoding="utf-8"))
                    if "incident_id" in doc:
                        valid_scenes.add(sc_id)
                except Exception:
                    continue
    return sorted(valid_scenes)

