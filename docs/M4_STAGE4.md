# M4 Stage 4: kinematic and mass-balance forensics

Investigative candidates only; not proof of causation or a finding of guilt.

## What Stage 4 adds
- Candidate evidence: each AIS candidate carries its score, the reasons, an evidence quality (low, medium, high), the assumptions made and a list of unavailable features.
- H3 index (resolution 7): app/ais/h3index.py uses H3 cells as a pre-filter around the origin zone and as the source of h3_cells. The exact distance filter stays the authority. The report prints an equivalence check (direct filter vs H3, vessels missed by H3, consistent yes/no). H3 is optional: without the h3 package the report says the index is unavailable and the exact filter runs alone.
- Reachability: a vessel with a gap in its track is checked against the origin zone using an assumed maximum speed. A gap is a missing broadcast, not evidence of intent.
- Dark target: reported as unavailable with a reason, because this repository has no SAR vessel-target detection. A missing detection is never reported as "no vessel there".
- Volume and flow: min / nominal / max ranges, only when a measured slick area exists. Otherwise n/a (unavailable).
- Integrity seal: the PDF is generated once and stored. Its SHA-256 is recorded and can be recomputed and compared.

## Contract
Stage4Verdict and Stage4Candidate in app/schemas.py. Unknown values are null, never guessed. dark_target_match.status is unavailable, detected or not_detected_in_supported_imagery. Ranges satisfy min <= nominal <= max and are never negative.

## Endpoints used by the dashboard
- GET /api/report/{job_id}/pdf : the stored PDF
- GET /api/report/{job_id}/sha256 : sha256, recorded_sha256, matches_recorded
- GET /api/health : shows whether the server is up

The dashboard should show unavailable and n/a as explicit states, not blanks or zeros.

## Run and verify
1. One-time setup while online: python scripts/bootstrap_demo.py
2. pip install -r requirements.txt
3. python -m pytest tests -q
4. python -m uvicorn app.main:app --port 8000 (keep this window open)
5. In a second window run the probe, download the PDF and compare: (Get-FileHash .\report.pdf -Algorithm SHA256).Hash must equal the sha256 value from the API.

## Known limits
- The Mumbai and Baku AIS scenes are simulated and labelled as such. Only the Gulf of Mexico and Santa Barbara scenes use real AIS.
- Tracks that cross the antimeridian are not tested.
- The score is a prioritisation aid from documented weights. It is not a probability and is not calibrated against ground truth.
- A PDF and checksum show a file is unchanged since generation. They do not make it legally admissible.
- Two M1 vision tests need data/sar files and PyTorch, which are not installed on every machine.
