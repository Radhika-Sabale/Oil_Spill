# SentinelTrace Repository Audit

**Audit scope:** Existing TideTrace repository compared with the SentinelTrace five-stage roadmap (updated 4 November 2026). This document is a review and prioritized change plan. It does not change application code or assert that planned work has been completed.

## How to use this audit

Start with the verdict, then follow the stage sections. Each file row describes its current role and the gap/action relative to the roadmap. `Inherited` means the file/functionality exists in the base repository; it does not mean it meets SentinelTrace acceptance criteria.

### Status key

- **KEEP / adapt** — useful foundation; preserve its contract and extend in place.
- **PARTIAL** — some relevant behavior exists; required roadmap behavior is missing or unverified.
- **MISSING** — no implementation was found in the audited source tree.
- **OPTIONAL** — useful only if time/data allow; not a core acceptance dependency.
- **VERIFY** — inspect runtime/data evidence before claiming the feature.

## Executive verdict

TideTrace is a useful functioning foundation for a map-based SAR/AIS investigation prototype: it already has a FastAPI pipeline, a Leaflet console, segmentation/inference paths, geospatial helpers, a backward drift model, AIS filtering/scoring, offline/demo data paths, and report generation. The current implementation is **not yet aligned with the specified SentinelTrace algorithms end to end**. The roadmap can be delivered incrementally by retaining these interfaces and adding stage status/provenance; a rewrite is not indicated by this audit.

Largest mismatches:

1. Stage 1 lacks verified incidence-angle normalization, the 3–12 m/s wind gate, and CA-CFAR screening.
2. Stage 2 is a different model/data/input-channel path (U-Net++/EfficientNet-B0, three input channels, Zenodo path); Kaggle dataset fit, labels, licence, georeferencing and model lineage remain to be audited. It is not the planned four-channel ResNet-34 U-Net.
3. Stage 3 now uses RK4 at 300-second steps (up to 18 hours), horizontal eddy diffusion, minimum-spread-variance hourly selection and a grid-derived KDE 95% convex-hull approximation. Stokes uses cached wave height, peak period and actual wave-from direction when all are present. M3 numerical checks pass, but the Golden Case cache has wind/current only, with no usable wave fields; its Stokes contribution remains unavailable. The convex hull is not a calibrated confidence ellipse.
4. Stage 4 has AIS filtering/scoring and gap handling, but no H3 index, SAR dark-target discrepancy detection, or slick volume/derived pump-flow analysis.
5. Stage 5 has a dark Leaflet console and a report endpoint, but no verified end-to-end five-stage status contract, SHA-256 report seal, or validated PDF/A output.

**Recommended approach:** preserve the existing TideTrace flow; add target behavior behind current interfaces; keep unsupported outputs explicit as `unavailable`, `simulated`, or `illustrative`. Do not drop a working capability until its replacement passes acceptance. The roadmap’s revised owner map is M1 Radhika Sabale, M2 Ruchira, M3 Prem, M4 Ruchika, M5 Akhilesh.

## Architecture at a glance

| Roadmap stage | Existing foundation | Main gap |
|---|---|---|
| 1. Ingest/gate (M2) | Scene/raster and metocean utilities | Calibration semantics, incidence-angle normalization, wind gate and CA-CFAR |
| 2. Segment (M1) | ML dataset/model/inference, vision adapter, geospatial vectorization | Kaggle audit, four channels, target model/config, sinuosity integration and proven lineage |
| 3. Hindcast (M3) | Current/wind fields, RK4, horizontal diffusion, optional wave-driven Stokes, min-variance origin choice, KDE-derived hull, land handling | Golden Case wave inputs missing; statistical calibration and real-case comparison remain unverified |
| 4. Attribute (M4) | AIS ingestion/interpolation/filter/scoring; API schemas | H3, radar dark targets, mass balance, derived flow and qualified evidence fields |
| 5. Present/package (M5) | Leaflet UI, FastAPI routes, HTML/PDF report | Stage-status UI/API, provenance dossier, SHA-256 verification, PDF/A validation if claimed |

