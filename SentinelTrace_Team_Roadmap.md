# SentinelTrace — Team Engineering Roadmap
**PCCOE International Grand Challenge: Indradhanu 2026**  
**Theme:** AI for Climate Change  
**Team:** Monarchs-of-Eden — 5 members  
**Working window:** 19 October–10 November 2026  
**Submission deliverable:** A working prototype demonstrated in a **3–8 minute YouTube video**, submitted through the participant dashboard by **10 November 2026**.

> **Status of this document:** This is the team's working plan, based on the supplied *SentinelTrace Maritime Forensics Architecture Review* PDF and the supplied *Track A Roadmap.md* as the detail/format reference. The project website link has not yet been supplied; add it in Section 2 when available. Names/roles below follow the role mapping in the supplied SentinelTrace PDF; change the names if the current team roster differs.

---

## Table of contents

1. [Read this first: the project in simple words](#1-read-this-first-the-project-in-simple-words)
2. [Project links and website](#2-project-links-and-website)
3. [What we can realistically finish by 10 November](#3-what-we-can-realistically-finish-by-10-november)
4. [System architecture and end-to-end flow](#4-system-architecture-and-end-to-end-flow)
5. [Repositories, datasets, APIs and tools to reuse](#5-repositories-datasets-apis-and-tools-to-reuse)
6. [Scope decisions: must-have vs stretch](#6-scope-decisions-must-have-vs-stretch)
7. [Repository structure and ownership](#7-repository-structure-and-ownership)
8. [Integration contracts: how members' code connects](#8-integration-contracts-how-members-code-connects)
9. [Exact five-person work division](#9-exact-five-person-work-division)
10. [Daily roadmap: 19 October–10 November](#10-daily-roadmap-19-october10-november)
11. [Development setup and Git workflow](#11-development-setup-and-git-workflow)
12. [Testing and acceptance criteria](#12-testing-and-acceptance-criteria)
13. [Demo scenario and video plan](#13-demo-scenario-and-video-plan)
14. [Risks, fallbacks and claims we must not overstate](#14-risks-fallbacks-and-claims-we-must-not-overstate)
15. [Team progress tracker](#15-team-progress-tracker)
16. [Final submission checklist](#16-final-submission-checklist)
17. [Questions to resolve when the project website is shared](#17-questions-to-resolve-when-the-project-website-is-shared)

---

## 1. Read this first: the project in simple words

### 1.1 The idea

SentinelTrace is a maritime pollution investigation dashboard. A satellite radar image can contain a dark patch that might be an oil slick, but dark patches can also be caused by calm water or natural films. The prototype will take a selected historical satellite image, identify a possible slick, display its mapped location, estimate how wind and currents could have moved it, compare the estimated origin/time window with historical ship AIS tracks, and show a ranked list of **candidate vessels** with the evidence and uncertainty visible.

### 1.2 The whole project in one paragraph for the team

**SentinelTrace is planned as a five-stage maritime investigation prototype. M2 validates and gates a georeferenced Sentinel-1 SAR scene using matched wind data, swath normalization and candidate screening. M1 creates a four-channel polarimetric segmentation and georeferenced slick polygons. M3 hindcasts currents, wind and wave Stokes drift to estimate an uncertain origin corridor. M4 compares AIS tracks and radar targets, then reports candidate-vessel kinematics and an assumption-bounded mass-balance estimate. M5 presents the evidence and provenance in a dashboard and a hashed report. Each stage must label missing, simulated and measured inputs. Rankings and reports are investigation aids; they do not independently prove causation, guilt, legal admissibility or authority to detain a vessel.**

### 1.3 What each technical term means

| Term | Plain-language meaning | Where we use it |
|---|---|---|
| SAR | Satellite radar imagery; unlike ordinary photos, it can image at night and through many cloud conditions | Input image |
| Sentinel-1 | Earth-observation satellite mission that supplies SAR scenes | Historical scene source |
| Segmentation model | AI that labels each pixel, not just the whole image | Potential oil-slick mask |
| Ground-truth mask | A human-labelled answer image used to teach/check the model | Training dataset |
| GeoTIFF / georeferencing | An image file with information linking pixels to real map coordinates | Convert pixels to map locations |
| GeoJSON polygon | A standard file format for a shape on a map | Slick outline and origin region |
| ERA5 | Historical weather reanalysis, including surface wind | Wind input |
| CMEMS | Copernicus Marine ocean products, including current fields | Current input, when suitable data is available |
| AIS | Ship identification/location/speed/heading broadcasts | Historical ship-track comparison |
| Backtracking / hindcast | Estimate earlier positions from a later observation and environmental conditions | Origin corridor |
| H3 | A global grid system for indexing locations | Stage 4 spatial indexing; use it where it improves the agreed AIS/radar query |
| Candidate attribution | Ranking vessels whose tracks are consistent with a scenario | Dashboard output; not proof of guilt |
| SHA-256 | A checksum that can reveal whether a file changed | Integrity check for the exported report |

### 1.4 User journey

1. The user opens the SentinelTrace dashboard.
2. The user loads the built-in **Golden Case** demo scenario or selects a supported historical scene.
3. The app displays the satellite image and the detected/annotated slick polygon.
4. The app shows the scene timestamp, area of interest and wind/current-data status.
5. The app runs the drift-estimation step (real model where configured; otherwise an explicitly labelled demonstration/synthetic result).
6. The map shows the estimated origin corridor and historical AIS tracks.
7. The system joins AIS tracks and supported radar targets, then explains candidate reachability, track gaps and mass-balance assumptions.
8. The user opens a candidate to inspect its observations, uncertainty, calculated pump-rate range and caveats; unavailable values remain unavailable.
9. The user downloads a provenance dossier and verifies its SHA-256 checksum. A checksum is an integrity check, not proof of authenticity or legal admissibility.

---

## 2. Project links and website

### 2.1 Official project/competition website

- **Project website / challenge page:** `TO ADD — awaiting the website link from the team`
- **Submission platform/dashboard:** `TO ADD — paste the exact participant dashboard URL and submission instructions`
- **Required video:** YouTube link, 3–8 minutes, submitted through the participant dashboard by 10 November 2026.

When the website link is received, verify the official problem statement, required sponsor/tool integration, judging rubric, report/template rules, and whether any additional deliverable is mandatory. If it conflicts with this working roadmap, the official competition instructions take precedence.

### 2.2 Team repository and code base

- **Current base repository:** https://github.com/S-T-A-RNalin1/tidetrace
- **Team-owned SentinelTrace repository:** confirm whether this is a fork, branch or separate repository before submission.
- The current checkout is organized as TideTrace (`app/`, `data/`, `scripts/`, `tests/`); this roadmap maps the five SentinelTrace stages onto it without requiring a wholesale restructure.
- Keep data licences, provenance and model lineage with the code. Do **not** commit credentials, private AIS, or large data/weight files unless redistribution is permitted and the repository plan supports them.

---

## 3. What we can realistically finish by 10 November

The window from 19 October to 10 November is only 23 calendar dates inclusive. We must build a **vertical slice** that works from input to visible output, not five disconnected research projects.

### 3.1 Recommended MVP (minimum viable prototype)

The prototype counts as a useful MVP when all of these work on one laptop:

- [ ] A documented historical Sentinel-1 SAR scene or labelled demo raster loads reliably.
- [ ] The image's timestamp and map projection/transform are read correctly.
- [ ] Stage 1 reports calibration, incidence-angle, wind-gate and CFAR status; any unavailable operation is explicit.
- [ ] Stage 2 reports the model, four input channels, training dataset/split, segmentation result and any baseline fallback.
- [ ] A slick polygon is displayed in a map with coordinates.
- [ ] Stage 3 reports RK4 hindcast settings, current/wind/wave sources, origin-window method and uncertainty; unavailable forcing is not presented as measured.
- [ ] Stage 4 shows H3/trajectory filtering, available AIS and radar-target evidence, and a mass-balance range with its assumptions.
- [ ] Candidate vessels are ranked by documented evidence; no automated guilt verdict or deterministic exoneration is issued.
- [ ] The user can download a provenance dossier with inputs, assumptions, uncertainty and a verifiable SHA-256 checksum. PDF/A and standards-compliance claims require separate verification.
- [ ] A fresh clone can run by following the README.
- [ ] A 3–8 minute demo video is recorded, uploaded to YouTube and checked in a private/incognito window.

### 3.2 Preserve the five stages; integrate them in risk order

The five stages are the planned product, not disposable ideas. Implement and connect them incrementally so the existing TideTrace pipeline remains a usable baseline while each replacement or extension is measured. Do not silently remove a stage to meet a date: show `implemented`, `fallback`, `unavailable` or `illustrative` status in the API and UI.

**Build in this order:**

1. Freeze the inter-stage JSON contract and select a reproducible Golden Case.
2. Audit the Kaggle training dataset and create a sample loader before changing the model.
3. Connect existing raster/metadata code to Stage 1 status and add calibration, wind gate and CFAR behind tested interfaces.
4. Keep current segmentation inference available while validating the four-channel model and polygon handoff.
5. Add RK4/Stokes hindcasting behind the drift interface and compare it with the existing solver on known fields.
6. Extend AIS ranking with H3, radar-target availability and an assumption-labelled mass-balance result.
7. Add dossier hashing/PDF-A only after the report inputs and provenance contract are stable.
8. Rehearse the full flow; show every unavailable or illustrative feature honestly.

### 3.3 Recommended prototype mode

Use **historical/offline replay**, not a claim of live satellite streaming. Sentinel-1 is an orbital satellite mission with discrete acquisitions, not a live video camera. Cache the exact demo inputs before the presentation so the demo does not fail because an external API is down.

---

## 4. System architecture and end-to-end flow

```text
Sentinel-1 SAR GRD + acquisition metadata + matched ERA5/CMEMS fields
              |
              v
STAGE 1 / M2  Calibrate + incidence-angle normalize + wind gate + CA-CFAR pyramid
              |     Output: validated scene, wind/gate status, candidate windows
              v
STAGE 2 / M1  [VV, VH, Span, Rvv/vh] segmentation + sinuosity feature + vectorization
              |     Output: slick GeoJSON, geometry, model/data provenance
              v
STAGE 3 / M3  Backward RK4, dt=-300 s, up to 18 h, current + wind + Stokes
              |     Output: origin time window, 95% KDE uncertainty geometry
              v
STAGE 4 / M4  H3 trajectory filter + AIS/radar dark-target comparison
              |     Output: candidate evidence + assumption-bounded volume/flow range
              v
STAGE 5 / M5  Leaflet console + provenance dossier + SHA-256 verification
                    Output: explainable investigative lead, never an automatic verdict
```

### 4.1 Module responsibilities

| Stage/module | Input | Required output | Primary owner |
|---|---|---|---|
| 1. Ingestion and gating | Sentinel-1 GRD, incidence angle, acquisition time, matched wind | Calibrated/normalized scene, 3–12 m/s gate status, CA-CFAR candidate windows, provenance | M2 Ruchira |
| 2. Polarimetric segmentation | VV/VH plus derived Span and VV/VH ratio | Oil mask, sinuosity feature, GeoJSON polygons, model/dataset metadata | M1 Radhika; M2 reviews georeferencing |
| 3. Hydrodynamic hindcast | Slick polygon/time, CMEMS currents, ERA5 wind, wave inputs if available | RK4 backward track, selected origin window, 95% KDE uncertainty geometry and forcing provenance | M3 Prem |
| 4. Kinematic/mass-balance forensics | Origin bounds/time, AIS, supported SAR target observations, slick geometry | H3/trajectory filter, candidate evidence, dark-target status, volume/flow ranges and assumptions | M4 Ruchika |
| 5. Dashboard/dossier | Stage outputs and provenance contract | Leaflet views, explicit status/caveats, downloadable dossier and verified hash | M5 Akhilesh |
| Shared API/integration | Versioned stage contracts | One stable request/response path that joins all five stages | M4 Ruchika + M5 Akhilesh |
| Demo/docs | Reproducible end-to-end flow | Golden Case, setup guide, report, video and submission evidence | M5 Akhilesh; all members contribute |

### 4.2 Target algorithm settings and validation notes

These are project targets, not claims that the current repository already implements or validates them:

- **M2 calibration and screening:** Normalize incidence angle in linear sigma-zero space before converting to dB. Define the expected units and sign for every threshold. Apply the 3–12 m/s wind gate to matched 10 m wind and record the gate result. The proposed 100 m CA-CFAR pyramid uses guard width 4, training width 16 and a provisional -3.5 dB damping threshold; benchmark it on the selected scenes before calling the >95% pixel reduction an achieved result.
- **M1 polarimetry:** Compute `Span = VV + 2*VH` and `Rvv/vh = VV/VH` from linear power values, not by adding/dividing dB values. Build the model input in the documented `[VV, VH, Span, Rvv/vh]` order. The proposed ResNet-34 U-Net and sinuosity cutoffs are hypotheses to validate against the selected dataset; do not hard-code them as universal labels without held-out evaluation.
- **M3 hindcast:** Target RK4 with `dt = -300 s` and a maximum 18-hour window. Include `current + alpha*wind + Stokes` only when each forcing field is available and time/space matched. Record the wave variables and units used by the Stokes calculation. Define how the minimum-variance origin time and the 95% KDE region are calculated and tested.
- **M4 forensics:** H3 resolution 7 is a planned spatial index, not an accuracy claim. Radar dark-target evidence is only available when the source imagery can resolve and validate a target. Compute slick-volume and flow-rate ranges only with explicit thickness, loiter-time and uncertainty assumptions; the example pump capacities and exoneration thresholds in the architecture notes remain provisional until sourced and tested.
- **M5 dossier:** The report must preserve source, model, forcing, AIS/radar, assumptions and generated-file hashes. A SHA-256 checksum detects byte changes; it does not establish evidence authenticity. Do not claim PDF/A conformance, ISO/IEC 27037 compliance, causation, guilt or authority to detain without a separately validated process.

### 4.3 Important data rule

The pixel model needs labelled images to learn visual patterns. Geographic coordinates are not inherently required for the model to classify a cropped image, but **they are required for mapping a detection back onto Earth**. Therefore, keep these separate:

- **Training:** labelled image tiles and masks.
- **Mapping/inference:** an image with known georeferencing, acquisition time and CRS.
- **Attribution:** environmental data and historical AIS covering compatible times and locations.

A model trained on cropped PNG tiles cannot by itself invent reliable latitude/longitude. The georeferencing must come from the source scene or an explicitly documented alignment step.

---

## 5. Repositories, datasets, APIs and tools to reuse

**Do not clone every repository and merge them together.** Select one main vision implementation, then use maintained libraries for the other modules. Reuse is about reading/adapting the necessary code under its licence, not copying an entire codebase blindly.

The links below are the candidates referenced by the supplied architecture notes and common upstream project pages. Before adopting code or data, inspect the current README, licence, last meaningful update, supported versions, dependencies, and whether the exact files match our required input format.

### 5.1 High-priority: use these first

| Priority | Project / resource | Link | What we use it for | Owner | Decision |
|---|---|---|---|---|---|
| P0 | Sentinel-1 SAR Oil Spill Detection Dataset (Kaggle, harikrishnacs) | https://www.kaggle.com/datasets/harikrishnacs/sentinel-1-sar-oil-spill-detection-dataset | Intended M1 training source; inspect actual files, masks, channels, licence, georeferencing and provenance before training | M1 | Proposed primary source; **audit pending**. Do not attribute existing Zenodo metrics to it |
| P1 | Marine SAR Oil Spill Detection Dataset (Krestenitis et al.) | https://zenodo.org/records/3358370 | Existing TideTrace training path / comparison candidate; inspect class labels, split, licence and metadata | M1 | Keep as a separate source unless the team explicitly selects it |
| P0 | Oil Spill Detection in SAR Images | https://github.com/d-elicio/Oil-Spill-Detection-in-SAR-images | Candidate starting point for dataset loader, train/validation split and segmentation implementation | M1 | Inspect before adapting; do not assume it is plug-and-play |
| P0 | PyTorch | https://github.com/pytorch/pytorch | Model training and inference | M1 | Use |
| P0 | segmentation-models.pytorch | https://github.com/qubvel/segmentation_models.pytorch | U-Net/DeepLab-style segmentation architectures and encoders | M1 | Use only after confirming channel count and label mapping |
| P0 | Rasterio | https://github.com/rasterio/rasterio | Read georeferenced rasters, affine transforms and write outputs | M1 + M2 | Use |
| P0 | Shapely | https://github.com/shapely/shapely | Clean polygons, geometry operations and area/buffer calculations | M1 + M2 | Use |
| P0 | FastAPI | https://github.com/fastapi/fastapi | Connect the analysis pipeline to the web UI | M4 | Use |
| P0 | Leaflet | https://github.com/Leaflet/Leaflet | Interactive map and GeoJSON/AIS layers | M5 | Use; simplest path for a short deadline |
| P0 | WeasyPrint | https://github.com/Kozea/WeasyPrint | Turn a controlled HTML template into a downloadable PDF report | M4 + M5 | Use if install works on team OS |

### 5.2 Important data sources

For the selected Kaggle dataset, record the exact version/date, licence text, source citation, folder/file inventory, label encodings, sensor/band units, scene identifiers and whether chips carry georeferencing. Confirm that train/validation/test splits are scene- or acquisition-separated where possible. The Kaggle listing did not provide a readable file/metadata view during this roadmap update, so these details remain an M1 audit task rather than assumed facts.

| Resource | Link | Data/use | Practical warning |
|---|---|---|---|
| Sentinel-1 via Google Earth Engine | https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S1_GRD | Search/query SAR scenes and metadata | Requires account/project setup and correct access; cache the demo scene |
| Earth Engine Python API | https://github.com/google/earthengine-api | Programmatic access to Earth Engine | Authentication and project configuration may take time |
| geemap | https://github.com/gee-community/geemap | Helpers for Earth Engine and geospatial workflows | Optional; do not add if the direct API is enough |
| NOAA Marine Cadastre AIS | https://marinecadastre.gov/accessais/ | Historical AIS data, especially for US waters/coverage | Coverage and availability vary by region/date; confirm the exact required period |
| Danish Maritime Authority AIS | https://www.dma.dk/safety-at-sea/navigational-information/ais-data | Historical AIS files | Check coverage, format, terms and timestamps |
| Copernicus Marine Service | https://marine.copernicus.eu/ | Marine currents and ocean data | Product access, time resolution and spatial coverage must match the case |
| ERA5 / Climate Data Store | https://cds.climate.copernicus.eu/ | Historical surface wind fields | Account/access and download/API setup may be required |
| NetCDF4 | https://github.com/Unidata/netcdf4-python | Read environmental grids in NetCDF format | Optional until we have a real grid file |
| xarray | https://github.com/pydata/xarray | Work with gridded wind/current data | Optional for the first demo if using pre-extracted arrays |

### 5.3 Optional advanced components

| Resource | Link | When to use it | MVP recommendation |
|---|---|---|---|
| OpenDrift | https://github.com/OpenDrift/opendrift | Particle drift simulations with environmental forcing | Add after a simple, testable drift interface exists |
| H3 Python | https://github.com/uber/h3-py | Stage 4 spatial indexing for AIS/radar candidates | Planned target; compare with the existing direct filter and document the selected resolution |
| CA-CFAR reference implementation | Select and record an upstream source after licence review | Stage 1 clutter screening | Do not copy a full repository; implement/adapt the smallest tested windowed screener that meets the agreed contract |
| GDAL | https://gdal.org/ | Advanced raster conversion/projection utilities | Use if Rasterio alone cannot do the required conversion |
| GeoPandas | https://github.com/geopandas/geopandas | Tabular geospatial analysis | Optional; use Shapely/Rasterio if sufficient |
| Uvicorn | https://github.com/encode/uvicorn | Run FastAPI locally | Use with FastAPI |
| Pydantic | https://github.com/pydantic/pydantic | Validate API request/response data | Use |
| pytest | https://github.com/pytest-dev/pytest | Automated tests | Use from the first week |
| Python h3 docs | https://uber.github.io/h3-py/ | H3 API reference | Use if H3 is selected |

### 5.4 Optional foundation model path

The source discussion mentions NASA-IBM Prithvi EO and DOFA. Treat these as **stretch options**, not the required starting point. They may require more work to adapt the input channels, preprocessing and output head to Sentinel-1 SAR. A pretrained encoder is not automatically a trained oil-spill detector.

- NASA-IBM Prithvi: https://github.com/NASA-IMPACT/Prithvi-EO-2.0
- DOFA: https://github.com/zhu-xlab/DOFA

**Deadline rule:** If the ResNet-34 U-Net baseline or a simpler trained segmentation model is working, do not replace it with a foundation model just to sound more advanced. Use the architecture that can be tested and explained honestly.

### 5.5 Reuse checklist for every external repo/data source

Before copying any code or downloading a dataset, record:

- [ ] Repository/data URL and version/commit/date accessed.
- [ ] Licence and attribution requirements.
- [ ] Input format expected and output format produced.
- [ ] Whether it handles SAR or instead uses optical/RGB imagery.
- [ ] Whether its labels match our classes.
- [ ] Dependencies and whether installation succeeds on our machines.
- [ ] What code was adapted and what changes we made.
- [ ] Any restrictions on redistributing data or model weights.

### 5.6 Avoid these traps

- Do not use an RGB drone/oil-photo detector as if it were a Sentinel-1 SAR model.
- Do not assume the benchmark includes latitude/longitude metadata for every cropped tile; verify the dataset files.
- Do not claim that a model trained on one dataset is validated globally.
- Do not invent a “real” spill, ship identity or ground-truth culprit to make the demo impressive.
- Do not claim the PDF is court-admissible or that the system proves guilt. A checksum supports file-integrity checking; it does not independently establish evidence authenticity or legal admissibility.

---

## 6. Scope decisions: must-have vs stretch

### 6.1 Must-have product stages

1. One reproducible Golden Case with source, licence, hashes, timestamp, CRS, forcing coverage and AIS/radar data status.
2. Stage 1 scene validation, incidence-angle handling, 3–12 m/s wind gate and a measurable CA-CFAR screening output.
3. Stage 2 four-channel segmentation, validated class mapping, sinuosity feature and georeferenced slick output. A labelled fallback may keep the demo running, but it must be identified as a fallback.
4. Stage 3 backward RK4 integration at the agreed step/window, current + wind + Stokes terms where inputs exist, plus an explicitly defined 95% origin uncertainty estimate.
5. Stage 4 H3/trajectory candidate filtering, supported radar dark-target comparison, and a mass-balance/pump-rate range with stated assumptions and unknowns.
6. Stage 5 dashboard, stable API, provenance dossier and recomputable SHA-256. PDF/A is a target only when it can be validated.
7. Tests, clean setup instructions, limitations, and a 3–8 minute demo.

### 6.2 Implementation order and bounded fallbacks

The five stage outputs remain in scope. If a complex algorithm cannot be validated by the feature freeze, retain its interface and report `unavailable` or `illustrative`; do not label a simpler substitute as the specified algorithm. The custom RK4 path is acceptable without OpenDrift if its inputs, units, tests and limitations are documented. H3, radar dark-target detection, pump-rate estimation and PDF/A remain planned capabilities, with validation gates before they are described as operational evidence.

Foundation models, MapLibre migration, live satellite ingestion and sponsor integrations not required by official rules remain optional. The existing Leaflet/offline demo path is the default until an alternative is demonstrably needed.

### 6.3 Scope freeze

The original 25 October and 1 November gates are historical plan dates. As of **4 November**, do not rewrite them as completed without evidence. Freeze new architecture work by **6 November**; after that, fix only release-blocking defects and make missing stage outputs explicit.

---

## 7. Repository structure and ownership

The team is adapting the existing TideTrace checkout. Do not reorganize it into the earlier illustrative `src/` tree just to match a diagram; map the five stages onto the current modules and add small adapters where contracts differ.

```text
Oil_Spill/
├── app/
│   ├── api/             # M4 backend/report endpoints; shared API contract
│   ├── ais/             # M4 AIS store, reconstruction, filtering and scoring
│   ├── drift/           # M3 fields, advection and uncertainty geometry
│   ├── geo/             # M1/M2 raster, CRS and polygon operations
│   ├── ml/              # M1 dataset, model, training, inference and fallback
│   ├── vision/          # M1 output adapter/schema/cache; connect to main path
│   ├── static/          # M5 Leaflet UI
│   ├── pipeline.py      # Shared end-to-end orchestration
│   ├── scenes.py        # M2 scene registry and metadata
│   └── main.py          # Shared FastAPI application
├── data/                # Cached indexes, outputs and fixtures; large data ignored
├── scripts/             # Acquisition, conversion, training and handover utilities
├── tests/               # Existing module and integration tests
├── docs/                # Current TideTrace docs plus SentinelTrace deliverables
├── models/              # Checkpoint reports; large weight files ignored
└── SentinelTrace_Team_Roadmap.md
```

Required handoff documents to add or adapt only when their content is ready: `docs/model_card.md`, `docs/data_sources.md`, `docs/limitations.md`, and a dossier outline. A small Golden Case manifest should name the exact scene, dataset/version, CRS, timestamp, forcing coverage, AIS/radar coverage, licences, hashes and real/synthetic/unavailable status.

### 7.1 Ownership rules

- **M1 — Radhika Sabale:** `app/ml/`, `app/vision/`, model training/data audit, and vision tests. Coordinate georeferencing changes with M2.
- **M2 — Ruchira:** `app/scenes.py`, `app/geo/raster.py`, `app/geo/tiffio.py`, metocean ingestion/cache preparation, Stage 1 calibration/gating/CFAR and source documentation.
- **M3 — Prem:** `app/drift/` and drift tests, including the target RK4/Stokes solver and origin uncertainty method.
- **M4 — Ruchika:** `app/ais/`, backend/API contracts, H3 and dark-target/mass-balance integration, dossier generation and report tests.
- **M5 — Akhilesh:** `app/static/`, dashboard integration, README/demo documentation, video and submission assembly.
- `app/pipeline.py`, `app/schemas.py`, `app/main.py`, and cross-stage tests are shared integration surfaces. Agree changes with all affected owners before merging.
- Everyone owns tests for their module and must review integration pull requests.
- Do not edit another person's module directly without discussing it first. Make a branch and pull request instead.
- M5 coordinates integration with M4 as backend/report counterpart; this does not make either member solely responsible for all code.

---

## 8. Integration contracts: how members' code connects

Agree these payloads on Day 1–2. A stable interface lets everyone build independently with mock data while other modules are unfinished.

### 8.1 Contract A — Scene and slick detection (M1 + M2)

File/API object: `slick_detection.json`

```json
{
  "incident_id": "DEMO-001",
  "case_type": "synthetic_demo",
  "scene": {
    "source": "documented source or synthetic fixture",
    "acquired_at_utc": "2026-05-14T05:22:18Z",
    "crs": "EPSG:4326",
    "raster_path": "data/golden_case/scene.tif"
  },
  "slick": {
    "geometry": {
      "type": "Polygon",
      "coordinates": []
    },
    "area_km2": null,
    "confidence": null,
    "method": "model | baseline | manual_demo"
  },
  "quality_flags": [
    "replace_with_real_flags"
  ]
}
```

Rules:
- `case_type` must be `real_historical`, `synthetic_demo` or `manual_demo`.
- Do not write made-up confidence/area values into a “real” output.
- Coordinates in GeoJSON use longitude, latitude order.
- If the input is not georeferenced, do not pretend that the polygon is an accurate real-world location.

### 8.2 Contract B — Origin corridor (M3)

File/API object: `origin_corridor.json`

```json
{
  "incident_id": "DEMO-001",
  "method": "synthetic_demo",
  "origin_window_utc": {
    "start": "2026-05-14T01:30:00Z",
    "end": "2026-05-14T02:15:00Z"
  },
  "origin_geometry": {
    "type": "Polygon",
    "coordinates": []
  },
  "uncertainty": {
    "level": "illustrative",
    "description": "Replace with a quantified estimate only when supported by the model"
  },
  "forcing": {
    "wind_source": null,
    "current_source": null,
    "time_coverage_valid": false
  }
}
```

Rules:
- A “95% origin ellipse” is only a valid claim if the algorithm actually calculates it and its statistical meaning is documented.
- Record whether forcing data is real, simulated or missing.
- If the full backward drift model is not working, use a transparent simplified demonstration and label it accordingly.

### 8.3 Contract C — Candidate attribution (M4)

File/API object: `attribution_verdict.json`

```json
{
  "incident_id": "DEMO-001",
  "case_type": "synthetic_demo",
  "candidates": [
    {
      "mmsi": "000000000",
      "vessel_name": "Demo vessel A",
      "time_overlap_minutes": 20,
      "distance_to_origin_km": null,
      "speed_change_knots": null,
      "signals": [
        "Track overlaps the illustrative origin window"
      ],
      "score": 0.0,
      "score_explanation": "Illustrative ranking only",
      "evidence_quality": "low",
      "h3_cells": [],
      "dark_target_match": null,
      "slick_volume_m3": {"min": null, "nominal": null, "max": null},
      "derived_flow_m3_h": {"min": null, "nominal": null, "max": null},
      "assumptions": [],
      "unavailable_features": []
    }
  ],
  "conclusion": "Investigative candidates only; not proof of causation or a finding of guilt"
}
```

Rules:
- Preserve missing values as `null`; never silently fill unknowns with invented data.
- The score is a prioritisation aid, not a probability of guilt.
- Explain every score using the features actually calculated.
- Never use a vessel name/identity from a fabricated example as if it were a verified real-world suspect.

### 8.4 Contract D — Dossier and API

Suggested endpoints:

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/health` or documented equivalent | Check API is alive |
| `GET` | `/api/v1/demo-case` or documented equivalent | Return the built-in Golden Case inputs and provenance |
| `POST` | `/api/v1/analyze` or documented equivalent | Run/replay the five-stage pipeline and return stage statuses and results |
| `POST` | `/api/v1/report` or documented equivalent | Generate the dossier from the same analysis response shown in the UI |

The current base exposes `/api/health`, `/api/scenes`, `/api/run`, job routes and `/api/report/{job_id}` under `app/api/`. Keep these working while adding an adapter or updating frontend and backend contracts together. The canonical schema should live in the existing `app/schemas.py` or an explicitly agreed module; do not create a second unused contract under the illustrative `src/api/` tree.

The dossier records its source-document identifiers and SHA-256 digest. PDF/A is a format target that must pass a validator before it is claimed. A hash can show that downloaded bytes match a digest; it does not establish authenticity, legal admissibility, causation, guilt or detention authority.

### 8.5 Suggested response shape

```json
{
  "incident_id": "DEMO-001",
  "status": "success",
  "case_type": "synthetic_demo",
  "scene": {},
  "stage_status": {"ingest": "available", "segmentation": "available", "hindcast": "available", "forensics": "partial", "dossier": "available"},
  "slick": {},
  "origin": {},
  "candidates": [],
  "mass_balance": {"volume_m3": {"min": null, "nominal": null, "max": null}, "flow_m3_h": {"min": null, "nominal": null, "max": null}, "assumptions": []},
  "dark_targets": {"status": "unavailable", "targets": []},
  "provenance": {
    "sources": [],
    "generated_at_utc": "2026-10-19T00:00:00Z",
    "warnings": []
  },
  "report": {
    "available": false,
    "sha256": null,
    "pdfa_validated": false
  }
}
```

The timestamp above is an example format only; the app must generate the actual current UTC time at runtime.

---

## 9. Exact five-person work division

Current ownership agreed by the team: **M1 Radhika Sabale, M2 Ruchira, M3 Prem, M4 Ruchika, M5 Akhilesh.** This assignment supersedes the older TideTrace role labels in inherited documentation. Ownership identifies the lead; stage interfaces and shared files still require review by affected members.

### M1 — Polarimetric segmentation / oil-slick vectorization (Radhika Sabale)

**Owns:** `app/ml/`, `app/vision/`, model/dataset handoff and vision tests; coordinate with M2 on georeferencing.

**Tasks**
1. Audit the named Kaggle dataset files, version, licence, labels, channels, units, georeferencing and scene/acquisition identifiers before training. Do not assume the repository's Zenodo loader is compatible.
2. Keep training/evaluation splits separated by scene or acquisition where metadata permits; record exact split files and random seed.
3. Validate the four input channels `[VV, VH, Span, Rvv/vh]`, calculating Span and ratio from linear power and documenting any dB conversion.
4. Train and export the target ResNet-34 U-Net (or document a tested compatible fallback). Record per-class metrics, data lineage and known failures.
5. Calculate boundary sinuosity from documented area/perimeter geometry and evaluate the proposed ranges on held-out examples before using them as rejection rules.
6. Produce mask, model metadata, uncertainty/status and map-ready polygons through one agreed output contract; connect the current `app/vision/` adapter to the main pipeline or retire the duplicate path by agreement.

**Done means:** dataset audit and model card; reproducible training command; checkpoint or explicit retrieval instructions; sample output; inference and georeferencing tests; metrics attributed to the correct dataset. No claim of generalization from one benchmark alone.

### M2 — SAR ingestion, calibration and screening (Ruchira)

**Owns:** scene acquisition/metadata, `app/scenes.py`, raster IO, metocean preparation, Stage 1 and source documentation.

**Tasks**
1. Select and document the Golden Case with acquisition time, CRS, transform, bounds, pixel size, source and licence.
2. Confirm whether the selected source is Sentinel-1 GRD or RTC and what calibrated values/bands it actually provides. Do not label RTC values as GRD sigma-zero without checking.
3. Implement/document radiometric and incidence-angle handling. Keep sigma-zero linear for cosine normalization, then convert to dB where needed.
4. Match ERA5 10 m wind to scene time/location and report whether it passes the proposed 3–12 m/s gate. Missing or out-of-range wind must be explicit.
5. Implement the 100 m image-pyramid CA-CFAR candidate screen with the proposed G=4, T=16 and -3.5 dB threshold as a validation target; record retained-area/pixel fraction on the Golden Case rather than asserting >95% savings in advance.
6. Pass validated chips and metadata to M1 and measured forcing to M3 using stable contracts.

**Done means:** scene manifest, source/licence record, tested CRS/transform, wind gate status, reproducible CFAR output and clear missing-data behavior.

### M3 — 4D hydrodynamic hindcasting (Prem)

**Owns:** `app/drift/`, Stage 3 interfaces and drift tests.

**Tasks**
1. Preserve the current solver as a baseline while implementing RK4 backward integration with the target `dt=-300 s` and maximum 18-hour window. The selectable RK4 path is now wired to the pipeline; analytical/step-refinement acceptance remains pending.
2. Integrate current, windage (`alpha=0.030`), Stokes drift and horizontal eddy diffusion (`K_h=1 m²/s`) only when corresponding data exists; record source, units, coverage and assumptions for each field. The solver uses wave height, peak period and wave-from direction; it converts the direction to propagation direction for the Kenyon Stokes vector.
3. Obtain/parse wave inputs required by the selected Stokes formulation and verify dimensional consistency. The cache builder requests significant wave height, peak period and wave direction, aligns by timestamp without extrapolation, and persists them in NPZ. **Golden Case result (5 Nov):** wind/current cached; the marine response yielded no usable wave fields, so Stokes is explicitly disabled for that cache. Retry with a supported wave product/date before claiming real Stokes forcing.
4. Compare RK4 against zero-current/constant-current analytical cases, step refinement and the existing solver on common inputs. M3 tests now cover analytical displacement, backward time, spatially varying flow convergence and diffusion variance.
5. Select the minimum-spread-variance snapshot at hourly intervals over negative time and return a ±1 hour window. The pipeline uses this rule. It computes a Gaussian KDE 95% HDR on a 256×256 local-metre grid and exports its convex hull; this polygon is explicitly approximate, not a calibrated confidence ellipse. Tests cover deterministic selection and polygon output; statistical calibration remains outside the verified evidence.
6. Emit time-stamped tracks, origin window, uncertainty geometry and forcing provenance for M4/M5.

**Done means:** repeatable solver tests, documented parameter values, origin output matching the agreed contract, and explicit limitation/status fields. Reverse integration is an estimate, not proof of the actual release point.

### M4 — Kinematic and mass-balance forensics / API (Ruchika)

**Owns:** `app/ais/`, backend schemas/routes and Stage 4 analytical outputs; coordinate dossier rendering with M5.

**Tasks**
1. Reuse AIS ingestion and reconstruction; preserve missing values and received-versus-interpolated status.
2. Add H3 resolution-7 indexing to the candidate path and compare it with the existing direct spatial/time filter on the Golden Case.
3. Add trajectory reachability and candidate evidence with component explanations. Track gaps are observations of missing broadcasts, not proof of intentional disabling.
4. Add radar dark-target comparison only where image resolution, acquisition timing and target confidence support it; otherwise return `unavailable` with a reason.
5. Estimate slick-volume and derived-flow ranges only from stated area/thickness/loiter-time assumptions. Treat the example BAOAC thicknesses and pump capacities as provisional inputs to source and validate, not deterministic proof or exoneration thresholds.
6. Return evidence, assumptions, missing-data flags and candidate rankings through the agreed API contract.
7. Test H3/filter consistency, track gaps, missing radar targets, null inputs, mass-balance ranges and deterministic outputs.

**Done means:** reproducible Stage 4 response with sources, computed features, uncertainties, and no fabricated or guilt-probability values.

### M5 — Tactical dashboard / dossier / integration (Akhilesh)

**Owns:** `app/static/`, UI/API integration, setup/demo docs, dossier presentation and submission media.

**Tasks**
1. Retain the current Leaflet console as the base; update it to show all five stage statuses, real/simulated/missing inputs, uncertainty, candidate evidence and assumptions.
2. Wire the UI to the agreed contract without breaking current working routes until the adapter is in place.
3. Build the dossier from the same analysis document shown by the UI. Include provenance, data status, model/forcing metadata, candidate reasons, limitations and report hash.
4. Validate PDF/A output if that format is claimed. A PDF plus checksum alone must not be described as ISO/IEC 27037 compliant or legally admissible.
5. Add download and independent SHA-256 verification display; test the hash against downloaded bytes.
6. Maintain SentinelTrace setup, data instructions, limitations and demo narrative; distinguish shipped TideTrace behavior from new target-stage behavior.
7. Rehearse the full Golden Case, record the actual application and verify submission links.

**Done means:** a teammate can start the app, replay the documented case, inspect every available stage and download/check the dossier; unavailable features are visible and clearly labelled.

### 9.1 Shared responsibility

- Stage outputs and API schemas are agreed before changing shared integration files.
- Each owner updates evidence links in Section 15; status is not inferred from code presence alone.
- M4 owns analytical evidence fields; M5 owns their dashboard/dossier presentation and submission packaging.
- Preserve existing working capabilities while adding the target algorithms behind interfaces. Do not replace an integrated module until its successor passes the agreed acceptance checks.

## 10. Daily roadmap: 19 October–10 November

The schedule is intentionally milestone-driven. If a task slips, cut stretch scope before delaying integration or the video.

**Schedule note (4 November 2026):** Dates through 3 November are the original plan, not proof of completion. Keep them as historical plan entries. The remaining 4–10 November rows are the re-baselined work; each owner must attach evidence before changing tracker status.

### Phase 1 — Foundation and contracts (19–25 October)

| Date | Main goal | M1 Radhika — Vision | M2 Ruchira — Ingestion | M3 Prem — Drift | M4 Ruchika — Forensics/API | M5 Akhilesh — UI/docs | End-of-day evidence |
|---|---|---|---|---|---|---|---|
| **Mon 19 Oct** | Kickoff and repository | Inspect dataset/repo | Identify scene/data options | Read OpenDrift quickstart | Draft API schemas | Create repo, issues, roadmap | Repo exists; owners and MVP agreed |
| **Tue 20 Oct** | Freeze interfaces | Agree mask/polygon output | Agree scene metadata format | Agree origin output | Freeze JSON contracts | Render mock JSON on map | Contracts committed; all can work in parallel |
| **Wed 21 Oct** | Golden Case selection | Load one dataset sample | Select/validate scene and metadata | Create synthetic drift fixture | Create AIS CSV schema/fixture | Build map skeleton | One documented case, labelled real or synthetic |
| **Thu 22 Oct** | First vertical slice | Run baseline inference or fixture | Rasterio can read scene | Toy drift function works | API returns mock analysis | UI reads API/mock JSON | One button displays one case on map |
| **Fri 23 Oct** | Basic tests | Dataset/mask test | CRS/transform test | Constant-current test | AIS parser test | UI empty/error states | Tests run locally |
| **Sat 24 Oct** | Environment and data gate | Confirm training environment | Confirm data licence/access | Confirm OpenDrift feasibility | Confirm report dependency | README setup draft | No unresolved blocker hidden |
| **Sun 25 Oct** | **Milestone 1: foundation freeze** | Demo inference input/output | Valid scene metadata | Stable drift contract | Stable API contract | Mock dashboard works | Every member can show a runnable component |

**Milestone 1 acceptance:** The repository is set up; all five members can run their modules; mock payloads pass schema validation; the Golden Case is cached or explicitly synthetic; the dashboard can show the mock case.

### Phase 2 — Core modules (26 October–1 November)

| Date | Main goal | M1 Radhika — Vision | M2 Ruchira — Ingestion | M3 Prem — Drift | M4 Ruchika — Forensics/API | M5 Akhilesh — UI/docs | End-of-day evidence |
|---|---|---|---|---|---|---|---|
| **Mon 26 Oct** | Baseline model | Train baseline; record config | Scene loader + metadata JSON | Drift function + units | Candidate filtering baseline | Map layers from mock response | Image→mask and API are separately testable |
| **Tue 27 Oct** | Geospatial accuracy | Export sample mask | Pixel-to-map transform verified | Synthetic trajectory plotted | AIS time parsing verified | Add scene and timestamp panel | Coordinates match known test point |
| **Wed 28 Oct** | Origin estimate | Improve inference/thresholds | Match wind/current sources | Add corridor output; label uncertainty | Add time/space overlap features | Render corridor on map | Candidate list is driven by API response |
| **Thu 29 Oct** | First data integration | Export model/checkpoint or backup | Validate forcing data/time coverage | Test real forcing if available | Rank candidates with reasons | Add candidate detail drawer | End-to-end response has provenance |
| **Fri 30 Oct** | Report generation | Metrics/model card draft | Data-source notes | Drift limitations note | PDF template and SHA-256 | Add download button | A PDF is generated from one analysis |
| **Sat 31 Oct** | Error handling | Test no-mask/empty result | Missing CRS/time errors | Missing forcing fallback | Empty AIS/no candidate cases | Loading/error states | Failure modes are understandable |
| **Sun 1 Nov** | **Milestone 2: core pipeline gate** | Model or documented baseline works | Scene georeferencing works | Origin output works or labelled fallback | Candidates + report work | Map shows all available layers | One scripted run produces a coherent analysis |

**Milestone 2 acceptance:** One command or short documented sequence can process/replay the Golden Case through the main modules. If real drift inputs are not available, the demo remains honest and explicitly labels the fallback.

### Phase 3 — End-to-end prototype (2–6 November)

| Date | Main goal | M1 Radhika — Vision | M2 Ruchira — Ingestion | M3 Prem — Drift | M4 Ruchika — Forensics/API | M5 Akhilesh — UI/docs | End-of-day evidence |
|---|---|---|---|---|---|---|---|
| **Mon 2 Nov** | Integration day | Fix inference adapter | Fix metadata mismatch | Fix origin schema | Wire analysis endpoint | Wire Analyze button | UI invokes API successfully |
| **Tue 3 Nov** | Map and evidence | Verify polygon output | Verify CRS/coordinates | Verify corridor layer | Verify candidate explanations | Style layers and legend | Map is understandable without narration |
| **Wed 4 Nov** | Target and evidence audit | Inspect Kaggle files, labels and checkpoint lineage | Confirm scene product, incidence-angle/wind/CFAR status | Record current solver and RK4/Stokes gap | Freeze Stage 4 schema; list H3/radar/mass-balance inputs | Align stage status and dossier UI contract | Every stage is marked implemented, inherited, partial or unavailable |
| **Thu 5 Nov** | Integrate the Golden Case | Re-run only with verified dataset lineage | Verify scene/forcing provenance and gate outputs | Compare target solver or clearly report unavailable | Run AIS filter; identify dark-target and pump-rate availability | Replay end-to-end and expose missing-stage states | No inherited output is mislabelled as SentinelTrace target output |
| **Fri 6 Nov** | **Milestone 3: feature freeze** | Freeze model/data path and document metrics | Freeze calibrated scene inputs and CFAR status | Freeze solver version and uncertainty method/status | Freeze H3/forensic results and assumptions | Freeze API/UI/dossier contracts | Clean-start vertical slice and complete stage-status record |

**Milestone 3 acceptance:** A user can click Analyze Incident, see the supported results, inspect the candidate ranking and download the report. Any unavailable subsystem is visibly labelled; no hidden mock data is represented as live or verified.

### Phase 4 — QA, video and submission (7–10 November)

| Date | Main goal | M1 Radhika | M2 Ruchira | M3 Prem | M4 Ruchika | M5 Akhilesh | End-of-day evidence |
|---|---|---|---|---|---|---|---|
| **Sat 7 Nov** | Code freeze + QA | Confirm model/data claims | Validate scene/gate provenance | Validate forcing and origin caveats | Verify candidate evidence and report fields | Freeze UI/dossier; compile report | Release candidate; unavailable features labelled |
| **Sun 8 Nov** | Record video | Explain dataset/model | Explain ingestion and gate | Explain hindcast and uncertainty | Explain candidate evidence and assumptions | Record/edit actual prototype demo | Full-length draft includes honest stage statuses |
| **Mon 9 Nov** | Final verification | Confirm displayed model lineage | Confirm data sources/licences | Confirm solver/result labels | Recompute report hash and verify output | Clean-start rehearsal; check video link | Final materials ready; no unsupported legal claims |
| **Tue 10 Nov** | Submission day | Available for urgent fix | Available for urgent fix | Available for urgent fix | Verify API/dossier if needed | Submit video link via dashboard | Submission confirmation saved |

### 10.1 Non-negotiable gates

- **25 Oct:** contracts and Golden Case frozen.
- **1 Nov:** complete core pipeline or labelled fallback.
- **6 Nov:** working vertical slice; feature freeze.
- **7 Nov:** code freeze except blocking bugs.
- **9 Nov:** video uploaded and checked; submission materials ready.
- **10 Nov:** submit early, not at the final minute.

---

## 11. Development setup and Git workflow

### 11.1 Suggested environment

The current `pyproject.toml` requires Python 3.11 or newer. Use Python 3.11 for a shared environment unless the team validates another version against the current code and pinned packages. Geospatial packages can be difficult to install together on Windows, so keep one documented environment.

**Current runtime packages:** follow `pyproject.toml` and `requirements.txt` in the base repository. Add training-only packages, `h3`, wave-data readers and PDF/A tooling only when the corresponding stage implementation is selected and tested.

The base uses an optional PyTorch/segmentation-models.pytorch training/inference path. Use a compatible Kaggle/Colab environment for training if local hardware is insufficient. Do not add OpenDrift as a required dependency if the team implements and validates the agreed RK4 solver directly.

### 11.2 Initial setup (Windows PowerShell)

```powershell
# 1. Clone the current base (or the confirmed team fork)
git clone https://github.com/S-T-A-RNalin1/tidetrace.git
cd tidetrace

# 2. Create a virtual environment using the agreed Python version
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Upgrade pip and install the pinned project dependencies
python -m pip install --upgrade pip
pip install -r requirements.txt

# 4. Run the test suite
python -m pytest -q

# 5. Start the existing API
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 6. Open the UI using the method documented in README.md
```

If a geospatial dependency fails on Windows, record the exact error and Python version before changing package versions. Do not let each member independently install a different stack. Use Conda or a Linux/Colab environment if that is the more reliable path for the relevant module.

### 11.3 Branch and commit rules

- `main`: stable demo branch; protected if possible.
- `dev`: integration branch.
- Feature branches: `feature/vision-inference`, `feature/scene-loader`, `feature/drift`, `feature/ais-ranking`, `feature/dashboard`.
- Commit small, meaningful changes.
- Every PR must say: what changed, how to run it, tests run, screenshots/sample output if relevant, and any contract changes.
- At least one other member reviews the PR.
- Never commit `.env`, access tokens, credentials, large raw datasets, or private AIS files.
- Tag stable versions such as `v0.1-mock-demo`, `v0.2-core-pipeline`, and `v1.0-submission` if useful.

### 11.4 Daily stand-up format

Each person sends the following in the team group by the agreed daily time:

```text
Yesterday:
- What I completed and where the code/output is.

Today:
- The one or two deliverables I will finish.

Blocked by:
- Exact dependency/person/error and what help I need.

Evidence:
- Commit/PR/test output/screenshot, not only “done”.
```

---

## 12. Testing and acceptance criteria

### 12.1 Module tests

| Area | Test | Pass condition |
|---|---|---|
| Scene metadata | Load valid GeoTIFF | CRS, bounds, transform and dimensions are returned |
| Scene metadata | Load missing/broken georeferencing | Clear error or explicit unsupported status |
| M2 calibration | Normalize known linear sigma-zero values at known incidence angles | Expected normalization matches independent calculation; inputs/outputs record units |
| M2 wind gate | Test below 3, within 3–12, above 12 m/s and missing wind | Gate status is deterministic and missing/out-of-range cases are not represented as valid detection conditions |
| M2 CA-CFAR | Known background plus injected dark targets | Candidate windows and retention fraction are reproducible; thresholds and pixel scale are reported |
| M1 dataset | Inspect representative Kaggle images/masks and split manifest | Dataset version, licence, channels, labels and scene-separated split are recorded before training |
| Vectorization | Convert a known mask region to polygon | Polygon coordinates agree with the known transform within a documented tolerance |
| Vision | Run inference on a fixture | Output mask shape is correct and values are in the expected range |
| M1 polarimetry | Calculate Span and VV/VH ratio from known linear inputs | Channels, order, units and resulting model tensor shape match the documented contract |
| M1 sinuosity | Compare known smooth and irregular polygons | Formula is correct; any cutoff is reported as validated only on held-out data |
| AIS loader | Parse timestamps and coordinates | UTC and numeric fields are normalised; bad rows are reported |
| Candidate filter | One ship crosses the corridor/time; another does not | Only the matching track is selected |
| Drift | Constant-current toy example | Direction and displacement match the analytical expected value within tolerance |
| M3 RK4 | Compare RK4 against an analytical constant-velocity case and step refinement | Position error is within a stated tolerance and integration direction/time steps are correct |
| M3 Stokes | Known wave inputs and units | Output units/direction match an independent calculation; absent wave inputs are explicitly unavailable |
| M3 origin estimate | Known particle ensemble with known minimum variance time | Selected origin window and 95% KDE region are reproducible and statistically described |
| Drift | Missing forcing data | Module reports missing/simulated forcing instead of fabricating a real result |
| Ranking | Known features | Ranking and component scores are deterministic and explainable |
| M4 H3 | Compare H3 candidate set against direct spatial/time filter | No eligible candidates are silently lost; resolution and boundary handling are recorded |
| M4 dark targets | Known target/no-target and unsupported-resolution cases | Target status and confidence are explicit; absence of a detection is not called proof of no vessel |
| M4 mass balance | Known area, thickness range and loiter interval | Volume/flow units and bounds are correct; unsupported comparisons remain null/unavailable |
| API | `/health`, demo case and analysis | Valid status and schema; useful errors for invalid requests |
| Dossier | Generate report | Dossier includes source/provenance/assumptions; SHA-256 matches downloaded bytes |
| PDF/A | Validate output if claimed | A PDF/A validator passes the specified conformance level before the UI/report claims it |
| UI | API unavailable | Visible error/retry state; no misleading stale “success” |
| Reproducibility | Run the Golden Case twice | Same inputs and deterministic modules produce the same expected output, or differences are documented |

### 12.2 End-to-end acceptance test

A teammate who did not write the code must be able to:

1. Follow README setup from a clean clone.
2. Start the API and dashboard.
3. Load the built-in Golden Case.
4. Click Analyze.
5. See a status for each of the five stages and the slick/origin layers where outputs exist.
6. See candidate ships, AIS/radar evidence availability, ranking reasons and mass-balance assumptions.
7. Download the dossier.
8. Recompute the report checksum and run PDF/A validation only if conformance is claimed.
9. Explain which inputs and outputs are measured, simulated, inherited baseline or unavailable.

If any step fails, it is a release blocker.

---

## 13. Demo scenario and video plan

### 13.1 Golden Case rules

The supplied Gemini document contains a worked example named `MED-S1-2026-0514` with a named vessel and very specific coordinates, speeds, drift distance and pump-flow result. **Do not treat those values or that vessel identity as verified historical facts unless the team independently finds and documents the original source data.** For the prototype, either:

- use a fully documented real historical case with traceable data sources; or
- turn it into an explicitly synthetic teaching scenario with fictional IDs/names and an obvious `SYNTHETIC DEMO` label.

Never use invented ground truth to claim the model correctly identified a real polluter.

### 13.2 Suggested 5–6 minute video structure

The competition allows 3–8 minutes. Aim for about 5 minutes so there is room for a clear live demonstration.

| Time | What to show | Speaker |
|---|---|---|
| 0:00–0:35 | Problem: satellite sees a possible slick, but the slick may drift and nearest-ship matching can mislead | M5 |
| 0:35–1:10 | Architecture diagram and explain the pipeline in plain language | M2 |
| 1:10–1:55 | Show source data, model/mask and how pixels become a georeferenced polygon | M1 |
| 1:55–2:40 | Show drift estimate, environmental inputs and uncertainty/caveats | M3 |
| 2:40–3:40 | Click Analyze; show map layers and candidate ranking with reasons | M4 + M5 |
| 3:40–4:20 | Generate PDF and show provenance/assumptions/checksum | M4 |
| 4:20–5:10 | Innovation, practical value, limitations and future work | M5 + all |
| 5:10–5:30 | Closing and thanks | M5 |

### 13.3 Recording checklist

- [ ] Record the working app locally, not a hosted free tier that may sleep.
- [ ] Use 1080p if possible, readable UI and clear audio.
- [ ] Close notifications and unrelated tabs.
- [ ] Use the same Golden Case that passed the end-to-end test.
- [ ] Keep a backup screen recording in case a live run fails.
- [ ] Show actual outputs, not only slides.
- [ ] Clearly identify any simulated data.
- [ ] Include the problem, solution, key features, how a user operates it, innovation, practical value and expected impact.
- [ ] Keep within 3–8 minutes.
- [ ] Upload to YouTube as Public or Unlisted according to the rules.
- [ ] Open the link in a private/incognito window and verify playback.
- [ ] Submit the YouTube link through the participant dashboard before 10 November.

---

## 14. Risks, fallbacks and claims we must not overstate

| Risk | Why it matters | Fallback |
|---|---|---|
| Training takes too long or results are weak | A model that never runs is no help to the prototype | Use a tested baseline/labelled fixture and report the limitation honestly |
| Dataset labels, licences, channel units or georeferencing are unclear | Training and reported metrics may not describe the intended sensor/task | Complete the Kaggle audit first; keep the existing Zenodo path separately identified until a decision is recorded |
| Target algorithms cannot be validated before the deadline | A named algorithm can be mistaken for an implemented or scientifically validated result | Preserve the stage contract and mark the capability as unavailable or illustrative; keep the current baseline visible as inherited |
| Volume, flow-rate, or pump-capacity assumptions are weak | False precision can make an investigative lead look like proof | Show ranges and assumptions; omit the comparison when inputs or sources are missing |
| PDF/A, ISO/IEC 27037, UNCLOS or enforcement claims are not independently verified | A generated report does not itself establish compliance, admissibility, causation or authority | Describe only verified output properties and keep legal conclusions with competent authorities |
| Dataset class labels/channels differ from assumptions | Wrong labels produce meaningless model results | Inspect sample images and masks before training; write a label mapping |
| No georeferencing for training crops | A mask cannot automatically become a true location | Use a separate georeferenced scene for the map demo; document alignment |
| Earth Engine credentials/API delay | Live query can fail during the demo | Cache a permitted historical scene and replay offline |
| ERA5/CMEMS files cannot be matched | Drift estimate cannot be called real-data-based | Use synthetic forcing with a visible simulated label |
| Reverse-time OpenDrift is not physically validated for the case | Backward integration is not automatically a reliable source reconstruction | Use a transparent illustrative corridor or forward model with uncertainty; document method |
| AIS coverage missing for the selected region/time | No valid candidate comparison is possible | Use a licensed small sample or labelled synthetic tracks; disclose it |
| AIS track gaps or transponder-off intervals | Missing data does not prove deliberate concealment | Show a coverage gap, do not label it as intentional “going dark” without evidence |
| Slick area does not determine true spill volume | Thickness varies and is uncertain | Omit pump-volume claim or show a range with assumptions and uncertainty |
| Candidate ranking looks like an accusation | False positives could harm real entities | Use “candidate”, show supporting/contradicting evidence, show uncertainty, no guilt verdict |
| “Court-admissible” wording is unsupported | A PDF and checksum do not establish legal admissibility | Say “structured incident report with integrity checksum”; legal admissibility requires separate validation |
| Foundation model integration expands scope | Channel/preprocessing mismatch may consume the sprint | Keep ResNet-34 U-Net or another tested baseline; do not switch late |
| Heavy geospatial dependency fails on Windows | Members cannot reproduce the app | Pin the environment; use Conda/Colab for difficult parts; keep UI/API lightweight |
| Team waits for everyone else's module | Integration starts too late | Use mock contracts on Day 2 and integrate every day |
| Video/report is left until the last day | Submission can fail despite good code | Start report on 22 October; record rough video by 5 November; final edit by 9 November |

### 14.1 Safe wording for the project and judges

Prefer:

- “detects candidate oil-like slicks in the selected scene”
- “estimates a possible origin corridor under stated environmental assumptions”
- “ranks vessels whose available AIS tracks overlap the estimated corridor/time window”
- “provides an explainable investigation lead and a structured report”
- “prototype results are not a legal finding and require expert validation”

Avoid:

- “the AI proves which ship dumped the oil”
- “the system guarantees court-admissible evidence”
- “the satellite gives live real-time video”
- “the origin is exact” or “95% certainty” unless the method and calibration support that number
- “the ship deliberately switched off AIS” based only on a gap in available records
- “pump mechanics prove causation” without verified physical measurements and validated assumptions

---

## 15. Team progress tracker

Update this section at the end of every day. Use `Inherited / unverified` for base-repository behavior that exists but has not passed SentinelTrace acceptance; use `In progress`, `Blocked`, or `Done` for current work and attach a link to the PR/output. Do not infer completion from the presence of code.

| Work item | Owner | Status | Evidence / PR link | Blocker / next action |
|---|---|---|---|---|
| Repo, branches, README skeleton | M5 | Not started | | |
| JSON contracts and mock case | M4 + M5 | Not started | | |
| Dataset/licence/label audit | M1 | Not started | | |
| Scene and georeferencing validation | M2 | Not started | | |
| Synthetic drift test | M3 | Not started | | |
| RK4 hindcast path and 300 s / 18 h settings | M3 | Done (automated checks + direct pipeline smoke) | `app/drift/advection.py`, `app/pipeline.py`, `tests/test_m3_hindcast.py` | Full detection-to-report Golden Case run and real-case RK2 benchmark are not completed |
| Stokes wave input and velocity | M3 | In progress (forcing unavailable) | `app/drift/fields.py`, `scripts/build_metocean_cache.py`, Golden Case metocean cache | Re-fetch a source/date with valid wave height, period and direction; current cache has current/wind only |
| Eddy diffusion (`K_h=1 m²/s`) | M3 | Done (unit check) | `app/config.py`, `app/drift/advection.py`, `tests/test_m3_hindcast.py` | Validate diffusivity against domain evidence before scientific interpretation |
| AIS schema and fixture | M4 | Not started | | |
| Dashboard displays mock case | M5 | Not started | | |
| Segmentation baseline/inference | M1 | Not started | | |
| Real or labelled demo scene | M2 | Not started | | |
| Origin minimum-variance time and 95% KDE region | M3 | Implemented; approximate method documented | `app/drift/advection.py`, `app/drift/cone.py`, `app/pipeline.py`, `tests/test_m3_hindcast.py` | KDE convex hull is not calibrated as a 95% confidence ellipse |
| Candidate filtering/ranking | M4 | Not started | | |
| PDF + SHA-256 | M4 | Not started | | |
| End-to-end test | All | Not started | | |
| Competition report | M5 compiles; all contribute | Not started | | |
| Video recorded and edited | M5 leads; all contribute | Not started | | |
| YouTube link verified | M5 | Not started | | |
| Dashboard submission confirmed | M5 + one verifier | Not started | | |

### 15.1 Definition of “done”

A task is not done because code exists. It is done when:
1. The code is committed and pushed.
2. The owner provides a reproducible run command or test.
3. The output matches the agreed contract.
4. A second member can run or inspect it.
5. The README/roadmap is updated if setup or behaviour changed.

---

## 16. Final submission checklist

### Working prototype
- [ ] Clean clone setup verified on a second machine or clean environment.
- [ ] API and dashboard both start reliably.
- [ ] Golden Case is repeatable without depending on an untested external service.
- [ ] Slick polygon, origin corridor and AIS tracks are visible where data exists.
- [ ] Real, synthetic and unavailable data are visibly distinguished.
- [ ] Candidate ranking has reasons and caveats.
- [ ] PDF report downloads and contains source/provenance information.
- [ ] SHA-256 checksum can be recomputed and matched.
- [ ] No debug credentials, secrets or unlicensed data are committed.

### Technical and documentation
- [ ] README has installation, run, test and demo instructions.
- [ ] Dataset/repository licences and attributions are recorded.
- [ ] Model metrics and limitations are documented.
- [ ] Architecture diagram and data-flow explanation are complete.
- [ ] Report follows the official template/page limit once the official website/rules are confirmed.
- [ ] All external code and datasets are credited.
- [ ] No unsupported accuracy, real-world culprit or legal-admissibility claims remain.

### Video and submission
- [ ] Video is 3–8 minutes.
- [ ] It demonstrates the actual working prototype.
- [ ] It explains problem, solution, user workflow, key features, innovation, value and expected impact.
- [ ] YouTube upload is complete and viewable in private/incognito mode.
- [ ] Correct video link is submitted through the participant dashboard.
- [ ] Submission confirmation is saved.
- [ ] Final deadline: **10 November 2026**.

---

## 17. Questions to resolve when the project website is shared

When the official website/problem statement is provided, check these before finalising the plan:

1. What exact rubric and deliverables are mandatory?
2. Is a written report required, and what is its exact page limit/template?
3. Is Nugen AI Engine or another sponsor technology mandatory? If yes, what API, access key, SDK and proof of integration are required?
4. Are there restrictions on public datasets, model weights, hosting, team repo visibility or video privacy?
5. Does the competition require a deployed website, or is a locally working prototype acceptable?
6. Is there a fixed submission time/time zone on 10 November?
7. Are there mandatory credits, disclaimers, branding or team details for the video?
8. Are there restrictions on the use of AI coding assistants or external open-source repositories?

**Next action:** Share the project/competition website URL. Replace the placeholders in Section 2, verify the official rules, and update this roadmap only where the source requirements demand it.
