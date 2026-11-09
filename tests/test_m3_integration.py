"""Integration checks across M3 forcing, advection, cones, API and storage."""
from __future__ import annotations

from datetime import datetime, timezone
from copy import copy
from pathlib import Path

import numpy as np
import pytest


T0 = datetime(2024, 2, 14, 6, 0, tzinfo=timezone.utc)


@pytest.mark.synthetic_data
def test_cached_metocean_drives_advection_and_forecast_cone(
        uniform_field, app_config, tmp_path, monkeypatch):
    from app.drift import advection, cone, fields
    from app.drift.fields import MetoceanField
    from app.geo.crs import haversine_km

    cache_dir = tmp_path / "metocean"
    cache_dir.mkdir()
    monkeypatch.setattr(app_config, "METOCEAN_DIR", cache_dir)

    # Store deliberately descending coordinates. The disk loader must reorder
    # axes and the associated cube dimensions together before interpolation.
    raw = MetoceanField(
        times=uniform_field.times[::-1].copy(),
        lats=uniform_field.lats[::-1].copy(),
        lons=uniform_field.lons[::-1].copy(),
        data={key: values[::-1, ::-1, ::-1].copy()
              for key, values in uniform_field.data.items()},
        source="integration test 1 m/s east current",
        license="n/a",
        scene_id="integration_scene",
    )
    fields.save_npz(cache_dir / "integration_scene.npz", raw)
    field = fields.load_for_scene("integration_scene", 19.0, 71.5, T0)

    assert field.scene_id == "integration_scene"
    assert field.source == raw.source
    assert field.times[0] < field.times[-1]
    assert field.lats[0] < field.lats[-1]
    assert field.lons[0] < field.lons[-1]
    assert field.sample(19.0, 71.5, T0)["u_current"] == pytest.approx([1.0])

    lon0 = np.array([71.49, 71.51, 71.51, 71.49])
    lat0 = np.array([18.99, 18.99, 19.01, 19.01])
    run = advection.advect(
        lon0, lat0, T0, hours=1, field_src=field, direction="forward",
        integrator="rk4", dt_seconds=600, alpha=0.0, deflection_deg=0.0,
        current_noise=0.0, wind_noise=0.0, eddy_diffusivity_m2_s=0.0,
    )

    assert run.times[0] == T0
    assert run.times[-1] == T0.replace(hour=7)
    assert run.meta["forcing_coverage_status"] == "covered"
    assert run.meta["metocean_source"] == raw.source
    for index in range(lon0.size):
        assert haversine_km(lat0[index], lon0[index], run.lat[-1, index],
                            run.lon[-1, index]) == pytest.approx(3.6, abs=0.02)
        assert run.lon[-1, index] > lon0[index]

    ring = cone.swept_cone(run, pct=100.0)
    feature = cone.cone_feature(ring, "forecast_cone", hours=1)
    bbox = cone.threatened_bbox(run)
    envelopes = cone.envelopes_by_hour(run, pct=100.0)
    coords = feature["geometry"]["coordinates"][0]
    assert coords[0] == coords[-1]
    assert feature["properties"]["area_km2"] > 0
    assert bbox["west"] <= float(np.min(lon0))
    assert bbox["east"] >= float(np.max(run.lon[-1]))
    assert len(envelopes) == run.n_steps
    assert envelopes[0]["t"] == T0.isoformat()
    assert envelopes[-1]["t"] == run.times[-1].isoformat()


@pytest.mark.synthetic_data
def test_missing_or_malformed_cache_falls_back_to_flagged_synthetic_field(
        app_config, tmp_path, monkeypatch):
    from app.drift import fields

    cache_dir = tmp_path / "metocean"
    cache_dir.mkdir()
    monkeypatch.setattr(app_config, "METOCEAN_DIR", cache_dir)
    monkeypatch.setattr(app_config, "OPEN_METEO_LIVE", False)
    monkeypatch.setattr(app_config, "OFFLINE", True)

    missing = fields.load_for_scene("missing_scene", 19.0, 71.5, T0)
    assert missing.synthetic is True
    assert missing.scene_id == "missing_scene"
    assert "SYNTHETIC CONSTANT FIELD" in missing.source

    shape = (1, 2, 2)
    np.savez_compressed(
        cache_dir / "bad_axes.npz",
        time=np.array([T0.timestamp()]),
        lat=np.array([19.0, 20.0]),
        lon=np.array([71.0, 72.0]),
        u_current=np.zeros((1, 1, 2)),  # inconsistent latitude dimension
        v_current=np.zeros(shape),
        u_wind10=np.zeros(shape),
        v_wind10=np.zeros(shape),
    )
    malformed = fields.load_for_scene("bad_axes", 19.0, 71.5, T0)
    assert malformed.synthetic is True
    assert malformed.scene_id == "bad_axes"


