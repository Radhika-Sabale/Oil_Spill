"""Acceptance checks for the SentinelTrace M3 hindcast implementation."""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

pytestmark = pytest.mark.synthetic_data


T0 = datetime(2024, 2, 14, 6, 0, tzinfo=timezone.utc)


def _field(times, lats, lons, data):
    from app.drift.fields import _from_arrays

    return _from_arrays(times, lats, lons, data, "M3 unit fixture", "n/a", "m3-test")


def test_rk4_constant_velocity_has_correct_forward_and_backward_time(uniform_field):
    from app.drift.advection import advect
    from app.geo.crs import haversine_km

    lon0, lat0 = np.array([71.5]), np.array([19.0])
    forward = advect(lon0, lat0, T0, 1, uniform_field, direction="forward",
                     integrator="rk4", dt_seconds=300,
                     current_noise=0, wind_noise=0, eddy_diffusivity_m2_s=0)
    backward = advect(lon0, lat0, T0, 1, uniform_field, direction="backward",
                      integrator="rk4", dt_seconds=300,
                      current_noise=0, wind_noise=0, eddy_diffusivity_m2_s=0)

    assert len(forward.times) == 13
    assert forward.meta["integrator"] == "rk4"
    assert forward.meta["forcing_coverage_status"] == "covered"
    assert (forward.times[-1] - T0).total_seconds() == 3600
    assert (backward.times[-1] - T0).total_seconds() == -3600
    d_forward = haversine_km(lat0[0], lon0[0], forward.lat[-1, 0], forward.lon[-1, 0])
    d_backward = haversine_km(lat0[0], lon0[0], backward.lat[-1, 0], backward.lon[-1, 0])
    assert d_forward == pytest.approx(3.6, abs=0.02)
    assert d_backward == pytest.approx(3.6, abs=0.02)
    assert forward.lon[-1, 0] > lon0[0] > backward.lon[-1, 0]


def test_rk4_step_refinement_converges_for_spatially_varying_current():
    from app.drift.advection import advect
    from app.geo.crs import LocalAEQD

    lon0, lat0 = 71.5, 19.0
    frame = LocalAEQD(lat0, lon0)
    lons = np.linspace(lon0 - 0.1, lon0 + 0.1, 41)
    lats = np.linspace(lat0 - 0.1, lat0 + 0.1, 9)
    times = np.array([T0.timestamp() + h * 3600 for h in range(-1, 3)])
    lon_grid = np.broadcast_to(lons[None, None, :], (times.size, lats.size, lons.size))
    x_grid, _ = frame.to_m(lon_grid, np.zeros_like(lon_grid) + lat0)
    k = 1.0e-4
    shape = (times.size, lats.size, lons.size)
    field = _field(times, lats, lons, {
        "u_current": k * x_grid,
        "v_current": np.zeros(shape),
        "u_wind10": np.zeros(shape),
        "v_wind10": np.zeros(shape),
    })
    start_x, _ = frame.to_m(lon0 + 0.009, lat0)
    expected_x = float(start_x) * np.exp(k * 3600)

    errors = []
    for dt in (900, 300, 150):
        run = advect(np.array([lon0 + 0.009]), np.array([lat0]), T0, 1, field,
                     direction="forward", integrator="rk4", dt_seconds=dt,
                     current_noise=0, wind_noise=0, deflection_deg=0,
                     eddy_diffusivity_m2_s=0)
        final_x, _ = frame.to_m(run.lon[-1, 0], run.lat[-1, 0])
        errors.append(abs(float(final_x) - expected_x))

    assert errors[2] < errors[1] < errors[0]
    assert errors[2] < 0.05


