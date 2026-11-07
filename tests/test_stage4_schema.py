"""Stage 4 contract models: unknowns stay null, ranges make sense, no guilt wording."""
from __future__ import annotations

import pytest

pytest.importorskip("pydantic")

from pydantic import ValidationError  # noqa: E402


def _cand(**over):
    base = {"mmsi": "000000001", "score": 0.5, "score_explanation": "Illustrative ranking only",
            "evidence_quality": "low"}
    base.update(over)
    return base


def test_empty_candidate_keeps_everything_null_or_unavailable():
    from app.schemas import Stage4Candidate

    c = Stage4Candidate(**_cand())
    assert c.slick_volume_m3.nominal is None and c.derived_flow_m3_h.max is None
    assert c.dark_target_match.status == "unavailable" and c.h3_cells == []


def test_range_must_be_ordered_non_negative_and_all_or_none():
    from app.schemas import Stage4Range

    Stage4Range(min=1, nominal=2, max=3)
    for bad in ({"min": 3, "nominal": 2, "max": 1}, {"min": -1, "nominal": 0, "max": 1},
                {"min": 1, "nominal": None, "max": 3}):
        with pytest.raises(ValidationError):
            Stage4Range(**bad)


def test_dark_target_has_no_no_vessel_status_and_needs_a_reason():
    from app.schemas import Stage4DarkTarget

    with pytest.raises(ValidationError):
        Stage4DarkTarget(status="no_vessel")
    with pytest.raises(ValidationError):
        Stage4DarkTarget(status="unavailable")
    Stage4DarkTarget(status="unavailable", reason="no SAR vessel detection in this build")


def test_score_bounds_and_unknown_fields_rejected():
    from app.schemas import Stage4Candidate

    with pytest.raises(ValidationError):
        Stage4Candidate(**_cand(score=1.5))
    with pytest.raises(ValidationError):
        Stage4Candidate(**_cand(guilt_probability=0.9))


def test_verdict_conclusion_and_case_type_are_constrained():
    from app.schemas import Stage4Verdict

    ok = "Investigative candidates only; not proof of causation or a finding of guilt"
    Stage4Verdict(case_type="synthetic_demo", conclusion=ok)
    with pytest.raises(ValidationError):
        Stage4Verdict(case_type="synthetic_demo", conclusion="This vessel did it")
    with pytest.raises(ValidationError):
        Stage4Verdict(case_type="made_up", conclusion=ok)
