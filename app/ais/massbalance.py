"""Assumption-bounded slick volume and derived flow ranges.

volume_m3 = area_km2 * 1e6 m2/km2 * thickness_um * 1e-6 m/um = area_km2 * thickness_um

The thickness band is an ILLUSTRATIVE, UNSOURCED assumption (min, nominal, max in
micrometres). SAR cannot measure thickness. Replace the band with sourced
values (for example Bonn Agreement appearance classes) before using any number
as evidence. Override with TIDETRACE_THICKNESS_UM="min,nominal,max".

derived flow = volume / loiter hours. It answers "what release rate would this
volume imply if it all came from this vessel during its time near the origin
zone", which is a strong assumption and is stated as one. Anything that cannot
be computed is returned as null with a reason, never as zero or a guess.
"""
from __future__ import annotations

import math
import os
from typing import List, Optional, Tuple

DEFAULT_THICKNESS_UM = (0.1, 1.0, 10.0)
MIN_LOITER_HOURS = 1.0 / 60.0

Range = dict


def _null_range() -> Range:
    return {"min": None, "nominal": None, "max": None}


def thickness_band(override: Optional[Tuple[float, float, float]] = None) -> Tuple[float, float, float]:
    band = override
    if band is None:
        raw = os.environ.get("TIDETRACE_THICKNESS_UM", "").strip()
        if raw:
            try:
                band = tuple(float(x) for x in raw.split(","))  # type: ignore[assignment]
            except ValueError:
                band = None
    if band is None or len(band) != 3:
        return DEFAULT_THICKNESS_UM
    lo, nom, hi = band
    if not (0.0 < lo <= nom <= hi) or not all(math.isfinite(x) for x in band):
        return DEFAULT_THICKNESS_UM
    return (float(lo), float(nom), float(hi))


def slick_volume(area_km2: Optional[float],
                 thickness_um: Optional[Tuple[float, float, float]] = None
                 ) -> Tuple[Range, List[str], Optional[str]]:
    """Return (range m3, assumptions, reason-if-unavailable)."""
    try:
        area = float(area_km2) if area_km2 is not None else float("nan")
    except (TypeError, ValueError):
        area = float("nan")
    if not math.isfinite(area) or area <= 0.0:
        return _null_range(), [], "slick area is unavailable"
    lo, nom, hi = thickness_band(thickness_um)
    rng = {"min": round(area * lo, 4), "nominal": round(area * nom, 4), "max": round(area * hi, 4)}
    assumptions = [
        "Slick thickness assumed %.2g to %.2g um (nominal %.2g um): illustrative and unsourced; "
        "SAR cannot measure thickness." % (lo, hi, nom),
        "Volume = detected slick area x assumed thickness; the area is the SAR polygon, not a "
        "measured oil volume.",
    ]
    return rng, assumptions, None


def derived_flow(volume: Range, loiter_hours: Optional[float]) -> Tuple[Range, List[str], Optional[str]]:
    """Return (range m3/h, assumptions, reason-if-unavailable)."""
    if volume is None or volume.get("nominal") is None:
        return _null_range(), [], "slick volume is unavailable"
    try:
        hours = float(loiter_hours) if loiter_hours is not None else float("nan")
    except (TypeError, ValueError):
        hours = float("nan")
    if not math.isfinite(hours) or hours < MIN_LOITER_HOURS:
        return _null_range(), [], "candidate has no usable time near the origin zone in the window"
    rng = {k: round(float(volume[k]) / hours, 4) for k in ("min", "nominal", "max")}
    assumptions = [
        "Derived flow = assumed slick volume / %.2f h this vessel spent within the search radius "
        "of the origin zone. It assumes the whole slick came from this vessel in that interval, "
        "which is not established." % hours,
    ]
    return rng, assumptions, None
