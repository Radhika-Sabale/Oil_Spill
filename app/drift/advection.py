"""Lagrangian surface advection in numpy.

OpenDrift is deliberately not a runtime dependency (GPL, heavy, and the judged
demo has to install on a laptop in minutes). This module implements the same
2D surface model the spec pins down:

    V = U_current + ALPHA_WIND * U_wind10        with ALPHA_WIND = 0.03

which is the value OpenDrift's own maintainers quote for wind drift when Stokes
drift is switched off. An optional leeway deflection rotates the wind term to
the right in the northern hemisphere.

The inherited baseline is RK2 (midpoint). An RK4 option is available for the
SentinelTrace hindcast target. Degrees are
converted to metres through a local azimuthal equidistant frame re-centred on
the ensemble each step, so nothing degrades with latitude.

Backward runs are the same integrator with a negative dt. That is what makes
the hindcast honest: it is the forward physics run in reverse, not a separate
heuristic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import math

from .. import config
from ..geo.crs import LocalAEQD
from ..geo.geometry import hull_ring, spread_radius_km
from .fields import MetoceanField


def _utc(t) -> datetime:
    if isinstance(t, datetime):
        return t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    s = str(t).strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@dataclass
class EnsembleRun:
    """Result of one ensemble integration."""

    times: List[datetime]                 # length nt
    lon: np.ndarray                       # (nt, n_particles)
    lat: np.ndarray                       # (nt, n_particles)
    direction: str                        # "backward" or "forward"
    spread_km: np.ndarray                 # (nt,) 90th percentile radius
    mean_lon: np.ndarray                  # (nt,)
    mean_lat: np.ndarray                  # (nt,)
    meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def n_steps(self) -> int:
        return len(self.times)

    def envelope(self, index: int) -> List[Tuple[float, float]]:
        return hull_ring(self.lon[index], self.lat[index])

    def track_geojson(self) -> Dict[str, Any]:
        coords = [[float(a), float(b)] for a, b in zip(self.mean_lon, self.mean_lat)]
        return {
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": coords},
            "properties": {
                "direction": self.direction,
                "times": [t.isoformat() for t in self.times],
                "spread_km": [round(float(v), 3) for v in self.spread_km],
            },
        }

    def hourly(self) -> List[Dict[str, Any]]:
        return [
            {
                "t": self.times[i].isoformat(),
                "lon": round(float(self.mean_lon[i]), 6),
                "lat": round(float(self.mean_lat[i]), 6),
                "spread_km": round(float(self.spread_km[i]), 3),
            }
            for i in range(self.n_steps)
        ]


def seed_particles(
    ring: Optional[Sequence[Tuple[float, float]]],
    centroid: Tuple[float, float],
    n: int,
    fallback_radius_km: float = 1.0,
    seed: int = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """Seed particles inside the slick polygon, or in a disc if it is tiny.

    Rejection sampling inside the ring keeps the initial cloud shaped like the
    real slick, which is what makes the backward envelope meaningful.
    """
    rng = np.random.default_rng(config.RANDOM_SEED if seed is None else seed)
    clon, clat = float(centroid[0]), float(centroid[1])

    if ring and len(ring) >= 4:
        from ..geo.geometry import point_in_ring

        lons = np.array([p[0] for p in ring])
        lats = np.array([p[1] for p in ring])
        w, e = float(lons.min()), float(lons.max())
        s, nn = float(lats.min()), float(lats.max())
        out_lon: List[float] = []
        out_lat: List[float] = []
        guard = 0
        while len(out_lon) < n and guard < 400 * n:
            guard += 1
            lo = rng.uniform(w, e)
            la = rng.uniform(s, nn)
            if point_in_ring(lo, la, ring):
                out_lon.append(lo)
                out_lat.append(la)
        if len(out_lon) >= max(4, n // 4):
            while len(out_lon) < n:
                k = rng.integers(0, len(out_lon))
                out_lon.append(out_lon[k])
                out_lat.append(out_lat[k])
            return np.array(out_lon[:n]), np.array(out_lat[:n])

    frame = LocalAEQD(clat, clon)
    r = fallback_radius_km * 1000.0 * np.sqrt(rng.random(n))
    th = rng.uniform(0, 2 * np.pi, n)
    lon, lat = frame.to_deg(r * np.cos(th), r * np.sin(th))
    return np.asarray(lon, dtype=float), np.asarray(lat, dtype=float)


def advect(
    lon0: np.ndarray,
    lat0: np.ndarray,
    t0,
    hours: int,
    field_src: MetoceanField,
    direction: str = "forward",
    dt_seconds: int = None,
    alpha: float = None,
    deflection_deg: float = None,
    current_noise: float = None,
    wind_noise: float = None,
    seed: int = None,
    integrator: str = "rk2",
    eddy_diffusivity_m2_s: float = None,
) -> EnsembleRun:
    """Integrate an ensemble for `hours`, forwards or backwards.

    Per-particle velocity noise is drawn once and held for the whole run, which
    is the standard way to build a drift cone: each member is a plausible
    realisation of the field error, not a random walk that averages itself out.
    """
    dt = int(config.DT_SECONDS if dt_seconds is None else dt_seconds)
    integrator = str(integrator).strip().lower()
    if integrator not in {"rk2", "rk4"}:
        raise ValueError("integrator must be 'rk2' or 'rk4'")
    if dt <= 0:
        raise ValueError("dt_seconds must be positive; use direction='backward' for reverse integration")
    if direction not in {"forward", "backward"}:
        raise ValueError("direction must be 'forward' or 'backward'")
    duration_seconds = float(hours) * 3600.0
    if duration_seconds <= 0:
        raise ValueError("hours must be positive")
    alpha = config.ALPHA_WIND if alpha is None else float(alpha)
    deflection_deg = config.DEFLECTION_DEG if deflection_deg is None else float(deflection_deg)
    cn = config.CURRENT_NOISE_MS if current_noise is None else float(current_noise)
    wn = config.WIND_NOISE_MS if wind_noise is None else float(wind_noise)
    kh = ((config.HORIZONTAL_EDDY_DIFFUSIVITY_M2_S if integrator == "rk4" else 0.0)
          if eddy_diffusivity_m2_s is None else float(eddy_diffusivity_m2_s))
    if kh < 0:
        raise ValueError("eddy_diffusivity_m2_s must be non-negative")

    sign = -1.0 if direction == "backward" else 1.0
    rng = np.random.default_rng(config.RANDOM_SEED if seed is None else seed)

    lon = np.asarray(lon0, dtype=float).copy()
    lat = np.asarray(lat0, dtype=float).copy()
    n = lon.size

    du = rng.normal(0.0, cn, n)
    dv = rng.normal(0.0, cn, n)
    dwu = rng.normal(0.0, wn, n)
    dwv = rng.normal(0.0, wn, n)

    t = _utc(t0)
    n_steps = max(1, int(math.ceil(duration_seconds / dt - 1e-12)))

    times = [t]
    lons = [lon.copy()]
    lats = [lat.copy()]
    coverage = {"samples": 0, "outside": 0}

    for step_index in range(n_steps):
        step_seconds = min(float(dt), duration_seconds - step_index * dt)
        u1, v1 = _velocity(field_src, lat, lon, t, alpha, deflection_deg,
                           du, dv, dwu, dwv, coverage)
        frame = LocalAEQD(float(np.mean(lat)), float(np.mean(lon)))
        x, y = frame.to_m(lon, lat)

        h = sign * step_seconds
        if integrator == "rk2":
            # Preserve the TideTrace midpoint solver as a comparison baseline.
            xm = x + u1 * (h / 2.0)
            ym = y + v1 * (h / 2.0)
            lon_m, lat_m = frame.to_deg(xm, ym)
            t_mid = t + timedelta(seconds=h / 2.0)
            u2, v2 = _velocity(field_src, lat_m, lon_m, t_mid, alpha,
                               deflection_deg, du, dv, dwu, dwv, coverage)
            x2 = x + u2 * h
            y2 = y + v2 * h
        else:
            # Classical RK4 in one local metric frame for this step. Each
            # stage samples forcing at its own position and timestamp.
            k1x, k1y = u1, v1
            k2x, k2y = _velocity_at_xy(
                field_src, frame, x + h * k1x / 2.0, y + h * k1y / 2.0,
                t + timedelta(seconds=h / 2.0), alpha, deflection_deg,
                du, dv, dwu, dwv, coverage)
            k3x, k3y = _velocity_at_xy(
                field_src, frame, x + h * k2x / 2.0, y + h * k2y / 2.0,
                t + timedelta(seconds=h / 2.0), alpha, deflection_deg,
                du, dv, dwu, dwv, coverage)
            k4x, k4y = _velocity_at_xy(
                field_src, frame, x + h * k3x, y + h * k3y,
                t + timedelta(seconds=h), alpha, deflection_deg,
                du, dv, dwu, dwv, coverage)
            x2 = x + (h / 6.0) * (k1x + 2*k2x + 2*k3x + k4x)
            y2 = y + (h / 6.0) * (k1y + 2*k2y + 2*k3y + k4y)
        if kh > 0:
            # Additive Brownian displacement for horizontal eddy diffusion.
            # The same variance applies to forward and backward ensembles.
            diffusion_sigma = math.sqrt(2.0 * kh * step_seconds)
            x2 = x2 + rng.normal(0.0, diffusion_sigma, n)
            y2 = y2 + rng.normal(0.0, diffusion_sigma, n)
        lon, lat = frame.to_deg(x2, y2)
        lon = np.asarray(lon, dtype=float)
        lat = np.asarray(lat, dtype=float)
        t = t + timedelta(seconds=sign * step_seconds)

        times.append(t)
        lons.append(lon.copy())
        lats.append(lat.copy())

    LON = np.vstack(lons)
    LAT = np.vstack(lats)
    spread = np.array([spread_radius_km(LON[i], LAT[i]) for i in range(LON.shape[0])])
    return EnsembleRun(
        times=times,
        lon=LON,
        lat=LAT,
        direction=direction,
        spread_km=spread,
        mean_lon=np.median(LON, axis=1),
        mean_lat=np.median(LAT, axis=1),
        meta={
            "alpha_wind": alpha,
            "deflection_deg": deflection_deg,
            "dt_seconds": dt,
            "duration_seconds": duration_seconds,
            "integrator": integrator,
            "n_particles": int(n),
            "current_noise_ms": cn,
            "wind_noise_ms": wn,
            "horizontal_eddy_diffusivity_m2_s": kh,
            "metocean_source": field_src.source,
            "metocean_synthetic": bool(field_src.synthetic),
            "stokes_available": bool(field_src.has_stokes),
            "forcing_coverage_status": ("covered" if coverage["outside"] == 0
                                        else "clamped_outside_coverage"),
            "forcing_evaluations": coverage["samples"],
            "forcing_outside_coverage_evaluations": coverage["outside"],
        },
    )


def _record_forcing_coverage(field_src, lat, lon, t, coverage):
    lat = np.atleast_1d(np.asarray(lat, dtype=float))
    lon = np.atleast_1d(np.asarray(lon, dtype=float))
    w, s, e, n = field_src.bounds
    te = t.timestamp() if hasattr(t, "timestamp") else float(t)
    in_bounds = ((lat >= s) & (lat <= n) & (lon >= w) & (lon <= e)
                 & (te >= field_src.times[0]) & (te <= field_src.times[-1]))
    coverage["samples"] += int(in_bounds.size)
    coverage["outside"] += int(in_bounds.size - np.count_nonzero(in_bounds))


def _velocity(field_src, lat, lon, t, alpha, deflection_deg, du, dv, dwu, dwv,
              coverage=None):
    if coverage is not None:
        _record_forcing_coverage(field_src, lat, lon, t, coverage)
    u, v = field_src.velocity(lat, lon, t, alpha=alpha, deflection_deg=deflection_deg)
    u = np.asarray(u, dtype=float) + du + alpha * dwu
    v = np.asarray(v, dtype=float) + dv + alpha * dwv
    return u, v


def _velocity_at_xy(field_src, frame, x, y, t, alpha, deflection_deg,
                    du, dv, dwu, dwv, coverage=None):
    """Evaluate ensemble velocity at intermediate local-metre coordinates."""
    lon, lat = frame.to_deg(x, y)
    return _velocity(field_src, lat, lon, t, alpha, deflection_deg,
                     du, dv, dwu, dwv, coverage)


def spatial_variance_m2(run: EnsembleRun, index: int) -> float:
    """Trace of the ensemble position covariance in a local metric frame."""
    frame = LocalAEQD(float(np.mean(run.lat[index])), float(np.mean(run.lon[index])))
    x, y = frame.to_m(run.lon[index], run.lat[index])
    return float(np.var(x) + np.var(y))


def pick_origin_index(run: EnsembleRun, trigger_km: float = None,
                      h_min: float = None, h_max: float = None,
                      method: str = "spread_threshold") -> int:
    """Choose an origin timestep by minimum variance or the legacy threshold.

    ``minimum_variance`` returns the global minimum of ensemble spatial
    variance across the run. ``spread_threshold`` preserves the inherited
    first-threshold-crossing rule for comparisons and older callers.
    """
    if method == "minimum_variance":
        elapsed_h = np.asarray([
            abs((t - run.times[0]).total_seconds()) / 3600.0 for t in run.times
        ])
        # The target estimator compares hourly dispersion snapshots, not every
        # internal five-minute integration state.
        candidates = np.flatnonzero(
            (elapsed_h > 0) & np.isclose(elapsed_h, np.round(elapsed_h), atol=1e-8))
        if candidates.size == 0:
            candidates = np.array([0, run.n_steps - 1])
        variances = [spatial_variance_m2(run, int(i)) for i in candidates]
        return int(candidates[int(np.argmin(variances))])
    if method != "spread_threshold":
        raise ValueError("method must be 'spread_threshold' or 'minimum_variance'")

    trigger_km = config.SPREAD_TRIGGER_KM if trigger_km is None else float(trigger_km)
    h_min = config.ORIGIN_H_MIN if h_min is None else float(h_min)
    h_max = config.ORIGIN_H_MAX if h_max is None else float(h_max)

    elapsed_h = np.asarray([
        abs((t - run.times[0]).total_seconds()) / 3600.0 for t in run.times
    ])
    eligible = np.flatnonzero((elapsed_h >= h_min) & (elapsed_h <= h_max))
    if eligible.size == 0:
        eligible = np.arange(1, run.n_steps)
    if eligible.size == 0:
        return 0
    i_min, i_max = int(eligible[0]), int(eligible[-1])

    hit = None
    for i in range(i_min, i_max + 1):
        if run.spread_km[i] >= trigger_km:
            hit = i
            break
    if hit is None:
        hit = i_max
    return int(hit)