## Stage 1 — SAR ingestion, calibration and screening (M2)

**Roadmap target:** Sentinel-1 GRD and acquisition metadata; calibrated sigma-zero; linear-space incidence normalization; matched ERA5 10 m wind gate (3–12 m/s); 100 m CA-CFAR candidate screening with reported parameters and retention.

| File/module | What it currently does | Flag and roadmap action |
|---|---|---|
| `app/scenes.py` | Scene catalogue/loading and scene metadata path | **PARTIAL** — retain; record product type (GRD/RTC), source, acquisition time, angle availability, units and transform. Do not call RTC sigma-zero without checking. |
| `app/geo/raster.py`, `app/geo/tiffio.py` | Raster read/write and georeferenced raster support | **KEEP / adapt** — use for validated calibrated inputs and candidate windows; carry nodata/units/CRS explicitly. |
| `app/geo/crs.py`, `app/geo/geometry.py` | CRS and geometry helpers | **KEEP** — use in scene-to-polygon coordinate handoff; verify against known control points. |
| `scripts/fetch_sentinel1_scene.py` | Fetches/caches scene inputs using the repository’s current source path | **VERIFY** — compare actual product and calibration metadata to the roadmap’s GRD assumptions; source differs from the roadmap’s proposed GEE route. |
| `scripts/build_metocean_cache.py` | Builds cached environmental fields | **PARTIAL** — current support does not establish the specified matched ERA5 wind gate or complete source/time provenance. |
| `app/drift/fields.py` | Loads/interpolates environmental forcing used by drift | **PARTIAL** — current current/wind fields do not provide validated Stage 1 gate status. Avoid conflating M2 wind matching with M3 forcing interpolation. |
| No Stage 1 calibration/gate/CFAR module found | — | **MISSING** — add behind existing scene/raster boundary: linear sigma-zero normalization, wind gate, CA-CFAR candidate windows, retained fraction and unavailable reasons. Thresholds remain provisional until measured on the Golden Case. |

**Avoid:** applying cosine normalization directly to dB values; calling a simple thresholding operation CA-CFAR; claiming >95% reduction without measured results.

## Stage 2 — Polarimetric segmentation (M1)

**Roadmap target:** audited Kaggle dataset; four channels `[VV, VH, Span, Rvv/vh]` with derived invariants computed from linear power; target ResNet-34 U-Net to be evaluated; sinuosity feature/rejection; map-ready GeoJSON and model/data provenance.

| File/module | What it currently does | Flag and roadmap action |
|---|---|---|
| `app/ml/dataset.py` | Dataset loading for the existing training path | **PARTIAL** — inspect against the actual Kaggle archive before reuse; document labels, units, band order, masks, licence and scene-separated splits. |
| `app/ml/model.py`, `app/ml/train.py` | Current model construction and training | **PARTIAL** — current configuration is a U-Net++/EfficientNet-B0-style three-channel path; target architecture is different. Preserve baseline and evaluate the target only after data audit. |
| `app/ml/infer.py`, `app/ml/fallback.py` | Inference and fallback behavior used by the main pipeline | **KEEP / adapt** — expose model/data/checkpoint identity and whether the output is learned, fallback or fixture. |
| `app/vision/predict.py`, `cache.py`, `schema.py`, `status.py`, `warmup.py` | Parallel vision adapter, caching/status and inference support | **PARTIAL** — adapter path duplicates `app/ml/`; main pipeline currently uses the ML path. Agree one public contract or explicitly connect both before adding new features. |
| `app/vision/vectorize.py`, `app/geo/geometry.py` | Converts detections/geometry for mapping | **KEEP / verify** — retain georeferencing and validate pixel-to-world transform using a known control point. |
| `scripts/download_zenodo_subset.py`, `scripts/prepare_tiles.py` | Existing Zenodo-oriented data preparation | **KEEP as separate baseline** — do not relabel its data or metrics as Kaggle results. |
| `scripts/build_kaggle_kernels.py`, `scripts/kaggle_push.py`, `scripts/train_kaggle.ipynb`, `kaggle/` | Kaggle-oriented experiments/support files | **VERIFY** — existence does not prove the named Kaggle dataset is loaded or that its licence/labels/channels fit. Record exact dataset version and sample inventory. |
| No integrated polarimetry/sinuosity feature found | — | **MISSING** — add derived channels from linear power and calculate sinuosity as a feature. Validate any algae rejection cutoff on held-out labels; do not hard-code an unvalidated universal rule. |

