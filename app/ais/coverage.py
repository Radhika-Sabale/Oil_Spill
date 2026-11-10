"""Is there enough AIS data to say anything about vessels for this scene?

A scene can be labelled "real AIS" only because a public source covers its
footprint. That says nothing about whether this database holds observations for
this place and time. This module answers the second question, from what is
actually in the store, and returns a status the report, the API and the console
can all show.

An empty or non-covering store must never read as "we checked and found no
suspicious vessels". Only the last two statuses below allow any statement about
vessels at all.

    database_missing              no AIS database file existed
    database_empty                database exists, zero positions
    store_does_not_cover_window   observations exist, none in the origin window
    no_observations_in_window     window is covered but no vessel reported near the zone
    time_coverage_insufficient    store spans under half of the origin window
    no_vessel_within_radius       vessels reported near the zone, none within the radius
    candidates_available          vessels within the radius were scored
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

NOT_POSSIBLE = {"database_missing", "database_empty", "store_does_not_cover_window",
                "no_observations_in_window"}
INCOMPLETE = {"time_coverage_insufficient"}
MIN_WINDOW_COVER = 0.5


def _ts(iso: Optional[str]) -> Optional[int]:
    if not iso:
        return None
    try:
        return int(datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone(timezone.utc).timestamp())
    except ValueError:
        return None


def assess(store: Dict[str, Any], res, db_existed: bool = True,
           declared_ais_mode: Optional[str] = None) -> Dict[str, Any]:
    """`store` is ingest.stats(...).to_dict(); `res` is the FilterResult."""
    rows = int((store or {}).get("rows") or 0)
    w0, w1 = int(res.window[0]), int(res.window[1])
    t0, t1 = _ts((store or {}).get("t_start")), _ts((store or {}).get("t_end"))
    kept = len(res.tracks)
    considered = int(res.considered)

    cover = None
    if rows and t0 is not None and t1 is not None and w1 > w0:
        cover = max(0.0, min(w1, t1) - max(w0, t0)) / float(w1 - w0)

    if not db_existed:
        status = "database_missing"
        msg = "No AIS database existed, so no vessel was checked."
    elif rows == 0:
        status = "database_empty"
        msg = "The AIS database holds no observations, so no vessel was checked."
    elif cover is not None and cover == 0.0:
        status = "store_does_not_cover_window"
        msg = ("The AIS database has observations, but none inside the origin window, so no vessel "
               "was checked for this scene.")
    elif considered == 0:
        status = "no_observations_in_window"
        msg = ("The AIS database has no vessel reports near the origin zone during the origin window, "
               "so no vessel was checked.")
    elif cover is not None and cover < MIN_WINDOW_COVER:
        status = "time_coverage_insufficient"
        msg = ("The AIS database spans only %d%% of the origin window, so any ranking is incomplete."
               % round(cover * 100))
    elif kept == 0:
        status = "no_vessel_within_radius"
        msg = ("AIS reports exist near the zone during the window, but no vessel came within the search "
               "radius. This is not evidence that no vessel was present: AIS can be off, gapped or absent.")
    else:
        status = "candidates_available"
        msg = "AIS observations were available and vessels within the search radius were scored."

    if status in NOT_POSSIBLE:
        attribution, zero_means = "not_possible", ("no_assessment: AIS was unavailable, so zero suspects is "
                                                   "NOT a finding that no suspicious vessel was present")
    elif status in INCOMPLETE:
        attribution, zero_means = "incomplete", ("incomplete: partial AIS coverage, so absence of a suspect "
                                                 "proves nothing")
    elif status == "no_vessel_within_radius":
        attribution, zero_means = "possible", ("none_within_radius: AIS vessels were present nearby but none "
                                               "within the radius; AIS is not a census of vessels")
    else:
        attribution, zero_means = "possible", "not_applicable"

    out = {
        "status": status,
        "attribution_status": attribution,
        "message": msg,
        "zero_suspects_means": zero_means,
        "store_rows": rows,
        "store_vessels": int((store or {}).get("vessels") or 0),
        "store_time_range": [(store or {}).get("t_start"), (store or {}).get("t_end")],
        "window": [datetime.fromtimestamp(w0, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
                   datetime.fromtimestamp(w1, tz=timezone.utc).isoformat().replace("+00:00", "Z")],
        "window_covered_fraction": None if cover is None else round(cover, 3),
        "vessels_near_zone_in_window": considered,
        "vessels_within_radius": kept,
        "declared_ais_mode": declared_ais_mode,
    }
    if declared_ais_mode == "real" and attribution != "possible":
        out["label_warning"] = ("This scene is labelled real-AIS because a public source covers its footprint. "
                                "That describes source coverage, not data in this database.")
    return out
