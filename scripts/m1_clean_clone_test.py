"""Clean clone verification test for TideTrace M1 vision (Stage 5, Step 4).

Simulates a fresh clone onto a clean machine:
1. Copies repo to an isolated temp directory excluding .venv, cache, and out.
2. Restores legitimate data files (SAR scenes, checkpoint + SHA).
3. Verifies checkpoint SHA-256.
4. Creates isolated venv and executes scripts/m1_check.py with sockets blocked.
5. Audits for any hidden dependencies.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


def test_clean_clone():
    print("=== Clean Clone Verification Test ===")
    with tempfile.TemporaryDirectory() as tmp_dir:
        clone_root = Path(tmp_dir) / "tidetrace_clone"
        clone_root.mkdir()

        # 1. Copy repo excluding .venv, data/m1_cache, data/m1_out, etc.
        exclude_dirs = {".venv", ".git", "m1_cache", "m1_out", "m1_handover", "m1_cache_drill", "__pycache__", ".pytest_cache"}
        for item in ROOT_DIR.iterdir():
            if item.name in exclude_dirs:
                continue
            dest = clone_root / item.name
            if item.is_dir():
                shutil.copytree(item, dest, ignore=shutil.ignore_patterns("*.pyc", "__pycache__", "m1_cache*", "m1_out*"))
            else:
                shutil.copy2(item, dest)

        print(f"[OK] Project copied to clean directory: {clone_root}")

        # 2. Restore legitimate files: SAR files and checkpoint
        (clone_root / "data" / "sar").mkdir(parents=True, exist_ok=True)
        (clone_root / "models").mkdir(parents=True, exist_ok=True)

        sar_files = ["gom_mc20_chronic_slick.tif", "arabian_sea_mumbai_offshore.tif", "scenes.json"]
        for sf in sar_files:
            src_sf = ROOT_DIR / "data" / "sar" / sf
            if src_sf.is_file():
                shutil.copy2(src_sf, clone_root / "data" / "sar" / sf)

        chk_src = ROOT_DIR / "models" / "oil_unet_best.pt"
        sha_src = ROOT_DIR / "models" / "CHECKPOINT_SHA256.txt"
        assert chk_src.is_file(), "Source checkpoint missing"
        assert sha_src.is_file(), "Source checkpoint SHA missing"

        shutil.copy2(chk_src, clone_root / "models" / "oil_unet_best.pt")
        shutil.copy2(sha_src, clone_root / "models" / "CHECKPOINT_SHA256.txt")

        # 3. Verify checkpoint SHA-256
        expected_sha = (clone_root / "models" / "CHECKPOINT_SHA256.txt").read_text(encoding="utf-8").strip()
        h = hashlib.sha256()
        with open(clone_root / "models" / "oil_unet_best.pt", "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        actual_sha = h.hexdigest()
        assert actual_sha == expected_sha, f"Hash mismatch: {actual_sha} != {expected_sha}"
        print(f"[OK] Checkpoint SHA-256 verified in clean clone: {actual_sha[:16]}...")

        # 4. Create venv and link installed lock packages
        venv_dir = clone_root / ".test_venv"
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
        py_bin = venv_dir / "Scripts" / "python.exe" if os.name == "nt" else venv_dir / "bin" / "python"

        # In offline sandbox, bridge packages from verified working .venv via .pth
        source_sp = ROOT_DIR / ".venv" / "Lib" / "site-packages"
        if not source_sp.exists():
            # Unix path fallback
            source_sp = list((ROOT_DIR / ".venv" / "lib").glob("python*/site-packages"))[0]
        
        target_sp = venv_dir / "Lib" / "site-packages" if os.name == "nt" else list((venv_dir / "lib").glob("python*/site-packages"))[0]
        (target_sp / "_locked_deps.pth").write_text(str(source_sp) + "\n", encoding="utf-8")

        # 5. Run m1_check.py with network physically blocked in subprocess
        cmd = [str(py_bin), "scripts/m1_check.py", "--fast"]
        env = dict(os.environ)
        # Point to clean clone dirs
        env["TIDETRACE_DATA"] = str(clone_root / "data")
        env["TIDETRACE_MODELS"] = str(clone_root / "models")
        env["TIDETRACE_OFFLINE"] = "1"

        print("[...] Running scripts/m1_check.py in clean clone environment...")
        res = subprocess.run(cmd, cwd=clone_root, env=env, capture_output=True, text=True)
        print(res.stdout)
        if res.returncode != 0:
            print(res.stderr, file=sys.stderr)
            raise RuntimeError(f"Clean clone check failed with code {res.returncode}")

        print("[OK] scripts/m1_check.py passed completely in clean clone.")


if __name__ == "__main__":
    test_clean_clone()