**Dataset gate:** before training, capture a small auditable inventory and inspect representative image/mask pairs. Record source/version/date, licence, file formats, channel meaning/units, label encoding, georeferencing and split policy. Do not claim the Kaggle dataset supports four-channel polarimetry or look-alike classification unless its contents establish that.

## Stage 3 — 4D Lagrangian hindcast (M3)

**Roadmap target:** backward RK4 with `dt=-300 s`, up to 18 h, current + 3% windage + Stokes when supported; source/time/units for forcing; minimum-variance origin window and 95% KDE uncertainty geometry.

| File/module | What it currently does | Flag and roadmap action |
|---|---|---|
| `app/drift/advection.py` | Retains the RK2 baseline and now supports selectable classical RK4; output metadata includes solver and step size | **PARTIAL** — backward pipeline selects RK4 at 300 s; validate direction, units, step convergence and analytical constant-current cases before considering it accepted. |
| `app/drift/fields.py` | Supplies/interpolates current/wind fields and optional wave height, peak period and wave-from direction; adds Kenyon Stokes velocity toward wave propagation when inputs are complete | **PARTIAL** — formula/unit checks pass, but Golden Case waves were unavailable; do not report Stokes as observed for that cache. |
| `app/drift/cone.py` | Builds baseline percentile hulls and a named KDE 95% HDR approximation using a 256×256 local grid and convex hull | **PARTIAL** — polygon output is tested, but convex hull may span low-density gaps and is not a calibrated 95% confidence ellipse. |
| `app/drift/land.py` | Land interaction/land-mask support | **KEEP** — preserve and include behavior/limitations in solver comparison. |
| `scripts/build_metocean_cache.py` | Prepares metocean cache | **PARTIAL** — does not alone establish CMEMS/ERA5/wave provenance or Stokes support; add source manifests and coverage. |
| `scripts/build_metocean_cache.py` wave fetch | Requests wave height, peak period and wave-from direction; interpolates by UTC timestamp without extrapolation and stores optional cache fields | **PARTIAL** — Golden Case request returned no usable wave grid. A supported source/date and complete spatial/time coverage are still needed for real Stokes forcing. |
| Minimum-variance/KDE origin path | `app/drift/advection.py` selects the global minimum ensemble spatial variance; `app/drift/cone.py` builds a 95% KDE-derived sample hull | **PARTIAL** — implementation is newly wired; validate selection, geometry stability and whether the approximate hull supports the intended uncertainty interpretation. |

**Important:** the roadmap’s formula and any external forcing need dimensional checks. Do not present a hindcast origin as the proven release point.

## Stage 4 — Kinematic and mass-balance analysis (M4)

**Roadmap target:** AIS candidate filtering with H3 res 7, supported radar/AIS discrepancy and dark-target status, blackout reachability, area/thickness volume range, loiter-based flow range, and explainable evidence fields.

