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

**We start with a satellite radar image that already has map coordinates. Our vision model marks pixels that may be oil, and we turn those pixels into a shape on the map. We then use wind/current data—or a clearly labelled simulated example if real matching data is unavailable—to estimate where the slick could have started. We compare that estimated area and time with ship GPS broadcasts called AIS. The dashboard shows which ships were nearby, what their speed/track looked like, and why they were ranked. Finally, we generate a report containing the inputs, outputs, assumptions and a checksum. The system is a research/demo aid: it does not prove that a particular ship committed a crime.**

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
| H3 | A global grid system for indexing locations | Faster geographic filtering; optional for MVP |
| Candidate attribution | Ranking vessels whose tracks are consistent with a scenario | Dashboard output; not proof of guilt |
| SHA-256 | A checksum that can reveal whether a file changed | Integrity check for the exported report |

### 1.4 User journey

1. The user opens the SentinelTrace dashboard.
2. The user loads the built-in **Golden Case** demo scenario or selects a supported historical scene.
3. The app displays the satellite image and the detected/annotated slick polygon.
4. The app shows the scene timestamp, area of interest and wind/current-data status.
5. The app runs the drift-estimation step (real model where configured; otherwise an explicitly labelled demonstration/synthetic result).
6. The map shows the estimated origin corridor and historical AIS tracks.
7. The system ranks candidate vessels using transparent, explainable signals such as time/location overlap and observed speed changes.
8. The user opens a candidate to see its track, supporting observations, uncertainty and caveats.
9. The user downloads a PDF incident report and can verify its SHA-256 checksum.

---

## 2. Project links and website

### 2.1 Official project/competition website

- **Project website / challenge page:** `TO ADD — awaiting the website link from the team`
- **Submission platform/dashboard:** `TO ADD — paste the exact participant dashboard URL and submission instructions`
- **Required video:** YouTube link, 3–8 minutes, submitted through the participant dashboard by 10 November 2026.

When the website link is received, verify the official problem statement, required sponsor/tool integration, judging rubric, report/template rules, and whether any additional deliverable is mandatory. If it conflicts with this working roadmap, the official competition instructions take precedence.

### 2.2 Team-owned repository

- **GitHub repository:** `TO CREATE OR CONFIRM`
- Suggested name: `sentineltrace`
- Suggested visibility: private during development; make public only if the competition rules and data/licensing allow it.
- The team repository should contain the source code, small demo fixtures, configuration, tests, documentation and instructions. Do **not** commit large datasets, credentials, private AIS data or model weights unless the licence and repository size make this appropriate.

---

## 3. What we can realistically finish by 10 November

The window from 19 October to 10 November is only 23 calendar dates inclusive. We must build a **vertical slice** that works from input to visible output, not five disconnected research projects.

### 3.1 Recommended MVP (minimum viable prototype)

The prototype counts as a useful MVP when all of these work on one laptop:

- [ ] A known historical SAR image or demo raster loads reliably.
- [ ] The image's timestamp and map projection/transform are read correctly.
- [ ] The app can show a real trained segmentation output **or** a clearly labelled baseline/demo mask if training/integration fails.
- [ ] A slick polygon is displayed in a map with coordinates.
- [ ] A drift/origin output is shown. If it is simulated, the interface labels it **SIMULATED**; if real metocean inputs are used, it records their source and time coverage.
- [ ] A small, licensed historical AIS sample or labelled synthetic AIS fixture is compared against the origin corridor.
- [ ] Candidate vessels are ranked by documented rules; the app does not call a vessel “guilty”.
- [ ] The user can download an incident PDF that includes inputs, assumptions, candidate ranking, uncertainty, data provenance and a SHA-256 checksum.
- [ ] A fresh clone can run by following the README.
- [ ] A 3–8 minute demo video is recorded, uploaded to YouTube and checked in a private/incognito window.

### 3.2 The ambitious architecture is not the Day-1 requirement

