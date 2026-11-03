"""One-command verification script for TideTrace M1 vision adapter (Stage 3 Step 7).

Runs in order:
1. Test suite (pytest tests/test_vision_*.py)
2. Contract A export (scripts/m1_export.py --all)
3. Control points generation (scripts/m1_control_points.py --all)
4. Overlays & comparison images (scripts/m1_overlay.py --all)
5. Reproducibility check (verifies byte-identical output across runs except elapsed_s)

Prints a PASS/FAIL summary table and exits non-zero on any failure.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run_step(name: str, cmd: list[str]) -> tuple[bool, str]:
    """Execute a command and return (success, details)."""
    print(f"\n========================================================")
    print(f"Running: {name}")
    print(f"Command: {' '.join(cmd)}")
    print(f"========================================================")
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if proc.returncode == 0:
        print(proc.stdout)
        return True, "Completed with exit code 0"
    else:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        return False, f"Failed with exit code {proc.returncode}"


def check_reproducibility(out_dir: Path, python_bin: str) -> tuple[bool, str]:
    """Verify that export runs produce byte-identical JSON (except elapsed_s) and mask bytes."""
    print(f"\n========================================================")
    print(f"Running: Reproducibility verification")
    print(f"========================================================")
    with tempfile.TemporaryDirectory() as tmp_dir:
        p = Path(tmp_dir)

        # Run 1
        res1 = subprocess.run(
            [python_bin, "scripts/m1_export.py", "--all", "--out", str(p), "--no-prefer-model"],
            cwd=ROOT, capture_output=True, text=True
        )
        if res1.returncode != 0:
            return False, f"Run 1 failed: {res1.stderr}"

        # Capture run 1 states
        run1_json = {}
        run1_npy = {}
        for jf in p.glob("*.slick_detection.json"):
            d = json.loads(jf.read_text(encoding="utf-8"))
            elapsed = d.pop("elapsed_s", None)
            run1_json[jf.name] = (d, elapsed)
            npy_f = p / f"{d['incident_id']}_mask.npy"
            if npy_f.exists():
                run1_npy[jf.name] = npy_f.read_bytes()

        # Run 2 into the exact same directory
        res2 = subprocess.run(
            [python_bin, "scripts/m1_export.py", "--all", "--out", str(p), "--no-prefer-model"],
            cwd=ROOT, capture_output=True, text=True
        )
        if res2.returncode != 0:
            return False, f"Run 2 failed: {res2.stderr}"

        # Compare run 2 against run 1
        for jf_name, (d1, elapsed1) in run1_json.items():
            jf2 = p / jf_name
            if not jf2.exists():
                return False, f"Missing file in run 2: {jf_name}"
            d2 = json.loads(jf2.read_text(encoding="utf-8"))
            elapsed2 = d2.pop("elapsed_s", None)

            if d1 != d2:
                return False, f"JSON content difference in {jf_name} (excluding elapsed_s)"

            npy_f = p / f"{d1['incident_id']}_mask.npy"
            if npy_f.exists() and jf_name in run1_npy:
                b1 = run1_npy[jf_name]
                b2 = npy_f.read_bytes()
                if b1 != b2:
                    return False, f"Mask .npy byte mismatch in {npy_f.name}"

        return True, "Byte-identical outputs confirmed (only elapsed_s timing varies)"


def main() -> int:
    parser = argparse.ArgumentParser(description="One-command verification check for M1 vision.")
    parser.add_argument("--fast", action="store_true", help="Run model in baseline mode for rapid check")
    parser.add_argument("--out", default="data/m1_out", help="Output directory")
    args = parser.parse_args()

    python_bin = sys.executable

    results: list[tuple[str, str, str]] = []
    all_ok = True

    # 1. Test suite
    cmd_tests = [python_bin, "-m", "pytest", "tests/test_vision_contract.py", "tests/test_vision_georef.py",
                 "tests/test_vision_robust.py", "tests/test_vision_fallback.py", "tests/test_vision_snapshot.py", "-v"]
    ok, msg = run_step("Vision Test Suite", cmd_tests)
    results.append(("Vision Test Suite", "PASS" if ok else "FAIL", msg))
    if not ok:
        all_ok = False

    # 2. Export
    cmd_export = [python_bin, "scripts/m1_export.py", "--all", "--out", args.out]
    if args.fast:
        cmd_export.append("--no-prefer-model")
    ok, msg = run_step("Contract A Export", cmd_export)
    results.append(("Contract A Export", "PASS" if ok else "FAIL", msg))
    if not ok:
        all_ok = False

    # 3. Control points
    cmd_cp = [python_bin, "scripts/m1_control_points.py", "--all", "--out", args.out]
    ok, msg = run_step("Control Points CSV Generation", cmd_cp)
    results.append(("Control Points CSV", "PASS" if ok else "FAIL", msg))
    if not ok:
        all_ok = False

    # 4. Overlays & comparison
    cmd_overlay = [python_bin, "scripts/m1_overlay.py", "--all", "--out", args.out]
    ok, msg = run_step("Human Review Overlays", cmd_overlay)
    results.append(("Human Review Overlays", "PASS" if ok else "FAIL", msg))
    if not ok:
        all_ok = False

    # 5. Reproducibility
    ok, msg = check_reproducibility(Path(args.out), python_bin)
    results.append(("Reproducibility Check", "PASS" if ok else "FAIL", msg))
    if not ok:
        all_ok = False

    # 6. Demo Day Simulation Drill (Stage 4)
    if not args.fast:
        cmd_drill = [python_bin, "scripts/m1_demo_drill.py"]
        ok, msg = run_step("Demo Day Resilience Drill", cmd_drill)
        results.append(("Demo Resilience Drill", "PASS" if ok else "FAIL", msg))
        if not ok:
            all_ok = False

    # Summary table
    print("\n" + "=" * 70)
    print("M1 VERIFICATION & HARDENING SUMMARY")
    print("=" * 70)
    print(f"{'Check / Step':<32} {'Result':<10} {'Details'}")
    print("-" * 70)
    for name, res, detail in results:
        print(f"{name:<32} {res:<10} {detail}")
    print("=" * 70)

    if all_ok:
        print("\nALL CHECKS PASSED.")
        return 0
    else:
        print("\nONE OR MORE CHECKS FAILED.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
