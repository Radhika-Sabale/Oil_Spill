"""Stage 1 (M2): scene validation, incidence normalisation, wind gate, CA-CFAR.

Every function returns plain dicts with an explicit `status` so the pipeline,
API and dossier can show `available`, `unavailable` or `partial` instead of
silently assuming. Nothing here invents a value: a missing input yields
`unavailable` with a reason.

Units contract
--------------
* Rasters in this repo carry VV/VH in dB (see scripts/fetch_sentinel1_scene.py).
* Normalisation and CFAR averaging happen in LINEAR power; dB is only used for
  the final threshold comparison.
* All thresholds below are PROVISIONAL (roadmap section 4.2) until measured on
  the Golden Case. They are reported in every output.
"""
from __future__ import annotations

import math
import warnings
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

try:
    from scipy import ndimage as _ndi
except Exception:  # pragma: no cover
    _ndi = None

WIND_MIN_MS = 3.0
WIND_MAX_MS = 12.0
CFAR_GUARD = 4            # guard cells (pyramid pixels)
CFAR_TRAIN = 16           # training cells beyond the guard
CFAR_THRESH_DB = -3.5     # provisional damping threshold
CFAR_PIXEL_M = 100.0
THETA_REF_DEG = 34.0      # provisional mid-swath reference angle
NORM_EXPONENT = 1.0       # provisional cosine exponent


def db_to_lin(db):
    return np.power(10.0, np.asarray(db, dtype=np.float64) / 10.0)


def lin_to_db(lin):
    lin = np.asarray(lin, dtype=np.float64)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(lin > 0, 10.0 * np.log10(lin), np.nan)


# --------------------------------------------------------------------------
# 1. Product / calibration status
# --------------------------------------------------------------------------
def classify_product(source: str) -> Dict[str, Any]:
    """Decide what radiometry the scene really carries from its source string.

    The scene index says "IW GRD RTC via Planetary Computer". RTC products are
    terrain-flattened GAMMA0, not GRD sigma0, so they must not be labelled
    sigma0 in the dossier.
    """
    s = (source or "").upper()
    if "RTC" in s:
        return {"status": "available", "product": "RTC", "quantity": "gamma0",
                "terrain_flattened": True,
                "note": "Planetary Computer RTC is terrain-flattened gamma0 "
                        "(linear), not GRD sigma0. Label it as gamma0."}
    if "GRD" in s:
        return {"status": "partial", "product": "GRD", "quantity": "unverified",
                "terrain_flattened": False,
                "note": "GRD needs radiometric calibration (sigma0 LUT) before "
                        "use; this repo does not apply it."}
    return {"status": "unavailable", "product": "unknown", "quantity": "unknown",
            "terrain_flattened": None, "note": "source string does not name the product"}


# --------------------------------------------------------------------------
# 2. Incidence-angle normalisation (linear space)
# --------------------------------------------------------------------------
def normalize_incidence(vv_db: np.ndarray,
                        incidence_deg: Optional[Any] = None,
                        theta_ref_deg: float = THETA_REF_DEG,
                        exponent: float = NORM_EXPONENT) -> Dict[str, Any]:
    """Cosine normalisation to a reference angle, done in linear power.

    sigma_norm = sigma * (cos(theta_ref) / cos(theta)) ** exponent

    `incidence_deg` may be a scalar or an array broadcastable to the image.
    The RTC chips in this repo carry no incidence angle, so the usual outcome
    is `unavailable`; the data are then passed through unchanged and flagged.
    """
    arr = np.asarray(vv_db, dtype=np.float64)
    if incidence_deg is None:
        return {"status": "unavailable", "array_db": arr,
                "reason": "no incidence angle supplied (RTC chip carries none)",
                "applied": False}
    theta = np.asarray(incidence_deg, dtype=np.float64)
    if np.any(~np.isfinite(theta)) or np.any(theta <= 0) or np.any(theta >= 89):
        return {"status": "unavailable", "array_db": arr,
                "reason": "incidence angle outside (0, 89) degrees or non-finite",
                "applied": False}
    factor = (math.cos(math.radians(theta_ref_deg)) /
              np.cos(np.radians(theta))) ** exponent
    lin = db_to_lin(arr) * factor
    return {"status": "available", "array_db": lin_to_db(lin), "applied": True,
            "theta_ref_deg": theta_ref_deg, "exponent": exponent,
            "provisional": True}


