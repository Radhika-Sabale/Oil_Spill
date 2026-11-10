"""Dataset-independent edge and contract tests for the M3 solver."""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

pytestmark = pytest.mark.synthetic_data


T0 = datetime(2024, 2, 14, 6, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"integrator": "rk3"}, "integrator must"),
        ({"dt_seconds": 0}, "dt_seconds must be positive"),
        ({"dt_seconds": -1}, "dt_seconds must be positive"),
        ({"direction": "sideways"}, "direction must"),
        ({"hours": 0}, "hours must be positive"),
        ({"hours": -1}, "hours must be positive"),
        ({"eddy_diffusivity_m2_s": -0.1}, "eddy_diffusivity_m2_s must be non-negative"),
    ],
)
def test_advect_rejects_invalid_solver_arguments(uniform_field, overrides, message):
    from app.drift.advection import advect

    kwargs = {
        "hours": 1,
        "field_src": uniform_field,
        "dt_seconds": 300,
        "current_noise": 0.0,
        "wind_noise": 0.0,
        "eddy_diffusivity_m2_s": 0.0,
    }
    kwargs.update(overrides)

    with pytest.raises(ValueError, match=message):
        advect(np.array([71.5]), np.array([19.0]), T0, **kwargs)


def test_advect_uses_short_final_step_and_reports_result_metadata(uniform_field):
    from app.drift.advection import advect

    run = advect(
        np.array([71.5]), np.array([19.0]), T0,
        hours=1, field_src=uniform_field, direction="backward",
        dt_seconds=700, current_noise=0.0, wind_noise=0.0,
    )

    assert len(run.times) == 7
    assert [(b - a).total_seconds() for a, b in zip(run.times, run.times[1:])] == [
        -700, -700, -700, -700, -700, -100,
    ]
    assert run.lon.shape == (7, 1)
    assert run.lat.shape == (7, 1)
    assert run.times[-1] == T0.replace(hour=5)
    assert run.meta["duration_seconds"] == 3600.0
    assert run.meta["n_particles"] == 1
    assert run.meta["forcing_coverage_status"] == "covered"
    assert len(run.hourly()) == run.n_steps
    assert run.track_geojson()["geometry"]["type"] == "LineString"
