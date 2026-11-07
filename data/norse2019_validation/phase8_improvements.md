# Phase 8 — Evidence-Based Improvements

**Date:** 2026-11-07
**Decision:** Presentation/documentation corrections were justified by direct code-to-claim mismatches. No M3 numerical or scientific implementation changes were made.

## Defects investigated and evidence

| Finding | Evidence | Decision |
|---|---|---|
| Origin-region confidence wording was inaccurate. | `app/pipeline.py` calls `origin_zone(..., pct=95.0, method="kde_hdr")`. `app/drift/cone.py` returns this as an approximate KDE HDR region. The same `origin.spread_km` is separately computed as a 90th-percentile distance in the ensemble code. The UI and generated attribution note described the region as a “90 percent envelope,” conflating the region mass with the radius statistic. | Confirmed presentation defect. Corrected the UI and report; added a focused test. The region is explicitly described as approximate and uncalibrated. |
| Browser UI named the result “Release zone.” | The UI layer legend said “Release zone”; the backend returns an origin estimate derived from modeled ensemble positions, and NORSE release coordinates remain unavailable. | Confirmed risk of implying a known release location. Renamed the layer “Estimated origin zone.” |
| General architecture and submission documents described the active backward pipeline as RK2/hourly and used the legacy spread-threshold origin rule. | Current `app.pipeline.run_drift()` explicitly uses RK4 at `HINDCAST_RK4_DT_SECONDS` (300 s), caps the backward horizon at `HINDCAST_RK4_MAX_H` (18 h), calls `pick_origin_index(..., method="minimum_variance")`, then builds the origin zone with 95% KDE HDR. The forward call uses the existing default RK2 integrator. `pick_origin_index()` still supports the legacy `spread_threshold` mode, but the active pipeline does not select it. | Confirmed documentation drift. Corrected the overview, architecture, compliance, and deck descriptions to distinguish the active pipeline from the legacy selector. No algorithm was changed. |
| Phase 6 hypotheses and metric code. | Read the Phase 6 diagnostic and its metric audit. It labels causal explanations as hypotheses and records corrected EPSG:32631, raster-footprint, and median-statistic handling. The current report cites the corrected aggregate values; no new contradictory metric defect was established in this pass. | No metric or benchmark-output changes. No hypothesis was promoted to a proven cause. |
| Normal browser launch versus NORSE validation. | `start.bat` launches Uvicorn at `127.0.0.1:8000`; `app/static/app.js::runPipeline()` posts to `/api/run` without a forcing profile, and the request schema defaults to `default`. The NORSE oil-mask runner is a separate script and writes over the saved benchmark outputs. | Kept the two-part demo route: ordinary UI, then existing precomputed NORSE artifacts. Did not add a UI selector or rerun the benchmark. |

No M3 integration defect was established in the reviewed checksum validation, fail-closed profile routing, temporal/spatial coverage checks, or solver behavior. The Phase 4B checks and Phase 5B results remain as previously recorded.

## Changes made

- `app/static/app.js`: renamed “Release zone” to “Estimated origin zone”; popup now distinguishes the approximate 95% KDE region from the separate 90th-percentile spread radius and says the region is not calibrated.
- `app/api/report.py`: corrected the generated attribution note to describe the approximate 95% KDE region and separately report the 90th-percentile spread radius.
- `tests/test_console_dom.py`: added presentation checks tying the UI claim to the active pipeline’s 95% KDE call and checking the generated report’s two distinct quantities.
- `README.md`, `docs/ARCHITECTURE.md`, `docs/COMPLIANCE.md`, `docs/architecture-pipeline.svg`, `docs/ps-26143-audit.html`, and `docs/tidetrace-deck.html`: corrected stale solver and origin-selection descriptions to reflect current pipeline behavior.
- `data/norse2019_validation/demo_readiness.md`: recorded the corrected UI language and preserved the separation between the default UI demo and precomputed NORSE validation.