The source PDF discusses GEE ingestion, trained U-Net segmentation, wind gating, CFAR screening, OpenDrift, Stokes drift, KDE origin ellipses, H3 indexing, AIS blackout reachability, pump-flow plausibility and PDF/A packaging. These are useful design ideas, but attempting all of them simultaneously is a major integration risk.

**Build in this order:**

1. A hard-coded demo case and map.
2. A working API that returns a stable JSON response.
3. Real image loading and georeferenced polygon display.
4. AIS candidate filtering using a small, documented dataset.
5. A drift module with explicit inputs and uncertainty.
6. Model training/inference if the baseline is already working.
7. PDF report and polished demo.
8. Advanced modules only if the MVP is stable.

### 3.3 Recommended prototype mode

Use **historical/offline replay**, not a claim of live satellite streaming. Sentinel-1 is an orbital satellite mission with discrete acquisitions, not a live video camera. Cache the exact demo inputs before the presentation so the demo does not fail because an external API is down.

---

## 4. System architecture and end-to-end flow

```text
Historical SAR scene / demo GeoTIFF
              |
              v
[Ingestion & metadata validation] <--- ERA5 wind / CMEMS current data
              |
              v
[Segmentation model or labelled baseline mask]
              |
              v
[Mask cleanup + georeferencing]
              |
              v
[GeoJSON slick polygon + timestamp + uncertainty]
              |
              v
[Drift estimate / origin corridor]
              |
              v
[Historical AIS tracks + time/location filtering]
              |
              v
[Explainable candidate ranking; no guilt verdict]
              |
              v
[FastAPI service]
              |
              v
[Leaflet map dashboard + candidate list]
              |
              v
[PDF incident report + SHA-256 checksum]
```

### 4.1 Module responsibilities

| Module | Input | Output | Primary owner |
|---|---|---|---|
| Ingestion | GeoTIFF, timestamp, CRS, optional wind/current grids | Validated scene metadata and raster | M2 |
| Vision | Raster/tile | Pixel mask, confidence, model metadata | M1 |
| Vectorization | Mask + affine transform/CRS | GeoJSON polygon and area estimate | M1, reviewed by M2 |
| Drift | Slick polygon/centroid, timestamp, currents/wind, time window | Estimated origin corridor and uncertainty | M3 |
| AIS filtering | Origin corridor/time window + AIS rows | Candidate vessels and track snippets | M4 |
| Ranking/report evidence | Candidate tracks and computed features | Ranked candidates with reasons and caveats | M4 |
| API | Validated requests and module outputs | Stable JSON endpoints | M4 + M5 |
| Dashboard | API response | Map layers, status, candidate list and report button | M5 |
| Demo/docs | Stable end-to-end flow | Video, report, README and final submission | M5, all members |

### 4.2 Important data rule

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
| P0 | Marine SAR Oil Spill Detection Dataset (Krestenitis et al.) | https://zenodo.org/records/3358370 | Primary labelled training/evaluation data; inspect class labels, file layout, licence and metadata first | M1 | Use if the files/licence fit |
| P0 | Oil Spill Detection in SAR Images | https://github.com/d-elicio/Oil-Spill-Detection-in-SAR-images | Candidate starting point for dataset loader, train/validation split and segmentation implementation | M1 | Inspect before adapting; do not assume it is plug-and-play |
| P0 | PyTorch | https://github.com/pytorch/pytorch | Model training and inference | M1 | Use |
| P0 | segmentation-models.pytorch | https://github.com/qubvel/segmentation_models.pytorch | U-Net/DeepLab-style segmentation architectures and encoders | M1 | Use only after confirming channel count and label mapping |
| P0 | Rasterio | https://github.com/rasterio/rasterio | Read georeferenced rasters, affine transforms and write outputs | M1 + M2 | Use |
| P0 | Shapely | https://github.com/shapely/shapely | Clean polygons, geometry operations and area/buffer calculations | M1 + M2 | Use |
| P0 | FastAPI | https://github.com/fastapi/fastapi | Connect the analysis pipeline to the web UI | M4 | Use |
| P0 | Leaflet | https://github.com/Leaflet/Leaflet | Interactive map and GeoJSON/AIS layers | M5 | Use; simplest path for a short deadline |
| P0 | WeasyPrint | https://github.com/Kozea/WeasyPrint | Turn a controlled HTML template into a downloadable PDF report | M4 + M5 | Use if install works on team OS |

