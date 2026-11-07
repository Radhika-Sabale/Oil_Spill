"""Run bounded, mask-seeded NORSE2019 M3 observational hindcasts.

This experiment uses the regular M3 NORSE forcing injection and solver unchanged.
It writes validation outputs only; it does not modify the source masks or M3.
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio
from rasterio.features import shapes
from pyproj import Transformer
from shapely.geometry import MultiPoint, box, shape
from shapely.ops import transform as geom_transform, unary_union
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
MASK_DIR = ROOT.parent
OUT = ROOT / "data" / "norse2019_validation"
T0 = datetime.fromisoformat("2019-06-12T12:17:24+00:00")
METERS = Transformer.from_crs("EPSG:4326", "EPSG:32631", always_xy=True)
WGS84 = Transformer.from_crs("EPSG:32631", "EPSG:4326", always_xy=True)
OILS = {
    "mineral": {"suffix": "MINERALOIL", "hours_back": 7},
    "soybean": {"suffix": "SOYAOIL", "hours_back": 6},
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_mask(path: Path):
    with rasterio.open(path) as ds:
        a = ds.read(1)
        rows, cols = np.nonzero(a == 1)
        if len(rows) == 0:
            raise RuntimeError(f"No oil pixels in {path}")
        # Pixel-center mean is the observed mask centroid, used only as the
        # latest observed endpoint / a comparison value, never as truth for release.
        xs, ys = rasterio.transform.xy(ds.transform, rows, cols, offset="center")
        xs, ys = np.asarray(xs), np.asarray(ys)
        cx, cy = float(xs.mean()), float(ys.mean())
        clon, clat = WGS84.transform(cx, cy)
        # Preserve the observed oil footprint for seeding and overlap scoring.
        polys = [shape(g) for g, val in shapes(a, mask=(a == 1), transform=ds.transform,
                                                 connectivity=8) if val == 1]
        oil_geom = unary_union(polys)
        metadata = {
            "name": path.name,
            "sha256": sha256(path),
            "timestamp_utc": datetime.strptime(path.name[:15], "%Y%m%dT%H%M%S").replace(
                tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
            "crs": str(ds.crs), "width": ds.width, "height": ds.height,
            "resolution": list(ds.res), "transform": list(ds.transform)[:6],
            "bounds": [ds.bounds.left, ds.bounds.bottom, ds.bounds.right, ds.bounds.top],
            "nodata": ds.nodata, "valid_data_flags": [str(x) for x in ds.mask_flag_enums[0]],
            "oil_pixels": int(len(rows)), "observed_centroid_utm_m": [cx, cy],
            "observed_centroid_lonlat": [float(clon), float(clat)],
        }
        return metadata, oil_geom, (cx, cy), (clon, clat)


def iso_dt(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def draw_plot(oil_name, masks, run, output):
    w, h, pad = 1500, 1000, 90
    all_bounds = [m["geom"].bounds for m in masks]
    track_x, track_y = METERS.transform(run.mean_lon, run.mean_lat)
    xmin = min([b[0] for b in all_bounds] + list(track_x))
    ymin = min([b[1] for b in all_bounds] + list(track_y))
    xmax = max([b[2] for b in all_bounds] + list(track_x))
    ymax = max([b[3] for b in all_bounds] + list(track_y))
    dx, dy = xmax - xmin, ymax - ymin
    xmin -= dx * .04; xmax += dx * .04; ymin -= dy * .04; ymax += dy * .04

    def xy(pt):
        x, y = pt
        return (int(pad + (x - xmin) / (xmax - xmin) * (w - 2 * pad)),
                int(h - pad - (y - ymin) / (ymax - ymin) * (h - 2 * pad)))

    img = Image.new("RGB", (w, h), (8, 18, 28))
    d = ImageDraw.Draw(img)
    # Observation outlines; opacity is represented by subdued line color.
    for m in masks:
        geoms = list(m["geom"].geoms) if hasattr(m["geom"], "geoms") else [m["geom"]]
        for poly in geoms:
            if poly.geom_type != "Polygon":
                continue
            pts = [xy(p) for p in poly.exterior.coords]
            d.line(pts, fill=(220, 157, 60), width=2)
    # M3 mean backward path; times are in observation-to-past order.
    pts = [xy(p) for p in zip(track_x, track_y)]
    d.line(pts, fill=(53, 188, 220), width=4)
    d.ellipse((pts[0][0]-7, pts[0][1]-7, pts[0][0]+7, pts[0][1]+7), fill=(255, 238, 155))
    d.ellipse((pts[-1][0]-7, pts[-1][1]-7, pts[-1][0]+7, pts[-1][1]+7), fill=(244, 105, 84))
    font = ImageFont.load_default()
    d.text((pad, 22), f"NORSE2019 {oil_name.title()} — M3 backward ensemble-median track", fill="white", font=font)
    d.text((pad, 44), "Amber outlines: observed masks   Cyan: ensemble-median path   pale: 12:17:24 seed   red: earliest hindcast", fill=(180, 198, 210), font=font)
    d.text((pad, h-35), "UTM zone 31N (EPSG:32631), metres", fill=(180, 198, 210), font=font)
    img.save(output)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT))
    from app import config, pipeline

    summary = {
        "benchmark": "NORSE2019 observation-seeded backward hindcast",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "No release-origin position accuracy; no algorithm changes, tuning, CODE forcing, or Stokes drift.",
        "forcing_profile": "norse2019",
        "forcing_manifest": str((ROOT / "data/norse2019_forcing/manifest.json").relative_to(ROOT)),
        "run_configuration": {}, "experiments": {},
    }
    comparison_rows = []
    for oil_name, spec in OILS.items():
        files = sorted(MASK_DIR.glob(f"20190612T*_{spec['suffix']}.tif"))
        masks = []
        for f in files:
            md, geom, xy, ll = load_mask(f)
            masks.append({"metadata": md, "geom": geom, "centroid_xy": xy,
                          "centroid_ll": ll, "path": f})
        latest = next(m for m in masks if m["metadata"]["timestamp_utc"] == "2019-06-12T12:17:24Z")
        # M3 accepts a single ring. Use the latest mask's convex hull as its
        # seed polygon; scoring remains against each full observed raster mask.
        seed_poly = latest["geom"].convex_hull.simplify(20, preserve_topology=True)
        seed_ring = [WGS84.transform(x, y) for x, y in seed_poly.exterior.coords]
        t = datetime.fromisoformat("2019-06-12T12:17:24+00:00")
        back_h = spec["hours_back"]
        forecast_h = 1
        # Record fully explicit inputs; preserve M3's frozen/default solver parameters.
        params = config.as_dict()
        run_cfg = {
            "oil": oil_name, "scene_id": f"norse2019-{oil_name}",
            "t_sat_utc": "2019-06-12T12:17:24Z",
            "endpoint_mask": latest["metadata"]["name"],
            "endpoint_mask_sha256": latest["metadata"]["sha256"],
            "endpoint_centroid_lonlat": latest["centroid_ll"],
            "endpoint_polygon_seed": "convex hull of 1-pixel latest-mask geometry, simplified by 20 m",
            "hindcast_hours": back_h, "forecast_hours": forecast_h,
            "requested_interval_utc": [
                (t - __import__('datetime').timedelta(hours=back_h)).isoformat().replace("+00:00", "Z"),
                (t + __import__('datetime').timedelta(hours=forecast_h)).isoformat().replace("+00:00", "Z")],
            "metocean_profile": "norse2019", "ensemble_n": params["ensemble_n"],
            "integrator_backward": "rk4", "dt_seconds_backward": config.HINDCAST_RK4_DT_SECONDS,
            "integrator_forward": "rk2 (existing pipeline default; excluded from scoring)",
            "dt_seconds_forward": params["dt_seconds"],
            "alpha_wind": params["alpha_wind"], "deflection_deg": params["deflection_deg"],
            "current_noise_ms": params["current_noise_ms"], "wind_noise_ms": params["wind_noise_ms"],
            "horizontal_eddy_diffusivity_m2_s": config.HORIZONTAL_EDDY_DIFFUSIVITY_M2_S,
            "random_seed": params["seed"], "stokes_enabled": False,
            "scoring_forecast": False,
        }
        # Run through the explicit normal M3 injection path, retaining _runs for comparisons.
        result = pipeline.run_drift(
            seed_ring, latest["centroid_ll"], t, back_h, forecast_h,
            params["ensemble_n"], run_cfg["scene_id"],
            metocean_profile="norse2019")
        back = result["_runs"]["back"]
        fwd = result["_runs"]["forward"]
        meta = dict(back.meta)
        field = result["metocean"]
        scoring_masks = [m for m in masks if m["metadata"]["timestamp_utc"] != "2019-06-12T12:17:24Z"]
        origin_rows = []
        for m in scoring_masks:
            obs_t = iso_dt(m["metadata"]["timestamp_utc"])
            idx = min(range(len(back.times)), key=lambda i: abs((back.times[i]-obs_t).total_seconds()))
            offset_s = abs((back.times[idx]-obs_t).total_seconds())
            # M3's field named mean_lon/mean_lat is the per-step ensemble median.
            # Preserve that solver statistic, but label it accurately in outputs.
            ensemble_median_x, ensemble_median_y = METERS.transform(
                float(back.mean_lon[idx]), float(back.mean_lat[idx]))
            ox, oy = m["centroid_xy"]
            displacement = float(np.hypot(ensemble_median_x-ox, ensemble_median_y-oy))
            cloud = MultiPoint(list(zip(*METERS.transform(back.lon[idx], back.lat[idx]))))
            hull = cloud.convex_hull
            raster_bounds = m["metadata"]["bounds"]
            observed_footprint = box(raster_bounds[0], raster_bounds[1],
                                     raster_bounds[2], raster_bounds[3])
            # NoData is absent, but a mask outside its raster window is unknown.
            # Clip predictions to the observed raster footprint before overlap scoring.
            scored_hull = hull.intersection(observed_footprint)
            inter = scored_hull.intersection(m["geom"]).area
            union = scored_hull.union(m["geom"]).area
            precision = inter / scored_hull.area if scored_hull.area else 0.0
            recall = inter / m["geom"].area if m["geom"].area else 0.0
            iou = inter / union if union else 0.0
            px, py = METERS.transform(back.lon[idx], back.lat[idx])
            rb = m["metadata"]["bounds"]
            in_bounds = np.array([rb[0] <= x <= rb[2] and rb[1] <= y <= rb[3]
                                  for x,y in zip(px,py)])
            hit = np.zeros(len(px), dtype=bool)
            if in_bounds.any():
                with rasterio.open(m["path"]) as ds:
                    rc = [ds.index(float(x), float(y)) for x,y in zip(px[in_bounds],py[in_bounds])]
                    vals = [ds.read(1, window=((r,r+1),(c,c+1)))[0,0] if 0 <= r < ds.height and 0 <= c < ds.width else 0 for r,c in rc]
                    hit[np.where(in_bounds)[0]] = np.asarray(vals) == 1
            obs_fraction = float(in_bounds.mean())
            hit_fraction_observed = float(hit.sum()/in_bounds.sum()) if in_bounds.sum() else None
            row = {
                "oil": oil_name, "mask": m["metadata"]["name"],
                "mask_timestamp_utc": m["metadata"]["timestamp_utc"],
                "nearest_model_time_utc": back.times[idx].isoformat().replace("+00:00", "Z"),
                "nearest_model_time_offset_seconds": offset_s,
                "observed_mask_centroid_utm_m": [ox,oy],
                "m3_ensemble_median_utm_m": [float(ensemble_median_x),float(ensemble_median_y)],
                "centroid_displacement_km": displacement/1000,
                "m3_spread_radius_90_km": float(back.spread_km[idx]),
                "ensemble_points": int(len(px)), "fraction_points_within_mask_raster_footprint": obs_fraction,
                "fraction_points_on_oil_among_observed": hit_fraction_observed,
                "ensemble_hull_area_km2": hull.area/1e6,
                "ensemble_hull_in_observed_footprint_km2": scored_hull.area/1e6,
                "observed_oil_mask_area_km2": m["geom"].area/1e6,
                "hull_mask_intersection_km2": inter/1e6,
                "hull_precision": precision, "mask_recall": recall, "hull_mask_iou": iou,
            }
            comparison_rows.append(row); origin_rows.append(row)

        # Per-time trajectory metrics; all observations in this series are scored.
        dists = [r["centroid_displacement_km"] for r in origin_rows]
        ious = [r["hull_mask_iou"] for r in origin_rows]
        experiment = {
            "configuration": run_cfg,
            "status": "success",
            "observations_scored": len(origin_rows),
            "seed_observation_excluded_from_scoring": latest["metadata"]["timestamp_utc"],
            "hindcast_coverage": {
                "status": meta.get("forcing_coverage_status"),
                "outside_coverage_evaluations": meta.get("forcing_outside_coverage_evaluations"),
                "requested_interval_utc": run_cfg["requested_interval_utc"],
                "forcing_interval_utc": [field.get("t_start"), field.get("t_end")],
                "forcing_source": field.get("source"),
                "synthetic": field.get("synthetic"), "live": field.get("live"),
                "stokes_available": field.get("stokes_available"),
                "adapter_metadata": field.get("adapter_metadata"),
            },
            "backward_steps": back.n_steps,
            "hindcast_origin_estimate": result["origin"],
            "aggregate": {
                "centroid_displacement_mean_km": float(np.mean(dists)),
                "centroid_displacement_median_km": float(np.median(dists)),
                "centroid_displacement_p90_km": float(np.percentile(dists,90)),
                "hull_mask_iou_mean": float(np.mean(ious)),
                "hull_mask_iou_median": float(np.median(ious)),
                "ensemble_hull_precision_mean": float(np.mean([r["hull_precision"] for r in origin_rows])),
                "ensemble_hull_mask_recall_mean": float(np.mean([r["mask_recall"] for r in origin_rows])),
                "observed_footprint_point_fraction_mean": float(np.mean([r["fraction_points_within_mask_raster_footprint"] for r in origin_rows])),
                "nearest_sample_offset_max_seconds": int(max(r["nearest_model_time_offset_seconds"] for r in origin_rows)),
            },
            "forecast": {"status": "completed; excluded from observation scoring",
                         "steps": fwd.n_steps,
                         "coverage_status": fwd.meta.get("forcing_coverage_status"),
                         "outside_coverage_evaluations": fwd.meta.get("forcing_outside_coverage_evaluations")},
            "masks": [m["metadata"] for m in masks],
            "per_observation": origin_rows,
        }
        experiment["plot"] = f"{oil_name}_hindcast_masks.png"
        draw_plot(oil_name, masks, back, OUT / experiment["plot"])
        summary["experiments"][oil_name] = experiment
        summary["run_configuration"][oil_name] = run_cfg
    (OUT / "validation_results.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    with (OUT / "per_observation_metrics.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(comparison_rows[0]))
        writer.writeheader()
        for row in comparison_rows:
            writer.writerow({k: json.dumps(v) if isinstance(v, (list, dict)) else v for k,v in row.items()})
    print(json.dumps({oil: {"status": e["status"], "aggregate": e["aggregate"],
                            "coverage": e["hindcast_coverage"], "forecast": e["forecast"]}
                      for oil,e in summary["experiments"].items()}, indent=2))


if __name__ == "__main__":
    main()
