"""Assemble Handover Bundle for TideTrace M1 Vision (Stage 5, Step 6).

Copies golden case artifacts into data/m1_handover/, generates MANIFEST.sha256,
writes the 10-line RUN.txt, and verifies all checksums.
"""
from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import config

HANDOVER_DIR = config.DATA_DIR / "m1_handover"
HANDOVER_DIR.mkdir(parents=True, exist_ok=True)

golden = "gom_mc20_chronic_slick"

files_to_copy = [
    (config.DATA_DIR / "m1_out" / f"{golden}.slick_detection.json", HANDOVER_DIR / f"{golden}.slick_detection.json"),
    (config.DATA_DIR / "m1_out" / f"{golden}_mask.npy", HANDOVER_DIR / f"{golden}_mask.npy"),
    (config.DATA_DIR / "m1_out" / f"{golden}_mask.tif", HANDOVER_DIR / f"{golden}_mask.tif"),
    (config.DATA_DIR / "m1_out" / f"{golden}.control_points.csv", HANDOVER_DIR / f"{golden}.control_points.csv"),
    (config.DATA_DIR / "m1_out" / "review" / f"{golden}_overlay.png", HANDOVER_DIR / f"{golden}_overlay.png"),
]

for src, dst in files_to_copy:
    assert src.is_file(), f"Missing handover source: {src}"
    shutil.copy2(src, dst)

# 10-line RUN.txt
run_txt_lines = [
    "# TideTrace M1 Vision Regeneration & Status Run Commands",
    "python scripts/m1_export.py --scene gom_mc20_chronic_slick --out data/m1_out",
    "python scripts/m1_control_points.py --scene gom_mc20_chronic_slick --out data/m1_out",
    "python scripts/m1_overlay.py --scene gom_mc20_chronic_slick --out data/m1_out",
    "python scripts/m1_demo_drill.py",
    "python scripts/m1_doctor.py",
    "python -c \"from app.vision.status import vision_status; import json; print(json.dumps(vision_status(), indent=2))\"",
    "python -m pytest tests/test_vision_*.py -q",
    "python scripts/m1_check.py --fast",
    "python -c \"from app.vision.cache import get_detection; d = get_detection('gom_mc20_chronic_slick'); print(d['slick']['polygon_count'])\"",
]
assert len(run_txt_lines) == 10, f"RUN.txt must be exactly 10 lines, got {len(run_txt_lines)}"

run_txt_path = HANDOVER_DIR / "RUN.txt"
run_txt_path.write_text("\n".join(run_txt_lines) + "\n", encoding="utf-8")

# Checkpoint file for manifest
chk_path = config.CHECKPOINT
assert chk_path.is_file(), f"Missing checkpoint: {chk_path}"

manifest_entries = []
files_to_hash = [
    (HANDOVER_DIR / f"{golden}.slick_detection.json", f"{golden}.slick_detection.json"),
    (HANDOVER_DIR / f"{golden}_mask.npy", f"{golden}_mask.npy"),
    (HANDOVER_DIR / f"{golden}_mask.tif", f"{golden}_mask.tif"),
    (HANDOVER_DIR / f"{golden}.control_points.csv", f"{golden}.control_points.csv"),
    (HANDOVER_DIR / f"{golden}_overlay.png", f"{golden}_overlay.png"),
    (chk_path, "models/oil_unet_best.pt"),
]

for fpath, label in files_to_hash:
    h = hashlib.sha256()
    with open(fpath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    digest = h.hexdigest()
    manifest_entries.append(f"{digest}  {label}")

manifest_path = HANDOVER_DIR / "MANIFEST.sha256"
manifest_path.write_text("\n".join(manifest_entries) + "\n", encoding="utf-8")

# Re-verify manifest
print("=== Verifying Handover Manifest ===")
for line in manifest_entries:
    sha, label = line.split("  ")
    if label == "models/oil_unet_best.pt":
        target = config.CHECKPOINT
    else:
        target = HANDOVER_DIR / label
    assert target.is_file(), f"Target missing: {target}"
    h = hashlib.sha256()
    with open(target, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    actual = h.hexdigest()
    assert actual == sha, f"Checksum verification failed on {label}: {actual} != {sha}"
    print(f"[OK] {label}: {sha}")

print("\nHandover bundle successfully created and verified in:", HANDOVER_DIR)

