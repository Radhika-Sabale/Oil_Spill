"""Fail-closed injection tests for NORSE2019 in the normal M3 drift path."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from copy import copy

import numpy as np
import pytest

from scripts import norse2019_adapter as adapter

pytestmark = pytest.mark.real_data


DATA = Path(__file__).resolve().parents[1] / "data" / "norse2019_forcing"
T_SAT = datetime(2019, 6, 12, 12, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def real_field():
    return adapter.load_norse2019_field(DATA)


class StopBeforeIntegration(Exception):
    pass


def _stop_at_advect(monkeypatch, pipeline, expected, calls):
    def seed(_ring, _centroid, n):
        return np.full(n, expected.lons[20]), np.full(n, expected.lats[20])

    def stop(lon, lat, t, hours, field, **kwargs):
        calls.append(field)
        raise StopBeforeIntegration

    monkeypatch.setattr(pipeline.advection, "seed_particles", seed)
    monkeypatch.setattr(pipeline.advection, "advect", stop)


def _run_drift(pipeline, profile, trace=None):
    return pipeline.run_drift(
        ring=[(2.1, 59.7), (2.2, 59.7), (2.2, 59.8), (2.1, 59.7)],
        centroid=(2.15, 59.75), t_sat=T_SAT, hindcast_hours=1,
        forecast_hours=1, ensemble_n=4, scene_id="norse2019-test",
        metocean_profile=profile, trace=trace,
    )


def test_norse_path_passes_adapter_field_without_touching_synthetic_fallback(
        monkeypatch, real_field):
    from app import pipeline
    from app.drift import fields
    from app.jobs.store import Trace

    calls = []
    monkeypatch.setattr(adapter, "load_norse2019_field", lambda: real_field)
    monkeypatch.setattr(fields, "load_for_scene", lambda *a, **k: pytest.fail("default loader called"))
    monkeypatch.setattr(fields, "synthetic_field", lambda *a, **k: pytest.fail("synthetic fallback called"))
    _stop_at_advect(monkeypatch, pipeline, real_field, calls)

    trace = Trace()
    with pytest.raises(StopBeforeIntegration):
        _run_drift(pipeline, "norse2019", trace)
    assert calls == [real_field]
    metocean_trace = next(step for step in trace.to_list() if step["step"] == "METOCEAN")
    assert metocean_trace["source"] == real_field.source
    assert metocean_trace["adapter_metadata"]["source_sha256"] == real_field.adapter_metadata["source_sha256"]


def test_norse_missing_or_invalid_forcing_fails_closed(monkeypatch):
    from app import pipeline
    from app.drift import fields

    monkeypatch.setattr(fields, "load_for_scene", lambda *a, **k: pytest.fail("default loader called"))
    monkeypatch.setattr(fields, "synthetic_field", lambda *a, **k: pytest.fail("synthetic fallback called"))

    def missing():
        raise adapter.ForcingCompatibilityError("required source checksum mismatch")

    monkeypatch.setattr(adapter, "load_norse2019_field", missing)
    with pytest.raises(pipeline.NorseForcingIntegrationError, match="checksum mismatch"):
        _run_drift(pipeline, "norse2019")


def test_norse_rejects_adapter_field_marked_synthetic(monkeypatch, real_field):
    from app import pipeline
    from app.drift import fields

    flagged = copy(real_field)
    flagged.synthetic = True
    monkeypatch.setattr(adapter, "load_norse2019_field", lambda: flagged)
    monkeypatch.setattr(fields, "load_for_scene", lambda *a, **k: pytest.fail("default loader called"))
    monkeypatch.setattr(fields, "synthetic_field", lambda *a, **k: pytest.fail("fallback called"))
    with pytest.raises(pipeline.NorseForcingIntegrationError, match="synthetic field"):
        _run_drift(pipeline, "norse2019")


@pytest.mark.parametrize(
    "t_sat,hours_back,hours_forward,centroid",
    [
        (datetime(2019, 6, 12, 12, tzinfo=timezone.utc), 12, 1, (2.15, 59.75)),
        (datetime(2019, 6, 12, 12, tzinfo=timezone.utc), 1, 1, (3.2, 59.75)),
        (datetime(2019, 6, 12, 12, tzinfo=timezone.utc), 1, 13, (2.15, 59.75)),
    ],
)
def test_norse_insufficient_spatiotemporal_coverage_fails_before_solver(
        monkeypatch, real_field, t_sat, hours_back, hours_forward, centroid):
    from app import pipeline
    from app.drift import fields

    monkeypatch.setattr(adapter, "load_norse2019_field", lambda: real_field)
    monkeypatch.setattr(fields, "load_for_scene", lambda *a, **k: pytest.fail("default loader called"))
    monkeypatch.setattr(fields, "synthetic_field", lambda *a, **k: pytest.fail("synthetic fallback called"))
    monkeypatch.setattr(pipeline.advection, "advect", lambda *a, **k: pytest.fail("solver started"))
    with pytest.raises(pipeline.NorseForcingCoverageError):
        pipeline.run_drift(
            ring=None, centroid=centroid, t_sat=t_sat, hindcast_hours=hours_back,
            forecast_hours=hours_forward, ensemble_n=4, scene_id="norse2019-test",
            metocean_profile="norse2019",
        )


def test_default_non_norse_profile_keeps_existing_scene_loader(monkeypatch, real_field):
    from app import pipeline
    from app.drift import fields

    seen = []
    monkeypatch.setattr(fields, "load_for_scene", lambda *a, **k: seen.append((a, k)) or real_field)
    monkeypatch.setattr(adapter, "load_norse2019_field", lambda: pytest.fail("NORSE adapter called"))
    monkeypatch.setattr(fields, "synthetic_field", lambda *a, **k: pytest.fail("not expected in this fixture"))
    calls = []
    _stop_at_advect(monkeypatch, pipeline, real_field, calls)

    with pytest.raises(StopBeforeIntegration):
        _run_drift(pipeline, "default")
    assert len(seen) == 1
    assert seen[0][0][0] == "norse2019-test"
    assert calls == [real_field]


def test_norse_rejects_clamped_solver_coverage_instead_of_accepting_edges(
        monkeypatch, real_field):
    from app import pipeline
    from app.drift import fields

    monkeypatch.setattr(adapter, "load_norse2019_field", lambda: real_field)
    monkeypatch.setattr(fields, "load_for_scene", lambda *a, **k: pytest.fail("default loader called"))
    monkeypatch.setattr(fields, "synthetic_field", lambda *a, **k: pytest.fail("synthetic fallback called"))
    monkeypatch.setattr(pipeline.advection, "seed_particles",
                        lambda _r, _c, n: (np.full(n, 2.15), np.full(n, 59.75)))

    class ClampedRun:
        meta = {"forcing_coverage_status": "clamped_outside_coverage",
                "forcing_outside_coverage_evaluations": 1}

    monkeypatch.setattr(pipeline.advection, "advect", lambda *a, **k: ClampedRun())
    with pytest.raises(pipeline.NorseForcingCoverageError, match="left forcing coverage"):
        _run_drift(pipeline, "norse2019")


def test_norse_field_disables_m3_edge_clamping(monkeypatch, real_field):
    from app import pipeline

    pipeline._install_norse_strict_sampling(real_field)
    with pytest.raises(pipeline.NorseForcingCoverageError, match="edge-clamped values are disabled"):
        real_field.sample(real_field.lats[0] - 1e-5, real_field.lons[0], real_field.times[0])


def test_run_api_exposes_opt_in_and_preserves_default(monkeypatch):
    from app.api import pipeline as api
    from app.schemas import RunRequest

    assert RunRequest(scene_id="scene").metocean_profile == "default"
    req = RunRequest(scene_id="scene", metocean_profile="norse2019")
    seen = {}
    monkeypatch.setattr(api.core, "run", lambda **kwargs: seen.update(kwargs) or {"ok": True})
    assert api.run(req) == {"ok": True}
    assert seen["metocean_profile"] == "norse2019"


def test_direct_drift_api_forwards_explicit_profile(monkeypatch):
    from app.api import drift as api
    from app.jobs.store import Trace
    from app.schemas import DriftRequest

    seen = {}
    monkeypatch.setattr(
        api.pipeline, "run_drift",
        lambda *args, **kwargs: seen.update(kwargs) or {"trace": Trace(), "metocean": {"source": "test"}},
    )
    response = api.drift(DriftRequest(
        centroid=[2.2, 59.7], t_sat="2019-06-12T12:00:00Z", metocean_profile="norse2019"
    ))
    assert seen["metocean_profile"] == "norse2019"
    assert response["metocean"]["source"] == "test"
