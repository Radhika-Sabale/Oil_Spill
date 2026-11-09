"""Focused pre-hindcast checks using only the approved real NORSE2019 forcing."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from scipy.io import netcdf_file

from scripts import norse2019_adapter as adapter

pytestmark = pytest.mark.real_data


DATA = Path(__file__).resolve().parents[1] / "data" / "norse2019_forcing"


@pytest.fixture(scope="module")
def real_field():
    return adapter.load_norse2019_field(DATA)


def test_adapter_returns_verified_m3_schema_and_disables_waves(real_field):
    from app.drift.fields import MetoceanField

    # conftest reloads the app package after collection to redirect its data
    # directory, so compare the M3 class contract after the adapter's lazy import.
    assert isinstance(real_field, MetoceanField)
    assert real_field.synthetic is False
    assert real_field.live is False
    assert set(real_field.data) == {"u_current", "v_current", "u_wind10", "v_wind10"}
    assert real_field.has_currents
    assert real_field.has_stokes is False
    assert real_field.adapter_metadata["wave_stokes_enabled"] is False
    assert real_field.adapter_metadata["synthetic_fallback"] is False
    assert all(np.isfinite(a).all() for a in real_field.data.values())
    assert all(a.shape == (21, 50, 88) for a in real_field.data.values())
    assert real_field.bounds == pytest.approx((2.0, 59.56, 2.87, 60.05))


@pytest.mark.parametrize(
    "filename,var,source_name",
    [
        (adapter.MEPS_NAME, "eastward_wind_10m", "u_wind10"),
        (adapter.NORKYST_NAME, "u_eastward", "u_current"),
    ],
)
def test_regridding_reproduces_known_source_grid_node(filename, var, source_name):
    doc = json.loads((DATA / adapter.MANIFEST_NAME).read_text(encoding="utf-8"))
    entry = next(row for row in doc["files"] if row["path"] == filename)
    with netcdf_file(DATA / filename, "r", mmap=False) as ds:
        lat = ds.variables["latitude"][:].copy()
        lon = ds.variables["longitude"][:].copy()
        source = ds.variables[var][0].copy()
    valid = np.isfinite(source) & np.isfinite(lat) & np.isfinite(lon) & (np.abs(source) < 1e36)
    iy, ix = np.argwhere(valid)[valid.sum() // 2]
    # One-node axes exercise the same linear scattered interpolator at an exact
    # source coordinate. Interpolation at an input vertex must reproduce it.
    cube = adapter._source_cube(DATA / filename, entry, (var,))
    got = adapter._regrid(cube, var, np.array([lat[iy, ix]]), np.array([lon[iy, ix]]))[0, 0, 0]
    assert got == pytest.approx(source[iy, ix], abs=2e-7)


def test_m3_spatiotemporal_interpolation_and_coverage_edges(real_field):
    iy, ix = 17, 33
    lat, lon = real_field.lats[iy], real_field.lons[ix]
    t0, t1 = real_field.times[:2]
    for key, cube in real_field.data.items():
        midpoint = real_field.sample(lat, lon, (t0 + t1) / 2.0)[key][0]
        assert midpoint == pytest.approx((cube[0, iy, ix] + cube[1, iy, ix]) / 2.0)
        assert real_field.sample(lat, lon, t0)[key][0] == pytest.approx(cube[0, iy, ix])
        assert real_field.sample(lat, lon, t1)[key][0] == pytest.approx(cube[1, iy, ix])

    start = real_field.times[0]
    end = real_field.times[-1]
    assert real_field.covers(lat, lon, start)
    assert real_field.covers(lat, lon, end)
    assert not real_field.covers(lat, lon, start - 1)
    assert not real_field.covers(lat, lon, end + 1)
    assert real_field.covers(real_field.lats[0], real_field.lons[0], start)
    assert not real_field.covers(real_field.lats[0] - 1e-5, real_field.lons[0], start)
    assert not real_field.covers(real_field.lats[0], real_field.lons[0] - 1e-5, start)
    # M3's field sampler clamps outside coverage; its advection coverage monitor
    # records such samples. Verify the clamp explicitly at the time edges.
    for key, cube in real_field.data.items():
        assert real_field.sample(lat, lon, start - 1)[key][0] == pytest.approx(cube[0, iy, ix])
        assert real_field.sample(lat, lon, end + 1)[key][0] == pytest.approx(cube[-1, iy, ix])
        assert real_field.sample(real_field.lats[0] - 1e-5, real_field.lons[0], start)[key][0] == pytest.approx(cube[0, 0, 0])


def test_real_forcing_is_nonzero_and_physically_bounded(real_field):
    currents = np.hypot(real_field.data["u_current"], real_field.data["v_current"])
    winds = np.hypot(real_field.data["u_wind10"], real_field.data["v_wind10"])
    assert np.any(currents > 0.01)
    assert np.any(winds > 0.5)
    assert float(np.max(currents)) < 3.0
    assert float(np.max(winds)) < 50.0
    assert float(np.mean(currents)) == pytest.approx(0.3733, abs=0.02)
    assert float(np.mean(winds)) == pytest.approx(8.071, abs=0.2)


def test_missing_or_modified_real_inputs_fail_closed_without_synthetic_fallback(tmp_path):
    with pytest.raises(adapter.ForcingCompatibilityError, match="manifest is missing"):
        adapter.load_norse2019_field(tmp_path)
    (tmp_path / adapter.MANIFEST_NAME).write_text("{}", encoding="utf-8")
    with pytest.raises(adapter.ForcingCompatibilityError, match="Invalid forcing manifest"):
        adapter.load_norse2019_field(tmp_path)
    manifest = json.loads((DATA / adapter.MANIFEST_NAME).read_text(encoding="utf-8"))
    manifest["files"][0]["sha256"] = "0" * 64
    (tmp_path / adapter.MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(adapter.ForcingCompatibilityError, match="Checksum mismatch"):
        adapter.load_norse2019_field(tmp_path)
