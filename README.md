# SentinelTrace

SentinelTrace is a maritime pollution investigation prototype. It brings satellite radar imagery, environmental drift estimates, and available vessel AIS tracks into one review workflow. Its outputs are investigative leads: a dark SAR feature is not proof of oil, a reconstructed corridor is not a known release point, and a vessel ranking is not a finding of causation or guilt.

This repository is adapted from an existing TideTrace application. The five-stage SentinelTrace design is described in [`SentinelTrace_Team_Roadmap.md`](SentinelTrace_Team_Roadmap.md); the implementation remains mixed: some stages are connected to the application, some are partial or inherited, and some target capabilities are not present. This README labels those differences instead of treating the roadmap as proof of implementation.

## What the system does

The current application is a local FastAPI service with a static browser interface. Its main analysis path reads a registered SAR scene, screens scene metadata, detects and characterizes dark-water features, estimates drift from metocean fields, queries and scores available AIS tracks, saves a job record, and exposes results and a report through the API. Optional inputs and dependencies affect which results are available. The API and UI report some missing-data and fallback states.

The project roadmap organizes the intended product into five stages:

| Stage | Intended responsibility | Repository implementation and status |
|---|---|---|
| M2 — SAR ingestion and screening | The roadmap targets calibrated Sentinel-1 ingestion, incidence-angle normalization in linear sigma-zero space, matched ERA5 10 m wind gating (proposed 3–12 m/s), and a 100 m CA-CFAR candidate pyramid (proposed guard 4, training 16, provisional −3.5 dB threshold). | `app/stage1.py` is called by `app/pipeline.py` and reports stage status, wind-gate and candidate-window information. The roadmap parameters are validation targets; their scientific suitability, complete product calibration, and claimed pixel-reduction performance are not established by their presence in code. |
| M1 — Slick segmentation and mapping | The roadmap targets `[VV, VH, Span, Rvv/vh]` input channels, with Span and ratio computed from linear power, segmentation, a sinuosity feature and georeferenced GeoJSON polygons. | `app/ml/`, `app/geo/`, and `app/vision/` contain dataset, inference, fallback, geometry and adapter code. The application pipeline uses detection and georeferenced polygon processing. Do not attribute the roadmap's proposed ResNet-34 U-Net, dataset metrics, or four-channel model to the active detector without matching checkpoint and evaluation evidence. |
| M3 — Drift hindcast and forecast | The roadmap specifies backward RK4 at 300-second steps up to 18 hours; current + windage and Stokes only when matched wave forcing exists; an origin window and uncertainty geometry with provenance. | `app/drift/` is connected to the pipeline. The backward path uses RK4 at 300-second steps, capped at 18 hours; the forward forecast uses RK2. Stokes drift is conditional on usable wave fields. The approximate 95% KDE region is uncalibrated; `spread_km` is a separate 90th-percentile ensemble radius. The checksum-pinned NORSE2019 adapter is an explicit profile and does not establish browser-to-backend or normal-UI operation. |
| M4 — AIS and forensic evidence | The roadmap targets H3 resolution 7 as a spatial prefilter, trajectory/AIS evidence, optional radar-target comparison, and assumption-bounded volume/flow ranges. | `app/ais/` and `app/api/` implement AIS ingestion/querying, reconstruction, filtering, scoring, reachability and mass-balance calculations. H3 is optional. SAR vessel-target comparison is explicitly unavailable in the current implementation. Actual candidate results depend on locally available AIS data, geographic/time coverage and provenance. |
| M5 — Dashboard and dossier | The roadmap calls for presenting status, evidence, caveats and provenance in a dashboard and downloadable dossier, with integrity verification. | `app/static/` provides the browser UI; `app/api/report.py` provides HTML and PDF reports (PDF requires ReportLab) and a SHA-256 endpoint. A digest detects byte changes against a known digest; it does not establish authenticity, legal admissibility or chain of custody. |

These descriptions summarize code paths and the project roadmap. They do not certify scientific accuracy, operational readiness, or full end-to-end behavior on a particular machine.

## User workflow