# --------------------------------------------------------------------------
# 3. Wind gate
# --------------------------------------------------------------------------
def wind_speed(u: Optional[float], v: Optional[float]) -> Optional[float]:
    if u is None or v is None or not (np.isfinite(u) and np.isfinite(v)):
        return None
    return float(math.hypot(u, v))


def wind_gate(speed_ms: Optional[float], source: Optional[str] = None,
              lo: float = WIND_MIN_MS, hi: float = WIND_MAX_MS) -> Dict[str, Any]:
    """3-12 m/s gate on matched 10 m wind. Missing wind is NOT a pass."""
    base = {"lo_ms": lo, "hi_ms": hi, "wind_source": source}
    if speed_ms is None or not np.isfinite(speed_ms):
        return {**base, "status": "unavailable", "gate": "unknown",
                "speed_ms": None, "reason": "no matched wind for this scene/time"}
    s = float(speed_ms)
    gate = "pass" if lo <= s <= hi else ("fail_low" if s < lo else "fail_high")
    msg = {"pass": "wind inside the usable window",
           "fail_low": "wind too low: slicks and look-alikes both unreliable",
           "fail_high": "wind too high: slick contrast is washed out"}[gate]
    return {**base, "status": "available", "gate": gate,
            "speed_ms": round(s, 3), "reason": msg}


def wind_from_metocean(field: Any, lat: float, lon: float, t: Any) -> Dict[str, Any]:
    """Adapter for app.drift.fields.MetoceanField (uses its own `covers`/`sample`).

    Reports coverage honestly; a synthetic field is flagged so the gate result is
    never presented as measured.
    """
    try:
        if not field.covers(lat, lon, t):
            return wind_gate(None)
        s = field.sample(lat, lon, t)
        sp = wind_speed(float(np.ravel(s["u_wind10"])[0]), float(np.ravel(s["v_wind10"])[0]))
    except Exception as exc:  # noqa: BLE001
        out = wind_gate(None)
        out["reason"] = "wind lookup failed: %s" % exc
        return out
    src = getattr(field, "source", None)
    out = wind_gate(sp, source=src)
    out["synthetic"] = bool(getattr(field, "synthetic", False))
    return out


# --------------------------------------------------------------------------
# 4. CA-CFAR dark-spot screen on a 100 m pyramid level
# --------------------------------------------------------------------------
def pixel_size_m(transform: Sequence[float], crs: str = "",
                 centre_lat: Optional[float] = None) -> float:
    a, b, _c, d, e, _f = transform
    if (crs or "").upper().endswith("4326"):
        lat = 0.0 if centre_lat is None else centre_lat
        mx = 111320.0 * math.cos(math.radians(lat))
        my = 110574.0
        return float(math.sqrt(abs(a * mx * e * my - b * mx * d * my)))
    return float(math.sqrt(abs(a * e - b * d)))


