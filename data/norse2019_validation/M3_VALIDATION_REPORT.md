# NORSE2019 Observational Hindcast Validation

**Scope:** backward reconstruction from each oil type’s 12:17:24 UTC mask to earlier same-type observations. No release-origin positional accuracy is evaluated. No solver algorithms or parameters were changed or tuned.

**Phase 6 metric-audit note:** use the corrected definitions below and in `phase6_error_diagnosis.md`. M3's `mean_lon`/`mean_lat` arrays are medians; displacement is now explicitly labelled ensemble-median-to-mask-centroid. Hull overlap is clipped to the full mask-raster footprint so pixels outside the observed footprint count as unknown. Raster-footprint point coverage uses the raster bounds, not the oil polygon bounds. Solver runs were repeated with the identical Phase 5B settings; M3 code and parameters are unchanged.

## Commands and configuration

Run from the repository root:

```powershell
.\venv\Scripts\python.exe scripts\run_norse2019_obs_hindcast.py
```

The script calls `app.pipeline.run_drift()` separately for each oil with `metocean_profile="norse2019"`, a 50-particle ensemble, the latest corresponding raster mask as its endpoint, and a 20 m simplified convex hull of that mask as the seed polygon. The mask centroid is only the observed endpoint coordinate, never a release coordinate.

| Setting | Mineral | Soybean |
|---|---:|---:|
| Observation time (`t_sat`) | 2019-06-12 12:17:24 UTC | 2019-06-12 12:17:24 UTC |
| Backward horizon | 7 h | 6 h |
| Forecast horizon (excluded from scoring) | 1 h | 1 h |
| Requested full interval | 05:17:24–13:17:24 UTC | 06:17:24–13:17:24 UTC |
| Hindcast integrator / step | RK4 / 300 s | RK4 / 300 s |
| Forward integrator / step | Existing RK2 / 3600 s | Existing RK2 / 3600 s |
| Windage / deflection | 0.03 / 15° | 0.03 / 15° |
| Current / wind noise | 0.1 / 1.0 m/s | 0.1 / 1.0 m/s |
| Horizontal eddy diffusivity | 1.0 m²/s | 1.0 m²/s |
| Random seed | 20260920 | 20260920 |
| Stokes drift | Disabled | Disabled |

These settings preserve the existing pipeline defaults. The API accepts whole-hour durations, so the backward intervals start a few minutes before each reported release start. The one-hour forecasts completed but were not scored.

## Forcing and run status

Both runs succeeded using the prepared MEPS and NorKyst800 subsets. The adapter reported `synthetic=false`, `live=false`, `stokes_available=false`, and `synthetic_fallback=false`. Both source checksums matched the manifest and the pinned hashes:

- MEPS: `22a41dad2d5af3308bf26b82d5fb833385c3c1ebd7c21ea353ab25cc372d314f`
- NorKyst800: `8749cedd3db73e512b745757e7695feae7b18813b561115c12730ad1141431f2`

Available forcing: 2019-06-12 04:00 through 2019-06-13 00:00 UTC (21 hourly samples). Both backward and forward legs reported `covered`, with zero out-of-coverage evaluations. The full adapter details and per-run metadata are preserved in `validation_results.json`.

## Aggregate results

| Oil | Earlier masks scored | Mean / median / P90 centroid displacement | Mean / median convex-hull IoU | Mean hull precision / mask recall | Mean ensemble points within raster footprints |
|---|---:|---:|---:|---:|---:|
| Mineral | 17 | 2.247 / 2.190 / 3.575 km | 0.028 / 0.000 | 0.048 / 0.295 | 0.848 |
| Soybean | 14 | 0.996 / 0.804 / 1.359 km | 0.158 / 0.078 | 0.195 / 0.407 | 0.879 |

Definitions:

