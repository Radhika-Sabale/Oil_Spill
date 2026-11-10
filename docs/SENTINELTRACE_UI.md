# SentinelTrace console — how to run it and what it shows

The console (`/console`) is the SentinelTrace front end for the existing analysis
pipeline. It adds a five-stage status strip, REAL / SIMULATED / MISSING input
badges, uncertainty blocks, candidate evidence, assumptions and limitations, a
real-vs-modelled map legend, and a downloadable dossier PDF with its SHA-256.

Everything is served from this repository. No CDN, remote font, remote tile or
web call is used, so the console works with the network unplugged. The landing
page hero plays a video loop from `app/static/media/hero-loop.mp4`; there is no
remote media request, and reduced-motion visitors get the still backdrop.

## Start

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

- Landing page: <http://127.0.0.1:8000/>
- Console: <http://127.0.0.1:8000/console>

## Replay the Golden Case

The Gulf of Mexico MC20 chronic-slick scene is the reference case.

```bash
curl -X POST http://127.0.0.1:8000/api/run \
  -H "Content-Type: application/json" \
  -d '{"scene_id":"gom_mc20_chronic_slick","job_id":"job_demo",
       "hindcast_hours":48,"forecast_hours":36,"search_radius_km":10,
       "origin_window_hours":3}'
```

Then open <http://127.0.0.1:8000/console#job=job_demo>. A case link is a
fragment, so it also loads when pasted into an already-open console.

Attribution needs AIS rows. If `/api/health` reports `ais_rows: 0`, the run
finishes with no suspects and says so, rather than inventing one.

## Five stages

| Stage | Status shown | Why |
| --- | --- | --- |
| 1 Ingest & gate | **Unavailable** | `app/stage1.py` exists but nothing writes a `stage1` block into the job document, so there is no wind gate, incidence status or CA-CFAR result to show. |
| 2 Segment | Done | Oil polygons and look-alikes from the detector actually used. |
| 3 Hindcast & forecast | Done | Estimated origin zone, cone, forecast track. |
| 4 Attribute | Done | Ranked candidates, or an explicit "no candidate passed". |
| 5 Present & package | Done | The analysis document the page and the dossier are both rendered from. |

Hovering or focusing a stage chip shows the reason. The same reasons appear on
the **Stages** tab.

## Data status

| Badge | Meaning |
| --- | --- |
| ● REAL | Measured or recorded: a SAR product actually read, a recorded AIS feed, a cached metocean cube. |
| ▲ SIMULATED | Generated values that are never presented as observations (for example a synthetic AIS scene). |
| ✕ MISSING | The input is not present for this case; the text says why. |

Status always comes with a word, not colour alone, and each badge carries a
`title` with its source. The legend under the map separates what was observed
from what the model drew.

## Where the data comes from

`app/static/js/adapter.js` maps the current responses into one
`sentineltrace.analysis/1` document. The repository has no agreed cross-route
five-stage contract (`app/schemas.py` is per route, plus Contract A and
`Stage4Verdict`), so the document is *derived* and labelled that way. The
adapter probes `/openapi.json`; when a dedicated analysis endpoint exists it
uses it, and the **Data** tab shows which mode is in use ("legacy route" is
shown in the header when mapping is used).

## Dossier PDF

**Dossier** tab → *Download dossier*. The PDF is written in the browser from the
same analysis document the page renders (`app/static/js/dossier.js`); nothing is
recomputed and the backend is untouched.

- The SHA-256 on the card is the hash of the exact bytes offered for download.
- A file cannot contain its own hash, which the PDF states.
- *Verify a dossier* hashes a file you select with Web Crypto and prints
  MATCH or MISMATCH.
- The format is described as **PDF** only. No PDF/A validator (veraPDF) has been
  run, so PDF/A is not claimed.
- A PDF plus a checksum is an integrity check. It does not establish that a
  vessel released oil.

## Known gaps

- No trained segmentation checkpoint (`models/oil_unet_best.pt`), so the dark-patch
  baseline runs and is named as the detector everywhere. Its IoU on the validation
  tiles is 0.000: treat its polygons as proof the pipeline runs, not as a measurement.
- `data/m2_out/golden_case_manifest.json` is referenced by
  `docs/README_STAGE1_M2.md` but does not exist, so Golden Case ground truth is
  shown as missing.
- Stokes drift is omitted when the cached forcing has no usable wave field; the UI
  says so instead of drawing it.

## Tests

```bash
python -m pytest tests -q --ignore=tests/e2e
```

`tests/e2e` needs Playwright, which is not installed here. `tests/test_ui_contract.py`
guards the UI rules: five stages present, no remote assets, text plus icon on every
data badge, no compliance or chain-of-custody phrasing, PDF/A mentioned only as
not validated, and the dossier built from the rendered document.
