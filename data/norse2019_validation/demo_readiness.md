# M3 Demo Readiness Checklist

**Audit date:** 2026-11-07
**Scope:** Existing TideTrace UI/API and the already completed NORSE2019 M3 artifacts. No hindcast was rerun and no validation results were regenerated.

## Decision

**A demo is possible as two clearly separated parts:** (1) demonstrate the current TideTrace web console on one of its indexed scenes, and (2) present the existing NORSE2019 M3 hindcast outputs as a precomputed, retrospective validation example. The current browser workflow does **not** provide an end-to-end NORSE2019 run selector.

Do not present the ordinary UI run as the NORSE2019 hindcast, or the saved hindcast plots as output generated live by the UI.

## What the current application exposes

### Browser entry and ordinary analysis flow

- Entry point: `app/static/index.html`, served at `/` by `app/main.py`; browser logic is in `app/static/app.js`.
- Select a scene from the left rail, adjust hindcast/forecast/search/window parameters, and choose **Run analysis**.
- `app/static/app.js` sends `POST /api/run` with scene ID and visible parameters. It does **not** include `metocean_profile`.
- `app/api/pipeline.py` passes the request to `app.pipeline.run()`. The `RunRequest` schema defaults `metocean_profile` to `default`; consequently the UI uses the default scene forcing path.
- The pipeline detects slick polygons, characterizes them, invokes M3 drift, and returns the job document. The UI can display slick geometry, backward ensemble track/cone and uncertainty, forecast products, metocean summary, and AIS attribution outputs when present in the job.
- The UI can expose the backend's default M3 behavior, but cannot choose NORSE forcing, nor initialize from the NORSE oil-mask experiment through the visible workflow.
- The UI labels the origin layer **Estimated origin zone**. Its popup distinguishes the approximate 95% KDE region from the separate 90th-percentile ensemble spread radius and states that the region is not calibrated.

### API and script-only capabilities

- `POST /api/run` accepts `metocean_profile: "norse2019"`, but it still runs the normal scene detection/pipeline path. The UI currently omits this option.
- `POST /api/drift` also accepts `metocean_profile: "norse2019"` for an explicit drift request. It requires a timestamp and centroid and/or polygon (or an existing job ID); the NORSE profile rejects invalid or insufficient real forcing rather than silently using synthetic forcing.
- The controlled oil-mask comparison is implemented by `scripts/run_norse2019_obs_hindcast.py`, which reads external local mask rasters, constructs a seed polygon from the latest mask for each oil, and calls `app.pipeline.run_drift()` with the NORSE profile. It is separate from the browser's ordinary workflow.
- The runner writes `validation_results.json`, `per_observation_metrics.csv`, and the two PNG plots into this directory. Do **not** rerun it as part of this checklist: it rewrites the existing validation artifacts, and its required mask rasters are external to the repository.

## Outputs confirmed on disk

The following completed outputs are present in `data/norse2019_validation/`:

| Artifact | What it supports in a demo | Limitation |
|---|---|---|
| `mineral_hindcast_masks.png` | Mineral-oil observed mask outlines and backward ensemble-median path overlay. | Static plot; does not animate particles or prove release-origin accuracy. |
| `soybean_hindcast_masks.png` | Soybean-oil observed mask outlines and backward ensemble-median path overlay. | Static plot; not full slick-spread simulation. |
| `validation_results.json` | Exact saved run configuration, forcing metadata, backward-step counts, origin diagnostics, and per-observation/aggregate results. | It does not contain the full raw particle trajectories; it is saved output, not a live UI result. |
| `per_observation_metrics.csv` | Per-mask comparison table for 31 scored earlier observations. | Retrospective mask comparison only. |
| `M3_VALIDATION_REPORT.md` | Human-readable experiment settings, metrics, and limitations. | Historical validation report. |
| `phase6_error_diagnosis.png` and `phase6_error_diagnosis.md` | Saved time/error diagnostics and interpretation. | Diagnostic hypotheses are not proven causes. |

Specific capability check:

- **Particle trajectories:** the saved PNGs show the ensemble-median backtrack over mask outlines. The JSON records backward-step counts and diagnostics, not full raw particle tracks; the current UI does not load these saved benchmark runs as a job.
- **Backward hindcast:** completed for mineral and soybean with real MEPS winds and NorKyst800 currents, using the `norse2019` profile; Stokes drift was disabled.
- **Ensemble uncertainty:** saved solver ensemble/origin diagnostics exist in JSON and plots. Ensemble spreads/hulls are not calibrated probabilities.
- **Observed oil-mask comparison:** completed against earlier same-type mask observations, with output plots and metrics.
- **Quantitative metrics:** present in JSON/CSV/report. Mineral mean centroid displacement is 2.247 km and mean hull IoU is 0.028; soybean is 0.996 km and 0.158, respectively. These describe the specific retrospective comparison, not release-origin error or full slick prediction accuracy.