- **Centroid displacement:** straight-line EPSG:32631 distance from the M3 backward ensemble-median position at the nearest 5-minute solver time to the centroid of all oil-class pixels in that observed mask. Nearest-sample time offsets were at most 136 s (mineral) and 127 s (soybean).
- **Hull IoU:** intersection-over-union of the convex hull of the 50 simulated particle positions, clipped to the observed raster footprint, and the class-1 mask geometry.
- **Hull precision / mask recall:** intersection area divided by the clipped ensemble-hull area / observed oil-mask area, respectively.
- **Footprint fraction:** fraction of ensemble points inside the full raster bounds. Points outside are unobserved. `per_observation_metrics.csv` separately reports the fraction of in-footprint particles falling on class-1 pixels.
- The hull metrics describe the M3 particle ensemble geometry against the mask. They are not claims of full slick-spread accuracy.

## Per-observation results

Each cell is **centroid displacement in km / hull IoU**. `—` means that oil type has no mask at that timestamp.

| Timestamp UTC | Mineral km / IoU | Soybean km / IoU |
|---|---:|---:|
| 06:10:21 | 3.60 / 0.003 | — |
| 06:18:44 | 3.56 / 0.004 | — |
| 06:24:40 | 3.51 / 0.003 | — |
| 06:32:45 | 3.64 / 0.006 | 3.90 / 0.001 |
| 10:51:24 | 2.16 / 0.000 | 1.38 / 0.008 |
| 10:58:07 | 2.40 / 0.000 | 1.30 / 0.014 |
| 11:04:31 | 1.94 / 0.000 | 1.25 / 0.014 |
| 11:10:58 | 2.10 / 0.000 | 1.00 / 0.043 |
| 11:17:33 | 2.39 / 0.000 | 0.97 / 0.052 |
| 11:24:23 | 2.07 / 0.000 | 0.90 / 0.046 |
| 11:30:56 | 2.27 / 0.000 | 0.71 / 0.113 |
| 11:38:04 | 2.48 / 0.000 | 0.68 / 0.103 |
| 11:44:23 | 2.19 / 0.000 | 0.58 / 0.131 |
| 11:50:49 | 1.81 / 0.021 | 0.39 / 0.283 |
| 11:57:22 | 0.44 / 0.039 | 0.36 / 0.324 |
| 12:04:06 | 0.41 / 0.109 | 0.37 / 0.411 |
| 12:11:08 | 1.20 / 0.289 | 0.15 / 0.665 |

The 12:17:24 seed masks are excluded from scoring. The one-hour forward forecasts are also excluded. Full rows, including raster footprint coverage and per-particle oil hits, are in `per_observation_metrics.csv`.

## Outputs

- `validation_results.json` — exact run configurations, forcing metadata/checksums, mask metadata/checksums, aggregate and per-observation metrics.
- `per_observation_metrics.csv` — analysis table for all 31 scored mask observations.
- `mineral_hindcast_masks.png` and `soybean_hindcast_masks.png` — backward ensemble-median trajectories overlaid on the observed mask outlines.
- `scripts/run_norse2019_obs_hindcast.py` — reproducible experiment runner.

## Limitations and recommendation

The local mask centroids are used only as observation endpoints and comparison statistics. Exact release coordinates remain unavailable, so release-origin positional error is not measured. Mineral agreement is weak over much of the earlier time series: mean hull IoU is 0.028 and mean centroid displacement is 2.247 km. Soybean shows higher mask agreement, with mean hull IoU 0.158 and mean centroid displacement 0.996 km, though the early observations are also poorly matched. Because these are manually delineated masks, the initial seed uses their convex hull, and the ensemble hull is not a physical slick model, the overlap scores should be treated as observational reconstruction diagnostics only.

The pipeline’s origin estimator selected 11:17:24 UTC for both cases; that algorithmic estimate is not compared with the known release time and is not evidence of release-origin accuracy. Waves/Stokes drift were unavailable, and no CODE drifter was used.

Phase 7C source reconciliation is complete. It did not verify the datum/CRS or provenance of the local drifter CSV. Therefore **Phase 7D remains NO-GO**: independent drifter spatial validation has not been performed and must not be represented as completed. Further drifter comparison can proceed only after the Phase 7C provenance and CRS gate is resolved. This does not change the historical oil-mask comparison reported above. **NO-GO for claiming validated release-origin accuracy or full slick-spread prediction** from these runs.

See [Phase 6 error diagnosis](phase6_error_diagnosis.md) and [error-versus-time plot](phase6_error_diagnosis.png) for signed bias, temporal trends, spread, and the metric audit.