| File/module | What it currently does | Flag and roadmap action |
|---|---|---|
| `app/ais/ingest.py` | AIS input ingestion | **KEEP / adapt** — preserve source/time provenance and distinguish received observations from reconstructed values. |
| `app/ais/interpolate.py` | Track interpolation/reconstruction | **KEEP / adapt** — preserve missingness and label interpolated segments; never imply a broadcast existed. |
| `app/ais/filter.py` | Spatial/time candidate filtering | **PARTIAL** — retain baseline; compare with H3 candidate indexing, including cell boundary and no-lost-candidate behavior. |
| `app/ais/score.py`, `app/ais/vessel_types.py` | Candidate scoring features and vessel-type handling | **PARTIAL** — useful ranking foundation; keep components explainable, do not express rank as guilt probability. |
| `app/ais/synthetic.py` | Synthetic AIS fixtures | **KEEP** — label synthetic data in API, UI and reports. |
| `app/api/ais.py` | AIS API endpoints | **PARTIAL** — extend only after M4/M5 agree schema; avoid route churn that breaks the existing UI. |
| `app/schemas.py` | Shared request/response schemas | **KEEP / adapt** — canonical place for H3 result, evidence status, assumptions, unknown values and mass-balance ranges. |
| No H3 dependency/use found | — | **MISSING** — add index at the candidate filter boundary and benchmark set equivalence with direct filtering. |
| No SAR dark-target/hull comparison found | — | **MISSING** — radar target detection requires suitable imagery/resolution and validation; otherwise status is unavailable, not “no dark vessel.” |
| No slick volume/derived flow code found | — | **MISSING** — calculate only with explicit polygon area, assumed thickness class/range and slowdown/resume interval. Keep units and uncertainty; do not present pump capacity examples or deterministic exoneration as established facts. |

## Stage 5 — Console and evidence dossier (M5, with M4 API fields)

| File/module | What it currently does | Flag and roadmap action |
|---|---|---|
| `app/static/index.html` | Existing TideTrace console structure | **KEEP / adapt** — maintain navigation and working features while surfacing SentinelTrace stage status and data provenance. |
| `app/static/style.css` | Dark UI styles/layout | **KEEP / adapt** — polish only after correct stage/API states are available; current visual layout is not evidence of backend capability. |
| `app/static/app.js` | UI map, controls and API interaction | **PARTIAL** — map existing fields to the agreed five-stage schema; identify simulated, inherited, unavailable and measured values. |
| `app/static/vendor/leaflet/*` | Vendored Leaflet library/assets | **KEEP** — third-party files; avoid unnecessary edits. |
| `app/api/report.py` | Report endpoint and current HTML/optional PDF generation | **PARTIAL** — no verified SHA-256 sealing or PDF/A claim found. Build report from the same canonical analysis payload and validate checksum against downloaded bytes. |
| `app/api/pipeline.py`, `app/pipeline.py` | Pipeline route/orchestration | **PARTIAL** — integration spine; preserve current routes and add stage results/status incrementally. The roadmap’s future/versioned routes are proposed contracts, not current endpoints. |
| `app/api/detect.py`, `drift.py`, `health.py` | Detection, drift and health endpoints | **KEEP / adapt** — existing API surface; document actual route/schema and keep old consumers working during integration. |
| `app/main.py` | FastAPI application setup/static serving | **KEEP** — application entry point. |
| `app/config.py`, `app/hub.py`, `app/jobs/store.py` | Configuration, shared application support and job storage | **KEEP / inspect** — preserve current runtime behavior; avoid replacing infrastructure while integrating stages. |
| `start.bat`, `stop.bat` | Local start/stop helpers | **VERIFY** — operational helpers, not part of analytical acceptance; ensure documentation matches current startup command. |

**Report language:** a SHA-256 hash can detect byte changes relative to a known digest; by itself it does not establish source authenticity, chain-of-custody compliance, causation, guilt, admissibility or detention authority. PDF/A and ISO/IEC 27037 claims require independent validation.

## Cross-cutting files and documentation

