"""Could a vessel have reached the origin zone during an AIS reporting gap?

This is a necessary-condition test, not a finding. A silent stretch of AIS is a
missing broadcast: it can be thin coverage, a failed transponder or simply a
long reporting interval. It is never treated here as evidence of intent.

For a gap from point A (last report) to point B (next report) lasting dt hours
at an assumed maximum speed v, the shortest path A -> zone -> B is at least
d(A, zone) + d(zone, B). If that sum exceeds v * dt, the zone could NOT have
been visited during the gap (status "excluded"). If it does not, the visit
"cannot be excluded", which is all this module ever says.

The assumed speed is an assumption and is returned with the result.
"""
from __future__ import annotations

import math
import os
from typing import Any, Dict, Optional, Sequence, Tuple

import numpy as np

KN_TO_KMH = 1.852


def _default_max_kn() -> float:
    try:
        return float(os.environ.get("TIDETRACE_REACH_MAX_KN", "20"))
    except ValueError:
        return 20.0


def _zone_distance_km(lon: float, lat: float, ring: Sequence[Tuple[float, float]],
                      lon0: float, lat0: float) -> float:
    from ..geo.crs import haversine_km
    from ..geo.geometry import ring_distances_km

    if ring:
        return float(ring_distances_km(np.array([lon], dtype=float), np.array([lat], dtype=float),
                                       list(ring))[0])
    return float(haversine_km(lat0, lon0, lat, lon))


def assumed_speed_kn(track, override: Optional[float] = None) -> float:
    """Assumed maximum speed: the larger of the default and the fastest received SOG."""
    if override is not None:
        return float(override)
    v = _default_max_kn()
    try:
        received = np.asarray(track.sog, dtype=float)[~np.asarray(track.dead_reckoned, dtype=bool)]
        received = received[np.isfinite(received)]
        if received.size:
            v = max(v, float(received.max()))
    except Exception:
        pass
    return v


def gap_reachability(track, ring: Sequence[Tuple[float, float]], lon0: float, lat0: float,
                     max_speed_kn: Optional[float] = None) -> Dict[str, Any]:
    v_kn = assumed_speed_kn(track, max_speed_kn)
    v_kmh = v_kn * KN_TO_KMH
    gaps_out = []
    for g in getattr(track, "gaps", []) or []:
        dt_h = float(g.minutes) / 60.0
        d_in = _zone_distance_km(g.start_lon, g.start_lat, ring, lon0, lat0)
        d_out = _zone_distance_km(g.end_lon, g.end_lat, ring, lon0, lat0)
        required = d_in + d_out
        budget = v_kmh * dt_h
        gaps_out.append({
            "start_ts": int(g.start_ts),
            "end_ts": int(g.end_ts),
            "minutes": round(float(g.minutes), 1),
            "required_km": round(required, 2),
            "budget_km": round(budget, 2),
            "status": "not_excluded" if required <= budget else "excluded",
        })

    if not gaps_out:
        status = "no_gaps"
    elif any(x["status"] == "not_excluded" for x in gaps_out):
        status = "gap_cannot_exclude_zone"
    else:
        status = "gaps_exclude_zone"

    return {
        "status": status,
        "assumed_max_speed_kn": round(v_kn, 1),
        "gaps": gaps_out,
        "assumption": ("Reachability uses an assumed maximum speed of %.1f kn (larger of the default and "
                       "the fastest received SOG) and straight-line distances. A gap is a missing "
                       "broadcast, not evidence of intent." % v_kn),
    }