## Recommended reproducible demo route

Use the browser for the current application, then open the saved NORSE artifacts directly. This route avoids the known Windows `TestClient` loopback stall and does not execute the hindcast.

### A. Show the current web application

1. From the repository root, launch:

   ```bat
   start.bat
   ```

2. Confirm the browser opens `http://127.0.0.1:8000/`. If it does not, inspect `data/server-error.log` and `data/server.log`.
3. Show the scene selector, visible run parameters, map/layer controls, drift and uncertainty panels, and the other tabs as current application capabilities.
4. If demonstrating **Run analysis**, state that this uses the default scene pipeline/profile. The normal-scene end-to-end regression remains unverified in this Windows environment due to a loopback `socketpair()` stall during TestClient setup; a manual browser run was not performed as part of this audit.
5. Stop the server with `stop.bat` when done.

### B. Present the precomputed NORSE2019 M3 experiment

With the server still running, open these read-only static artifacts in a browser:

- `http://127.0.0.1:8000/data/norse2019_validation/mineral_hindcast_masks.png`
- `http://127.0.0.1:8000/data/norse2019_validation/soybean_hindcast_masks.png`
- `http://127.0.0.1:8000/data/norse2019_validation/phase6_error_diagnosis.png`
- `http://127.0.0.1:8000/data/norse2019_validation/M3_VALIDATION_REPORT.md` (may download or display as text depending on browser)

For an on-screen explanation, open `data/norse2019_validation/M3_VALIDATION_REPORT.md` and `per_observation_metrics.csv` in an editor or spreadsheet, and use `validation_results.json` as the exact machine-readable record. Explain that these are previously generated outputs; they are not loaded into or generated by the TideTrace UI.

### C. Optional source/API walkthrough (no execution needed)

Show the implementation path in the repository:

1. `app/static/app.js`: `runPipeline()` constructs the UI's `/api/run` request and does not set a forcing profile.
2. `app/api/pipeline.py` and `app/schemas.py`: API forwarding and the default profile.
3. `app/pipeline.py`: explicit real-forcing integration path and fail-closed coverage checks.
4. `scripts/run_norse2019_obs_hindcast.py`: the separate NORSE validation runner and explicit `metocean_profile="norse2019"` call.

The API supports NORSE profile selection, but no exact equivalent historical request is listed here: reproducing the benchmark requires the actual external mask geometries and their associated metadata, and running the experiment would rewrite the saved validation artifacts. Do not substitute guessed coordinates or a fabricated polygon for this demo.

## Scientific statements for the video

Use wording such as:

> “This is a retrospective NORSE2019 backward-transport experiment initialized from the latest observed oil masks. It uses archived MEPS winds and NorKyst800 surface currents; wave/Stokes drift is disabled. We compared reconstructed ensemble positions with earlier masks. This does not establish release-origin accuracy, calibrated uncertainty, or full slick-spread prediction.”

Also state:

- Mineral and soybean runs are separate; their mean centroid displacement / mean ensemble-hull IoU were 2.247 km / 0.028 and 0.996 km / 0.158, respectively.
- Exact release coordinates are unavailable in the established benchmark metadata, so release-origin positional error is not measured.
- Phase 7C did not establish the local drifter CSV's datum/CRS and provenance. Phase 7D remains **NO-GO**; independent drifter spatial validation has not been performed.
- The forecast segment in the historical runs was excluded from mask scoring because no later observations were available.
- The oil-mask hull scores are diagnostics of the particle ensemble geometry against mask rasters, not proof that the model captures the full physical slick footprint.
- The ordinary UI scenes are separate from the 2019 NORSE benchmark; do not conflate them.

## Genuine blockers and status

- **No blocker to showing saved artifacts** if this project directory and existing outputs are available.
- **No UI-driven NORSE2019 run:** the UI has no forcing-profile control and no NORSE mask-seeded benchmark view.
- **No verified full normal-scene regression on this Windows setup:** TestClient stalls before `/api/run`; this does not prove the server/browser flow itself fails.
- **No independent drifter validation:** datum/CRS and local file provenance remain unresolved, so Phase 7D remains NO-GO.
- **No live benchmark rerun recommended for the submission video:** it risks overwriting the current authoritative outputs and depends on external masks.

**Demo recommendation:** GO for a two-part, clearly labelled demo of the existing app plus saved NORSE2019 evidence; NO-GO for claiming that the UI runs the NORSE2019 validation live or that the system is independently validated for release-origin accuracy.