### 5.2 Important data sources

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
| H3 Python | https://github.com/uber/h3-py | Spatially index tracks and corridors | Optional; a direct point-in-polygon/time filter may be enough for a small demo |
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

### 6.1 Must-have

1. One reproducible Golden Case with all inputs stored or referenced.
2. A working map UI with scene location, slick polygon, origin corridor, AIS tracks and candidate list.
3. A documented detection output: model-generated if available, otherwise clearly labelled baseline/annotated fixture.
4. Candidate filtering based on time and geographic overlap.
5. Transparent ranking features, such as distance to corridor, time overlap and speed-change evidence if present in the data.
6. PDF report with provenance, assumptions, limitations and SHA-256 checksum.
7. Tests, README, and the recorded demo.

### 6.2 Stretch features, only after the MVP works

- Direct Google Earth Engine query for another scene.
- Full ResNet-34 U-Net training and model export.
- Real ERA5/CMEMS download and drift simulation.
- OpenDrift/OpenOil integration.
- H3 spatial indexing.
- AIS blackout reachability analysis.
- CFAR radar-target extraction and AIS dark-target comparison.
- Detailed pump-flow plausibility calculation.
- Nugen AI Engine integration if the official challenge requires it and its API/access details are available.
- PDF/A or sophisticated evidence-chain workflow beyond a basic report/checksum.

### 6.3 Scope freeze

By **25 October**, decide which stretch features are genuinely working. After that, new ideas must not destabilize the demo. By **6 November**, feature development stops except for a fix that is necessary to make the existing demo work.

---

## 7. Repository structure and ownership

Use one repository and clear ownership boundaries. The exact layout can evolve, but interfaces must not change without telling the affected owner.

```text
sentineltrace/
├── README.md                         # M5; all members contribute
├── ROADMAP.md                        # This file; M5 maintains
├── pyproject.toml                    # M4; shared Python tooling
├── requirements.txt                  # M2 + M4; keep minimal and tested
├── .env.example                      # M4; variable names only, no secrets
├── .gitignore
├── configs/
│   ├── pipeline.yaml                 # M4: thresholds and feature weights
│   └── metocean.yaml                 # M2: data sources, wind gates, time units
├── data/
│   ├── README.md                     # Where data came from, licences and download steps
│   ├── golden_case/
│   │   ├── manifest.json             # Timestamp, CRS, sources, hashes, synthetic/real flag
│   │   ├── scene.tif                 # Small demo GeoTIFF if redistribution is permitted
│   │   ├── mask.geojson              # Optional labelled/reference mask
│   │   ├── wind_sample.nc             # Optional; only if licensed and available
│   │   ├── current_sample.nc          # Optional; only if licensed and available
│   │   └── ais_sample.csv             # Licensed/synthetic, clearly labelled
│   └── models/
│       └── README.md                 # Download or train instructions; avoid committing huge files
├── notebooks/
│   └── 01_train_segmentation.ipynb   # M1; exploratory only
├── src/
│   ├── __init__.py
│   ├── ingestion/                    # M2
│   │   ├── scene_loader.py
│   │   ├── metadata.py
│   │   └── metocean_loader.py
│   ├── vision/                       # M1
│   │   ├── dataset.py
│   │   ├── model.py
│   │   ├── predict.py
│   │   ├── vectorize.py
│   │   └── metrics.py
│   ├── hydrodynamics/                # M3
│   │   ├── drift.py
│   │   └── origin_corridor.py
│   ├── forensics/                    # M4
│   │   ├── ais_loader.py
│   │   ├── candidate_filter.py
│   │   ├── rank_candidates.py
│   │   └── report.py
│   └── api/                          # M4 + M5
│       ├── main.py
│       └── schemas.py
├── ui/                               # M5
│   ├── index.html
│   └── static/
│       ├── css/app.css
│       └── js/app.js
├── tests/
│   ├── fixtures/
│   ├── test_scene_metadata.py
│   ├── test_geojson.py
│   ├── test_drift.py
│   ├── test_candidate_filter.py
│   ├── test_api.py
│   └── test_report_hash.py
├── docs/
│   ├── architecture.md
│   ├── data_sources.md
│   ├── model_card.md
│   ├── limitations.md
│   └── report_outline.md
└── scripts/
    ├── run_api.ps1
    ├── run_api.sh
    └── run_demo.ps1
```

