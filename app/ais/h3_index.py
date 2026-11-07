"""H3 resolution-7 pre-index for the AIS candidate funnel (M4, Stage 4).

Purpose
-------
Give every candidate track a set of H3 cells (for the Stage 4 `h3_cells` field)
and provide a cheap cell-overlap pre-check that is checked AGAINST the exact
filter in app/ais/filter.py. H3 never decides who is a candidate: the exact
metre-based test stays authoritative. The zone cells are built conservatively
(a superset of the search radius), so a vessel the exact filter keeps can only
be missed if a track sample was never inside a cell the vessel actually
crossed. The consistency report below makes any such miss visible.

Works with h3-py v4 (latlng_to_cell, grid_disk) and falls back to v3 names.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import numpy as np

H3_RES = 7


def _h3():
    import h3  # imported lazily so the rest of the app runs without it

    return h3


def available() -> bool:
    """True when the optional h3 package can be imported."""
    try:
        _h3()
        return True
    except Exception:
        return False


def _cell_of(h3, lat: float, lon: float, res: int) -> str:
    fn = getattr(h3, "latlng_to_cell", None) or getattr(h3, "geo_to_h3")
    return fn(float(lat), float(lon), res)


def _disk(h3, cell: str, k: int) -> Set[str]:
    fn = getattr(h3, "grid_disk", None) or getattr(h3, "k_ring")
    return set(fn(cell, k))


def _edge_km(h3, res: int) -> float:
    fn = getattr(h3, "average_hexagon_edge_length", None)
    if fn is not None:
        return float(fn(res, unit="km"))
    return float(h3.edge_length(res, unit="km"))


def track_cells(lon: Sequence[float], lat: Sequence[float], res: int = H3_RES,
                mask: Optional[np.ndarray] = None) -> Set[str]:
    """Distinct H3 cells touched by the track samples (optionally masked)."""
    h3 = _h3()
    lon = np.asarray(lon, dtype=float)
    lat = np.asarray(lat, dtype=float)
    if mask is not None:
        lon, lat = lon[mask], lat[mask]
    return {_cell_of(h3, a, o, res) for o, a in zip(lon, lat)}


def cells_for_track(track, res: int = H3_RES, window: Optional[Tuple[int, int]] = None) -> List[str]:
    """Sorted list (deterministic) for the Stage 4 `h3_cells` field."""
    mask = None
    if window is not None:
        mask = (track.ts >= window[0]) & (track.ts <= window[1])
    return sorted(track_cells(track.lon, track.lat, res, mask))


def zone_cells(ring: Sequence[Tuple[float, float]], lon0: float, lat0: float,
               radius_km: float, res: int = H3_RES) -> Set[str]:
    """Cells covering the origin zone grown by radius_km, deliberately generous.

    k rings around the centre cell, with k sized from the farthest zone vertex
    plus the radius, plus one extra ring of safety margin.
    """
    from ..geo.crs import haversine_km

    h3 = _h3()
    extent_km = 0.0
    if ring:
        d = haversine_km(lat0, lon0, np.array([p[1] for p in ring]), np.array([p[0] for p in ring]))
        extent_km = float(np.max(d))
    reach_km = float(radius_km) + extent_km
    # Conservative ring count. On a hex grid a cell k steps from the centre lies at least
    # 1.5 * edge * k / safety from it, and a point sits within one (largest) edge of its
    # cell centre. H3 edge lengths vary by cell, so a 1.3 safety factor is applied both ways.
    edge = _edge_km(h3, res)
    safety = 1.3
    k = int(math.ceil((reach_km + safety * edge) / (1.5 * edge / safety))) + 1
    return _disk(h3, _cell_of(h3, lat0, lon0, res), k)


def prefilter(tracks: Dict[int, Any], ring: Sequence[Tuple[float, float]], lon0: float, lat0: float,
              radius_km: float, res: int = H3_RES,
              window: Optional[Tuple[int, int]] = None) -> Set[int]:
    """MMSIs whose track cells overlap the zone cells."""
    zone = zone_cells(ring, lon0, lat0, radius_km, res)
    keep: Set[int] = set()
    for mmsi, tr in tracks.items():
        mask = None
        if window is not None:
            mask = (tr.ts >= window[0]) & (tr.ts <= window[1])
        if track_cells(tr.lon, tr.lat, res, mask) & zone:
            keep.add(int(mmsi))
    return keep


def consistency_report(tracks: Dict[int, Any], ring: Sequence[Tuple[float, float]], lon0: float, lat0: float,
                       radius_km: float, res: int = H3_RES,
                       window: Optional[Tuple[int, int]] = None) -> Dict[str, Any]:
    """Compare the H3 pre-check with the exact distance test.

    `missed` lists vessels the exact filter keeps but H3 drops. It must be empty.
    """
    from .filter import _min_distance

    h3_keep = prefilter(tracks, ring, lon0, lat0, radius_km, res, window)
    exact_keep: Set[int] = set()
    for mmsi, tr in tracks.items():
        mask = None
        if window is not None:
            mask = (tr.ts >= window[0]) & (tr.ts <= window[1])
        d, _ = _min_distance(tr, list(ring), lon0, lat0, mask=mask)
        if d <= float(radius_km):
            exact_keep.add(int(mmsi))
    missed = sorted(exact_keep - h3_keep)
    return {
        "resolution": res,
        "vessels": len(tracks),
        "exact_kept": len(exact_keep),
        "h3_kept": len(h3_keep),
        "missed_by_h3": missed,
        "h3_extra": len(h3_keep - exact_keep),
        "consistent": not missed,
    }
