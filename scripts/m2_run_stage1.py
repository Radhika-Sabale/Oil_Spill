"""M2: run Stage 1 (product check, wind gate, CA-CFAR) on every indexed scene.

    python scripts/m2_run_stage1.py                 # all real scenes
    python scripts/m2_run_stage1.py --scene gom_mc20_chronic_slick

Writes data/m2_out/<scene>.stage1.json and data/m2_out/stage1_summary.csv.
Nothing is invented: missing wind or angle shows up as unavailable/unknown.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import config, scenes as scenes_mod, stage1          # noqa: E402
from app.drift import fields as fields_mod                      # noqa: E402


def run_scene(scene):
    sar = scenes_mod.load_raster(scene)
    vv = sar.array[0]
    clon, clat = sar.centre_lonlat()

    wind = stage1.wind_gate(None)
    cube = Path(config.METOCEAN_DIR) / (scene.id + ".npz")
    if cube.exists():
        field = fields_mod.load_npz(cube)
        wind = stage1.wind_from_metocean(field, clat, clon, scene.t_sat)
    else:
        wind["reason"] = "no metocean cache file %s" % cube.name

    doc = stage1.run_stage1(
        vv, sar.transform, sar.crs, source=scene.source,
        incidence_deg=None, wind_ms=wind.get("speed_ms"),
        wind_source=wind.get("wind_source"), centre_lat=clat)
    doc["wind_gate"] = wind                       # keep synthetic flag and reason
    if wind.get("gate") == "unknown" and "no metocean" in str(wind.get("reason")):
        doc["status"] = "partial"
    doc["scene"] = {"id": scene.id, "t_sat": scene.t_sat, "crs": sar.crs,
                    "shape": list(sar.array.shape), "bounds": scene.bounds,
                    "centroid": scene.centroid, "source": scene.source,
                    "license": scene.license,
                    "pixel_m": doc["cfar"].get("params", {}).get("native_pixel_m")}
    return doc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", action="append", default=[])
    args = ap.parse_args()
    out_dir = Path(config.DATA_DIR) / "m2_out"
    out_dir.mkdir(parents=True, exist_ok=True)
    scs = [s for s in scenes_mod.all_scenes(include_selftest=False)
           if not args.scene or s.id in args.scene]
    rows = []
    for s in scs:
        if not Path(s.sar_path).exists():
            print("%-30s SKIP (no tif at %s)" % (s.id, s.sar_path))
            continue
        d = run_scene(s)
        (out_dir / (s.id + ".stage1.json")).write_text(json.dumps(d, indent=2, default=float))
        w, c = d["wind_gate"], d["cfar"]
        row = {"scene": s.id, "status": d["status"], "product": d["product"]["quantity"],
               "wind_ms": w.get("speed_ms"), "wind_gate": w.get("gate"),
               "wind_synthetic": w.get("synthetic"),
               "cfar_windows": c.get("n_windows"),
               "retained_fraction": c.get("retained_fraction")}
        rows.append(row)
        print("%-30s %-11s wind %s m/s %-9s windows %s retained %s"
              % (s.id, d["status"], row["wind_ms"], row["wind_gate"],
                 row["cfar_windows"], row["retained_fraction"]))
    if rows:
        with open(out_dir / "stage1_summary.csv", "w", newline="") as fh:
            wr = csv.DictWriter(fh, fieldnames=list(rows[0]))
            wr.writeheader()
            wr.writerows(rows)
        print("\nwrote", out_dir)


if __name__ == "__main__":
    main()