### 7.1 Ownership rules

- **M1** owns `src/vision/`, training notebook and model card.
- **M2** owns `src/ingestion/`, `configs/metocean.yaml` and `docs/data_sources.md`.
- **M3** owns `src/hydrodynamics/` and `tests/test_drift.py`.
- **M4** owns `src/forensics/`, API schemas/backend, report generation and core test integration.
- **M5** owns `ui/`, `README.md`, `ROADMAP.md`, video and final report assembly.
- Everyone owns tests for their module and must review integration pull requests.
- Do not edit another person's module directly without discussing it first. Make a branch and pull request instead.
- One person (M5, with M4 as backup) is the integration coordinator, not the sole person responsible for all code.

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
      "evidence_quality": "low"
    }
  ],
  "conclusion": "Candidate ranking only; not a finding of guilt"
}
```

Rules:
- Preserve missing values as `null`; never silently fill unknowns with invented data.
- The score is a prioritisation aid, not a probability of guilt.
- Explain every score using the features actually calculated.
- Never use a vessel name/identity from a fabricated example as if it were a verified real-world suspect.

### 8.4 Contract D — PDF report and API

Suggested endpoints:

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/health` | Check API is alive |
| `GET` | `/api/v1/demo-case` | Return the built-in demo inputs |
| `POST` | `/api/v1/analyze` | Run or replay the pipeline and return scene, origin and candidate results |
| `POST` | `/api/v1/report` | Generate the PDF report for a selected analysis |

The exact request/response models live in `src/api/schemas.py`. Keep the UI using these schemas rather than reading private Python internals.

### 8.5 Suggested response shape

```json
{
  "incident_id": "DEMO-001",
  "status": "success",
  "case_type": "synthetic_demo",
  "scene": {},
  "slick": {},
  "origin": {},
  "candidates": [],
  "provenance": {
    "sources": [],
    "generated_at_utc": "2026-10-19T00:00:00Z",
    "warnings": []
  },
  "report": {
    "available": false,
    "sha256": null
  }
}
```

The timestamp above is an example format only; the app must generate the actual current UTC time at runtime.

---

## 9. Exact five-person work division

The PDF's role mapping is M1 Radhika, M2 Ruchira, M3 Prem, M4 Akhilesh and M5 Ruchika. If these names do not match the current five people, keep the role numbers and replace the names.

### M1 — Computer Vision / Oil-Slick Segmentation

**Owns:** `src/vision/`, training notebook, model files/instructions, `docs/model_card.md`.

**Why this role matters:** The rest of the project needs a reliable output mask or polygon. The model should not be the only thing that works; a baseline must be available if training takes longer than expected.