1. Start the local application and open the landing page at `http://127.0.0.1:8000/`.
2. Open the operations console at `http://127.0.0.1:8000/console`.
3. Select an indexed scene and review its availability, source and coverage information.
4. Run analysis. The UI submits a request to the local API and displays the resulting detection, drift and AIS outputs that are available for that scene.
5. Inspect the job, map layers, candidate explanations and warnings. Missing or synthetic inputs limit what can be concluded.
6. Open the HTML report or request a PDF when the optional PDF dependency is installed; retrieve the PDF digest from the corresponding SHA-256 endpoint.

The default configuration is offline. Network-backed acquisition and synchronization utilities are under `scripts/`; they are separate from the ordinary application request path. Do not treat a cached or synthetic result as newly acquired real-world evidence.

## Architecture

```text
Browser: app/static/landing.html and index.html
                 | same-origin HTTP
                 v
FastAPI app.main
  ├── app/api/health.py       health, runtime and data status
  ├── app/api/detect.py       scene list, detection and upload routes
  ├── app/api/drift.py        standalone drift route
  ├── app/api/ais.py          AIS query, scoring and track routes
  ├── app/api/pipeline.py     analysis runs, jobs and progress
  ├── app/api/stage4.py       structured attribution response
  └── app/api/report.py       HTML/PDF report and SHA-256 digest
                 |
                 v
app/pipeline.py orchestrates scene loading, Stage 1 screening,
detection/geometry, drift, optical corroboration and AIS attribution
                 |
                 v
data/ — local scene index and optional SAR, AIS, metocean, job and cache data
```

The browser assets are served from `app/static/`. `GET /` serves `landing.html`; `GET /console` serves the dashboard shell in `index.html`. API routes are registered in `app/main.py` through routers in `app/api/`. The service binds to loopback in the documented startup commands.

### Main subsystems

| Subsystem | Key files | Inputs and outputs | Dependencies and caveats |
|---|---|---|---|
| Application and configuration | `app/main.py`, `app/config.py`, `app/schemas.py` | HTTP requests, runtime configuration, validated request/response models. | FastAPI, Uvicorn, Pydantic. Configuration reads `TIDETRACE_*` environment variables for legacy compatibility. |
| Scenes and SAR screening | `app/scenes.py`, `app/stage1.py`, `app/geo/raster.py`, `app/geo/tiffio.py`, `app/geo/crs.py` | Scene index and raster files; scene metadata and screen status. | Rasterio and PyProj are recommended; built-in paths exist. A scene can be indexed while its raster file is absent. |
| Detection and vision | `app/ml/`, `app/vision/`, `app/geo/geometry.py` | SAR raster and optional model checkpoint; masks, feature measurements and georeferenced polygons. | The model path is optional; fallback behavior exists. Training/data utilities are separate from the request path. The `app/vision/` contract/adapter and main inference path should not be assumed to be identical. |
| Drift | `app/drift/fields.py`, `advection.py`, `cone.py`, `land.py` | Cached or synthetic metocean fields, detection location/time and run parameters; hindcast/forecast tracks and uncertainty geometry. | SciPy and PyProj are recommended. Missing forcing may produce explicitly synthetic default fields; the explicit NORSE2019 profile uses a fail-closed adapter. Wave/Stokes forcing is only available when compatible wave data exists. |
| AIS | `app/ais/ingest.py`, `interpolate.py`, `filter.py`, `score.py`, `reachability.py`, `h3_index.py`, `stage4.py`, `massbalance.py` | Locally stored AIS records and estimated origin/time; tracks, candidate scores and evidence details. | SQLite is built in. H3 is optional. Simulated and real sources must remain distinguishable; a track gap is not proof of intent. |
| Optical corroboration | `app/eo/corroborate.py` | Local scene-associated optical imagery and detected polygons; corroboration status. | Optional evidence only; it does not replace SAR detection. |
| Jobs and visualization | `app/jobs/store.py`, `app/viz/tiles.py`, `app/static/` | Analysis outputs and map requests; persisted job documents, overlays and browser display. | Job data is stored under the configured local data directory. |
| Reports and external-data utilities | `app/api/report.py`, `app/hub.py`, `scripts/` | Completed job, report metadata, or explicitly requested data/model synchronization; HTML/PDF/hash or local prepared data. | PDF generation needs ReportLab. Downloading, syncing or training may require network access and credentials; these are not required for the local default path. |