def block_mean_linear(db: np.ndarray, factor: int) -> np.ndarray:
    """NaN-aware block mean in LINEAR power, returned in dB."""
    f = max(int(factor), 1)
    lin = db_to_lin(db)
    lin[~np.isfinite(db)] = np.nan
    h, w = lin.shape
    H, W = (h // f) * f, (w // f) * f
    blocks = lin[:H, :W].reshape(H // f, f, W // f, f)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        m = np.nanmean(blocks, axis=(1, 3))
    return lin_to_db(m)


def _box_sum(a: np.ndarray, r: int) -> np.ndarray:
    """Sum over a (2r+1) square, zero outside the image (integral image)."""
    ii = np.pad(a, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    h, w = a.shape
    y0 = np.clip(np.arange(h) - r, 0, h)
    y1 = np.clip(np.arange(h) + r + 1, 0, h)
    x0 = np.clip(np.arange(w) - r, 0, w)
    x1 = np.clip(np.arange(w) + r + 1, 0, w)
    return (ii[np.ix_(y1, x1)] - ii[np.ix_(y0, x1)]
            - ii[np.ix_(y1, x0)] + ii[np.ix_(y0, x0)])


def ca_cfar_dark(db: np.ndarray, guard: int = CFAR_GUARD, train: int = CFAR_TRAIN,
                 thresh_db: float = CFAR_THRESH_DB) -> np.ndarray:
    """Boolean mask of cells darker than their local clutter mean by `thresh_db`.

    Clutter = mean linear power over the ring between half-widths `guard` and
    `guard + train` (cell averaging, NaN cells excluded). Cells with an empty
    ring are never flagged.
    """
    lin = db_to_lin(db)
    valid = np.isfinite(db)
    lin = np.where(valid, lin, 0.0)
    v = valid.astype(np.float64)
    rg, ro = guard, guard + train
    s_ring = _box_sum(lin, ro) - _box_sum(lin, rg)
    n_ring = _box_sum(v, ro) - _box_sum(v, rg)
    with np.errstate(divide="ignore", invalid="ignore"):
        clutter = s_ring / n_ring
        ratio_db = 10.0 * np.log10(np.where(lin > 0, lin, np.nan) / clutter)
    ok = valid & (n_ring > 0) & np.isfinite(ratio_db)
    return ok & (ratio_db < thresh_db)


def cfar_screen(vv_db: np.ndarray, transform: Sequence[float], crs: str = "EPSG:4326",
                centre_lat: Optional[float] = None, min_cells: int = 3,
                guard: int = CFAR_GUARD, train: int = CFAR_TRAIN,
                thresh_db: float = CFAR_THRESH_DB) -> Dict[str, Any]:
    """Run the screen and report candidate windows plus the retained fraction."""
    params = {"guard": guard, "train": train, "threshold_db": thresh_db,
              "pyramid_pixel_m": CFAR_PIXEL_M, "min_cells": min_cells,
              "provisional": True}
    arr = np.asarray(vv_db, dtype=np.float64)
    if arr.ndim != 2 or arr.size == 0 or not np.isfinite(arr).any():
        return {"status": "unavailable", "reason": "no finite pixels", "params": params}
    if _ndi is None:
        return {"status": "unavailable", "reason": "scipy not installed", "params": params}

    px = pixel_size_m(transform, crs, centre_lat)
    if not np.isfinite(px) or px <= 0:
        return {"status": "unavailable", "reason": "invalid pixel size", "params": params}
    factor = max(int(round(CFAR_PIXEL_M / px)), 1)
    params["native_pixel_m"] = round(px, 3)
    params["block_factor"] = factor

    level = block_mean_linear(arr, factor)
    hit = ca_cfar_dark(level, guard, train, thresh_db)
    lab, n = _ndi.label(hit, structure=np.ones((3, 3)))
    windows: List[Dict[str, Any]] = []
    a, b, c, d, e, f = transform
    for i, sl in enumerate(_ndi.find_objects(lab), start=1):
        cells = int((lab[sl] == i).sum())
        if cells < min_cells:
            continue
        r0, r1 = sl[0].start * factor, sl[0].stop * factor
        c0, c1 = sl[1].start * factor, sl[1].stop * factor
        windows.append({"id": len(windows) + 1, "cells": cells,
                        "row_range": [int(r0), int(r1)], "col_range": [int(c0), int(c1)],
                        "native_bounds_xy": [a * c0 + b * r0 + c, d * c0 + e * r0 + f,
                                             a * c1 + b * r1 + c, d * c1 + e * r1 + f]})
    kept = sum(w["cells"] for w in windows)
    valid_cells = int(np.isfinite(level).sum())
    frac = (kept / valid_cells) if valid_cells else None
    return {"status": "available", "params": params, "windows": windows,
            "n_windows": len(windows), "valid_cells": valid_cells,
            "retained_cells": int(kept),
            "retained_fraction": None if frac is None else round(float(frac), 5),
            "pixel_reduction": None if frac is None else round(1.0 - float(frac), 5),
            "note": "Reduction is measured on this scene only; not a general claim."}


# --------------------------------------------------------------------------
# 5. Orchestrator
# --------------------------------------------------------------------------
def run_stage1(vv_db: np.ndarray, transform: Sequence[float], crs: str,
               source: str = "", incidence_deg: Optional[Any] = None,
               wind_ms: Optional[float] = None, wind_source: Optional[str] = None,
               centre_lat: Optional[float] = None) -> Dict[str, Any]:
    """One status document for the whole of Stage 1 (feeds the stage_status API)."""
    prod = classify_product(source)
    norm = normalize_incidence(vv_db, incidence_deg)
    gate = wind_gate(wind_ms, wind_source)
    cfar = cfar_screen(norm["array_db"], transform, crs, centre_lat)
    parts = [prod["status"], norm["status"], gate["status"], cfar["status"]]
    if all(p == "available" for p in parts):
        overall = "available"
    elif cfar["status"] == "unavailable":
        overall = "unavailable"
    else:
        overall = "partial"
    warnings = []
    if gate["gate"] in ("fail_low", "fail_high"):
        warnings.append("wind gate failed: detections in this scene are low confidence")
    if gate["gate"] == "unknown":
        warnings.append("wind gate unknown: do not treat this scene as validated")
    if norm["status"] != "available":
        warnings.append("incidence normalisation not applied: " + norm.get("reason", ""))
    norm_out = {k: v for k, v in norm.items() if k != "array_db"}
    return {"stage": "ingest", "status": overall, "product": prod,
            "incidence_normalization": norm_out, "wind_gate": gate,
            "cfar": cfar, "warnings": warnings}


def for_scene(scene: Any, t_sat: Optional[Any] = None, sar: Optional[Any] = None) -> Dict[str, Any]:
    """Run Stage 1 for a registry Scene. Never raises: a failure becomes `unavailable`.

    Wind comes from the scene's own cached metocean cube (never a synthetic
    fallback), sampled at the acquisition time and the chip centre.
    """
    try:
        from pathlib import Path
        from . import config, scenes as scenes_mod
        from .drift import fields as fields_mod

        if sar is None:
            sar = scenes_mod.load_raster(scene)
        clon, clat = sar.centre_lonlat()
        cube = Path(config.METOCEAN_DIR) / (scene.id + ".npz")
        if cube.exists():
            wind = wind_from_metocean(fields_mod.load_npz(cube), clat, clon,
                                      t_sat or scene.t_sat)
        else:
            wind = wind_gate(None)
            wind["reason"] = "no metocean cache file %s" % cube.name
        doc = run_stage1(sar.array[0], sar.transform, sar.crs, source=scene.source,
                         incidence_deg=None, wind_ms=wind.get("speed_ms"),
                         wind_source=wind.get("wind_source"), centre_lat=clat)
        doc["wind_gate"] = wind
        if wind.get("gate") == "unknown":
            doc["status"] = "partial" if doc["cfar"]["status"] == "available" else "unavailable"
        return doc
    except Exception as exc:  # noqa: BLE001 - Stage 1 must never break the pipeline
        return {"stage": "ingest", "status": "unavailable",
                "warnings": ["stage 1 could not run: %s" % exc]}
