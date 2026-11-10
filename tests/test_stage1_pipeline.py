"""Tests for Stage 1 (M2) integration into the analysis pipeline."""
from __future__ import annotations

from typing import Any, Dict
from unittest.mock import patch

import pytest

from app import pipeline, scenes, stage1


def test_stage1_executes_before_m1(selftest_scene):
    """Execution trace must place INGEST before DETECT, and Stage 1 must run before M1."""
    call_order = []

    orig_for_scene = pipeline.stage1.for_scene
    orig_segment = pipeline.infer.segment_scene

    def tracked_for_scene(*args, **kwargs):
        call_order.append("stage1")
        return orig_for_scene(*args, **kwargs)

    def tracked_segment(*args, **kwargs):
        call_order.append("segment_scene")
        return orig_segment(*args, **kwargs)

    with patch.object(pipeline.stage1, "for_scene", side_effect=tracked_for_scene), \
         patch.object(pipeline.infer, "segment_scene", side_effect=tracked_segment):
        det = pipeline.detect_scene(selftest_scene, render_overlays=False)

    assert call_order == ["stage1", "segment_scene"], (
        "Stage 1 must be invoked before M1 segment_scene is called; got: %s" % call_order
    )

    steps = [s["step"] for s in det["trace"].to_list()]
    assert "INGEST" in steps, "INGEST must be in trace steps: %s" % steps
    assert "DETECT" in steps, "DETECT must be in trace steps: %s" % steps
    assert steps.index("INGEST") < steps.index("DETECT"), (
        "INGEST must precede DETECT in the execution trace; got: %s" % steps
    )


def test_job_result_contains_stage1_report(selftest_scene):
    """The pipeline run result must contain a populated stage1 block with valid schema."""
    doc = pipeline.run(scene_id=selftest_scene.id, render_overlays=False)

    assert "stage1" in doc, "Job document must contain 'stage1'"
    s1 = doc["stage1"]
    assert s1["stage"] == "ingest"
    assert s1["status"] in ("available", "partial", "unavailable")
    assert "product" in s1
    assert "incidence_normalization" in s1
    assert "wind_gate" in s1
    assert "cfar" in s1
    assert isinstance(s1["warnings"], list)

    # Ingest trace step must be present
    steps = [s["step"] for s in doc["trace"]]
    assert steps[0] == "INGEST", "First trace step in job must be INGEST; got: %s" % steps


def test_stage1_warnings_reach_job_result(selftest_scene):
    """Stage 1 warnings must be propagated directly into doc['warnings']."""
    dummy_warning = "Synthetic wind warning: speed 2.1 m/s is below 3.0 m/s threshold"

    def mock_for_scene(*args, **kwargs):
        return {
            "stage": "ingest",
            "status": "partial",
            "product": {"status": "available", "product": "RTC", "quantity": "gamma0"},
            "incidence_normalization": {"status": "unavailable", "applied": False},
            "wind_gate": {"status": "available", "gate": "fail_low", "speed_ms": 2.1},
            "cfar": {"status": "available", "n_windows": 1, "retained_fraction": 0.01},
            "warnings": [dummy_warning],
        }

    with patch.object(pipeline.stage1, "for_scene", side_effect=mock_for_scene):
        doc = pipeline.run(scene_id=selftest_scene.id, render_overlays=False)

    assert dummy_warning in doc.get("warnings", []), (
        "Stage 1 warnings must be included in top-level doc['warnings']; got: %s"
        % doc.get("warnings")
    )


def test_stage1_exception_does_not_crash_pipeline(selftest_scene):
    """A failure or unhandled exception in Stage 1 must fail open without crashing the pipeline."""
    def crash_for_scene(*args, **kwargs):
        raise RuntimeError("Simulated internal Stage 1 hardware/IO fault")

    with patch.object(pipeline.stage1, "for_scene", side_effect=crash_for_scene):
        doc = pipeline.run(scene_id=selftest_scene.id, render_overlays=False)

    assert doc["status"] in ("ok", "clean_water", "no_oil_detected")
    assert "stage1" in doc
    s1 = doc["stage1"]
    assert s1["status"] == "unavailable"
    assert any("Simulated internal Stage 1" in w for w in s1.get("warnings", []))
    assert any("Simulated internal Stage 1" in w for w in doc.get("warnings", []))