## API overview

The API is same-origin with the browser application. The principal routes are:

| Method | Route | Purpose |
|---|---|---|
| `GET` | `/api/health` | Application, model, scene, AIS and metocean status. |
| `GET` | `/api/config` | Effective runtime configuration and scoring explanation. |
| `GET` | `/api/scenes` | Indexed scenes and per-scene availability metadata. |
| `POST` | `/api/detect` | Detect features in a registered scene. |
| `POST` | `/api/detect/upload` | Submit an uploaded raster where supported georeferencing is present. |
| `POST` | `/api/run` | Run the end-to-end analysis for a registered scene. |
| `GET` | `/api/jobs`, `/api/jobs/{job_id}` | List and retrieve saved jobs. |
| `GET` | `/api/jobs/{job_id}/progress` | Read the current job progress status. |
| `GET` | `/api/jobs/{job_id}/geojson` | Export mapped job layers as a GeoJSON feature collection. |
| `POST` | `/api/drift` | Run the standalone drift endpoint. |
| `POST` | `/api/attribute` | Run the standalone AIS attribution endpoint. |
| `GET` | `/api/ais/*`, `/api/scoring` | Inspect AIS tracks/windows and scoring details. |
| `GET` | `/api/v1/attribution/{job_id}` | Retrieve the structured Stage 4 attribution view. |
| `GET` | `/api/report/{job_id}` | View an HTML report. `/pdf` and `/sha256` provide PDF and digest when available. |

For authoritative request and response shapes, use `app/schemas.py` and the route implementations in `app/api/`. The roadmap's proposed JSON contracts are design references, not a substitute for the current API schemas.

## Setup

### Requirements

- Python 3.11 or newer.
- Runtime dependencies from `requirements.txt` (or the project metadata in `pyproject.toml`).
- Optional scene, model, AIS and metocean data, depending on the workflow.

The repository supports optional dependency paths. `scipy`, `pyproj` and `rasterio` are recommended for performance/geospatial handling; `h3` enables the Stage 4 spatial prefilter; `reportlab` enables PDF reports. PyTorch and the training packages are for model training or the optional checkpoint path, not required by the minimal dependency list. Exact behavior depends on which optional packages are installed.

### Windows

From the repository directory, create and activate a virtual environment, install the dependencies, then start the local server:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/console` for the dashboard. Alternatively, `start.bat` launches the same `app.main:app` service and opens the site; it uses an existing `venv` or `.venv` when present. If port 8000 is already occupied, identify the existing service before starting another server. `stop.bat` is the paired Windows helper.

### macOS and Linux

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Data and configuration

`data/sar/scenes.json` is the scene index. Raster files, AIS SQLite data, metocean caches, jobs, reports and generated overlays live beneath the configured data directory. The default is the repository's `data/` directory. The `TIDETRACE_DATA` and `TIDETRACE_MODELS` settings can redirect data and model paths. Other runtime settings are defined and defaulted in `app/config.py`; the effective configuration is exposed by `/api/config`. Do not place credentials in committed configuration or logs.

Some registered scenes require raster files that are not included in a checkout. The API reports a missing raster rather than manufacturing the source image. Use a supported, licensed data preparation workflow in `scripts/` only when you intend to acquire or create local data. This repository does not claim that every indexed scene is locally runnable.

## Testing and validation

Pytest is configured in `pyproject.toml` with tests under `tests/`; markers distinguish `synthetic_data` and `real_data`. The existing suite includes coverage for detection/vision, geospatial handling, AIS, drift, Stage 1, reports, offline behavior, API/pipeline integration, and browser E2E. Browser tests are in `tests/e2e/` and use Playwright. This README does not claim that any test was run or passed.

The GitHub Actions workflow at `.github/workflows/ci.yml` currently installs Python 3.11 dependencies, checks dependency consistency and Python compilation, runs selected M3 unit and integration tests, installs Chromium, runs browser E2E, and records an informational M3 performance smoke measurement. It is scoped and is not a complete validation of all subsystems or of the whole product. Check the workflow file for the exact commands and triggers.

Useful commands when you are ready to validate locally:

```bash
python -m pip check
python -m compileall -q app scripts
python -m pytest -q
```

These commands are documentation only; no test or application command was executed as part of this README update.

## Repository map

```text
app/
  api/       FastAPI route modules
  ais/       AIS storage, reconstruction, filtering, scoring and Stage 4
  drift/     Metocean sampling, particle advection and uncertainty regions
  eo/        Optional optical corroboration
  geo/       Raster IO, projections and geometry
  jobs/      Job persistence and progress traces
  ml/        Dataset handling, model, inference, training and fallback
  static/    Landing page, dashboard, styles and browser scripts
  vision/    Vision output schema, prediction adapter and cache
  main.py    FastAPI app, route mounting and static page routes
  pipeline.py End-to-end analysis orchestration
  scenes.py  Scene metadata and local availability
  stage1.py  Scene screening and Stage 1 report
