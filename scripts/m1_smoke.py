"""Stage 1 smoke test for TideTrace.

Usage:
    python scripts/m1_smoke.py [--scene SCENE_ID]

Runs segment_scene on every SAR chip that exists on disk (or just the one named
with --scene).  Exits non-zero if the U-Net was NOT used for any scene.

Step spec reference:
  1. Load the scene with app.geo.raster.load_sar.
  2. Call app.ml.infer.segment_scene on the sigma0 dB array.
  3. Print method, fallback_reason, mask shape/dtype, class pixel counts,
     oil_prob min/max, elapsed_s.
  4. Call app.geo.geometry.polygons_from_mask for class 2; print count +
     largest polygon area_km2 and first 3 coordinate pairs.
  5. State explicitly whether the first coord pair is (lon, lat) or (lat, lon).
  6. Exit non-zero if method is not "unet".
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure the project root is on sys.path so "app.*" imports work when the
# script is run from any directory.
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# Imports from the project
# ---------------------------------------------------------------------------
from app.config import SCENES_INDEX, SAR_DIR       # noqa: E402
from app.geo.raster import load_sar                 # noqa: E402
from app.geo.geometry import polygons_from_mask     # noqa: E402
from app.ml.infer import segment_scene              # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_scenes_index() -> list[dict]:
    if not SCENES_INDEX.exists():
        print(f"ERROR: scenes index not found at {SCENES_INDEX}", file=sys.stderr)
        sys.exit(1)
    with open(SCENES_INDEX, encoding="utf-8") as fh:
        data = json.load(fh)
    # Accept either a plain list or {"scenes": [...]}
    if isinstance(data, list):
        return data
    return data.get("scenes", [])


def find_sar_path(scene: dict) -> Path | None:
    """Return the .tif path for this scene entry if the file exists, else None.

    scenes.json stores paths as relative strings like "sar/foo.tif" under
    the "sar_path" key; they are relative to data/.
    """
    from app.config import DATA_DIR
    # Primary: "sar_path" key, relative to DATA_DIR
    stored = scene.get("sar_path") or scene.get("path") or scene.get("file") or scene.get("tif")
    if stored:
        p = Path(stored)
        if not p.is_absolute():
            # Try relative to DATA_DIR first, then ROOT
            candidates = [DATA_DIR / p, ROOT / p]
            for c in candidates:
                if c.exists():
                    return c
    # Fall back: <id>.tif under data/sar/
    sid = scene.get("id") or scene.get("scene_id") or ""
    if sid:
        p = SAR_DIR / f"{sid}.tif"
        if p.exists():
            return p
    return None


def run_scene(scene: dict, sar_path: Path, prefer_model: bool = True) -> bool:
    """Run the smoke test for one scene. Returns True if method == 'unet'."""
    sid = scene.get("id") or scene.get("scene_id") or sar_path.stem
    bbox = scene.get("bounds") or scene.get("bbox") or []

    print()
    print("=" * 72)
    print(f"SCENE: {sid}")
    print(f"  file : {sar_path}  ({sar_path.stat().st_size / 1e6:.1f} MB)")
    print(f"  bbox : {bbox}  (west, south, east, north from scenes.json)")
    print("=" * 72)

    # ------------------------------------------------------------------
    # Step 1: load SAR chip
    # ------------------------------------------------------------------
    t0 = time.perf_counter()
    print("\n[1] Loading SAR chip …")
    sar = load_sar(sar_path)
    sigma0_db = sar.array            # shape (bands, h, w) float32
    print(f"    array shape  : {sigma0_db.shape}  dtype={sigma0_db.dtype}")
    print(f"    CRS          : {sar.crs}")
    print(f"    transform    : {sar.transform}")
    bounds_wsen = sar.bounds_lonlat()
    print(f"    bounds (W,S,E,N) from raster: {[round(v,6) for v in bounds_wsen]}")

    # ------------------------------------------------------------------
    # Step 2: segment
    # ------------------------------------------------------------------
    print("\n[2] Calling segment_scene …")
    result = segment_scene(sigma0_db, prefer_model=prefer_model)
    elapsed = result.get("elapsed_s", round(time.perf_counter() - t0, 3))

    # ------------------------------------------------------------------
    # Step 3: print results
    # ------------------------------------------------------------------
    method = result.get("method", "unknown")
    fallback_reason = result.get("fallback_reason")
    mask = result["mask"]
    oil_prob = result["oil_prob"]

    import numpy as np
    c0 = int((mask == 0).sum())
    c1 = int((mask == 1).sum())
    c2 = int((mask == 2).sum())
    total = mask.size

    print("\n[3] Segmentation results:")
    print(f"    method         : {method}")
    print(f"    fallback_reason: {fallback_reason}")
    print(f"    mask shape     : {mask.shape}  dtype={mask.dtype}")
    print(f"    class 0 (sea)  : {c0:>10,} px  ({100*c0/total:.2f}%)")
    print(f"    class 1 (look) : {c1:>10,} px  ({100*c1/total:.2f}%)")
    print(f"    class 2 (oil)  : {c2:>10,} px  ({100*c2/total:.2f}%)")
    finite_prob = oil_prob[np.isfinite(oil_prob)]
    if finite_prob.size:
        print(f"    oil_prob min   : {float(finite_prob.min()):.6f}")
        print(f"    oil_prob max   : {float(finite_prob.max()):.6f}")
    else:
        print("    oil_prob       : (no finite values)")
    print(f"    elapsed_s      : {elapsed}")

    # ------------------------------------------------------------------
    # Step 4: polygons for class 2
    # ------------------------------------------------------------------
    print("\n[4] Extracting class-2 (mineral oil) polygons …")
    polys = polygons_from_mask(
        class_mask=mask,
        sar=sar,
        klass=2,
        prob=oil_prob,
        sigma0_db=sigma0_db[0] if sigma0_db.ndim == 3 else sigma0_db,
    )
    print(f"    number of polygons : {len(polys)}")
    if polys:
        largest = polys[0]          # already sorted by area_km2 descending
        print(f"    largest polygon    : id={largest.polygon_id}")
        print(f"      area_km2         : {largest.area_km2:.4f}")
        print(f"      pixel_count      : {largest.pixel_count}")
        ring = largest.ring_lonlat
        first3 = ring[:3]
        print(f"      first 3 coord pairs from ring_lonlat:")
        for i, pair in enumerate(first3):
            print(f"        [{i}] ({pair[0]:.6f}, {pair[1]:.6f})")

        # ------------------------------------------------------------------
        # Step 5: coordinate order check
        # ------------------------------------------------------------------
        print()
        print("[5] Coordinate order check:")
        if bbox:
            west, south, east, north = bbox[0], bbox[1], bbox[2], bbox[3]
        else:
            west, south, east, north = bounds_wsen
        lon0, lat0 = float(first3[0][0]), float(first3[0][1])
        # A value in [west..east] range is a longitude; [south..north] is latitude
        looks_like_lon = west <= lon0 <= east
        looks_like_lat = south <= lat0 <= north
        print(f"    scene bbox (from scenes.json or raster): W={west:.3f} S={south:.3f} E={east:.3f} N={north:.3f}")
        print(f"    first coord [0] = {lon0:.6f}  ->  {'within lon range' if looks_like_lon else 'OUTSIDE lon range'}")
        print(f"    first coord [1] = {lat0:.6f}  ->  {'within lat range' if looks_like_lat else 'OUTSIDE lat range'}")
        if looks_like_lon and looks_like_lat:
            print("    CONCLUSION: ring_lonlat stores (LON, LAT) order. [OK]")
        elif not looks_like_lon and looks_like_lat:
            print("    WARNING: first element looks like LAT, second like LON — order may be (lat, lon).")
        else:
            print("    NOTE: coord check inconclusive (scene bbox not available or polygon near boundary).")
    else:
        print("    (no class-2 polygons meet the minimum area/pixel threshold)")
        print()
        print("[5] Coordinate order check: skipped — no class-2 polygons extracted.")
        print("    ring_lonlat is documented as (lon, lat) in app/geo/geometry.py line 348.")

    # ------------------------------------------------------------------
    # Step 6: pass/fail
    # ------------------------------------------------------------------
    print()
    if method == "unet":
        print(f"PASS: method=unet for scene {sid}")
        return True
    else:
        print(f"FAIL: method={method!r} (fallback). "
              f"Reason: {fallback_reason}. "
              f"Ensure the checkpoint is at models/oil_unet_best.pt and torch is installed.")
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="TideTrace Stage-1 smoke test")
    parser.add_argument("--scene", default=None, help="scene_id to test (default: all with existing .tif)")
    parser.add_argument("--prefer-model", dest="prefer_model", default=True,
                        action=argparse.BooleanOptionalAction,
                        help="pass prefer_model=False to force baseline path")
    args = parser.parse_args()

    scenes = load_scenes_index()
    print(f"scenes.json contains {len(scenes)} scene(s).")

    # Filter to requested scene or all existing
    to_run = []
    for s in scenes:
        sid = s.get("id") or s.get("scene_id") or ""
        if args.scene and sid != args.scene:
            continue
        p = find_sar_path(s)
        if p is None:
            print(f"  SKIP {sid}: SAR .tif not found on disk")
        else:
            to_run.append((s, p))

    if not to_run:
        print("\nNo scenes to run (no .tif files found, or --scene filter matched nothing).")
        sys.exit(1)

    print(f"\nWill run smoke test on {len(to_run)} scene(s).")

    all_passed = True
    for scene, sar_path in to_run:
        ok = run_scene(scene, sar_path, prefer_model=args.prefer_model)
        if not ok:
            all_passed = False

    print()
    print("=" * 72)
    if all_passed:
        print(f"ALL {len(to_run)} SCENE(S) PASSED (method=unet)")
        sys.exit(0)
    else:
        print("ONE OR MORE SCENES DID NOT USE THE UNET — see FAIL lines above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
