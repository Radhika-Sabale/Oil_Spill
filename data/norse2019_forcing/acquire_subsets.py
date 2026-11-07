"""Acquire the approved NORSE2019 regional forcing subset using OPeNDAP."""
from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy.io import netcdf_file

OUT = Path(__file__).parent
MEPS = "https://thredds.met.no/thredds/dodsC/meps25epsarchive/2019/06/12/meps_mbr0_pp_2_5km_20190612T00Z.nc"
NKROOT = "https://thredds.met.no/thredds/dodsC/fou-hi/norkyst800m-1h/"
TIME = np.arange(4, 25)
BBOX = (1.968, 2.901, 59.552, 60.073)  # approved buffered WGS84 bounds


def crop_window(lon, lat):
    w, e, s, n = BBOX
    inside = np.isfinite(lon) & np.isfinite(lat) & (lon >= w) & (lon <= e) & (lat >= s) & (lat <= n)
    rows, cols = np.where(inside)
    if not len(rows):
        raise RuntimeError("Selected source grid does not intersect approved regional bbox")
    r0, r1 = max(0, rows.min()-1), min(lon.shape[0], rows.max()+2)
    c0, c1 = max(0, cols.min()-1), min(lon.shape[1], cols.max()+2)
    return slice(r0, r1), slice(c0, c1)


