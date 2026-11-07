"""Fail-closed NORSE2019 forcing adapter for TideTrace M3.

This module converts the approved MEPS and NorKyst regional subsets into the
regular (time, lat, lon) cube required by ``app.drift.fields.MetoceanField``.
It deliberately does not call ``load_for_scene``: that routine can return a
synthetic field when the cache misses.  No solver or pipeline algorithm is
changed by this adapter.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from scipy.interpolate import LinearNDInterpolator
from scipy.spatial import QhullError
from scipy.io import netcdf_file



DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "norse2019_forcing"
MEPS_NAME = "meps_mbr0_pp_20190612T00Z_norse_roi_20190612T0400_20190613T0000.nc"
NORKYST_NAME = "norkyst800_zdepths_surface_20190612T0400_20190613T0000.nc"
MANIFEST_NAME = "manifest.json"
EXPECTED_SHA256 = {
    MEPS_NAME: "22a41dad2d5af3308bf26b82d5fb833385c3c1ebd7c21ea353ab25cc372d314f",
    NORKYST_NAME: "8749cedd3db73e512b745757e7695feae7b18813b561115c12730ad1141431f2",
}
GRID_STEP_DEG = 0.01
MISSING_LIMIT = 1.0e36
EXPECTED_TIMES = np.arange(
    1560312000.0, 1560312000.0 + 21 * 3600.0, 3600.0, dtype=np.float64
)  # 2019-06-12 04:00 through 2019-06-13 00:00 UTC inclusive


class ForcingCompatibilityError(ValueError):
    """Raised when inputs are missing, altered, incompatible, or incomplete."""


@dataclass(frozen=True)
class SourceCube:
    times: np.ndarray
    lat: np.ndarray
    lon: np.ndarray
    fields: dict[str, np.ndarray]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_nc(path: Path, required: tuple[str, ...]) -> dict[str, np.ndarray]:
    if not path.is_file():
        raise ForcingCompatibilityError(f"Required real forcing file is missing: {path}")
    try:
        with netcdf_file(path, "r", mmap=False) as ds:
            missing = [name for name in required if name not in ds.variables]
            if missing:
                raise ForcingCompatibilityError(f"{path.name} lacks variables: {missing}")
            result = {name: np.array(ds.variables[name][:], copy=True) for name in required}
            for name in ("longitude", "latitude"):
                if name not in ds.variables:
                    raise ForcingCompatibilityError(f"{path.name} lacks {name} coordinates")
                result[name] = np.array(ds.variables[name][:], copy=True)
            return result
    except ForcingCompatibilityError:
        raise
    except Exception as exc:
        raise ForcingCompatibilityError(f"Cannot read {path.name}: {exc}") from exc


def _source_cube(path: Path, manifest_entry: dict[str, Any], names: tuple[str, ...]) -> SourceCube:
    expected_digest = manifest_entry.get("sha256")
    pinned_digest = EXPECTED_SHA256.get(path.name)
    actual_digest = _sha256(path) if path.is_file() else None
    if not expected_digest or expected_digest != pinned_digest or actual_digest != pinned_digest:
        raise ForcingCompatibilityError(
            f"Checksum mismatch for {path.name}; refusing unverified or synthetic replacement data"
        )
    vars_ = _read_nc(path, ("time",) + names)
    times = vars_["time"].astype(np.float64).reshape(-1)
    lat, lon = vars_["latitude"].astype(float), vars_["longitude"].astype(float)
    if times.shape != EXPECTED_TIMES.shape or not np.array_equal(times, EXPECTED_TIMES):
        raise ForcingCompatibilityError(f"{path.name} timestamps do not match the approved UTC interval")
    if lat.ndim != 2 or lon.shape != lat.shape:
        raise ForcingCompatibilityError(f"{path.name} must contain matching 2D curvilinear coordinates")
    fields = {}
    for name in names:
        values = vars_[name].astype(np.float64)
        if values.shape != (times.size,) + lat.shape:
            raise ForcingCompatibilityError(f"Unexpected shape for {name}: {values.shape}")
        values[~np.isfinite(values) | (np.abs(values) >= MISSING_LIMIT)] = np.nan
        fields[name] = values
    return SourceCube(times, lat, lon, fields)


def _target_axes(bbox: dict[str, float], step: float) -> tuple[np.ndarray, np.ndarray]:
    west, east = float(bbox["west"]), float(bbox["east"])
    south, north = float(bbox["south"]), float(bbox["north"])
    # Use grid-aligned regular axes strictly within the requested source box.
    lon0 = math.ceil((west - 1e-10) / step) * step
    lon1 = math.floor((east + 1e-10) / step) * step
    lat0 = math.ceil((south - 1e-10) / step) * step
    lat1 = math.floor((north + 1e-10) / step) * step
    lons = np.round(np.arange(lon0, lon1 + step * 0.25, step), 10)
    lats = np.round(np.arange(lat0, lat1 + step * 0.25, step), 10)
    if min(lats.size, lons.size) < 2:
        raise ForcingCompatibilityError("Regional bbox is too small for M3's bilinear interpolation")
    return lats, lons


def _regrid(cube: SourceCube, field_name: str, lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
    """Linear scattered interpolation in local equirectangular coordinates."""
    lat2, lon2 = cube.lat, cube.lon
    lat_mesh, lon_mesh = np.meshgrid(lats, lons, indexing="ij")
    # At this latitude, cos(mean latitude) converts longitude degrees to an
    # approximately metric east axis and avoids skewing triangulation weights.
    lat_ref = float(np.nanmean(lat2))
    scale = math.cos(math.radians(lat_ref))
    source_points = np.column_stack((lon2.ravel() * scale, lat2.ravel()))
    target_points = np.column_stack((lon_mesh.ravel() * scale, lat_mesh.ravel()))
    source_values = cube.fields[field_name]
    result = np.full((cube.times.size, lats.size, lons.size), np.nan, dtype=np.float64)
    for it in range(cube.times.size):
        vals = source_values[it].ravel()
        valid = np.isfinite(source_points).all(axis=1) & np.isfinite(vals)
        points, samples = source_points[valid], vals[valid]
        if len(samples) < 3:
            raise ForcingCompatibilityError(f"Too few valid real samples for {field_name} at time index {it}")
        try:
            interp = LinearNDInterpolator(points, samples, fill_value=np.nan, rescale=False)
            result[it] = np.asarray(interp(target_points)).reshape(lats.size, lons.size)
        except QhullError as exc:
            raise ForcingCompatibilityError(f"Cannot triangulate real {field_name} at time index {it}") from exc
    return result


def _largest_true_rectangle(mask: np.ndarray) -> tuple[slice, slice]:
    """Find the largest axis-aligned all-valid block in a 2D boolean mask."""
    heights = np.zeros(mask.shape[1], dtype=int)
    best_area, best = 0, None
    for row in range(mask.shape[0]):
        heights = np.where(mask[row], heights + 1, 0)
        stack: list[int] = []
        for col in range(mask.shape[1] + 1):
            height = heights[col] if col < mask.shape[1] else 0
            while stack and heights[stack[-1]] > height:
                idx = stack.pop()
                h = heights[idx]
                left = stack[-1] + 1 if stack else 0
                area = h * (col - left)
                if area > best_area:
                    best_area = area
                    best = (slice(row - h + 1, row + 1), slice(left, col))
            stack.append(col)
    if best is None or best_area < 4:
        raise ForcingCompatibilityError("No sufficiently large fully covered regular grid is shared by both forcings")
    return best


def load_norse2019_field(data_dir: Path | str = DEFAULT_DATA_DIR,
                         grid_step_deg: float = GRID_STEP_DEG) -> MetoceanField:
    """Load verified forcing and convert it to M3's exact field schema.

    Raises on absent or modified source files, incompatible time arrays, missing
    forcing, or insufficient common interpolation coverage. It never falls back.
    """
    # Import lazily so the app's test harness may configure TIDETRACE_DATA
    # before importing app modules.
    from app.drift.fields import MetoceanField

    root = Path(data_dir)
    manifest_path = root / MANIFEST_NAME
    if not manifest_path.is_file():
        raise ForcingCompatibilityError(f"Required forcing manifest is missing: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        entries = {item["path"]: item for item in manifest["files"]}
        bbox = manifest["wgs84_subset_bbox_with_buffer"]
    except Exception as exc:
        raise ForcingCompatibilityError(f"Invalid forcing manifest: {exc}") from exc
    meps_path, nk_path = root / MEPS_NAME, root / NORKYST_NAME
    if MEPS_NAME not in entries or NORKYST_NAME not in entries:
        raise ForcingCompatibilityError("Manifest does not identify both approved source subsets")

    meps = _source_cube(meps_path, entries[MEPS_NAME], ("eastward_wind_10m", "northward_wind_10m"))
    norkyst = _source_cube(nk_path, entries[NORKYST_NAME], ("u_eastward", "v_northward"))
    if not np.array_equal(meps.times, norkyst.times):
        raise ForcingCompatibilityError("MEPS and NorKyst time coordinates do not align exactly")
    if not np.isfinite(grid_step_deg) or grid_step_deg <= 0:
        raise ValueError("grid_step_deg must be a positive finite number")

    lats, lons = _target_axes(bbox, float(grid_step_deg))
    converted = {
        "u_wind10": _regrid(meps, "eastward_wind_10m", lats, lons),
        "v_wind10": _regrid(meps, "northward_wind_10m", lats, lons),
        "u_current": _regrid(norkyst, "u_eastward", lats, lons),
        "v_current": _regrid(norkyst, "v_northward", lats, lons),
    }
    common = np.ones((lats.size, lons.size), dtype=bool)
    for data in converted.values():
        common &= np.isfinite(data).all(axis=0)
    rs, cs = _largest_true_rectangle(common)
    lats, lons = lats[rs], lons[cs]
    converted = {key: values[:, rs, cs] for key, values in converted.items()}
    if any(not np.isfinite(values).all() for values in converted.values()):
        raise ForcingCompatibilityError("Internal adapter error: output has missing/nonfinite forcing")
    for name, values in converted.items():
        if np.max(np.abs(values)) >= MISSING_LIMIT:
            raise ForcingCompatibilityError(f"Unmasked fill values remain in {name}")

    field = MetoceanField(
        times=meps.times.copy(), lats=lats, lons=lons, data=converted,
        source="NORSE2019 MEPS 10 m winds + NorKyst800 surface currents",
        license="Source datasets: Norwegian Meteorological Institute; see source dataset terms.",
        synthetic=False, scene_id="norse2019_real_forcing", live=False,
    )
    # Extra audit metadata is kept outside the M3 data contract.
    field.adapter_metadata = {
        "adapter": "scripts/norse2019_adapter.py",
        "source_files": {"meps": MEPS_NAME, "norkyst800": NORKYST_NAME},
        "source_sha256": {"meps": EXPECTED_SHA256[MEPS_NAME], "norkyst800": EXPECTED_SHA256[NORKYST_NAME]},
        "time_units": "seconds since 1970-01-01 00:00:00 UTC",
        "time_count": int(meps.times.size),
        "time_start_epoch": float(meps.times[0]), "time_end_epoch": float(meps.times[-1]),
        "source_wind_units": "m s-1; already rotated to east/north in prepared MEPS subset",
        "source_current_units": "m s-1; u_eastward/v_northward already earth-oriented",
        "source_current_depth_index": 0, "source_current_depth_m": 0.0,
        "target_grid": "regular latitude/longitude; linear scattered interpolation in local metric coordinates",
        "grid_step_deg": float(grid_step_deg),
        "source_bbox": dict(bbox), "output_bounds_wsen": list(field.bounds),
        "output_shape_time_lat_lon": [int(meps.times.size), int(lats.size), int(lons.size)],
        "wave_stokes_enabled": False,
        "synthetic_fallback": False,
    }
    return field


def describe_mapping() -> dict[str, str]:
    return {
        "MEPS eastward_wind_10m (m s-1)": "MetoceanField.data['u_wind10']",
        "MEPS northward_wind_10m (m s-1)": "MetoceanField.data['v_wind10']",
        "NorKyst u_eastward at depth index 0 (m s-1)": "MetoceanField.data['u_current']",
        "NorKyst v_northward at depth index 0 (m s-1)": "MetoceanField.data['v_current']",
        "Unix epoch time (UTC seconds)": "MetoceanField.times (epoch seconds, strictly increasing)",
        "2D curvilinear lon/lat source grids": "Regular 1D MetoceanField.lons/lats via linear scattered interpolation",
        "Wave height/period/direction": "Absent; Stokes is explicitly disabled",
    }