**Exact tasks**
1. Inspect the Zenodo dataset structure and licence; write down the classes and mask encoding.
2. Run the chosen repository's smallest example first. Do not start by rewriting the whole training pipeline.
3. Implement a dataset loader that pairs each image with the correct mask.
4. Confirm label mapping and whether the data has VV/VH channels, single-channel images or visualised PNGs.
5. Create train/validation/test splits. Keep related tiles/scenes from leaking across splits where metadata allows.
6. Train a baseline segmentation model in Colab or another suitable environment. Log seed, parameters, loss and metrics.
7. Export the model weights and an inference function with a documented input/output shape.
8. Produce a sample mask and metrics figure for the dashboard/report.
9. Implement or reuse mask-to-polygon conversion with M2's review of CRS/georeferencing.
10. If training is not stable by 29 October, deliver a tested inference adapter and labelled baseline mask so the rest of the demo continues.

**Deliverables / done means**
- `src/vision/dataset.py`, `model.py`, `predict.py`, `vectorize.py`.
- A notebook or script that another member can run.
- Model checkpoint or explicit download/training instructions.
- `model_card.md`: data source, labels, split, metrics, known failure cases.
- A test showing inference returns a mask with the expected shape.
- No unsupported promise of mIoU ≥ 0.78; report the measured value, even if lower.

**Plain-English version:** “I am responsible for teaching/using the AI to mark the pixels that may be oil. I must show what data it learned from, how well it performed, and give the rest of the team a mask they can put on the map. If the model does not finish in time, I must still provide a clearly labelled backup output.”

### M2 — Geospatial Ingestion / Satellite and Environmental Data

**Owns:** `src/ingestion/`, `configs/metocean.yaml`, `docs/data_sources.md`.

**Why this role matters:** A pixel mask only becomes a map location if the image's coordinate metadata is handled correctly. Environmental data also needs compatible time and spatial coverage.

**Exact tasks**
1. Inspect the Golden Case and select one historical SAR scene or a small valid GeoTIFF fixture.
2. Record the scene source, acquisition timestamp, coordinate reference system (CRS), transform, bounds, pixel size and licence.
3. Implement `scene_loader.py` to read the image and metadata through Rasterio.
4. Write checks that fail clearly if CRS, timestamp or geotransform is missing.
5. Make a function to convert pixel/row/column positions to longitude/latitude using the correct transform and CRS.
6. If using GEE, get access and run one small query; cache the chosen scene so the presentation does not rely on network access.
7. Investigate whether matching ERA5 wind and CMEMS current data can be obtained for the selected case. Record data coverage and units.
8. Implement a minimal `metocean_loader.py` only when there is a real file to load; validate time, units, coordinate ordering and missing values.
9. If time allows, add a wind-quality gate with configurable thresholds and tests. Do not treat thresholds as universal truth without documenting why they were selected.
10. Write the exact dataset download/setup steps in `docs/data_sources.md`.

**Deliverables / done means**
- A valid small demo scene or documented download path.
- Scene metadata JSON and a working raster viewer/input function.
- A test that pixel coordinates convert to expected map coordinates.
- Data-source/licence/provenance table.
- A clear status for wind/current inputs: real and matched, simulated, or unavailable.

**Plain-English version:** “I make sure the satellite image is a real map image rather than just a picture, so any detected patch can be placed in the right place on Earth. I also check whether wind and ocean-current data actually match the image's time and location. I must not pretend missing data is real.”

### M3 — Hydrodynamics / Drift and Origin Estimate

**Owns:** `src/hydrodynamics/`, `tests/test_drift.py`.

**Why this role matters:** The slick can drift after release, so looking only at the ships nearest the detected patch can be misleading. The model needs to show how it estimated a possible origin and how uncertain that estimate is.