| File/path | Current purpose | Recommendation |
|---|---|---|
| `app/main.py`, `app/config.py`, `app/pipeline.py`, `app/scenes.py`, `app/schemas.py` | Application setup, configuration, orchestration, scenes and shared contracts | **KEEP** — these are integration boundaries. Agree response fields before changing them across modules. |
| `app/api/*` | Route handlers | **KEEP / adapt** — existing routes are the compatibility surface; document actual paths separately from roadmap proposals. |
| `app/geo/*` | Raster, CRS, geometry and TIFF helpers | **KEEP** — shared foundation; test transforms and unit/CRS assumptions before new algorithms consume outputs. |
| `app/eo/corroborate.py` | Optional optical corroboration | **OPTIONAL** — separate corroboration signal; do not conflate it with Sentinel-1 oil detection. |
| `app/viz/tiles.py` | Map tile support | **OPTIONAL** — visualization support, not satellite ingestion or analytical evidence. |
| `README.md`, `PROJECT_JOURNAL.md` | Setup/project history | **UPDATE later** — distinguish inherited TideTrace behavior from implemented SentinelTrace stages; include reproducible clean setup and known limits. |
| `docs/ARCHITECTURE.md`, `docs/COMPLIANCE.md` | Existing architecture/compliance notes | **RECONCILE** — compare with five-stage architecture and avoid compliance assertions that have not been verified. |
| `docs/tidetrace-deck.html`, `docs/ps-26143-audit.html`, architecture SVGs | Existing TideTrace-era presentation/audit artifacts | **REUSE selectively** — update only if used in submission; old branding/claims can misrepresent this project. |
| `pyproject.toml`, `requirements.txt`, `requirements-m1.lock` | Packaging and dependencies | **KEEP / verify** — check Python version and optional ML/geospatial/report dependencies against README and actual environment; avoid making optional features hard requirements without need. |
| `.gitignore` | Excludes generated/local data | **KEEP / inspect** — confirm model weights, downloaded data, caches, logs and environment files are handled safely and reproducibly. |
| `data/sar/scenes.json`, `data/` | Scene manifest and local/demo outputs | **VERIFY** — distinguish checked-in fixture metadata from ignored/local imagery, metocean and AIS. Some output references may be machine-specific; do not treat those as portable evidence. |
| `models/` | Model assets/reports | **VERIFY** — record actual checkpoint availability, digest, training data and config. A report without a checkpoint/lineage is not proof of model reproducibility. |

## Scripts, notebooks and tests

### Scripts

| Group | Files/examples | Audit finding/action |
|---|---|---|
| Data acquisition/cache | `scripts/fetch_sentinel1_scene.py`, `fetch_sentinel2_chip.py`, `fetch_basemap.py`, `fetch_land_mask.py`, `fetch_world_land.py`, `build_land_mask.py`, `build_metocean_cache.py`, `fetch_marinecadastre_ais.py`, `fetch_vendor.py`, `build_synthetic_ais.py`, `bootstrap_demo.py` | **KEEP selectively** — classify each source as real, cached, optional or synthetic; log licences, time/space coverage and product type. |
| Model/dataset | `download_zenodo_subset.py`, `inspect_archive.py`, `prepare_tiles.py`, `build_kaggle_kernels.py`, `kaggle_push.py`, `hf_sync.py`, `train_kaggle.ipynb`, `kaggle/` notebooks | **VERIFY** — current Zenodo workflow and Kaggle experiments must remain distinct until source lineage is confirmed. Avoid training/publishing before licence review. |
| M1 diagnostics/demo | `m1_check.py`, `m1_clean_clone_test.py`, `m1_control_points.py`, `m1_demo_drill.py`, `m1_double_run.py`, `m1_doctor.py`, `m1_export.py`, `m1_overlay.py`, `m1_scene_report.py`, `m1_speed_bench.py`, `m1_smoke.py`, `m1_bundle_handover.py` | **KEEP as diagnostics** — useful for evidence, but their existence does not establish the target model, four channels, dataset identity or acceptance. |
| AIS/fixture tooling | `record_ais.py`, `make_selftest_scene.py` | **OPTIONAL / label clearly** — live recording is not necessary for an offline demo; self-test scenes must be identified as fixtures. |

### Existing tests

