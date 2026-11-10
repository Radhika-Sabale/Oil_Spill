"""An empty or non-covering AIS store must never read as 'no suspicious vessels'."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.ais import coverage

W0, W1 = 1_710_288_000, 1_710_309_600          # a 6 hour origin window
ISO = "%Y-%m-%dT%H:%M:%SZ"


def _iso(t):
    from datetime import datetime, timezone
    return datetime.fromtimestamp(t, tz=timezone.utc).strftime(ISO)


def _store(rows=100, t0=W0 - 3600, t1=W1 + 3600, vessels=5):
    if rows == 0:
        return {"rows": 0, "vessels": 0, "t_start": None, "t_end": None}
    return {"rows": rows, "vessels": vessels, "t_start": _iso(t0), "t_end": _iso(t1)}


def _res(considered=3, kept=2):
    return SimpleNamespace(window=(W0, W1), considered=considered, tracks={i: object() for i in range(kept)})


def test_missing_database_is_not_possible():
    c = coverage.assess(_store(0), _res(0, 0), db_existed=False)
    assert c["status"] == "database_missing" and c["attribution_status"] == "not_possible"
    assert "NOT a finding" in c["zero_suspects_means"]


def test_empty_database_is_not_possible():
    c = coverage.assess(_store(0), _res(0, 0))
    assert c["status"] == "database_empty" and c["attribution_status"] == "not_possible"


def test_store_outside_the_window_is_not_possible():
    c = coverage.assess(_store(t0=W1 + 7200, t1=W1 + 9000), _res(0, 0))
    assert c["status"] == "store_does_not_cover_window" and c["attribution_status"] == "not_possible"
    assert c["window_covered_fraction"] == 0.0


def test_window_covered_but_no_vessel_near_zone_is_not_possible():
    c = coverage.assess(_store(), _res(0, 0))
    assert c["status"] == "no_observations_in_window" and c["attribution_status"] == "not_possible"


def test_partial_time_coverage_is_incomplete():
    c = coverage.assess(_store(t0=W0 - 3600, t1=W0 + 3600), _res(3, 2))     # 1h of a 6h window
    assert c["status"] == "time_coverage_insufficient" and c["attribution_status"] == "incomplete"
    assert 0 < c["window_covered_fraction"] < 0.5


def test_vessels_nearby_but_none_within_radius_is_possible_but_not_a_census():
    c = coverage.assess(_store(), _res(4, 0))
    assert c["status"] == "no_vessel_within_radius" and c["attribution_status"] == "possible"
    assert "not a census" in c["zero_suspects_means"]


def test_candidates_available():
    c = coverage.assess(_store(), _res(3, 2))
    assert c["status"] == "candidates_available" and c["attribution_status"] == "possible"
    assert c["zero_suspects_means"] == "not_applicable"


def test_real_label_is_flagged_when_no_data_backs_it():
    c = coverage.assess(_store(0), _res(0, 0), declared_ais_mode="real")
    assert "source coverage" in c["label_warning"]
    ok = coverage.assess(_store(), _res(3, 2), declared_ais_mode="real")
    assert "label_warning" not in ok


def test_pipeline_reports_no_assessment_for_an_empty_store(tmp_path, monkeypatch):
    """Through the real run_attribution: an empty database cannot yield a clean 'no suspects'."""
    from datetime import datetime, timezone
    from app import config, pipeline

    monkeypatch.setattr(config, "AIS_SQLITE", tmp_path / "ais.sqlite")
    ring = [(71.44, 18.99), (71.46, 18.99), (71.46, 19.01), (71.44, 19.01), (71.44, 18.99)]
    t = datetime(2024, 3, 13, 0, 3, 42, tzinfo=timezone.utc)
    attr = pipeline.run_attribution(ring, 71.45, 19.0, t, 71.45, 19.0, radius_km=10.0, window_h=3.0)
    assert attr["suspects"] == []
    assert attr["ais_coverage"]["status"] == "database_missing"
    assert attr["ais_coverage"]["attribution_status"] == "not_possible"
    assert attr["stage4"]["stage4_status"]["ais"] == "database_missing"
    assert attr["stage4"]["candidates"] == []


def test_schema_rejects_candidates_when_ais_was_not_possible():
    pytest.importorskip("pydantic")
    from pydantic import ValidationError
    from app.schemas import Stage4Verdict

    ok = "Investigative candidates only; not proof of causation or a finding of guilt"
    cand = {"mmsi": "000000001", "score": 0.5, "score_explanation": "x", "evidence_quality": "low"}
    Stage4Verdict(case_type="synthetic_demo", conclusion=ok, candidates=[cand],
                  ais_coverage={"attribution_status": "possible"})
    with pytest.raises(ValidationError):
        Stage4Verdict(case_type="synthetic_demo", conclusion=ok, candidates=[cand],
                      ais_coverage={"attribution_status": "not_possible"})
