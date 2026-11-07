"""Create Phase 6 observational error diagnostics from Phase 5B run outputs."""
from __future__ import annotations

import csv
import json
import math
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "norse2019_validation"
SEED_TIME = datetime.fromisoformat("2019-06-12T12:17:24+00:00")
COLORS = {"mineral": (235, 153, 69), "soybean": (62, 190, 218)}


def rankdata(values):
    indexed = sorted(enumerate(values), key=lambda pair: pair[1])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i + 1
        while j < len(indexed) and indexed[j][1] == indexed[i][1]:
            j += 1
        rank = (i + 1 + j) / 2.0
        for k in range(i, j):
            ranks[indexed[k][0]] = rank
        i = j
    return ranks


def corr(x, y):
    if len(x) < 2:
        return None
    mx, my = sum(x) / len(x), sum(y) / len(y)
    sx = math.sqrt(sum((v - mx) ** 2 for v in x))
    sy = math.sqrt(sum((v - my) ** 2 for v in y))
    if not sx or not sy:
        return None
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / (sx * sy)


def quantile(values, q):
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return ordered[lo] if lo == hi else ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def analyze(data):
    diagnostics = {"scope": "descriptive only; repeated observations are not independent",
                   "experiments": {}}
    rows = []
    for oil, experiment in data["experiments"].items():
        records = []
        for row in experiment["per_observation"]:
            t = datetime.fromisoformat(row["mask_timestamp_utc"].replace("Z", "+00:00"))
            elapsed = (SEED_TIME - t).total_seconds() / 3600.0
            dx = (row["m3_ensemble_median_utm_m"][0] - row["observed_mask_centroid_utm_m"][0]) / 1000.0
            dy = (row["m3_ensemble_median_utm_m"][1] - row["observed_mask_centroid_utm_m"][1]) / 1000.0
            item = {
                "oil": oil, "mask": row["mask"], "timestamp_utc": row["mask_timestamp_utc"],
                "elapsed_backward_hours": elapsed,
                "nearest_model_offset_seconds": row["nearest_model_time_offset_seconds"],
                "centroid_displacement_km": row["centroid_displacement_km"],
                "east_bias_km": dx, "north_bias_km": dy,
                "hull_iou": row["hull_mask_iou"],
                "hull_precision": row["hull_precision"], "mask_recall": row["mask_recall"],
                "hull_area_km2": row["ensemble_hull_area_km2"],
                "hull_area_in_raster_km2": row["ensemble_hull_in_observed_footprint_km2"],
                "observed_oil_area_km2": row["observed_oil_mask_area_km2"],
                "m3_spread_radius_90_km": row["m3_spread_radius_90_km"],
                "ensemble_point_fraction_in_raster": row["fraction_points_within_mask_raster_footprint"],
                "ensemble_point_fraction_on_oil_given_observed": row["fraction_points_on_oil_among_observed"],
            }
            records.append(item)
            rows.append(item)
        elapsed = [r["elapsed_backward_hours"] for r in records]
        errors = [r["centroid_displacement_km"] for r in records]
        ious = [r["hull_iou"] for r in records]
        east = [r["east_bias_km"] for r in records]
        north = [r["north_bias_km"] for r in records]
        hull_area = [r["hull_area_km2"] for r in records]
        mask_area = [r["observed_oil_area_km2"] for r in records]
        spread = [r["m3_spread_radius_90_km"] for r in records]
        diagnostics["experiments"][oil] = {
            "n_observations": len(records),
            "elapsed_hours_range": [min(elapsed), max(elapsed)],
            "centroid_displacement_km": {
                "mean": sum(errors) / len(errors),
                "median": quantile(errors, .5),
                "p90": quantile(errors, .9),
                "pearson_r_vs_elapsed": corr(elapsed, errors),
                "spearman_r_vs_elapsed": corr(rankdata(elapsed), rankdata(errors)),
            },
            "hull_iou": {
                "mean": sum(ious) / len(ious),
                "median": quantile(ious, .5),
                "pearson_r_vs_elapsed": corr(elapsed, ious),
                "spearman_r_vs_elapsed": corr(rankdata(elapsed), rankdata(ious)),
            },
            "signed_bias_km_predicted_minus_observed": {
                "east_mean": sum(east) / len(east), "east_median": sorted(east)[len(east) // 2],
                "north_mean": sum(north) / len(north), "north_median": sorted(north)[len(north) // 2],
                "east_positive_count": sum(x > 0 for x in east),
                "east_negative_count": sum(x < 0 for x in east),
                "north_positive_count": sum(x > 0 for x in north),
                "north_negative_count": sum(x < 0 for x in north),
            },
            "spread_and_geometry": {
                "m3_spread_radius_90_km_median": quantile(spread, .5),
                "m3_spread_radius_90_km_max": max(spread),
                "hull_area_km2_median": quantile(hull_area, .5),
                "hull_area_km2_max": max(hull_area),
                "observed_mask_area_km2_median": quantile(mask_area, .5),
                "median_hull_to_mask_area_ratio": quantile([a / b for a, b in zip(hull_area, mask_area)], .5),
                "hull_area_pearson_r_vs_elapsed": corr(elapsed, hull_area),
                "spread_pearson_r_vs_elapsed": corr(elapsed, spread),
            },
            "nearest_solver_time_offset_max_s": max(r["nearest_model_offset_seconds"] for r in records),
            "per_observation": records,
        }
    return diagnostics, rows


def draw_diagnostics(diag, dest):
    W, H = 1700, 1280
    im = Image.new("RGB", (W, H), (11, 20, 30))
    d = ImageDraw.Draw(im)
    font_path = Path("C:/Windows/Fonts/arial.ttf")
    font = ImageFont.truetype(str(font_path), 18) if font_path.exists() else ImageFont.load_default()
    small = ImageFont.truetype(str(font_path), 14) if font_path.exists() else ImageFont.load_default()
    d.text((52, 24), "NORSE2019 · Phase 6 error diagnosis", fill=(240, 245, 250), font=font)
    d.text((52, 54), "Saved Phase 5B ensemble outputs; elapsed time is measured backward from 12:17:24 UTC.", fill=(165, 184, 201), font=small)

    panels = [(65, 110, 820, 600), (875, 110, 1630, 600),
              (65, 665, 820, 1155), (875, 665, 1630, 1155)]
    exps = diag["experiments"]
    record_sets = {oil: exps[oil]["per_observation"] for oil in exps}

    def frame(box, title, xlabel, ylabel, xmin, xmax, ymin, ymax, xticks, yticks):
        x0, y0, x1, y1 = box
        d.rectangle(box, outline=(65, 83, 102), width=2)
        d.text((x0 + 12, y0 + 8), title, fill=(235, 241, 248), font=font)
        gx0, gy0, gx1, gy1 = x0 + 75, y0 + 55, x1 - 24, y1 - 58
        def xy(x, y):
            return (int(gx0 + (x - xmin) / (xmax - xmin) * (gx1 - gx0)),
                    int(gy1 - (y - ymin) / (ymax - ymin) * (gy1 - gy0)))
        for tick in xticks:
            px, _ = xy(tick, ymin)
            d.line((px, gy0, px, gy1), fill=(36, 52, 68), width=1)
            d.text((px - 18, gy1 + 8), f"{tick:g}", fill=(167, 184, 200), font=small)
        for tick in yticks:
            _, py = xy(xmin, tick)
            d.line((gx0, py, gx1, py), fill=(36, 52, 68), width=1)
            d.text((gx0 - 55, py - 9), f"{tick:g}", fill=(167, 184, 200), font=small)
        d.line((gx0, gy1, gx1, gy1), fill=(150, 166, 181), width=2)
        d.line((gx0, gy0, gx0, gy1), fill=(150, 166, 181), width=2)
        d.text((gx0 + (gx1-gx0)//2 - 55, y1 - 30), xlabel, fill=(190, 204, 216), font=small)
        d.text((x0 + 8, gy0 + (gy1-gy0)//2), ylabel, fill=(190, 204, 216), font=small)
        return xy

    # Displacement vs elapsed backward integration.
    xy = frame(panels[0], "Centroid displacement", "Elapsed (h)", "Error (km)",
               0, 6.5, 0, 4.5, [0,1,2,3,4,5,6], [0,1,2,3,4])
    # IoU vs elapsed.
    xy2 = frame(panels[1], "Ensemble hull IoU", "Elapsed (h)", "IoU", 0, 6.5, 0, .75,
                [0,1,2,3,4,5,6], [0,.15,.30,.45,.60,.75])
    # East/north signed reconstruction offsets.
    xy3 = frame(panels[2], "Directional bias (predicted − observed)", "East offset (km)", "North offset (km)",
                -1, 4.5, -2.8, .6, [-1,0,1,2,3,4], [-2.5,-2,-1.5,-1,-.5,0,.5])
    # M3 90% ensemble spread radius.
    xy4 = frame(panels[3], "M3 90% ensemble spread radius", "Elapsed (h)", "Radius (km)",
                0, 6.5, 0, 5.5, [0,1,2,3,4,5,6], [0,1,2,3,4,5])

    for oil, records in record_sets.items():
        color = COLORS[oil]
        for r in records:
            t = r["elapsed_backward_hours"]
            for mapper, val in ((xy, r["centroid_displacement_km"]),
                                (xy2, r["hull_iou"]),
                                (xy4, r["m3_spread_radius_90_km"])):
                x, y = mapper(t, val)
                d.ellipse((x-5,y-5,x+5,y+5), fill=color, outline=(238,243,248), width=1)
            x, y = xy3(r["east_bias_km"], r["north_bias_km"])
            d.ellipse((x-5,y-5,x+5,y+5), fill=color, outline=(238,243,248), width=1)
    # Legends
    for box, y in ((panels[0], panels[0][1]+38), (panels[1], panels[1][1]+38),
                   (panels[2], panels[2][1]+38), (panels[3], panels[3][1]+38)):
        x = box[0] + 190
        d.ellipse((x,y,x+12,y+12), fill=COLORS["mineral"]); d.text((x+18,y-4), "Mineral", fill=(214,225,235), font=small)
        x += 100
        d.ellipse((x,y,x+12,y+12), fill=COLORS["soybean"]); d.text((x+18,y-4), "Soybean", fill=(214,225,235), font=small)
    im.save(dest)


def main():
    path = OUT / "validation_results.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    diag, rows = analyze(data)
    (OUT / "phase6_error_diagnosis.json").write_text(json.dumps(diag, indent=2), encoding="utf-8")
    fields = list(rows[0])
    with (OUT / "phase6_observation_diagnostics.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)
    draw_diagnostics(diag, OUT / "phase6_error_diagnosis.png")
    print(json.dumps({oil: {k:v for k,v in e.items() if k != "per_observation"}
                      for oil,e in diag["experiments"].items()}, indent=2))


if __name__ == "__main__":
    main()
