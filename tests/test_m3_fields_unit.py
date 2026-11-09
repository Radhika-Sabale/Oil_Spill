"""Dataset-independent unit tests for M3 metocean fields."""
from __future__ import annotations

import numpy as np
import pytest

pytestmark = pytest.mark.synthetic_data


def _field(times=None, lats=None, lons=None, data=None):
    from app.drift.fields import _from_arrays

    times = np.asarray([3600.0, 0.0] if times is None else times)
    lats = np.asarray([20.0, 10.0] if lats is None else lats)
    lons = np.asarray([2.0, 1.0] if lons is None else lons)
    if data is None:
        data = {}
        for offset, name in enumerate(("u_current", "v_current", "u_wind10", "v_wind10")):
            cube = np.empty((times.size, lats.size, lons.size), dtype=float)
            for ti, t in enumerate(times):
                for yi, lat in enumerate(lats):
                    for xi, lon in enumerate(lons):
                        cube[ti, yi, xi] = t / 3600.0 * 100 + lat * 10 + lon + offset * 1000
            data[name] = cube
    return _from_arrays(times, lats, lons, data, "unit fixture", "n/a", "unit")


def test_from_arrays_sorts_axes_and_sample_interpolates_in_time_and_space():
    field = _field()

    assert field.times.tolist() == [0.0, 3600.0]
    assert field.lats.tolist() == [10.0, 20.0]
    assert field.lons.tolist() == [1.0, 2.0]

    sample = field.sample(15.0, 1.5, 1800.0)
    assert sample["u_current"] == pytest.approx([201.5])
    assert sample["v_current"] == pytest.approx([1201.5])
    assert sample["u_wind10"] == pytest.approx([2201.5])
    assert sample["v_wind10"] == pytest.approx([3201.5])


def test_sample_clamps_outside_grid_and_covers_is_inclusive():
    field = _field()

    low = field.sample(-5.0, -1.0, -1.0)
    high = field.sample(30.0, 9.0, 7200.0)
    assert low["u_current"] == pytest.approx([101.0])
    assert high["u_current"] == pytest.approx([302.0])

    assert field.covers(10.0, 1.0, 0.0)
    assert field.covers(20.0, 2.0, 3600.0)
    assert not field.covers(9.999, 1.0, 0.0)
    assert not field.covers(10.0, 1.0, -0.001)


@pytest.mark.parametrize(
    ("latitude", "expected_v"),
    [(10.0, -0.5), (-10.0, 0.5)],
)
def test_velocity_deflects_wind_to_hemisphere_relative_right(latitude, expected_v):
    shape = (1, 2, 2)
    zero = np.zeros(shape)
    field = _field(
        times=[0.0], lats=[-10.0, 10.0], lons=[0.0, 1.0],
        data={
            "u_current": zero,
            "v_current": zero,
            "u_wind10": np.full(shape, 10.0),
            "v_wind10": zero,
        },
    )

    u, v = field.velocity(latitude, 0.5, 0.0, alpha=0.1, deflection_deg=30.0)

    assert u == pytest.approx([np.sqrt(3) / 2])
    assert v == pytest.approx([expected_v])


def test_from_arrays_replaces_nan_in_required_forcing_with_zero():
    data = {name: np.ones((1, 1, 1)) for name in
            ("u_current", "v_current", "u_wind10", "v_wind10")}
    data["u_current"][0, 0, 0] = np.nan

    field = _field(times=[0.0], lats=[10.0], lons=[1.0], data=data)

    assert field.data["u_current"][0, 0, 0] == 0.0
    assert field.velocity(10.0, 1.0, 0.0, alpha=0.0, deflection_deg=0.0)[0] == pytest.approx([0.0])
