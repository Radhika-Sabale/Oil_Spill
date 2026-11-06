"""Stage 4 (M4) contract tests: Contract C from SentinelTrace_Team_Roadmap.md."""
import json

import pytest
from pydantic import ValidationError

from app.schemas import (STAGE4_CONCLUSION, DarkTargetMatch, Range3, Stage4Candidate,
                         Stage4Verdict)

ROADMAP_EXAMPLE = {
    "incident_id": "DEMO-001",
    "case_type": "synthetic_demo",
    "candidates": [{
        "mmsi": "000000000", "vessel_name": "Demo vessel A", "time_overlap_minutes": 20,
        "distance_to_origin_km": None, "speed_change_knots": None,
        "signals": ["Track overlaps the illustrative origin window"],
        "score": 0.0, "score_explanation": "Illustrative ranking only", "evidence_quality": "low",
        "h3_cells": [], "dark_target_match": None,
        "slick_volume_m3": {"min": None, "nominal": None, "max": None},
        "derived_flow_m3_h": {"min": None, "nominal": None, "max": None},
        "assumptions": [], "unavailable_features": [],
    }],
    "conclusion": "Investigative candidates only; not proof of causation or a finding of guilt",
}


def test_roadmap_example_is_valid_apart_from_null_dark_target():
    # The roadmap example shows dark_target_match as null; our model requires an explicit status.
    doc = json.loads(json.dumps(ROADMAP_EXAMPLE))
    doc["candidates"][0]["dark_target_match"] = {"status": "unavailable", "reason": "no SAR target stage"}
    v = Stage4Verdict.model_validate(doc)
    assert v.candidates[0].distance_to_origin_km is None      # null stays null
    assert v.conclusion == STAGE4_CONCLUSION


def test_defaults_never_invent_values():
    c = Stage4Candidate(mmsi="999000001")
    assert c.slick_volume_m3 == Range3() and c.derived_flow_m3_h == Range3()
    assert c.dark_target_match.status == "unavailable" and c.dark_target_match.confidence is None
    assert c.h3_cells == [] and c.score == 0.0 and c.evidence_quality == "low"


@pytest.mark.parametrize("bad", [
    dict(min=5, max=1), dict(min=1, nominal=9, max=5), dict(min=-1), dict(nominal=3, max=2),
])
def test_range_rejects_inconsistent_values(bad):
    with pytest.raises(ValidationError):
        Range3(**bad)


def test_range_accepts_valid_and_partial():
    assert Range3(min=2, nominal=8, max=20).nominal == 8
    assert Range3(min=2).max is None


@pytest.mark.parametrize("score", [-0.1, 1.01])
def test_score_is_bounded(score):
    with pytest.raises(ValidationError):
        Stage4Candidate(mmsi="1", score=score)


def test_dark_target_confidence_bounded_and_status_closed():
    with pytest.raises(ValidationError):
        DarkTargetMatch(confidence=1.5)
    with pytest.raises(ValidationError):
        DarkTargetMatch(status="no_vessel")      # absence of detection must not read as proof


def test_conclusion_cannot_be_turned_into_a_guilt_claim():
    with pytest.raises(ValidationError):
        Stage4Verdict(incident_id="X", case_type="manual_demo", conclusion="Vessel is responsible")
    with pytest.raises(ValidationError):
        Stage4Verdict(incident_id="X", case_type="manual_demo", conclusion="The candidate is guilty")


def test_case_type_is_closed():
    with pytest.raises(ValidationError):
        Stage4Verdict(incident_id="X", case_type="live_real")


def test_json_roundtrip_is_stable():
    v = Stage4Verdict(incident_id="X", case_type="synthetic_demo", h3_resolution=7,
                      candidates=[Stage4Candidate(mmsi="999000001", h3_cells=["8760d66d3ffffff"])])
    assert Stage4Verdict.model_validate_json(v.model_dump_json()) == v
