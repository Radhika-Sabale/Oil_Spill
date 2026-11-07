# Phase 9 — Final Validation and Submission Readiness

**Date:** 2026-11-07
**Scope:** Post-Phase-8 review of the current worktree, M3/NORSE integration, saved validation results, tests, and demo path. No hindcast, forcing download, or benchmark regeneration was performed.

## Overall decision

**CONDITIONAL GO for a carefully labelled prototype submission; NO-GO for a verified live interactive demo from this checkout.** Focused M3/adapter/pipeline/offline tests pass, prepared real forcing remains checksum-valid, and the saved retrospective oil-mask comparison is internally consistent. However, the full normal-scene regression remains unverified, the local server could not be reached in this execution environment, and all four scene-index SAR TIFF paths are missing from this checkout. A live run must be verified on the actual presentation machine with its SAR inputs before it is shown.

The NORSE experiment is a completed retrospective real-wind/current comparison against earlier oil masks. It is not independent drifter validation, release-origin accuracy, a calibrated uncertainty assessment, or a real-time validation.

## 1. Repository and change audit

- Branch/status: `roadmap`, ahead of `origin/roadmap` by one commit. No commit or push was made in this phase.
- `git diff --stat`: 13 tracked files currently differ from `HEAD`. The four M3 route/schema/pipeline files (`app/api/drift.py`, `app/api/pipeline.py`, `app/pipeline.py`, `app/schemas.py`) are the previously audited Phase 4B NORSE opt-in/fail-closed integration. Phase 8 changes are the intended attribution-note wording (`app/api/report.py`), UI labels (`app/static/app.js`), two focused tests, and solver/claim documentation in `README.md` and `docs/`.
- Existing untracked M3/NORSE adapter, runner, test, forcing, and validation files remain untracked as recorded in the previous audits. They were not newly generated in Phase 9. The only Phase 9 deliverable added is this report.
- Complete tracked diff review found no Phase 9 change to the RK2/RK4 solvers, windage, diffusion, particle count, forcing, benchmark configurations, or saved metrics. The existing Phase 4B changes pass the fail-closed checks below.
- `git diff --check`: exit code **0**, no whitespace errors.
- Validation file sizes and timestamps remained as recorded before the checks: `validation_results.json` 84,572 bytes; `per_observation_metrics.csv` 10,531 bytes; mineral plot 33,353 bytes; soybean plot 37,015 bytes. The benchmark runner was not invoked.

## 2. Focused tests

Command run from the repository root:

```powershell
.\venv\Scripts\python.exe -m pytest -q --basetemp=.pytest_cache/phase9_focused tests/test_m3_hindcast.py tests/test_advection.py tests/test_norse2019_adapter.py tests/test_norse2019_pipeline.py tests/test_console_dom.py tests/test_offline_boundary.py
```

**Exit code 0 — 49 passed, 0 failed, 0 skipped** (pytest: 36.62 s; wall: 42.78 s). This includes numerical/hindcast and advection tests, adapter checks, NORSE API/pipeline failure-path checks, Phase 8 UI/report wording regressions, and all 9 offline-boundary tests. There were no skip reasons because no tests were skipped. A repository-local `--basetemp` was used to avoid the Windows default-temp setup failure recorded in Phase 8.

Checks relevant to the NORSE path include checksum/manifest validation, exact timestamps, known-grid interpolation, physical bounds, missing/altered input failures, insufficient space/time coverage failures, adapter field injection, no call to the default or synthetic fallback on the NORSE route, and preservation of the default non-NORSE path.

## 3. Bounded full normal-scene regression

One bounded attempt was made using the previously documented single-test scope, with a 60-second faulthandler diagnostic and a 120-second stop bound:

```powershell
.\venv\Scripts\python.exe -m pytest -vv -o faulthandler_timeout=60 --basetemp=.pytest_cache/phase9_fullrun tests/test_pipeline_offline.py::test_full_pipeline_runs_offline
```