@pytest.mark.synthetic_data
def test_non_finite_forcing_is_sanitized_before_solver(uniform_field):
    from app.drift import advection, fields

    data = {key: values.copy() for key, values in uniform_field.data.items()}
    data["u_current"][10, 4, 4] = np.inf
    data["v_current"][10, 4, 4] = np.nan
    data["u_wind10"][10, 4, 4] = -np.inf
    safe = fields._from_arrays(
        uniform_field.times, uniform_field.lats, uniform_field.lons,
        data, "non-finite integration fixture", "n/a", "nonfinite",
    )

    assert all(np.isfinite(cube).all() for cube in safe.data.values())
    assert safe.data["u_current"][10, 4, 4] == 0.0
    assert safe.data["v_current"][10, 4, 4] == 0.0
    assert safe.data["u_wind10"][10, 4, 4] == 0.0
    run = advection.advect(
        np.array([safe.lons[4]]), np.array([safe.lats[4]]), T0, hours=1,
        field_src=safe, direction="forward", dt_seconds=600,
        current_noise=0.0, wind_noise=0.0, eddy_diffusivity_m2_s=0.0,
    )
    assert np.isfinite(run.lon).all() and np.isfinite(run.lat).all()


@pytest.mark.synthetic_data
def test_unexpected_and_duplicate_time_axes_are_rejected(uniform_field):
    from app.drift import fields

    data = {key: values[:2, :2, :2] for key, values in uniform_field.data.items()}
    with pytest.raises(ValueError, match="NaT"):
        fields._from_arrays(
            np.array(["NaT", "2024-02-14T06:00"], dtype="datetime64[s]"),
            uniform_field.lats[:2], uniform_field.lons[:2], data,
            "bad timestamp", "n/a", "bad_time",
        )
    with pytest.raises(ValueError, match="strictly increasing"):
        fields._from_arrays(
            [T0, T0], uniform_field.lats[:2], uniform_field.lons[:2], data,
            "duplicate timestamp", "n/a", "duplicate_time",
        )


@pytest.mark.synthetic_data
def test_cone_rejects_incomplete_and_non_monotonic_solver_trajectories(uniform_field):
    from app.drift import advection, cone

    lon = np.array([71.49, 71.51, 71.51, 71.49])
    lat = np.array([18.99, 18.99, 19.01, 19.01])
    run = advection.advect(
        lon, lat, T0, hours=1, field_src=uniform_field, direction="forward",
        dt_seconds=600, alpha=0.0, deflection_deg=0.0,
        current_noise=0.0, wind_noise=0.0, eddy_diffusivity_m2_s=0.0,
    )

    incomplete = copy(run)
    incomplete.lon = run.lon[:-1]
    with pytest.raises(ValueError, match="matching non-empty"):
        cone.swept_cone(incomplete)

    non_monotonic = copy(run)
    non_monotonic.times = list(run.times)
    non_monotonic.times[2] = non_monotonic.times[1]
    with pytest.raises(ValueError, match="strictly monotonic"):
        cone.envelopes_by_hour(non_monotonic)

    with pytest.raises(ValueError, match="step must be positive"):
        cone.swept_cone(run, step=0)
    with pytest.raises(ValueError, match="index range"):
        cone.swept_cone(run, start=run.n_steps)


@pytest.mark.synthetic_data
def test_m3_api_rejects_invalid_coordinates_timestamps_and_horizons():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        invalid_centroid = client.post("/api/drift", json={
            "centroid": [181.0, 95.0], "t_sat": "2024-02-14T06:00:00Z",
        })
        short_centroid = client.post("/api/drift", json={
            "centroid": [71.5], "t_sat": "2024-02-14T06:00:00Z",
        })
        invalid_time = client.post("/api/drift", json={
            "centroid": [71.5, 19.0], "t_sat": "not-a-timestamp",
        })
        invalid_horizon = client.post("/api/run", json={
            "scene_id": "selftest_synthetic", "hindcast_hours": 0,
        })

    assert invalid_centroid.status_code == 422
    assert short_centroid.status_code == 422
    assert invalid_time.status_code == 422
    assert invalid_horizon.status_code == 422


