"""Download real currents, 10 m wind and optional wave forcing once.

Clause (b) of the problem statement is not mockable, so this script fetches real
fields and freezes them into `data/metocean/<scene_id>.npz`. Run it while you
have internet. The product then runs in airplane mode.

Source: Open-Meteo. No API key, no account, free for non-commercial use, data
licensed CC BY 4.0. Two endpoints are used:

  wind      https://archive-api.open-meteo.com/v1/archive
            hourly wind_speed_10m, wind_direction_10m   (ERA5 reanalysis)
  currents  https://marine-api.open-meteo.com/v1/marine
            hourly ocean_current_velocity, ocean_current_direction
  waves     https://marine-api.open-meteo.com/v1/marine
            hourly wave_height, wave_peak_period, wave_direction

Conventions, which are easy to get backwards and matter enormously:

  * Wind direction is meteorological, the direction the wind comes FROM.
    u = -speed * sin(dir),  v = -speed * cos(dir)
  * Ocean current direction is oceanographic, the direction the water goes TO.
    u =  speed * sin(dir),  v =  speed * cos(dir)
  * Wind is requested in m/s. Current velocity arrives in km/h and is converted.

Usage:
    python scripts/build_metocean_cache.py --all
    python scripts/build_metocean_cache.py --scene arabian_sea_demo
    python scripts/build_metocean_cache.py --lat 19.2 --lon 71.4 --t 2023-06-14T05:40:00Z --id manual_box
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config, scenes as scenes_mod          # noqa: E402
from app.drift import fields as fields_mod            # noqa: E402

WIND_URL = "https://archive-api.open-meteo.com/v1/archive"
WIND_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
LICENSE = "Open-Meteo, CC BY 4.0, free for non-commercial use"

# Copernicus Marine. Eddy-resolving at 1/12 degree, hourly, and the currents
# an operational drift model would actually use. It needs an account, read
# from the environment so no credential is ever written into the repository:
#
#     set COPERNICUSMARINE_SERVICE_USERNAME and ..._PASSWORD
#
# It does NOT cover every basin. See the note in `fetch_currents_cmems`.
# 6-hourly instantaneous currents, interpolated to the cube's hourly steps.
# Deliberately the `-cur` physics product and not `merged-uv`: the merged one
# folds in Stokes drift, and the drift model adds its own wind term at 3% of
# U10, so taking both would count the wave-driven part twice. Daily is the
# fallback when a date sits outside the 6-hourly window.
CMEMS_HOURLY = "cmems_mod_glo_phy-cur_anfc_0.083deg_PT6H-i"
CMEMS_DAILY = "cmems_mod_glo_phy-cur_anfc_0.083deg_P1D-m"
CMEMS_LICENSE = ("E.U. Copernicus Marine Service Information; "
                 "Global Ocean Physics Analysis and Forecast, GLOBAL_ANALYSISFORECAST_PHY_001_024")
KMH_TO_MS = 1000.0 / 3600.0


def _http_json(url: str, params: Dict[str, Any], retries: int = 3, pause: float = 2.0) -> Dict[str, Any]:
    import urllib.parse
    import urllib.request

    qs = urllib.parse.urlencode(params, doseq=True)
    full = "%s?%s" % (url, qs)
    last: Optional[Exception] = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(full, timeout=90) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            last = exc
            time.sleep(pause * (attempt + 1))
    raise RuntimeError("request failed after %d attempts: %s\n%s" % (retries, last, full))


def _grid(lat0: float, lon0: float, half_deg: float, n: int) -> Tuple[np.ndarray, np.ndarray]:
    lats = np.linspace(lat0 - half_deg, lat0 + half_deg, n)
    lons = np.linspace(lon0 - half_deg, lon0 + half_deg, n)
    return lats, lons


def _as_list(payload: Any) -> List[Dict[str, Any]]:
    """Open-Meteo returns a list for multi-point queries and a dict for one."""
    return payload if isinstance(payload, list) else [payload]


def _hours(t_center: datetime, back_h: int, fwd_h: int) -> Tuple[str, str]:
    start = (t_center - timedelta(hours=back_h)).date().isoformat()
    end = (t_center + timedelta(hours=fwd_h)).date().isoformat()
    return start, end


def fetch_wind(lats: np.ndarray, lons: np.ndarray, start: str, end: str,
               use_archive: bool = True) -> Tuple[List[str], np.ndarray, np.ndarray]:
    """Returns (times, u, v) with u and v shaped (nt, nlat, nlon) in m/s."""
    lat_list, lon_list = _flatten(lats, lons)
    params = {
        "latitude": lat_list,
        "longitude": lon_list,
        "hourly": "wind_speed_10m,wind_direction_10m",
        "wind_speed_unit": "ms",
        "timezone": "UTC",
        "start_date": start,
        "end_date": end,
    }
    url = WIND_URL if use_archive else WIND_FORECAST_URL
    data = _as_list(_http_json(url, params))
    times = data[0]["hourly"]["time"]
    nt = len(times)
    u = np.zeros((nt, lats.size, lons.size), dtype=np.float32)
    v = np.zeros_like(u)
    for k, block in enumerate(data):
        i, j = divmod(k, lons.size)
        sp = np.array(block["hourly"]["wind_speed_10m"], dtype=np.float64)
        di = np.array(block["hourly"]["wind_direction_10m"], dtype=np.float64)
        if sp.size != nt or di.size != nt or not (np.isfinite(sp).all() and np.isfinite(di).all()):
            raise ValueError("ERA5 wind response contains missing or invalid hourly values")
        rad = np.radians(di)
        u[:, i, j] = -sp * np.sin(rad)   # meteorological: comes FROM
        v[:, i, j] = -sp * np.cos(rad)
    return times, u, v


def fetch_currents(lats: np.ndarray, lons: np.ndarray, start: str, end: str,
                   times_ref: List[str]) -> Tuple[np.ndarray, np.ndarray, bool]:
    """Returns (u, v, ok). Falls back to zeros with ok=False if unavailable."""
    lat_list, lon_list = _flatten(lats, lons)
    params = {
        "latitude": lat_list,
        "longitude": lon_list,
        "hourly": "ocean_current_velocity,ocean_current_direction",
        "timezone": "UTC",
        "start_date": start,
        "end_date": end,
    }
    try:
        data = _as_list(_http_json(MARINE_URL, params))
    except Exception as exc:
        print("  currents unavailable: %s" % exc)
        return (np.zeros((len(times_ref), lats.size, lons.size), dtype=np.float32),
                np.zeros((len(times_ref), lats.size, lons.size), dtype=np.float32), False)

    src_times = data[0]["hourly"]["time"]
    idx = _align(src_times, times_ref)
    if idx is None:
        print("  currents unavailable: timestamps do not cover the full wind interval")
        return _zero_currents(lats, lons, times_ref) + (False,)
    nt = len(times_ref)
    u = np.zeros((nt, lats.size, lons.size), dtype=np.float32)
    v = np.zeros_like(u)
    any_data = False
    for k, block in enumerate(data):
        i, j = divmod(k, lons.size)
        sp = np.array(block["hourly"].get("ocean_current_velocity") or [], dtype=np.float64)
        di = np.array(block["hourly"].get("ocean_current_direction") or [], dtype=np.float64)
        if (sp.size != len(src_times) or di.size != len(src_times)
                or not (np.isfinite(sp).all() and np.isfinite(di).all())):
            print("  currents unavailable: incomplete grid; wind-only field retained")
            return _zero_currents(lats, lons, times_ref) + (False,)
        any_data = True
        sp = sp * KMH_TO_MS
        rad = np.radians(di)
        cu = sp * np.sin(rad)   # oceanographic: goes TO
        cv = sp * np.cos(rad)
        u[:, i, j] = cu[idx]
        v[:, i, j] = cv[idx]
    return u, v, any_data


def fetch_waves(lats: np.ndarray, lons: np.ndarray, start: str, end: str,
                times_ref: List[str]) -> Tuple[Optional[np.ndarray], Optional[np.ndarray], Optional[np.ndarray]]:
    """Fetch significant wave height (m) and peak period (s), or report absent.

    Missing or incomplete wave data remains absent rather than being
    replaced with zeros and presented as a measured wave field.
    """
    lat_list, lon_list = _flatten(lats, lons)
    params = {
        "latitude": lat_list,
        "longitude": lon_list,
        "hourly": "wave_height,wave_peak_period,wave_direction",
        "timezone": "UTC",
        "start_date": start,
        "end_date": end,
    }
    try:
        data = _as_list(_http_json(MARINE_URL, params))
        src_times = data[0]["hourly"]["time"]
        hs = np.full((len(times_ref), lats.size, lons.size), np.nan, dtype=np.float32)
        tp = np.full_like(hs, np.nan)
        direction = np.full_like(hs, np.nan)
        for k, block in enumerate(data):
            i, j = divmod(k, lons.size)
            hourly = block["hourly"]
            block_hs = np.asarray(hourly.get("wave_height") or [], dtype=float)
            block_tp = np.asarray(hourly.get("wave_peak_period") or [], dtype=float)
            block_dir = np.asarray(hourly.get("wave_direction") or [], dtype=float)
            if (block_hs.size == len(src_times) and block_tp.size == len(src_times)
                    and block_dir.size == len(src_times)):
                hs[:, i, j] = _interpolate_hourly(src_times, times_ref, block_hs)
                tp[:, i, j] = _interpolate_hourly(src_times, times_ref, block_tp)
                direction[:, i, j] = _interpolate_hourly(src_times, times_ref, block_dir)
        if not (np.isfinite(hs).any() and np.isfinite(tp).any()
                and np.isfinite(direction).any()):
            return None, None, None
        return hs, tp, direction
    except Exception as exc:
        print("  waves unavailable: %s" % exc)
        return None, None, None


def _flatten(lats: np.ndarray, lons: np.ndarray) -> Tuple[List[float], List[float]]:
    lat_list: List[float] = []
    lon_list: List[float] = []
    for la in lats:
        for lo in lons:
            lat_list.append(round(float(la), 4))
            lon_list.append(round(float(lo), 4))
    return lat_list, lon_list


def _align(src_times: List[str], ref_times: List[str]) -> np.ndarray:
    pos = {t: i for i, t in enumerate(src_times)}
    if any(t not in pos for t in ref_times):
        return None
    return np.array([pos[t] for t in ref_times], dtype=int)


def _interpolate_hourly(src_times: List[str], ref_times: List[str], values) -> np.ndarray:
    """Interpolate wave values by UTC timestamp; never align by array index."""
    def epoch(value):
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()

    source_t = np.asarray([epoch(t) for t in src_times], dtype=float)
    target_t = np.asarray([epoch(t) for t in ref_times], dtype=float)
    values = np.asarray(values, dtype=float)
    valid = np.isfinite(values)
    if valid.sum() == 0:
        return np.full(target_t.shape, np.nan, dtype=float)
    if valid.sum() == 1:
        out = np.full(target_t.shape, np.nan, dtype=float)
        exact = np.isclose(target_t, source_t[valid][0], atol=1.0)
        out[exact] = values[valid][0]
        return out
    return np.interp(target_t, source_t[valid], values[valid],
                     left=np.nan, right=np.nan)


def fetch_currents_cmems(lats: np.ndarray, lons: np.ndarray, start: str, end: str,
                         times_ref: List[str]) -> Tuple[np.ndarray, np.ndarray, bool]:
    """Surface currents from Copernicus Marine, same contract as the Open-Meteo path.

    Returns (u, v, ok). `ok` is False whenever the box comes back entirely
    masked, which is not an error and not a network failure -- it is the honest
    answer for a basin the model does not solve.

    The Caspian is exactly that case. It is endorheic, so the global ocean model
    carries it as land: a query over the Baku footprint returns 306 cells and
    306 NaNs. Copernicus publishes no Caspian product either, so this closes the
    Gulf of Mexico and the Arabian Sea and leaves the Caspian wind-driven, which
    the run already warns about. Better an explicit gap than an invented field.
    """
    try:
        import copernicusmarine as cm
    except ImportError:
        print("  CMEMS: copernicusmarine is not installed; skipping")
        return _zero_currents(lats, lons, times_ref) + (False,)

    if not os.environ.get("COPERNICUSMARINE_SERVICE_USERNAME"):
        print("  CMEMS: no credentials in the environment; skipping")
        return _zero_currents(lats, lons, times_ref) + (False,)

    ref = np.array([np.datetime64(t) for t in times_ref])
    pad = 0.3                      # a little wider than the grid, for interpolation
    for dataset_id in (CMEMS_HOURLY, CMEMS_DAILY):
        try:
            ds = cm.open_dataset(
                dataset_id=dataset_id,
                minimum_longitude=float(lons.min()) - pad,
                maximum_longitude=float(lons.max()) + pad,
                minimum_latitude=float(lats.min()) - pad,
                maximum_latitude=float(lats.max()) + pad,
                start_datetime=start, end_datetime=end,
                maximum_depth=1.0)
        except Exception as exc:
            print("  CMEMS %s: %s" % (dataset_id, str(exc)[:110]))
            continue

        try:
            if "depth" in ds.dims:
                ds = ds.isel(depth=0)
            got = ds.interp(longitude=("lon", lons), latitude=("lat", lats),
                            time=("time", ref), kwargs={"fill_value": None})
            u = np.asarray(got["uo"].values, dtype=np.float32)
            v = np.asarray(got["vo"].values, dtype=np.float32)
        except Exception as exc:
            print("  CMEMS %s: interpolation failed: %s" % (dataset_id, str(exc)[:110]))
            continue

        # interp returns (time, lat, lon) here, which is the cube's own order.
        u = u.reshape(len(times_ref), lats.size, lons.size)
        v = v.reshape(len(times_ref), lats.size, lons.size)
        finite = np.isfinite(u) & np.isfinite(v)
        if not finite.all():
            print("  CMEMS %s: every cell is masked over this box" % dataset_id)
            print("  CMEMS %s: partial values will not be substituted with zero current" % dataset_id)
            continue

        coverage = 100.0 * finite.mean()
        print("  CMEMS %s: %.1f%% of cells have data" % (dataset_id, coverage))
        return (u, v, True)

    return _zero_currents(lats, lons, times_ref) + (False,)


def _zero_currents(lats, lons, times_ref):
    z = np.zeros((len(times_ref), lats.size, lons.size), dtype=np.float32)
    return z, z.copy()


def build_box(scene_id: str, lat: float, lon: float, t_center: datetime,
              half_deg: float = 1.0, n: int = 5,
              back_h: int = 72, fwd_h: int = 48,
              out_dir: Path = None, currents: str = "auto") -> Dict[str, Any]:
    """Fetch, convert, and freeze one cube."""
    out_dir = Path(out_dir or config.METOCEAN_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    lats, lons = _grid(lat, lon, half_deg, n)
    start, end = _hours(t_center, back_h, fwd_h)

    recent = (datetime.now(timezone.utc) - t_center).days < 6
    print("[%s] wind %s .. %s  grid %dx%d  centre %.3f, %.3f%s"
          % (scene_id, start, end, n, n, lat, lon, "  (forecast endpoint)" if recent else ""))
    times, uw, vw = fetch_wind(lats, lons, start, end, use_archive=not recent)

    print("[%s] currents" % scene_id)
    current_source = None
    uc = vc = None
    ok = False
    if currents in ("auto", "cmems"):
        uc, vc, ok = fetch_currents_cmems(lats, lons, start, end, times)
        if ok:
            current_source = "CMEMS GLOBAL_ANALYSISFORECAST_PHY_001_024"
    if not ok and currents in ("auto", "open-meteo"):
        if currents == "auto":
            print("  falling back to the Open-Meteo marine model")
        uc, vc, ok = fetch_currents(lats, lons, start, end, times)
        if ok:
            current_source = "Open-Meteo marine"
    if uc is None:
        uc, vc = _zero_currents(lats, lons, times)
    if not ok:
        print("  WARNING: no ocean current data returned for this box and period.")
        print("  Drift will be wind driven only. That is a real limitation, not a mock.")

    print("[%s] wave forcing" % scene_id)
    wave_hs, wave_tp, wave_dir = fetch_waves(lats, lons, start, end, times)
    wave_data = {}
    if (wave_hs is not None and wave_tp is not None and wave_dir is not None
            and np.isfinite(wave_hs).all() and np.isfinite(wave_tp).all()
            and np.isfinite(wave_dir).all()):
        wave_data = {"wave_hs": wave_hs, "wave_tp": wave_tp, "wave_dir": wave_dir}
        print("  significant wave height and peak period cached")
    else:
        print("  WARNING: wave forcing unavailable; Stokes drift will be omitted")

    retrieved_utc = datetime.now(timezone.utc).isoformat()
    field = fields_mod._from_arrays(
        times, lats, lons,
        {"u_current": uc, "v_current": vc, "u_wind10": uw, "v_wind10": vw,
         **wave_data},
        source="Open-Meteo ERA5 10 m wind + %s currents%s (retrieved %s)"
               % (current_source or "no",
                  " + marine Hs/Tp/direction waves" if wave_data else "",
                  retrieved_utc),
        license_=LICENSE + ("; " + CMEMS_LICENSE if current_source and "CMEMS" in current_source else ""),
        scene_id=scene_id,
        metadata={
            "retrieved_utc": retrieved_utc,
            "crs": "EPSG:4326",
            "time_resolution": "hourly UTC",
            "period_start_utc": times[0],
            "period_end_utc": times[-1],
            "wind": {"provider": "Open-Meteo", "dataset": "ERA5 reanalysis",
                     "endpoint": WIND_URL,
                     "variables": ["wind_speed_10m", "wind_direction_10m"],
                     "units": "m/s; eastward/northward components"},
            "currents": ({"provider": current_source,
                          "endpoint": "Copernicus Marine Toolbox" if current_source and "CMEMS" in current_source else MARINE_URL,
                          "variables": ["ocean_current_velocity", "ocean_current_direction"],
                          "units": "m/s; eastward/northward components"}
                         if ok else {"status": "unavailable; wind-only forcing"}),
            "waves": ({"provider": "Open-Meteo Marine API", "endpoint": MARINE_URL,
                       "variables": ["wave_height", "wave_peak_period", "wave_direction"]}
                      if wave_data else {"status": "unavailable; Stokes drift omitted"}),
        },
    )
    path = out_dir / ("%s.npz" % scene_id)
    fields_mod.save_npz(path, field)

    speed = float(np.mean(np.hypot(uc, vc)))
    wspeed = float(np.mean(np.hypot(uw, vw)))
    print("  saved %s  (%d hours, mean current %.3f m/s, mean wind %.2f m/s)"
          % (path.name, len(times), speed, wspeed))
    return {"scene_id": scene_id, "path": str(path), "hours": len(times),
            "mean_current_ms": round(speed, 4), "mean_wind_ms": round(wspeed, 3),
            "currents_available": ok, "current_source": current_source,
            "stokes_available": fields_mod.load_npz(path).has_stokes}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true", help="every indexed scene")
    ap.add_argument("--scene", action="append", default=[], help="scene id, repeatable")
    ap.add_argument("--lat", type=float)
    ap.add_argument("--lon", type=float)
    ap.add_argument("--t", help="observation time, ISO 8601 UTC")
    ap.add_argument("--id", help="scene id for a manual box")
    ap.add_argument("--half-deg", type=float, default=1.0)
    ap.add_argument("--grid", type=int, default=5, help="points per side")
    ap.add_argument("--back-hours", type=int, default=72)
    ap.add_argument("--forward-hours", type=int, default=48)
    ap.add_argument("--currents", choices=("auto", "cmems", "open-meteo"), default="auto",
                    help="auto tries Copernicus Marine first, then Open-Meteo")
    ap.add_argument("--force", action="store_true", help="refetch even if cached")
    args = ap.parse_args()

    targets: List[Tuple[str, float, float, datetime]] = []

    if args.lat is not None and args.lon is not None:
        t = datetime.fromisoformat((args.t or datetime.now(timezone.utc).isoformat()).replace("Z", "+00:00"))
        targets.append((args.id or "manual_box", args.lat, args.lon, t))

    wanted = set(args.scene)
    if args.all or wanted:
        for s in scenes_mod.all_scenes(include_selftest=True):
            if wanted and s.id not in wanted:
                continue
            t = datetime.fromisoformat(s.t_sat.replace("Z", "+00:00"))
            targets.append((s.id, s.centroid[1], s.centroid[0], t))

    if not targets:
        ap.error("nothing to do: pass --all, --scene ID, or --lat/--lon/--t/--id")

    results = []
    for scene_id, lat, lon, t in targets:
        out = Path(config.METOCEAN_DIR) / ("%s.npz" % scene_id)
        if out.exists() and not args.force:
            print("[%s] already cached, skipping (use --force to refetch)" % scene_id)
            continue
        try:
            results.append(build_box(scene_id, lat, lon, t,
                                     half_deg=args.half_deg, n=args.grid,
                                     back_h=args.back_hours, fwd_h=args.forward_hours,
                                     currents=args.currents))
        except Exception as exc:
            print("[%s] FAILED: %s" % (scene_id, exc))

    print("\ncached cubes now on disk:")
    for item in fields_mod.list_cached():
        print("  %-28s %s .. %s  %s" % (item["scene_id"], item["t_start"][:16],
                                        item["t_end"][:16], item["bounds"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