Pytest collected one test and entered it. At 60 seconds the diagnostic showed the existing block in `socket._fallback_socketpair()` → `asyncio.ProactorEventLoop._make_self_pipe()` → `starlette.testclient.TestClient.__enter__()` at `tests/test_pipeline_offline.py:103`, before `/api/run`. The run was interrupted at approximately 120 seconds (shell exit code **1** from interruption): **0 passed, 0 assertion failures, 0 skipped, 1 interrupted/uncompleted**. This regression remains **NOT VERIFIED**. No application or dependency workaround was attempted.

## 4. Forcing integrity and NORSE fail-closed behavior

Both prepared NetCDF files still match their manifest checksums and are byte-for-byte the previously approved subset files:

| Product | Actual bytes | SHA-256 | Time samples |
|---|---:|---|---|
| MEPS | 271,156 | `22a41dad2d5af3308bf26b82d5fb833385c3c1ebd7c21ea353ab25cc372d314f` | 21 hourly samples, 2019-06-12 04:00 through 2019-06-13 00:00 UTC |
| NorKyst800 | 1,474,144 | `8749cedd3db73e512b745757e7695feae7b18813b561115c12730ad1141431f2` | 21 hourly samples, same interval |

The adapter report and manifest still document the variable mapping and conventions: prepared MEPS `eastward_wind_10m` / `northward_wind_10m` are already earth-oriented after subset-time rotation; NorKyst `u_eastward` / `v_northward` are earth-oriented and use the shallowest valid surface level, depth index 0 / 0 m. Components are in m s⁻¹, times are UTC epoch seconds, and target grid axes are ascending. The current forcing report explicitly disables wave/Stokes input.

The Phase 4B route remains opt-in and fail-closed. Tests prove NORSE bypasses `load_for_scene()` and synthetic fallback; adapter checksum/manifest and coverage errors reject the run. The historical JSON records `metocean_profile="norse2019"`, both input hashes, covered hindcast/forecast intervals, zero out-of-coverage evaluations, and `stokes_enabled=false` for both oil runs. This is verification of the prepared/integrated real forcing path, not a new hindcast.

## 5. Saved benchmark consistency and scientific claims

- The 31 scored rows in the CSV split into 17 mineral and 14 soybean observations, matching the JSON and report.
- Recomputed CSV means equal the saved JSON and Phase 6 diagnostic values at full precision:
  - Mineral: mean centroid displacement **2.246798 km**; mean hull IoU **0.0278228**.
  - Soybean: mean centroid displacement **0.995723 km**; mean hull IoU **0.1576658**.
- The Markdown report rounds these to 2.247 km / 0.028 and 0.996 km / 0.158. The corrected Phase 6 results remain the source-of-truth; no stale rounded mean was found.
- Origin terminology is now consistent: the displayed polygon is an approximate **95% KDE HDR region**, while `spread_km` is a separate **90th-percentile ensemble radius**. Neither is calibrated. The current UI and attribution note say so.
- Phase 7C source reconciliation is marked complete. Phase 7D remains **NO-GO** because the local drifter CSV's coordinate datum/CRS and provenance remain unverified. Independent drifter spatial validation has not been performed.
- The report does not claim release-origin positional accuracy. Exact release coordinates remain unavailable. The ensemble hull is not presented as full slick-spread accuracy.

## 6. Application and demo verification

The demo checklist's code path is accurate: `start.bat` selects `.venv`, then `venv`, launches Uvicorn on `127.0.0.1:8000`, and opens `/`; the frontend posts its normal analysis to `/api/run` without `metocean_profile`, so it uses the default profile. NORSE mask-seeded hindcasts remain a separate script/API workflow, and saved NORSE plots/results are precomputed static artifacts.

The application was not available for browser interaction in this execution sandbox:

- A controlled isolated-data Uvicorn attempt on port 8011 did not become reachable; the bounded attempt was stopped without an application response.
- The documented `start.bat` returned exit code **1** with “The app did not become ready.” The subsequent loopback HTTP probe failed with Windows socket error “An attempt was made to access a socket in a way forbidden by its access permissions.” Existing server log/error/PID files were backed up and restored; no run job was created.
- Browser automation was not used because no local application endpoint could be reached. No browser dependencies were installed.
- `data/sar/scenes.json` lists four scenes, but each indexed TIFF path is absent, and `data/sar` contains **0 `.tif` files**. Therefore an actual normal-scene analysis could not be initiated without obtaining the missing scene rasters. No self-test/synthetic SAR was substituted or shown as real data.

