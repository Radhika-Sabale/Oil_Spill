"""On-call diagnostic triage script for TideTrace M1 vision (Stage 5, Step 7).

Executes in under 10 seconds to verify environment, weights, data,
readiness status, and cached replay health.
"""
from __future__ import annotations

import hashlib
import sys
import tempfile
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def check_python_version() -> tuple[bool, str]:
    v = sys.version_info
    v_str = f"{v.major}.{v.minor}.{v.micro}"
    if v >= (3, 11):
        return True, f"Python {v_str} >= 3.11"
    return False, f"Python {v_str} is below minimum requirement 3.11"


def check_packages_importable() -> tuple[bool, str]:
    required = ["numpy", "scipy", "rasterio", "pyproj", "pydantic", "torch", "segmentation_models_pytorch"]
    missing = []
    for pkg in required:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if not missing:
        return True, f"All core packages importable ({', '.join(required)})"
    return False, f"Missing packages: {', '.join(missing)}"


def check_checkpoint() -> tuple[bool, str]:
    from app import config
    chk = config.CHECKPOINT
    if not chk.is_file():
        return False, f"Checkpoint file missing: {chk}"
    
    sha_file = config.MODELS_DIR / "CHECKPOINT_SHA256.txt"
    if not sha_file.is_file():
        return False, f"Reference SHA-256 file missing: {sha_file}"
    
    expected = sha_file.read_text(encoding="utf-8").strip()
    h = hashlib.sha256()
    with open(chk, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    actual = h.hexdigest()
    if actual == expected:
        return True, f"Checkpoint valid, SHA-256 matches ({actual[:12]}...)"
    return False, f"Hash mismatch: actual {actual[:12]}... != expected {expected[:12]}..."


def check_scenes_present() -> tuple[bool, str]:
    from app import config, scenes as scenes_mod
    idx = scenes_mod.load_index()
    if not idx:
        return False, "No scenes in scenes.json index"
    
    found_tifs = []
    for sc in idx:
        p = Path(sc.sar_path)
        if not p.is_file():
            if (config.SAR_DIR / p.name).is_file():
                p = config.SAR_DIR / p.name
        if p.is_file():
            found_tifs.append(sc.id)
            
    if found_tifs:
        return True, f"Found {len(found_tifs)} existing SAR scene(s): {', '.join(found_tifs)}"
    return False, "No SAR .tif files found on disk for indexed scenes"


def check_cache_writable() -> tuple[bool, str]:
    from app.vision import cache
    cdir = cache.CACHE_DIR
    try:
        cdir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=cdir, delete=True) as tf:
            tf.write(b"health_check")
            tf.flush()
        return True, f"Cache directory writable ({cdir})"
    except Exception as exc:
        return False, f"Cache directory not writable: {exc}"


def check_vision_status() -> tuple[bool, str]:
    from app.vision import status
    try:
        st = status.vision_status()
        if st.get("method_available") == "unet" and st.get("checkpoint_present"):
            return True, f"Method available: {st['method_available']}, device: {st.get('device')}"
        return False, f"vision_status degraded: {st}"
    except Exception as exc:
        return False, f"vision_status raised: {exc}"


def check_cached_replay() -> tuple[bool, str]:
    from app.vision import cache
    try:
        t0 = time.perf_counter()
        doc = cache.get_detection("gom_mc20_chronic_slick", use_cache=True, force=False)
        elapsed = time.perf_counter() - t0
        prov = doc.get("provenance", {})
        served = prov.get("served_from_cache", False)
        flags = doc.get("quality_flags", [])
        if elapsed < 1.0 and served and ("replayed_from_cache" in flags):
            return True, f"Cached replay verified in {elapsed*1000:.1f}ms (<1s)"
        elif not served:
            return True, f"Initial cache entry populated in {elapsed:.2f}s"
        return False, f"Replay failed: served={served}, elapsed={elapsed:.3f}s"
    except Exception as exc:
        return False, f"Cached replay error: {exc}"


def main() -> int:
    t_start = time.perf_counter()
    checks = [
        ("Python Version", check_python_version),
        ("Packages Importable", check_packages_importable),
        ("Checkpoint Integrity", check_checkpoint),
        ("Scenes Present", check_scenes_present),
        ("Cache Writable", check_cache_writable),
        ("Vision Status API", check_vision_status),
        ("Cached Replay Health", check_cached_replay),
    ]

    print("========================================================")
    print("M1 VISION DOCTOR - ON-CALL SYSTEM TRIAGE")
    print("========================================================")
    all_ok = True
    for name, fn in checks:
        ok, reason = fn()
        status_label = "[PASS]" if ok else "[FAIL]"
        print(f"{status_label} {name:<22}: {reason}")
        if not ok:
            all_ok = False

    t_total = time.perf_counter() - t_start
    print("========================================================")
    print(f"TRIAGE COMPLETE in {t_total:.2f}s: {'ALL HEALTHY' if all_ok else 'SYSTEM ATTENTION REQUIRED'}")
    print("========================================================")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())

