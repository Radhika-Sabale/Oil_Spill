"""Dataset-independent tests for M3 ensemble envelope summaries."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

pytestmark = pytest.mark.synthetic_data


def _run():
    from app.drift.advection import EnsembleRun

    t0 = datetime(2024, 2, 14, tzinfo=timezone.utc)
    lon = np.array([[71.50, 71.51], [72.00, 72.01], [72.50, 72.51]])
    lat = np.array([[19.00, 19.01], [19.10, 19.11], [19.20, 19.21]])
    return EnsembleRun(
        times=[t0 + timedelta(hours=i) for i in range(3)],
        lon=lon,
        lat=lat,
        direction="forward",
        spread_km=np.array([0.5, 1.0, 1.5]),
        mean_lon=np.median(lon, axis=1),
        mean_lat=np.median(lat, axis=1),
        meta={},
    )


def test_percentile_ring_trims_a_distant_particle_and_closes_the_hull():
    from app.drift.cone import percentile_ring

    lons = np.array([71.50, 71.51, 71.52, 71.53, 85.0])
    lats = np.array([19.00, 19.01, 19.02, 19.01, 30.0])

    ring = percentile_ring(lons, lats, pct=60.0)

    assert len(ring) >= 4
    assert ring[0] == ring[-1]
    assert max(lon for lon, _ in ring) < 72.0


def test_swept_cone_respects_requested_indices_and_threatened_bounds():
    from app.drift.cone import swept_cone, threatened_bbox

    run = _run()
    ring = swept_cone(run, step=2, pct=100.0)

    assert min(lon for lon, _ in ring) == pytest.approx(71.50)
    assert max(lon for lon, _ in ring) == pytest.approx(72.51)
    assert threatened_bbox(run) == {
        "west": 71.5,
        "south": 19.0,
        "east": 72.51,
        "north": 19.21,
    }


def test_hourly_envelopes_preserve_times_particle_medians_and_spread():
    from app.drift.cone import envelopes_by_hour

    run = _run()
    envelopes = envelopes_by_hour(run, pct=100.0)

    assert [item["index"] for item in envelopes] == [0, 1, 2]
    assert [item["t"] for item in envelopes] == [t.isoformat() for t in run.times]
    assert envelopes[1]["lon"] == 72.005
    assert envelopes[1]["lat"] == 19.105
    assert [item["spread_km"] for item in envelopes] == [0.5, 1.0, 1.5]