The repository includes coverage for current advection, AIS gaps/live ingestion/scoring, offline pipeline, geospatial helpers, dataset layout, model smoke/UNet path, vision contract/fallback/georeferencing/cache/status and console DOM. Keep these as regression coverage while adding the target acceptance cases.

**New M3 acceptance coverage:** `tests/test_m3_hindcast.py` checks RK4 forward/backward analytical displacement, step refinement, Stokes units/direction and missing-wave status, hourly minimum-variance selection, KDE polygon output, forcing coverage flags, diffusion variance, wave timestamp alignment and NPZ persistence. With `tests/test_advection.py` and `tests/test_offline_boundary.py`, 24 tests passed. A direct `run_drift` smoke on the cached Golden Case also returned RK4/300 s, zero out-of-coverage evaluations, origin window and the named KDE output. The full detection-to-report test suite remains unverified; prior attempts were stopped during slow integration/model tests. No usable Golden Case wave fields were returned, so real Stokes forcing is not validated.

## Prioritized change suggestions

### P0 — contracts and evidence (do first)

1. Keep a single agreed API analysis contract in `app/schemas.py`; include five stage status/source fields and distinguish measured, simulated, inherited, unavailable and illustrative data.
2. Audit the Kaggle archive, its licence and labels before connecting it to `app/ml/dataset.py`; record model/checkpoint lineage. Keep the Zenodo baseline attributed separately.
3. Select one documented Golden Case and inventory the files/metadata required by each stage. Mark synthetic and cached inputs visibly.
4. Preserve existing routes and UI. Integrate stage results incrementally rather than replacing the pipeline.

### P1 — target analytics by stage

1. M2: add/test calibration semantics, incidence normalization, matched wind gate and CA-CFAR with reported retention.
2. M1: add linear-power four-channel derivation and sinuosity; compare the target model with the existing baseline using valid splits and georeferenced outputs.
3. M3: acquire supported wave fields for the Golden Case and compare hindcasts on real forcing; calibrate the KDE region before making probabilistic accuracy claims.
4. M4: add H3 with equivalence checks; add dark-target status only with suitable radar evidence; implement assumption-labelled volume/flow ranges.

### P2 — presentation and reporting

1. M5: display stage status/provenance and preserve all working console controls.
2. M4/M5: use one report payload; add reproducible SHA-256 calculation and independent verification.
3. Claim PDF/A only after a validator confirms the chosen conformance level. Keep legal/causation language qualified.
4. Update setup/demo/model/data/limitations documentation after behavior is verified.

## Claims to keep out of demo/report until evidenced

- That the Kaggle dataset has the required channels, labels, georeferencing, licence or class balance.
- That the running model is a fine-tuned ResNet-34 U-Net trained on Kaggle, or that it distinguishes mineral from biogenic slicks.
- That ingestion performs GRD sigma-zero calibration, swath normalization, 3–12 m/s gating or CA-CFAR.
- That drift uses RK4 at five-minute steps, Stokes drift, or a validated 95% origin KDE.
- That H3, radar dark-vessel detection, pump rate, or deterministic exoneration is implemented.
- That a checksum proves authenticity, a report is PDF/A or ISO/IEC 27037 compliant, or the tool proves guilt/causation or orders detention.

## Suggested audit sequence for the team

1. M2 + M1: inspect actual selected SAR scene and Kaggle samples; agree data/units/labels before model integration.
2. All owners: freeze the shared schema and Golden Case; attach source/status to every output.
3. Each module owner: implement only the stage gap in their interface and supply the corresponding acceptance evidence.
4. M5 + M4: wire the same payload into the console and dossier; verify download/hash.
5. Team: use the roadmap tracker’s `Inherited / unverified` state until acceptance evidence exists; record unavailable features honestly.

---

**Scope note:** This audit is based on the checked-out repository structure and code review context. It is not a fresh execution/benchmark, dataset licence determination, model evaluation, legal opinion or compliance certification. No application code was changed for this audit.