**Exact tasks**
1. Read OpenDrift's basic examples and determine whether the available version supports the desired time direction/configuration for this case.
2. Implement a simple, independently testable drift interface first: input slick location/time plus wind/current vectors; output a time-stamped trajectory and origin region.
3. Add unit conversions and explicit UTC timestamps. Keep longitude/latitude order consistent.
4. Start with a toy/synthetic current field where expected displacement is known. This validates the code without depending on a remote service.
5. If matching ERA5/CMEMS files are available, wire them in and record their source, units and coverage.
6. Only then test an OpenDrift/OpenOil-based experiment. Document whether the run is forward simulation or backward inference; do not imply reverse-time simulation is automatically a physically validated reconstruction.
7. Return a corridor/ellipse only if the code calculates it. Include particle spread or another explicit uncertainty representation.
8. Write tests for zero current, constant current, missing forcing data, timestamp order and reproducibility.
9. Produce a map-ready GeoJSON corridor for M4/M5.
10. Document limitations such as uncertain windage, currents, slick age, and unknown release volume.

**Deliverables / done means**
- `drift.py` and `origin_corridor.py` with stable inputs/outputs.
- A trajectory CSV/JSON and map-ready corridor.
- Tests for a synthetic known-displacement case.
- A note saying whether the demo output is real-data-based or illustrative.

**Plain-English version:** “I estimate how the oil might have moved between the release and the satellite observation. I need to show the assumptions and the uncertainty. If I only have made-up/test currents, the map must say the origin estimate is simulated, not a verified historical fact.”

### M4 — AIS / Forensics / Backend / Report Generator

**Owns:** `src/forensics/`, `src/api/`, `configs/pipeline.yaml`, API and report tests.

**Why this role matters:** This module connects the origin estimate to vessel tracks, explains why candidates are shown, and provides a repeatable API/report.

**Exact tasks**
1. Define the AIS CSV columns needed: timestamp UTC, MMSI, latitude, longitude, SOG/speed, COG/course, and vessel name/type if legitimately available.
2. Implement a loader that normalises timestamps, coordinate fields and missing values.
3. Create a small, reproducible AIS fixture. If synthetic, label it as synthetic in the file and dashboard.
4. Implement a transparent filter for AIS points/tracks that overlap the origin corridor and time window.
5. Calculate explainable features where the input supports them: time overlap, minimum distance, observed speed change, duration in area. If data is sparse, mark the feature unavailable.
6. Rank candidates with documented rules/weights and return the component values and reasons. Do not present the score as a calibrated probability of guilt.
7. Keep pump-flow estimation as a stretch feature unless the slick volume and loiter duration are defensible. Slick thickness/volume is highly uncertain; show a range and assumptions if attempted.
8. Implement FastAPI endpoints and Pydantic schemas using the contracts in Section 8.
9. Generate a PDF incident report from the same JSON response shown in the UI.
10. Compute a SHA-256 hash of the final PDF and expose it in the UI/report metadata.
11. Test malformed timestamps, empty AIS data, no candidates, duplicate points and missing drift results.

**Deliverables / done means**
- Candidate filtering/ranking module and tests.
- `/health`, `/api/v1/demo-case`, `/api/v1/analyze`, `/api/v1/report`.
- PDF download and hash output.
- Ranking explanation and caveats included in the report.
- No “PHYSICAL_CAUSATION_CONFIRMED” or similar certainty label unless a genuinely validated evidence process supports it; for this student prototype use “candidate ranking” language.

**Plain-English version:** “I compare ship tracking records with the possible place and time of the spill. I show which ships match the available clues and explain why. I also connect the code to the website and make a report the user can download. My system ranks leads; it does not declare a ship guilty.”

### M5 — Dashboard / Integration / Documentation / Video

**Owns:** `ui/`, `README.md`, `ROADMAP.md`, demo script, video, report assembly and submission checklist.

**Why this role matters:** The competition asks for a working prototype video. A strong algorithm hidden in a notebook is not enough; judges need to see the system work.

