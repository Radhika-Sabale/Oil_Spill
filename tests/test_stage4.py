"""Stage 4: reachability, mass balance and the assembled Contract C result."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

T0 = datetime(2024, 2, 14, 0, 0, tzinfo=timezone.utc)
LON0, LAT0 = 71.45, 19.00
RING = [(LON0 - 0.01, LAT0 - 0.01), (LON0 + 0.01, LAT0 - 0.01),
        (LON0 + 0.01, LAT0 + 0.01), (LON0 - 0.01, LAT0 + 0.01), (LON0 - 0.01, LAT0 - 0.01)]
RADIUS_KM = 5.0
T_START = int(T0.timestamp())
T_END = int((T0 + timedelta(minutes=240)).timestamp())
T_ORIGIN = int((T0 + timedelta(minutes=118)).timestamp())


def _rows(points, mmsi, name):
    out = []
    for m, lon, lat in points:
        ts = int((T0 + timedelta(minutes=m)).timestamp())
        out.append({
            "mmsi": mmsi, "ts": ts,
            "base_date_time": datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
            "lat": lat, "lon": lon, "sog": 12.0, "cog": 90.0, "heading": 90.0,
            "vessel_name": name, "imo": "IMO1234567", "call_sign": "TEST", "vessel_type": "80",
            "status": "0", "length": 250.0, "width": 44.0, "draft": 13.0, "cargo": "80",
            "source": "unit_test_synthetic",
        })
    return out


def _track(mmsi, name, lat_offset=0.0, skip=()):
    from app.ais.interpolate import resample

    pts = [(m, 71.30 + 0.30 * m / 235.0, LAT0 + lat_offset) for m in range(0, 240, 5) if m not in skip]
    return resample(_rows(pts, mmsi, name), T_START, T_END, step_seconds=60, gap_minutes=30.0)


def _case():
    """A crosses the zone, B is far away, C crosses with a 55 minute AIS gap beside the zone."""
    from app.ais import score as ais_score
    from app.ais.filter import FilterResult, _min_distance

    tracks = {
        419000001: _track(419000001, "SYNTH A"),
        419000002: _track(419000002, "SYNTH B", lat_offset=1.5),
        419000003: _track(419000003, "SYNTH C", skip=set(range(100, 150, 5))),
    }
    closest = {m: _min_distance(t, RING, LON0, LAT0) for m, t in tracks.items()}
    res = FilterResult(tracks, closest, len(tracks), 0, 0, (T_START, T_END), (0, 0, 0, 0))
    suspects = ais_score.rank_suspects(tracks, closest, RING, LON0, LAT0, LON0, LAT0,
                                       t_origin_ts=T_ORIGIN, zone_radius_km=2.0, top_n=10)
    return res, suspects


def _build(**kw):
    from app.ais.stage4 import build_stage4

    res, suspects = _case()
    args = dict(slick_area_km2=2.0, incident_id="DEMO-001", case_type="synthetic_demo")
    args.update(kw)
    return build_stage4(res, suspects, RING, LON0, LAT0, RADIUS_KM, **args)


# ----------------------------------------------------------------- mass balance

def test_volume_is_area_times_thickness():
    from app.ais.massbalance import slick_volume

    rng, assumptions, reason = slick_volume(2.0, (0.1, 1.0, 10.0))
    assert reason is None
    assert (rng["min"], rng["nominal"], rng["max"]) == (0.2, 2.0, 20.0)
    assert any("unsourced" in a for a in assumptions)


@pytest.mark.parametrize("bad", [None, 0, -1.0, float("nan"), "abc"])
def test_volume_unavailable_stays_null(bad):
    from app.ais.massbalance import slick_volume

    rng, assumptions, reason = slick_volume(bad)
    assert rng == {"min": None, "nominal": None, "max": None}
    assert reason and assumptions == []


def test_flow_divides_volume_by_hours_and_keeps_order():
    from app.ais.massbalance import derived_flow

    vol = {"min": 0.2, "nominal": 2.0, "max": 20.0}
    rng, _, reason = derived_flow(vol, 2.0)
    assert reason is None
    assert (rng["min"], rng["nominal"], rng["max"]) == (0.1, 1.0, 10.0)
    assert rng["min"] <= rng["nominal"] <= rng["max"]


@pytest.mark.parametrize("hours", [None, 0, -3, 0.001, float("nan")])
def test_flow_without_usable_time_is_null(hours):
    from app.ais.massbalance import derived_flow

    rng, _, reason = derived_flow({"min": 0.2, "nominal": 2.0, "max": 20.0}, hours)
    assert rng == {"min": None, "nominal": None, "max": None} and reason


def test_flow_without_volume_is_null():
    from app.ais.massbalance import derived_flow

    rng, _, reason = derived_flow({"min": None, "nominal": None, "max": None}, 2.0)
    assert rng["nominal"] is None and reason


# ----------------------------------------------------------------- reachability

def test_gap_beside_zone_cannot_be_excluded_at_normal_speed():
    from app.ais.reachability import gap_reachability

    tr = _track(419000003, "SYNTH C", skip=set(range(100, 150, 5)))
    r = gap_reachability(tr, RING, LON0, LAT0)
    assert r["status"] == "gap_cannot_exclude_zone"
    assert len(r["gaps"]) == 1 and r["gaps"][0]["status"] == "not_excluded"
    assert "not evidence of intent" in r["assumption"]


def test_same_gap_is_excluded_when_the_vessel_is_assumed_very_slow():
    from app.ais.reachability import gap_reachability

    tr = _track(419000003, "SYNTH C", skip=set(range(100, 150, 5)))
    r = gap_reachability(tr, RING, LON0, LAT0, max_speed_kn=2.0)
    assert r["status"] == "gaps_exclude_zone"


def test_no_gap_means_no_gap_status():
    from app.ais.reachability import gap_reachability

    assert gap_reachability(_track(419000001, "SYNTH A"), RING, LON0, LAT0)["status"] == "no_gaps"


# ------------------------------------------------------------------- stage 4

CONTRACT_C_KEYS = {
    "mmsi", "vessel_name", "time_overlap_minutes", "distance_to_origin_km", "speed_change_knots",
    "signals", "score", "score_explanation", "evidence_quality", "h3_cells", "dark_target_match",
    "slick_volume_m3", "derived_flow_m3_h", "assumptions", "unavailable_features",
}


def test_candidates_follow_contract_c_and_rank_order():
    st = _build()
    assert st["incident_id"] == "DEMO-001" and st["case_type"] == "synthetic_demo"
    assert st["candidates"]
    for c in st["candidates"]:
        assert CONTRACT_C_KEYS <= set(c)
        assert 0.0 <= c["score"] <= 1.0
        assert c["evidence_quality"] in {"low", "medium", "high"}
    ranks = [c["evidence"]["rank"] for c in st["candidates"]]
    assert ranks == sorted(ranks)


def test_the_crossing_vessel_has_overlap_and_the_far_vessel_has_none():
    st = _build()
    by = {c["mmsi"]: c for c in st["candidates"]}
    a, b = by["419000001"], by["419000002"]
    assert 80.0 <= a["time_overlap_minutes"] <= 100.0
    assert b["time_overlap_minutes"] == 0.0
    assert b["derived_flow_m3_h"] == {"min": None, "nominal": None, "max": None}
    assert any(u.startswith("derived_flow_m3_h") for u in b["unavailable_features"])


def test_flow_matches_volume_over_overlap_hours():
    a = {c["mmsi"]: c for c in _build()["candidates"]}["419000001"]
    hours = a["time_overlap_minutes"] / 60.0
    assert a["derived_flow_m3_h"]["nominal"] == pytest.approx(a["slick_volume_m3"]["nominal"] / hours, abs=1e-3)


def test_dark_target_is_unavailable_with_a_reason_and_never_a_no_vessel_claim():
    for c in _build()["candidates"]:
        d = c["dark_target_match"]
        assert d["status"] == "unavailable" and d["reason"]
        assert "not evidence that no vessel" in d["reason"]
        assert any(u.startswith("dark_target_match") for u in c["unavailable_features"])


def test_missing_slick_area_keeps_volume_and_flow_null():
    st = _build(slick_area_km2=None)
    assert st["stage4_status"]["mass_balance"] == "unavailable"
    for c in st["candidates"]:
        assert c["slick_volume_m3"] == {"min": None, "nominal": None, "max": None}
        assert c["derived_flow_m3_h"] == {"min": None, "nominal": None, "max": None}


def test_gap_candidate_carries_reachability_and_the_not_intent_caveat():
    c = {c["mmsi"]: c for c in _build()["candidates"]}["419000003"]
    assert c["evidence"]["reachability"]["status"] == "gap_cannot_exclude_zone"
    assert any("missing_broadcast_not_intent" in s for s in c["signals"])


def test_simulated_sources_force_synthetic_case_type():
    st = _build(case_type="real_historical", sources_used={"gulf_simulated": 3})
    assert st["case_type"] == "synthetic_demo"


def test_output_is_deterministic_and_makes_no_guilt_claim():
    a = json.dumps(_build(), sort_keys=True)
    b = json.dumps(_build(), sort_keys=True)
    assert a == b
    low = a.lower()
    assert "guilty" not in low and "culprit" not in low
    assert "not proof of causation or a finding of guilt" in low


def test_h3_cells_are_filled_only_when_h3_is_installed():
    from app.ais import h3_index

    st = _build()
    if h3_index.available():
        assert st["stage4_status"]["h3"] == "implemented"
        assert st["h3"]["consistent"] is True and st["h3"]["missed_by_h3"] == []
        a = {c["mmsi"]: c for c in st["candidates"]}["419000001"]
        assert a["h3_cells"] == sorted(a["h3_cells"]) and a["h3_cells"]
    else:
        assert st["stage4_status"]["h3"] == "unavailable"
        assert all(c["h3_cells"] == [] for c in st["candidates"])


def test_result_validates_against_the_schema():
    pytest.importorskip("pydantic")
    from app.schemas import Stage4Verdict

    Stage4Verdict.model_validate(_build())