No changes were made to the RK2/RK4 integrators, advection/diffusion implementation, time steps, windage, particle count, forcing, adapter, M3 pipeline settings, or validation artifacts. `validation_results.json`, `per_observation_metrics.csv`, and both saved hindcast plots retain their existing timestamps and sizes. The hindcast runner was not invoked.

## Tests and checks

The first focused invocation omitted `--basetemp` and failed in the autouse fixture before test bodies ran because pytest could not create a temp directory under the Windows AppContainer temp path. This was an environment/setup error, not an assertion failure. The same test selection was rerun with its temporary base inside the repository; scope and assertions were unchanged.

| Exact command | Exit | Result | Wall duration |
|---|---:|---|---:|
| `.\venv\Scripts\python.exe -m pytest -q tests/test_console_dom.py tests/test_norse2019_pipeline.py tests/test_norse2019_adapter.py tests/test_m3_hindcast.py` | 1 | 34 setup errors; pytest reported inability to create numbered temp directories under the Windows packaged-app temporary directory. No test body executed. | 94.75 s |
| `.\venv\Scripts\python.exe -m pytest -q --basetemp=.pytest_cache/phase8_focus tests/test_console_dom.py tests/test_norse2019_pipeline.py tests/test_norse2019_adapter.py tests/test_m3_hindcast.py` | 0 | **34 passed** in pytest’s 199.65 s. Includes new UI/report wording checks and existing M3 numerical, NORSE adapter, and fail-closed pipeline tests. | 212.83 s |
| `.\venv\Scripts\python.exe -m pytest -q --basetemp=.pytest_cache/phase8_offline tests/test_offline_boundary.py` | 0 | **9 passed** in pytest’s 7.27 s. | 11.79 s |
| `git diff --check` | 0 | No whitespace errors. | 0.59 s |

The complete normal-scene TestClient regression was not run in this pass. Its previously documented Windows `socketpair()` stall occurs before `/api/run`; Phase 8 does not claim that test passed or that the app itself fails in a browser.

## Updated demo guidance

Use the current `start.bat` route to show TideTrace at `http://127.0.0.1:8000/`, then open the already saved files through the read-only `/data/norse2019_validation/` mount or in an editor. Label those NORSE plots and metrics as **precomputed retrospective results**, not outputs generated live by the console. The UI’s normal run uses the default profile and does not provide a NORSE selector.

For M3 visuals, describe the dotted line as the **ensemble-median backtrack**. Describe the origin polygon as an **approximate 95% KDE region, uncalibrated**, with the displayed spread radius being a distinct 90th-percentile distance. The hindcast PNGs show ensemble-median paths over observed masks; the saved JSON does not include full raw particle trajectories. Keep the scientific caveats in `demo_readiness.md` visible in the video narrative.

## Deliberately unresolved

- The Windows full normal-scene TestClient regression remains unverified because of the already diagnosed loopback `socketpair()` environment stall; it was not bypassed with mocks or dependency upgrades.
- There is no UI-driven NORSE validation view. The benchmark remains script/API-only and the current demo artifacts are static/precomputed.
- No full particle-track dump is present among the saved NORSE artifacts; none was invented or regenerated.
- NORSE release-origin positional accuracy, calibrated uncertainty, and independent drifter spatial validation remain unestablished. Phase 7D remains **NO-GO** because local drifter datum/CRS and provenance are unverified.
- The historical comparison lacks wave/Stokes forcing; this remains a stated limitation, with no substitute forcing introduced.

## Final status

**GO** for the two-part demo of the current UI plus explicitly labelled saved NORSE2019 outputs. **NO-GO** for presenting the UI as running the NORSE benchmark live, claiming calibrated uncertainty or release-origin accuracy, or calling independent drifter validation complete. Phase 8 is complete; Phase 9 has not been started.

No commit or push was made.
