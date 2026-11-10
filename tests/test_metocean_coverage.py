from datetime import datetime, timezone

from app import config
from app.drift import fields


def test_full_interval_coverage_is_required_for_cache_selection(tmp_path, monkeypatch, uniform_field):
    monkeypatch.setattr(config, "METOCEAN_DIR", tmp_path)
    cache = tmp_path / "scene.npz"
    fields.save_npz(cache, uniform_field)
    center = datetime.fromtimestamp(float(uniform_field.times[len(uniform_field.times) // 2]), timezone.utc)

    loaded = fields.load_for_scene(
        "scene", float(uniform_field.lats[0]), float(uniform_field.lons[0]), center,
        required_start=uniform_field.times[0], required_end=uniform_field.times[-1],
    )
    assert loaded.synthetic is False

    outside_end = uniform_field.times[-1] + 3600
    rejected = fields.load_for_scene(
        "scene", float(uniform_field.lats[0]), float(uniform_field.lons[0]), center,
        required_start=uniform_field.times[0], required_end=outside_end,
    )
    assert rejected.synthetic is True


def test_coverage_interval_rejects_partial_time_and_space(uniform_field):
    t0, t1 = uniform_field.times[0], uniform_field.times[-1]
    assert uniform_field.covers_interval(float(uniform_field.lats[0]),
                                         float(uniform_field.lons[0]), t0, t1)
    assert not uniform_field.covers_interval(float(uniform_field.lats[0]),
                                             float(uniform_field.lons[0]), t0 - 1, t1)
    assert not uniform_field.covers_interval(float(uniform_field.lats[-1] + 1),
                                             float(uniform_field.lons[-1]), t0, t1)


def test_synthetic_fallback_is_not_reported_as_measured_forcing():
    field = fields.synthetic_field(34.0, -120.0, datetime(2023, 8, 29, tzinfo=timezone.utc))
    description = field.describe()
    assert description["synthetic"] is True
    assert description["has_currents"] is False
    assert description["mean_current_ms"] is None
    assert description["mean_wind_ms"] is None