**Exact tasks**
1. Set up the Leaflet page and create the dark maritime-themed layout without over-designing it.
2. Add a map layer for the scene bounds, slick polygon, origin corridor and candidate vessel tracks.
3. Build an incident information panel: case type, acquisition time, data-source status, model method and warnings.
4. Build a candidate list showing vessel identifier, overlap, available speed-change evidence, score and score explanation.
5. Add loading, empty-result and error states. The UI must not freeze if the API fails.
6. Connect the UI to the agreed API contracts; initially use mock JSON so frontend work does not wait for ML.
7. Add a “Generate report” button and test PDF download and hash display.
8. Maintain the README with setup, commands, data instructions, screenshots and known limitations.
9. Write the competition report outline early and collect each member's technical contribution.
10. Draft the demo narration, record a stable local run, edit to 3–8 minutes, upload to YouTube and verify access.
11. Submit the video link via the correct dashboard before the deadline; keep a screenshot/record of successful submission.

**Deliverables / done means**
- Dashboard that runs locally and can replay the Golden Case.
- Map layers and candidate list use the real API response schema.
- PDF button works.
- README can get a new teammate from clone to demo without verbal help.
- Video link is viewable in private/incognito mode and submitted.

**Plain-English version:** “I build the screen that brings everyone's work together. The user should be able to click Analyze, see the slick and possible origin on a map, inspect candidate ships, and download a report. I also make sure the whole project can be run, explained and submitted on time.”

### 9.1 Shared responsibility

Each member must:
- Attend a 10–15 minute daily check-in.
- Push small commits daily and raise a pull request for integration.
- Add at least one test for important logic in their module.
- Write a short explanation of their module for the report/video.
- Tell the team early if a dependency, dataset, model or API is blocked.
- Help test the full application, not only their own component.

---

## 10. Daily roadmap: 19 October–10 November

The schedule is intentionally milestone-driven. If a task slips, cut stretch scope before delaying integration or the video.

### Phase 1 — Foundation and contracts (19–25 October)

| Date | Main goal | M1 — Vision | M2 — Ingestion | M3 — Drift | M4 — AIS/API | M5 — UI/docs | End-of-day evidence |
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

| Date | Main goal | M1 — Vision | M2 — Ingestion | M3 — Drift | M4 — AIS/API | M5 — UI/docs | End-of-day evidence |
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

| Date | Main goal | M1 — Vision | M2 — Ingestion | M3 — Drift | M4 — AIS/API | M5 — UI/docs | End-of-day evidence |
|---|---|---|---|---|---|---|---|
| **Mon 2 Nov** | Integration day | Fix inference adapter | Fix metadata mismatch | Fix origin schema | Wire analysis endpoint | Wire Analyze button | UI invokes API successfully |
| **Tue 3 Nov** | Map and evidence | Verify polygon output | Verify CRS/coordinates | Verify corridor layer | Verify candidate explanations | Style layers and legend | Map is understandable without narration |
| **Wed 4 Nov** | Full report | Supply model details | Supply source citations | Supply assumptions | Finish PDF contents/hash | Wire report download | Report matches what the UI displays |
| **Thu 5 Nov** | Golden Case rehearsal | Re-run inference | Verify cached data | Re-run drift deterministically | Re-run candidate ranking | Run whole demo twice | Repeat runs give consistent expected output |
| **Fri 6 Nov** | **Milestone 3: feature freeze** | No new architecture changes | No new data-source changes | No new algorithm unless essential | API/report stable | Dashboard and script stable | Complete vertical slice works on a clean start |

**Milestone 3 acceptance:** A user can click Analyze Incident, see the supported results, inspect the candidate ranking and download the report. Any unavailable subsystem is visibly labelled; no hidden mock data is represented as live or verified.

### Phase 4 — QA, video and submission (7–10 November)