@pytest.mark.real_data
def test_real_norse_forcing_coverage_error_propagates_as_client_error():
    """The checksum-verified adapter and M3 API fail closed outside their time window."""
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        response = client.post("/api/drift", json={
            "centroid": [2.15, 59.75],
            "t_sat": "2024-02-14T06:00:00Z",
            "hours_back": 1,
            "hours_fwd": 1,
            "ensemble_n": 4,
            "metocean_profile": "norse2019",
        })

    assert response.status_code == 422
    assert "does not cover the full requested UTC interval" in response.json()["detail"]


@pytest.mark.synthetic_data
def test_m3_run_api_persists_semantically_consistent_results(
        selftest_scene, cached_metocean):
    from datetime import datetime

    from fastapi.testclient import TestClient

    from app.main import app

    payload = {
        "scene_id": selftest_scene.id,
        "job_id": "job_m3_integration_api",
        "hindcast_hours": 6,
        "forecast_hours": 6,
        "ensemble_n": 12,
        "prefer_model": False,
        "render_overlays": False,
    }
    with TestClient(app) as client:
        response = client.post("/api/run", json=payload)
        assert response.status_code == 200, response.text
        document = response.json()
        fetched = client.get("/api/jobs/%s" % document["job_id"])
        fetched_again = client.get("/api/jobs/%s" % document["job_id"])
        jobs = client.get("/api/jobs?limit=50")

    assert document["status"] == "ok"
    assert document["input"]["scene_id"] == selftest_scene.id
    assert document["drift"]["metocean"]["synthetic"] is False
    assert document["drift"]["metocean"]["source"] == cached_metocean.source
    assert document["drift"]["physics"]["metocean_source"] == cached_metocean.source
    assert fetched.status_code == fetched_again.status_code == jobs.status_code == 200
    assert fetched.json() == fetched_again.json() == document
    assert any(row["job_id"] == document["job_id"] for row in jobs.json())

    drift = document["drift"]
    observation = datetime.fromisoformat(document["input"]["t_sat"].replace("Z", "+00:00"))
    back_times = [datetime.fromisoformat(value.replace("Z", "+00:00"))
                  for value in drift["hindcast_track"]["properties"]["times"]]
    forecast_times = [datetime.fromisoformat(value.replace("Z", "+00:00"))
                      for value in drift["forecast_track"]["properties"]["times"]]
    assert back_times[0] == observation
    assert back_times[-1] < observation
    assert forecast_times[0] == observation
    assert forecast_times[-1] > observation
    assert drift["origin"]["t"] <= observation.isoformat()

    for track, times in ((drift["hindcast_track"], back_times),
                         (drift["forecast_track"], forecast_times)):
        coordinates = track["geometry"]["coordinates"]
        assert len(coordinates) == len(times)
        assert all(len(pair) == 2 for pair in coordinates)
        assert all(70.5 <= lon <= 72.5 and 18.0 <= lat <= 20.0
                   for lon, lat in coordinates)

    for key in ("cone_back", "cone_fwd", "origin_zone"):
        geometry = drift[key]["geometry"]
        assert geometry["type"] == "Polygon"
        ring = geometry["coordinates"][0]
        assert len(ring) >= 4 and ring[0] == ring[-1]
        assert drift[key]["properties"]["area_km2"] > 0

    bbox = drift["threatened_bbox"]
    for lon, lat in drift["forecast_track"]["geometry"]["coordinates"]:
        assert bbox["west"] <= lon <= bbox["east"]
        assert bbox["south"] <= lat <= bbox["north"]


@pytest.mark.synthetic_data
def test_job_store_replace_failure_keeps_last_complete_document(
        app_config, tmp_path, monkeypatch):
    from app.jobs import store

    jobs_dir = tmp_path / "jobs"
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(app_config, "JOBS_DIR", jobs_dir)
    monkeypatch.setattr(app_config, "CACHE_DIR", cache_dir)
    job_id = "job_store_atomicity"
    store.save(job_id, {"job_id": job_id, "revision": 1})
    complete_path = store.path_for(job_id)
    part_path = complete_path.with_suffix(".json.part")
    original_replace = Path.replace

    def fail_part_replace(path, target):
        if path == part_path:
            raise OSError("simulated storage replace failure")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", fail_part_replace)
    with pytest.raises(OSError, match="simulated storage replace failure"):
        store.save(job_id, {"job_id": job_id, "revision": 2})

    assert store.load(job_id) == {"job_id": job_id, "revision": 1}
    assert not part_path.exists()