def test_stokes_kenyon_velocity_and_missing_wave_status():
    from app.drift.fields import _from_arrays

    times = np.array([T0.timestamp() + h * 3600 for h in range(3)])
    lats, lons = np.array([18.0, 19.0, 20.0]), np.array([71.0, 71.5, 72.0])
    shape = (3, 3, 3)
    data = {
        "u_current": np.zeros(shape), "v_current": np.zeros(shape),
        "u_wind10": np.full(shape, 10.0), "v_wind10": np.zeros(shape),
        "wave_hs": np.full(shape, 2.0), "wave_tp": np.full(shape, 8.0),
        "wave_dir": np.full(shape, 270.0),  # waves come from west, travel east
    }
    field = _from_arrays(times, lats, lons, data, "wave fixture", "n/a", "wave")
    expected = 2 * np.pi**2 * 2.0**2 / (9.80665 * 8.0**3)
    u, v = field.velocity(np.array([19.0]), np.array([71.5]), T0,
                          alpha=0.0, deflection_deg=0.0)
    assert field.has_stokes
    assert float(u[0]) == pytest.approx(expected, rel=1e-10)
    assert float(v[0]) == pytest.approx(0.0, abs=1e-12)

    no_waves = _from_arrays(times, lats, lons,
        {k: value for k, value in data.items() if not k.startswith("wave_")},
        "no waves", "n/a", "no-wave")
    assert not no_waves.has_stokes
    assert no_waves.describe()["stokes_available"] is False


