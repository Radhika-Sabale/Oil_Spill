# SentinelTrace NuGen Domain Alignment Benchmark

## Purpose

This JSONL contains 51 concise question–answer pairs for domain-alignment and evaluation experiments. It describes the implementation found in this repository and distinguishes implemented behavior from roadmap plans. It is a content artifact only: it has not been uploaded to NuGen, and no alignment or evaluation job has been run.

## Category distribution

| Category | Pairs |
|---|---:|
| SAR fundamentals and VV/VH interpretation | 5 |
| Dark slick candidates and look-alike causes | 5 |
| Backscatter, polarimetric interpretation, and evidence limits | 5 |
| Active M1 architecture, preprocessing, inference, and checkpoint limitations | 8 |
| M2 ingestion, wind checks, CFAR, and preprocessing | 6 |
| M3 advection, forcing, hindcast, and uncertainty | 7 |
| Geospatial masks, polygons, CRS, and provenance | 5 |
| Confidence and metric interpretation | 4 |
| Responsible investigation and attribution | 5 |
| NuGen's supplementary role | 1 |
| **Total** | **51** |

## Repository sources consulted

- `SentinelTrace_Team_Roadmap.md` — planned architecture, user journey, caveats, and separation of M1–M5 responsibilities.
- `README.md` and `docs/ARCHITECTURE.md` — current system description and explicit differences between roadmap targets and implementation.
- `app/ml/model.py`, `app/ml/dataset.py`, `app/ml/infer.py`, `app/ml/fallback.py` — active model definition, band order, preprocessing, tiled inference, fallback behavior, and outputs.
- `models/oil_unet_best.report.json` — checkpoint architecture and reported class validation pixel counts/metrics.
- `app/stage1.py`, `app/pipeline.py`, `docs/README_STAGE1_M2.md` — M2 checks, warnings, CFAR screen, and how Stage 1 relates to the M1 call.
- `app/drift/advection.py`, `app/drift/fields.py`, `app/config.py`, `app/pipeline.py` — M3 integration settings, forcing and fallback representation, and pipeline handoffs.
- `app/geo/raster.py`, `app/geo/geometry.py` — raster georeferencing and mask-to-polygon implementation.
- `tests/test_unet_path.py`, `tests/test_stage1.py`, `tests/test_vision_georef.py`, `tests/test_m3_integration.py` — test definitions used to cross-check implementation contracts. Tests were read, not executed.
- `pyproject.toml` and `requirements.txt` — environment and dependency context.

## Important implementation and scientific caveats

- The active checkpoint is U-Net++ with a `timm-efficientnet-b0` encoder. The code and checkpoint do not establish Prithvi EO 2.0 or DOFA as part of current M1.
- M1 forms three model channels from two SAR bands: the darker band is placed in channels one and three and the brighter band in channel two after ordering by median brightness. It uses the checkpoint's normalization metadata and 512-pixel tiles with 64-pixel overlap by default.
- The checkpoint report has zero validation pixels for class 1 (look-alike), marks it unsupervised, and reports NaN look-alike IoU. The existence of a class output does not demonstrate validated look-alike rejection.
- A dB-threshold fallback can be used when learned inference is unavailable or errors. It is a different detector and is not presented as learned inference.
- Stage 1 provides product/radiometry status, optional incidence normalization, a wind gate, and CA-CFAR dark-spot candidate windows. The main pipeline records these diagnostics but does not feed the CFAR windows as crops to M1 or use the wind result as a hard gate on M1.
- Stage 1 settings such as its wind window and CFAR threshold are documented in code as provisional. A CFAR candidate is not a confirmed oil slick.
- M3 numerically advects an ensemble using selected environmental forcing and assumptions. It estimates plausible paths/origin areas; it cannot prove the actual release location, source, vessel, or cause.
- Synthetic forcing and incomplete forcing coverage limit physical interpretation. Outputs and their source/status should be considered together.
- SAR-dark features are not unique to oil. Calm water, biogenic films, natural seepage, and other conditions can be look-alikes. Satellite imagery alone does not establish responsible-vessel identity.
- The repository does not provide a complete, curated scientific bibliography for every general SAR interpretation statement in this benchmark. Those answers are deliberately qualified and should receive domain-expert review before being used as authoritative scientific guidance.
- The JSON shape follows the task's requested NuGen QA pair format (`question`, `answer`). Actual acceptance, import schema, and behavior in the authenticated NuGen benchmark workflow were not verified in this phase.

## Validation results

Structural validation was run locally against `sentineltrace_benchmark.jsonl`:

- **PASS** — UTF-8 decoding; no UTF-8 BOM.
- **PASS** — 51 lines parsed as JSON objects.
- **PASS** — every object has exactly `question` and `answer`.
- **PASS** — both fields are non-empty strings in every record.
- **PASS** — no duplicate questions (case-insensitive comparison after trimming).
- **NOT PERFORMED** — scientific/domain-expert validation, NuGen import, model alignment, benchmark execution, or any credit-consuming action.