So the HTML/API workflow is verified by code inspection and focused tests, but the live browser startup/interaction is **not verified** in this environment. This is an environment and input-availability limitation; it does not prove that the UI fails on a presentation machine with loopback access and the scene files present.

## 7. Outstanding scientific and operational limitations

- Independent drifter validation is pending; Phase 7D remains NO-GO.
- Release-origin accuracy is unverified because exact release coordinates are unavailable.
- The 95% KDE region and ensemble spreads are not empirically calibrated.
- Full slick-spread physics are not validated by particle-ensemble overlap with oil masks.
- Wave/Stokes forcing is absent from the NORSE comparison.
- The full normal-scene end-to-end regression is not verified due to the Windows loopback stall.
- Live frontend analysis was not demonstrated here because loopback access was denied and the indexed SAR TIFFs are absent.

## 8. Recommended demo sequence

On the actual presentation laptop, first confirm its loopback/network policy permits the local server and that each intended indexed scene TIFF exists. Do not proceed with a live analysis if either check fails.

1. Run `start.bat` from the project root and confirm the browser reaches `http://127.0.0.1:8000/`.
2. If the correct SAR scene files are present, choose a scene and run the normal UI analysis. Describe it as the default-profile application path; do not call it the NORSE2019 experiment. Stop if the run fails or reports a missing scene/forcing.
3. Separately open the existing precomputed artifacts: `mineral_hindcast_masks.png`, `soybean_hindcast_masks.png`, `phase6_error_diagnosis.png`, `M3_VALIDATION_REPORT.md`, and `per_observation_metrics.csv` under `data/norse2019_validation/` (or read-only `/data/norse2019_validation/...` URLs while the app is available).
4. Say that the NORSE outputs are retrospective, initialized from the latest observed masks, and use archived MEPS winds and NorKyst800 currents with Stokes disabled. State the metrics separately for mineral and soybean; explicitly say they are not release-origin errors or calibrated probabilities.
5. State that Phase 7D independent drifter validation is pending and that no real-time NORSE prediction is demonstrated. Stop TideTrace with `stop.bat`.

If step 1 or 2 cannot be verified on the presentation laptop, use a recorded/screenshot walkthrough of the interface only if it is clearly separated from the precomputed NORSE plots; otherwise present the existing reports/plots as precomputed research results without claiming a working live demo.

## 9. Readiness distinctions

| Claim | Status |
|---|---|
| Focused M3 numerical, adapter, integration, Phase 8 presentation, and offline-boundary tests passed | **Verified: 49 passed, 0 failed, 0 skipped** |
| Real forcing inputs load through the NORSE adapter and NORSE pipeline rejects invalid/insufficient forcing without synthetic fallback | **Verified by focused tests and saved run metadata/checksums** |
| Historical oil-mask observational comparison | **Completed: 31 earlier masks scored across separate mineral and soybean hindcasts** |
| Independent drifter validation | **Pending; Phase 7D NO-GO** |
| Release-origin accuracy | **Unverified / not evaluated** |
| Calibrated uncertainty | **Unverified** |
| Full normal-scene TestClient regression | **NOT VERIFIED; stopped at known Windows socketpair block** |
| Live browser startup and normal UI analysis in this environment | **NOT VERIFIED; loopback denied and indexed SAR TIFFs absent** |

**Submission recommendation:** conditional on presenting the NORSE evidence as precomputed historical comparison results, preserving the caveats above, and verifying the live app plus input availability on the presentation machine. Do not claim the full interactive pipeline or full end-to-end regression was validated by this Phase 9 run.

No solver, benchmark, forcing, or saved validation result was modified. No commit or push was made. Phase 9 is complete; Phase 10 has not been started.
