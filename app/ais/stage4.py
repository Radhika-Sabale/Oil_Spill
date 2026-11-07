"""Stage 4 forensics: assemble Contract C (attribution verdict) from the ranked suspects.

Nothing here changes the ranking. It takes the suspects and tracks the existing
pipeline already produced and adds the evidence fields the roadmap asks for:
H3 cells and an H3-versus-direct-filter consistency check, gap reachability,
a dark-target status, and assumption-bounded volume and flow ranges.

Rules kept throughout: unknowns stay null and carry a reason; every assumption
is listed; the score is a prioritisation aid, never a probability of guilt.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import h3_index, massbalance, reachability

log = logging.getLogger("tidetrace.stage4")

CONCLUSION = "Investigative candidates only; not proof of causation or a finding of guilt"

DARK_TARGET_UNAVAILABLE = {
    "status": "unavailable",
    "reason": ("No SAR vessel-detection stage exists in this build, so AIS tracks cannot be compared "
               "with radar targets. Absence of a detection is not evidence that no vessel was there."),
    "confidence": None,
}

EVIDENCE_QUALITY_RULE = ("low: sparse coverage, fewer than 6 receptions or track confidence < 0.5; "
                         "high: track confidence >= 0.8; otherwise medium")


def _case_type(case_type: str, sources_used: Optional[Dict[str, int]]) -> str:
    for key in (sources_used or {}):
        k = str(key).lower()
        if "simulated" in k or "synthetic" in k or "selftest" in k:
            return "synthetic_demo"
    return case_type


def _overlap_minutes(track, ring, lon0: float, lat0: float, radius_km: float,
                     window: Tuple[int, int]) -> Tuple[float, float]:
    """Minutes inside the search radius during the window: (all samples, received only)."""
    from ..geo.crs import haversine_km
    from ..geo.geometry import ring_distances_km

    m = (track.ts >= window[0]) & (track.ts <= window[1])
    if not m.any():
        return 0.0, 0.0
    if ring:
        d = ring_distances_km(track.lon[m], track.lat[m], list(ring))
    else:
        d = np.asarray(haversine_km(lat0, lon0, track.lat[m], track.lon[m]), dtype=float)
    inside = d <= float(radius_km)
    step_min = float((track.meta or {}).get("step_seconds", 60)) / 60.0
    received = ~np.asarray(track.dead_reckoned, dtype=bool)[m]
    return (round(int(inside.sum()) * step_min, 1),
            round(int((inside & received).sum()) * step_min, 1))


def _quality(confidence: float, raw_positions: int, sparse: bool) -> str:
    if sparse or confidence < 0.5 or raw_positions < 6:
        return "low"
    return "high" if confidence >= 0.8 else "medium"


def _explanation(s) -> str:
    parts = ", ".join("%s=%.3f" % (k, v) for k, v in sorted(s.weighted.items()))
    return ("Prioritisation aid only, not a probability of guilt. Weighted components: %s; "
            "track confidence x%.2f; score %.1f of 100." % (parts, s.confidence, s.score))


def build_stage4(res, suspects: Sequence[Any], ring: Sequence[Tuple[float, float]],
                 lon0: float, lat0: float, radius_km: float,
                 slick_area_km2: Optional[float] = None, incident_id: Optional[str] = None,
                 case_type: str = "manual_demo", sources_used: Optional[Dict[str, int]] = None,
                 thickness_um: Optional[Tuple[float, float, float]] = None,
                 max_speed_kn: Optional[float] = None, h3_res: int = h3_index.H3_RES) -> Dict[str, Any]:
    """Build the Stage 4 result. `res` is the FilterResult from ais.filter.candidates."""
    window = tuple(res.window)
    ring = list(ring) if ring else []
    h3_ok = h3_index.available()

    h3_report: Dict[str, Any]
    if h3_ok:
        h3_report = h3_index.consistency_report(res.tracks, ring, lon0, lat0, radius_km, h3_res, window)
        h3_report["status"] = "implemented"
        h3_report["note"] = ("H3 is a pre-index checked against the direct filter; the direct distance "
                             "test stays authoritative. Resolution %d, window-masked." % h3_res)
    else:
        h3_report = {"status": "unavailable", "resolution": h3_res, "missed_by_h3": [],
                     "consistent": None, "note": "The optional h3 package is not installed."}

    vol_range, vol_assumptions, vol_reason = massbalance.slick_volume(slick_area_km2, thickness_um)

    candidates: List[Dict[str, Any]] = []
    for s in suspects:
        tr = res.tracks.get(s.mmsi)
        behavior = (s.detail or {}).get("behavior") or {}
        unavailable: List[str] = ["dark_target_match: " + DARK_TARGET_UNAVAILABLE["reason"]]
        assumptions: List[str] = []
        signals: List[str] = list(s.reasons)

        overlap = received_overlap = None
        cells: List[str] = []
        reach: Dict[str, Any] = {"status": "unavailable", "gaps": [], "assumed_max_speed_kn": None}
        if tr is not None:
            overlap, received_overlap = _overlap_minutes(tr, ring, lon0, lat0, radius_km, window)
            if h3_ok:
                cells = h3_index.cells_for_track(tr, h3_res, window)
            reach = reachability.gap_reachability(tr, ring, lon0, lat0, max_speed_kn)
            if reach["gaps"]:
                assumptions.append(reach["assumption"])
                longest = max(g["minutes"] for g in reach["gaps"])
                signals.append("ais_gap_%dmin_origin_zone_%s_at_assumed_%.0fkn_missing_broadcast_not_intent"
                               % (round(longest),
                                  "not_excluded" if reach["status"] == "gap_cannot_exclude_zone" else "excluded",
                                  reach["assumed_max_speed_kn"]))
        if not h3_ok:
            unavailable.append("h3_cells: the optional h3 package is not installed")

        hours = None if overlap is None else overlap / 60.0
        flow_range, flow_assumptions, flow_reason = massbalance.derived_flow(vol_range, hours)
        assumptions += vol_assumptions + flow_assumptions
        if vol_reason:
            unavailable.append("slick_volume_m3: " + vol_reason)
        if flow_reason:
            unavailable.append("derived_flow_m3_h: " + flow_reason)

        candidates.append({
            "mmsi": str(s.mmsi).zfill(9),
            "vessel_name": s.name or None,
            "time_overlap_minutes": overlap,
            "distance_to_origin_km": (s.detail or {}).get("origin_distance_km"),
            "speed_change_knots": behavior.get("speed_swing_kn"),
            "signals": signals,
            "score": round(float(s.score) / 100.0, 4),
            "score_explanation": _explanation(s),
            "evidence_quality": _quality(float(s.confidence), int((s.detail or {}).get("raw_positions") or 0),
                                         bool(behavior.get("ais_gap_is_sparse_coverage"))),
            "h3_cells": cells,
            "dark_target_match": dict(DARK_TARGET_UNAVAILABLE),
            "slick_volume_m3": dict(vol_range),
            "derived_flow_m3_h": flow_range,
            "assumptions": assumptions,
            "unavailable_features": unavailable,
            "evidence": {
                "rank": int(s.rank),
                "time_overlap_received_minutes": received_overlap,
                "reachability": reach,
                "evidence_quality_rule": EVIDENCE_QUALITY_RULE,
            },
        })

    return {
        "incident_id": incident_id,
        "case_type": _case_type(case_type, sources_used),
        "candidates": candidates,
        "conclusion": CONCLUSION,
        "stage4_status": {
            "h3": h3_report["status"],
            "reachability": "implemented",
            "dark_target": "unavailable",
            "mass_balance": "unavailable" if vol_reason else "illustrative",
        },
        "h3": h3_report,
        "slick": {"area_km2": None if slick_area_km2 is None else round(float(slick_area_km2), 4),
                  "volume_m3": dict(vol_range), "volume_unavailable_reason": vol_reason},
        "parameters": {"search_radius_km": float(radius_km),
                       "window_start_ts": int(window[0]), "window_end_ts": int(window[1]),
                       "h3_resolution": h3_res},
    }