def test_minimum_variance_selects_known_converged_timestep():
    from app.drift.advection import EnsembleRun, pick_origin_index, spatial_variance_m2

    centres = [(71.5, 19.0)] * 3
    radii_m = [1500.0, 100.0, 700.0]
    frame = __import__("app.geo.crs", fromlist=["LocalAEQD"]).LocalAEQD(19.0, 71.5)
    angles = np.linspace(0, 2 * np.pi, 20, endpoint=False)
    lon = np.empty((3, angles.size))
    lat = np.empty_like(lon)
    for i, radius in enumerate(radii_m):
        lon[i], lat[i] = frame.to_deg(radius * np.cos(angles), radius * np.sin(angles))
    run = EnsembleRun(
        times=[T0, T0.replace(hour=5), T0.replace(hour=4)], lon=lon, lat=lat,
        direction="backward", spread_km=np.array(radii_m) / 1000,
        mean_lon=np.median(lon, axis=1), mean_lat=np.median(lat, axis=1),
        meta={"dt_seconds": 3600},
    )
    assert spatial_variance_m2(run, 1) < spatial_variance_m2(run, 0)
    assert pick_origin_index(run, method="minimum_variance") == 1

    # Internal five-minute minima are intentionally ignored; selection follows
    # the roadmap's hourly covariance snapshots.
    times_5m = [T0.replace(minute=(i * 5) % 60,
                           hour=T0.hour + (i * 5) // 60) for i in range(13)]
    hourly_only = EnsembleRun(
        times=times_5m, lon=np.repeat(lon[:1], 13, axis=0),
        lat=np.repeat(lat[:1], 13, axis=0), direction="backward",
        spread_km=np.ones(13), mean_lon=np.median(lon[:1], axis=1).repeat(13),
        mean_lat=np.median(lat[:1], axis=1).repeat(13), meta={"dt_seconds": 300},
    )
    small = frame.to_deg(1.0 * np.cos(angles), 1.0 * np.sin(angles))
    hourly_only.lon[1], hourly_only.lat[1] = small
    hourly_only.lon[12], hourly_only.lat[12] = lon[1], lat[1]
    assert pick_origin_index(hourly_only, method="minimum_variance") == 12


def test_kde_hdr_returns_closed_nonempty_95_percent_polygon():
    from app.drift.cone import kde_hdr_ring, origin_zone
    from app.drift.advection import EnsembleRun

    rng = np.random.default_rng(314)
    lons = 71.5 + rng.normal(0, 0.02, 250)
    lats = 19.0 + rng.normal(0, 0.015, 250)
    ring = kde_hdr_ring(lons, lats, pct=95.0)
    assert len(ring) >= 4
    assert ring[0] == pytest.approx(ring[-1])

    run = EnsembleRun(
        times=[T0], lon=lons[None, :], lat=lats[None, :], direction="backward",
        spread_km=np.array([3.0]), mean_lon=np.array([np.median(lons)]),
        mean_lat=np.array([np.median(lats)]), meta={"dt_seconds": 300},
    )
    zone = origin_zone(run, 0, pct=95.0, method="kde_hdr")
    assert zone["percentile"] == 95.0
    assert zone["uncertainty_method"] == "kde_hdr_256_grid_convex_hull_approx"
    assert zone["ring"]


def test_forcing_outside_field_is_recorded_not_hidden():
    from app.drift.advection import advect

    times = np.array([T0.timestamp() - 3600, T0.timestamp(), T0.timestamp() + 3600])
    lats, lons = np.array([19.0]), np.array([71.5, 71.5001])
    shape = (3, 1, 2)
    field = _field(times, lats, lons, {
        "u_current": np.ones(shape), "v_current": np.zeros(shape),
        "u_wind10": np.zeros(shape), "v_wind10": np.zeros(shape),
    })
    run = advect(np.array([71.5]), np.array([19.0]), T0, 1, field,
                 direction="forward", integrator="rk4", dt_seconds=300,
                 current_noise=0, wind_noise=0, eddy_diffusivity_m2_s=0)
    assert run.meta["forcing_coverage_status"] == "clamped_outside_coverage"
    assert run.meta["forcing_outside_coverage_evaluations"] > 0


def test_eddy_diffusion_has_expected_per_axis_variance():
    from app.drift.advection import advect
    from app.drift.fields import _from_arrays
    from app.geo.crs import LocalAEQD

    times = np.array([T0.timestamp() - 3600, T0.timestamp(), T0.timestamp() + 3600])
    lats, lons = np.array([18.0, 19.0, 20.0]), np.array([71.0, 71.5, 72.0])
    shape = (3, 3, 3)
    zero = np.zeros(shape)
    field = _from_arrays(times, lats, lons, {
        "u_current": zero, "v_current": zero,
        "u_wind10": zero, "v_wind10": zero,
    }, "zero field", "n/a", "diffusion")
    n = 4000
    run = advect(np.full(n, 71.5), np.full(n, 19.0), T0, 300 / 3600,
                 field, direction="forward", integrator="rk4", dt_seconds=300,
                 current_noise=0, wind_noise=0, eddy_diffusivity_m2_s=1.0, seed=77)
    frame = LocalAEQD(19.0, 71.5)
    x, y = frame.to_m(run.lon[-1], run.lat[-1])
    assert np.var(x) == pytest.approx(600.0, rel=0.10)
    assert np.var(y) == pytest.approx(600.0, rel=0.10)


def test_wave_fetch_aligns_by_time_and_does_not_extrapolate(monkeypatch):
    from scripts import build_metocean_cache as cache

    payload = [{
        "hourly": {
            "time": ["2024-02-14T06:00", "2024-02-14T09:00"],
            "wave_height": [2.0, 5.0],
            "wave_peak_period": [8.0, 11.0],
            "wave_direction": [270.0, 270.0],
        }
    }]
    monkeypatch.setattr(cache, "_http_json", lambda _url, _params: payload)
    hs, tp, direction = cache.fetch_waves(
        np.array([19.0]), np.array([71.5]), "2024-02-14", "2024-02-14",
        ["2024-02-14T06:00", "2024-02-14T07:00", "2024-02-14T09:00",
         "2024-02-14T10:00"],
    )
    assert hs[:3, 0, 0] == pytest.approx([2.0, 3.0, 5.0])
    assert tp[:3, 0, 0] == pytest.approx([8.0, 9.0, 11.0])
    assert direction[:3, 0, 0] == pytest.approx([270.0, 270.0, 270.0])
    assert np.isnan(hs[3, 0, 0]) and np.isnan(tp[3, 0, 0]) and np.isnan(direction[3, 0, 0])


def test_wave_fields_round_trip_through_npz_cache(tmp_path):
    from app.drift.fields import _from_arrays, load_npz, save_npz

    times = np.array([T0.timestamp(), T0.timestamp() + 3600])
    lats, lons = np.array([19.0]), np.array([71.5])
    shape = (2, 1, 1)
    field = _from_arrays(times, lats, lons, {
        "u_current": np.zeros(shape), "v_current": np.zeros(shape),
        "u_wind10": np.ones(shape), "v_wind10": np.zeros(shape),
        "wave_hs": np.full(shape, 2.0), "wave_tp": np.full(shape, 8.0),
        "wave_dir": np.full(shape, 270.0),
    }, "cache test", "CC BY 4.0", "roundtrip")
    path = tmp_path / "waves.npz"
    save_npz(path, field)
    restored = load_npz(path)
    assert restored.has_stokes
    assert np.array_equal(restored.data["wave_hs"], field.data["wave_hs"])
    assert np.array_equal(restored.data["wave_tp"], field.data["wave_tp"])
    assert np.array_equal(restored.data["wave_dir"], field.data["wave_dir"])

