"""H3 pre-index must never drop a vessel the exact filter keeps."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

pytest.importorskip("h3")

T0 = datetime(2024, 2, 14, 0, 0, tzinfo=timezone.utc)
LON0, LAT0 = 71.45, 19.00
RING = [(LON0 - 0.01, LAT0 - 0.01), (LON0 + 0.01, LAT0 - 0.01),
        (LON0 + 0.01, LAT0 + 0.01), (LON0 - 0.01, LAT0 + 0.01), (LON0 - 0.01, LAT0 - 0.01)]
RADIUS_KM = 5.0
T_START = int(T0.timestamp())
T_END = int((T0 + timedelta(minutes=240)).timestamp())


def _rows(points, mmsi):
    out = []
    for m, lon, lat in points:
        ts = int((T0 + timedelta(minutes=m)).timestamp())
        out.append({
            "mmsi": mmsi, "ts": ts,
            "base_date_time": datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
            "lat": lat, "lon": lon, "sog": 10.0, "cog": 90.0, "heading": 90.0,
            "vessel_name": "V%d" % mmsi, "imo": "IMO1234567", "call_sign": "TEST", "vessel_type": "80",
            "status": "0", "length": 250.0, "width": 44.0, "draft": 13.0, "cargo": "80",
            "source": "unit_test_synthetic",
        })
    return out


def _track(mmsi, lat_offset_deg, lon_start=71.30, lon_end=71.60):
    from app.ais.interpolate import resample

    minutes = list(range(0, 240, 5))
    pts = [(m, lon_start + (lon_end - lon_start) * m / 235.0, LAT0 + lat_offset_deg) for m in minutes]
    return resample(_rows(pts, mmsi), T_START, T_END, step_seconds=60, gap_minutes=30.0)


def test_cells_are_deterministic_and_sorted():
    from app.ais.h3_index import cells_for_track

    tr = _track(1, 0.0)
    a, b = cells_for_track(tr), cells_for_track(tr)
    assert a == b == sorted(a) and len(a) > 1


def test_crossing_vessel_kept_and_far_vessel_dropped():
    from app.ais.h3_index import prefilter

    tracks = {1: _track(1, 0.0), 2: _track(2, 1.5)}   # 1.5 deg lat is about 166 km away
    kept = prefilter(tracks, RING, LON0, LAT0, RADIUS_KM)
    assert 1 in kept and 2 not in kept


def test_h3_never_misses_an_exact_keeper_across_offsets():
    from app.ais.h3_index import consistency_report

    # Offsets straddle the 5 km radius (0.045 deg of latitude is about 5 km).
    offsets = np.linspace(-0.12, 0.12, 49)
    tracks = {100 + i: _track(100 + i, float(o)) for i, o in enumerate(offsets)}
    rep = consistency_report(tracks, RING, LON0, LAT0, RADIUS_KM)
    assert rep["missed_by_h3"] == []
    assert rep["consistent"] is True
    assert 0 < rep["exact_kept"] < rep["vessels"]


def test_window_mask_is_respected():
    from app.ais.h3_index import consistency_report

    tracks = {1: _track(1, 0.0)}
    # A window before the vessel gets near the zone: both tests must agree.
    early = (T_START, T_START + 10 * 60)
    rep = consistency_report(tracks, RING, LON0, LAT0, RADIUS_KM, window=early)
    assert rep["consistent"] is True


def test_empty_tracks():
    from app.ais.h3_index import consistency_report

    rep = consistency_report({}, RING, LON0, LAT0, RADIUS_KM)
    assert rep["vessels"] == 0 and rep["consistent"] is True