| Date | Main goal | M1 | M2 | M3 | M4 | M5 | End-of-day evidence |
|---|---|---|---|---|---|---|---|
| **Sat 7 Nov** | Code freeze + QA | Fix only blocking bugs | Validate source/metadata | Validate drift caveats | Test API/PDF/hash | Freeze code; compile report | Tagged release candidate; report draft complete |
| **Sun 8 Nov** | Record video | Explain model/data | Explain georeferencing | Explain origin estimate | Explain candidate ranking/report | Record/edit demo | Full-length video draft exists |
| **Mon 9 Nov** | Final verification | Confirm results shown | Confirm sources credited | Confirm output labels | Test clean clone and PDF | Upload YouTube; test link; prepare submission | Final video and report ready |
| **Tue 10 Nov** | Submission day | Available for urgent fix | Available for urgent fix | Available for urgent fix | Verify API/report if needed | Submit video link via dashboard | Submission confirmed before deadline |

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

Because GDAL, Rasterio and some geospatial packages can be difficult to install together on Windows, start with a small working environment and add optional dependencies only when needed.

**Core MVP packages:** Python 3.10 or 3.11 (choose one version and pin it), `numpy`, `pandas`, `rasterio`, `shapely`, `fastapi`, `uvicorn`, `pydantic`, `pytest`, and the package used for the chosen UI/report route.

Add `torch`, `segmentation-models-pytorch`, `xarray`, `netCDF4`, `opendrift`, `h3` and `weasyprint` only as required by the selected scope. Use Google Colab for model training if local hardware is insufficient.

### 11.2 Initial setup (Windows PowerShell)

```powershell
# 1. Clone the team repository
git clone <TEAM_GITHUB_URL>
cd sentineltrace

# 2. Create a virtual environment using the agreed Python version
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Upgrade pip and install the pinned project dependencies
python -m pip install --upgrade pip
pip install -r requirements.txt

# 4. Run the test suite
python -m pytest -q

# 5. Start the API (once src/api/main.py exists)
uvicorn src.api.main:app --reload

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
| Vectorization | Convert a known mask region to polygon | Polygon coordinates agree with the known transform within a documented tolerance |
| Vision | Run inference on a fixture | Output mask shape is correct and values are in the expected range |
| AIS loader | Parse timestamps and coordinates | UTC and numeric fields are normalised; bad rows are reported |
| Candidate filter | One ship crosses the corridor/time; another does not | Only the matching track is selected |
| Drift | Constant-current toy example | Direction and displacement match the analytical expected value within tolerance |
| Drift | Missing forcing data | Module reports missing/simulated forcing instead of fabricating a real result |
| Ranking | Known features | Ranking and component scores are deterministic and explainable |
| API | `/health`, demo case and analysis | Valid status and schema; useful errors for invalid requests |
| PDF | Generate report | PDF opens, contains the case ID and caveats, and SHA-256 matches the file bytes |
| UI | API unavailable | Visible error/retry state; no misleading stale “success” |
| Reproducibility | Run the Golden Case twice | Same inputs and deterministic modules produce the same expected output, or differences are documented |

### 12.2 End-to-end acceptance test

A teammate who did not write the code must be able to:

1. Follow README setup from a clean clone.
2. Start the API and dashboard.
3. Load the built-in Golden Case.
4. Click Analyze.
5. See the slick and origin layers (real or clearly labelled illustrative).
6. See candidate ships and the reason for their ranking.
7. Download the report.
8. Check that the report checksum matches the downloaded file.
9. Explain which inputs were real, simulated or missing.

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

Update this section at the end of every day. Replace `Not started` with `In progress`, `Blocked`, or `Done` and add a link to the PR/output.

| Work item | Owner | Status | Evidence / PR link | Blocker / next action |
|---|---|---|---|---|
| Repo, branches, README skeleton | M5 | Not started | | |
| JSON contracts and mock case | M4 + M5 | Not started | | |
| Dataset/licence/label audit | M1 | Not started | | |
| Scene and georeferencing validation | M2 | Not started | | |
| Synthetic drift test | M3 | Not started | | |
| AIS schema and fixture | M4 | Not started | | |
| Dashboard displays mock case | M5 | Not started | | |
| Segmentation baseline/inference | M1 | Not started | | |
| Real or labelled demo scene | M2 | Not started | | |
| Origin corridor output | M3 | Not started | | |
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