data/        Scene index and optional local inputs/outputs
docs/        Architecture, compliance, stage handoffs and UI notes
models/      Checkpoint metadata and reports; weights may be external/ignored
scripts/     Data preparation, diagnostics, training and handoff tools
tests/       Unit, integration, data-dependent and E2E test definitions
benchmarks/  M3 benchmark/smoke utility
```

## Known limits and interpretation

- The application and its Python package/configuration retain the legacy `tidetrace` identifier. SentinelTrace is the project-facing name used by this README and the team roadmap; the legacy identifier has not been renamed throughout the codebase.
- The five-stage roadmap includes target methods such as the four-channel `[VV, VH, Span, Rvv/vh]` model, a calibrated origin uncertainty method, dark-target comparison and a provenance dossier. Their appearance in the roadmap does not establish that each is implemented or validated in the application.
- The active drift implementation and the roadmap's target description are not identical in all respects. The current backward solver is RK4 and the forecast remains RK2; Stokes is conditional on wave forcing. The NORSE2019 adapter is a distinct explicit profile, not the default UI workflow.
- The approximate 95% KDE highest-density polygon is not empirically calibrated. `spread_km` is a separate 90th-percentile ensemble distance statistic. Neither is a guarantee of release-location coverage.
- Synthetic forcing or simulated AIS is not real observation data. Read each run's source, warnings and availability status before interpreting results.
- AIS scores rank track consistency under stated features and assumptions. They are not probabilities of guilt. Missing AIS broadcasts do not establish intentional disabling.
- Slick area alone does not determine spill volume, source vessel or discharge rate. Mass-balance output depends on assumptions and can contain unavailable values.
- A SHA-256 digest can detect whether report bytes changed relative to a known digest; it does not prove authenticity or legal admissibility. No legal or enforcement conclusion is produced by this prototype.
- Real-data availability is checkout- and scene-specific. Raster files, local AIS records, metocean cache coverage, checkpoints and optional packages must be checked on the machine running the app.

## Project references

- [SentinelTrace team roadmap](SentinelTrace_Team_Roadmap.md) — intended architecture, stage methods, contracts and project plan.
- [Repository audit](SentinelTrace_Repository_Audit.md) — repository-specific engineering findings.
- [Architecture notes](docs/ARCHITECTURE.md) — inherited application architecture.
- [Compliance mapping](docs/COMPLIANCE.md) — implementation mapping and caveats; verify status against code and current local data.
- [M2/Stage 1 handoff](docs/README_STAGE1_M2.md)
- [M4/Stage 4 handoff](docs/M4_STAGE4.md)
- [Dashboard notes](docs/SENTINELTRACE_UI.md)
- [Benchmark notes](benchmarks/README.md)

## Responsible use

Use the system to organize and inspect evidence, not to accuse or exonerate a vessel. Preserve source provenance, data status, assumptions and uncertainty in any analysis shared with others. A qualified analyst must independently review the underlying imagery, environmental forcing, AIS coverage and calculation assumptions before drawing operational conclusions.