def ascii_data(url: str, expr: str) -> str:
    req = urllib.request.Request(url + ".ascii?" + urllib.parse.quote(expr, safe=".,"),
                                 headers={"User-Agent": "SentinelTrace-NORSE2019-subset/1.0"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.read().decode("ascii")


def values(url: str, expr: str, var: str) -> np.ndarray:
    s = ascii_data(url, expr)
    # DAP2 ASCII uses one data block followed by optional Grid coordinate maps.
    marker = re.search(r"(?m)^" + re.escape(var) + r"(?:\." + re.escape(var) + r")?\[[^\n]*\]\s*$", s)
    if not marker:
        raise RuntimeError(f"Could not find {var} block in OPeNDAP response: {s[:350]}")
    body = s[marker.end():].split("\n\n", 1)[0]
    out = []
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        # Indexed DAP rows look like [0][1], value, value; discard row labels.
        if line.startswith("["):
            line = line.split(",", 1)[1] if "," in line else ""
        out.extend(float(x) for x in re.findall(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?", line))
    return np.asarray(out, dtype=np.float64)


def get(url, expr, var, shape):
    a = values(url, expr, var)
    if a.size != int(np.prod(shape)):
        raise RuntimeError(f"{var} expected {shape} = {np.prod(shape)} values; received {a.size}")
    return a.reshape(shape)


def put(nc, name, dims, data, units=None, **attrs):
    v = nc.createVariable(name, "f", dims)
    v[:] = np.asarray(data, dtype=np.float32)
    if units:
        v.units = units
    for k, val in attrs.items():
        setattr(v, k, val)
    return v


def epoch_iso(a):
    return [datetime.fromtimestamp(float(x), timezone.utc).isoformat().replace("+00:00", "Z") for x in a]


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


# MEPS indices previously spatially selected from the approved buffered ROI.
iy0, iy1, ix0, ix1 = 313, 341, 106, 132  # inclusive; y=29, x=27
sel = f"[{TIME[0]}:1:{TIME[-1]}][{iy0}:1:{iy1}][{ix0}:1:{ix1}]"
shape = (len(TIME), iy1-iy0+1, ix1-ix0+1)
uw = get(MEPS, "x_wind_10m"+sel, "x_wind_10m", shape)
vw = get(MEPS, "y_wind_10m"+sel, "y_wind_10m", shape)
lon = get(MEPS, f"longitude.longitude[{iy0}:1:{iy1}][{ix0}:1:{ix1}]", "longitude", shape[1:],)
lat = get(MEPS, f"latitude.latitude[{iy0}:1:{iy1}][{ix0}:1:{ix1}]", "latitude", shape[1:])
t = get(MEPS, f"time[{TIME[0]}:1:{TIME[-1]}]", "time", (len(TIME),))
x = get(MEPS, f"x[{ix0}:1:{ix1}]", "x", (shape[2],))
y = get(MEPS, f"y[{iy0}:1:{iy1}]", "y", (shape[1],))
# MEPS LCC grid x/y winds rotated to true east/north using local meridian convergence.
gamma = np.deg2rad(np.sin(np.deg2rad(63.0)) * (lon - 15.0))
east = uw * np.cos(gamma)[None, :, :] + vw * np.sin(gamma)[None, :, :]
north = -uw * np.sin(gamma)[None, :, :] + vw * np.cos(gamma)[None, :, :]
rs, cs = crop_window(lon, lat)
uw, vw, east, north = uw[:, rs, cs], vw[:, rs, cs], east[:, rs, cs], north[:, rs, cs]
lon, lat, x, y = lon[rs, cs], lat[rs, cs], x[cs], y[rs]
shape = uw.shape
mw, me, ms, mn = BBOX
meps_region = (lon >= mw) & (lon <= me) & (lat >= ms) & (lat <= mn)
for arr in (uw, vw, east, north):
    arr[:, ~meps_region] = np.nan
if len(t) != 21 or epoch_iso(t)[0] != "2019-06-12T04:00:00Z" or epoch_iso(t)[-1] != "2019-06-13T00:00:00Z":
    raise RuntimeError("MEPS selected times do not match requested UTC interval")
meps_path = OUT / "meps_mbr0_pp_20190612T00Z_norse_roi_20190612T0400_20190613T0000.nc"
with netcdf_file(meps_path, "w", version=2) as nc:
    nc.createDimension("time", len(t)); nc.createDimension("y", len(y)); nc.createDimension("x", len(x))
    tv = nc.createVariable("time", "d", ("time",)); tv[:] = t; tv.units = "seconds since 1970-01-01 00:00:00 UTC"; tv.standard_name = "time"
    xv = nc.createVariable("x", "f", ("x",)); xv[:] = x; xv.units = "m"; xv.axis = "X"
    yv = nc.createVariable("y", "f", ("y",)); yv[:] = y; yv.units = "m"; yv.axis = "Y"
    put(nc, "longitude", ("y","x"), lon, "degrees_east"); put(nc, "latitude", ("y","x"), lat, "degrees_north")
    put(nc, "x_wind_10m", ("time","y","x"), uw, "m s-1", long_name="source grid-relative x wind")
    put(nc, "y_wind_10m", ("time","y","x"), vw, "m s-1", long_name="source grid-relative y wind")
    put(nc, "eastward_wind_10m", ("time","y","x"), east, "m s-1", standard_name="eastward_wind")
    put(nc, "northward_wind_10m", ("time","y","x"), north, "m s-1", standard_name="northward_wind")
    nc.title = "Regional MEPS wind subset for NORSE2019; OPeNDAP extraction"
    nc.source_url = MEPS; nc.grid_rotation = "gamma = sin(63deg)*(longitude-15deg); east=u*cos(gamma)+v*sin(gamma); north=-u*sin(gamma)+v*cos(gamma)"

# NorKyst indices for the same buffered WGS84 region; surface depth is index 0 (0 m).
ny0, ny1, nx0, nx1 = 650, 739, 226, 319  # inclusive; Y=90, X=94
nk_shape = (20, ny1-ny0+1, nx1-nx0+1)
def nk_get(day, var, time_range, ntime):
    base = NKROOT + f"NorKyst-800m_ZDEPTHS_his.an.201906{day:02d}00.nc"
    s = f"[{time_range}][0][{ny0}:1:{ny1}][{nx0}:1:{nx1}]"
    return get(base, var+"."+var+s, var, (ntime, nk_shape[1], nk_shape[2]))

u12 = nk_get(12, "u_eastward", "4:1:23", 20)
v12 = nk_get(12, "v_northward", "4:1:23", 20)
u13 = nk_get(13, "u_eastward", "0:1:0", 1)[0:1]
v13 = nk_get(13, "v_northward", "0:1:0", 1)[0:1]
u = np.concatenate([u12, u13]); v = np.concatenate([v12, v13])
def nk_coord(var):
    return get(NKROOT+"NorKyst-800m_ZDEPTHS_his.an.2019061200.nc", f"{var}[{ny0}:1:{ny1}][{nx0}:1:{nx1}]", var, nk_shape[1:])
nlon, nlat = nk_coord("lon"), nk_coord("lat")
rs, cs = crop_window(nlon, nlat)
nlon, nlat = nlon[rs, cs], nlat[rs, cs]
u12, v12, u13, v13 = u12[:, rs, cs], v12[:, rs, cs], u13[:, rs, cs], v13[:, rs, cs]
u = np.concatenate([u12, u13]); v = np.concatenate([v12, v13])
nk_shape = (20, nlon.shape[0], nlon.shape[1])
mw, me, ms, mn = BBOX
nk_region = (nlon >= mw) & (nlon <= me) & (nlat >= ms) & (nlat <= mn)
fill = np.float32(1.0e37)
u[:, ~nk_region] = fill; v[:, ~nk_region] = fill
nt12 = get(NKROOT+"NorKyst-800m_ZDEPTHS_his.an.2019061200.nc", "time[4:1:23]", "time", (20,))
nt13 = get(NKROOT+"NorKyst-800m_ZDEPTHS_his.an.2019061300.nc", "time[0:1:0]", "time", (1,))
nt = np.concatenate([nt12, nt13])
if len(nt) != 21 or epoch_iso(nt)[0] != "2019-06-12T04:00:00Z" or epoch_iso(nt)[-1] != "2019-06-13T00:00:00Z":
    raise RuntimeError("NorKyst selected times do not match requested UTC interval")
# NorKyst's documented ROMS depth coordinate is positive down; index zero is 0 m.
depths = get(NKROOT+"NorKyst-800m_ZDEPTHS_his.an.2019061200.nc", "depth[0:1:15]", "depth", (16,))
if depths[0] != 0.0:
    raise RuntimeError("NorKyst depth index 0 is not the shallowest level")
# Preserve the source fill sentinel in the NetCDF variable and report it as missing.
nk_path = OUT / "norkyst800_zdepths_surface_20190612T0400_20190613T0000.nc"
with netcdf_file(nk_path, "w", version=2) as nc:
    nc.createDimension("time", len(nt)); nc.createDimension("Y", nk_shape[1]); nc.createDimension("X", nk_shape[2])
    tv = nc.createVariable("time", "d", ("time",)); tv[:] = nt; tv.units = "seconds since 1970-01-01 00:00:00 UTC"; tv.standard_name = "time"
    put(nc, "longitude", ("Y","X"), nlon, "degrees_east"); put(nc, "latitude", ("Y","X"), nlat, "degrees_north")
    for name, data in (("u_eastward", u), ("v_northward", v)):
        var = put(nc, name, ("time","Y","X"), data, "m s-1")
        var._FillValue = fill
    nc.surface_depth_m = float(depths[0]); nc.source_depth_index = 0
    nc.source_files = "NorKyst-800m_ZDEPTHS_his.an.2019061200.nc; NorKyst-800m_ZDEPTHS_his.an.2019061300.nc"
    nc.source_url_root = NKROOT

# Reopen and validate deliverables using SciPy's NetCDF reader.
manifest = {
  "benchmark": "NORSE2019; forcing subset only; no hindcast performed",
  "requested_utc_interval": ["2019-06-12T04:00:00Z", "2019-06-13T00:00:00Z"],
  "wgs84_subset_bbox_with_buffer": {"west":1.968,"east":2.901,"south":59.552,"north":60.073,"buffer_km":20},
  "spatial_selection": "A rectangular native-grid window enclosing the approved WGS84 bbox; data cells outside the bbox are masked. Reported valid-coordinate coverage below.",
  "files": [],
  "excluded": {"wave_stokes_forcing": "Explicitly excluded from first experiment; no substitute used."},
  "source_changes": "None; only this separate acquisition adapter and its outputs are in the benchmark folder."
}
for path, dims, vars_, coverage in [
 (meps_path, {"time":21,"y":shape[1],"x":shape[2]}, ["time","x","y","longitude","latitude","x_wind_10m","y_wind_10m","eastward_wind_10m","northward_wind_10m"], [lon,lat]),
 (nk_path, {"time":21,"Y":nk_shape[1],"X":nk_shape[2]}, ["time","longitude","latitude","u_eastward","v_northward"], [nlon,nlat])]:
    with netcdf_file(path, "r", mmap=False) as nc:
        gotdims = {k: (len(v) if not isinstance(v, int) else v) for k,v in nc.dimensions.items()}
        if gotdims != dims or not set(vars_).issubset(nc.variables):
            raise RuntimeError(f"Validation failed for {path.name}: dims={gotdims}, vars={list(nc.variables)}")
    lo, la = coverage
    region_mask = meps_region if path == meps_path else nk_region
    region_lon, region_lat = lo[region_mask], la[region_mask]
    vals = u if path == nk_path else uw
    relevant_vals = vals[..., region_mask]
    miss = int(np.count_nonzero(~np.isfinite(relevant_vals) | (np.abs(relevant_vals) >= 1e36)))
    manifest["files"].append({
      "path": path.name, "size_bytes": path.stat().st_size, "sha256": sha(path), "dimensions": dims,
      "variables": vars_, "units": {"time":"seconds since 1970-01-01 00:00:00 UTC", "coordinates":"degrees", "wind_and_current":"m s-1"},
      "timestamps_utc": ["2019-06-12T04:00:00Z", "2019-06-13T00:00:00Z"], "timestamp_count":21,
      "actual_coordinate_bounds": {"longitude":[float(np.nanmin(region_lon)),float(np.nanmax(region_lon))],"latitude":[float(np.nanmin(region_lat)),float(np.nanmax(region_lat))]},
      "missing_or_nonfinite_in_first_component_within_bbox": miss, "masked_grid_cells_outside_bbox": int(region_mask.size-region_mask.sum()), "array_order":"time, y/Y, x/X; axes ascending",
      "details": ("source x/y winds retained; true EN winds derived with LCC meridian convergence gamma = sin(63deg)*(lon-15deg). No explicit source fill metadata on wind variables; nonfinite/extreme values counted." if path==meps_path else "u_eastward/v_northward are already earth-oriented; depth index 0 = 0.0 m; values >= 1e36 and nonfinite treated as missing; original fill sentinel 1e37 recorded."),
    })
manifest["inputs"] = {
 "MEPS": {"file":"meps_mbr0_pp_2_5km_20190612T00Z.nc","archive_size_estimate_bytes":1551000000,"selected_lead_hours":[4,24],"native_resolution":"2.5 km; hourly; Lambert conformal grid","wind_rotation":"east=u*cos(gamma)+v*sin(gamma); north=-u*sin(gamma)+v*cos(gamma)"},
 "NorKyst800": {"files":["NorKyst-800m_ZDEPTHS_his.an.2019061200.nc","NorKyst-800m_ZDEPTHS_his.an.2019061300.nc"],"archive_size_estimates_bytes":[5189000000,5200000000],"native_resolution":"800 m; hourly; 16 fixed depths","surface_depth_index":0,"depth_levels_m":depths.tolist(),"coordinates":"curvilinear lon/lat; projected X/Y axes ascending","current_components":"u_eastward, v_northward already earth-oriented"}
}
(OUT/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
print(json.dumps({"files":[{"name":x["path"],"bytes":x["size_bytes"],"sha256":x["sha256"],"dims":x["dimensions"]} for x in manifest["files"]],"bbox":manifest["files"]},indent=2))
