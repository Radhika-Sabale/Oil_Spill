# Stage 1 (M2): SAR ingest, wind gate and CA-CFAR screen

Owner: M2 (Ruchira). Status date: 7 Nov 2026.

Stage 1 is the first step of the SentinelTrace pipeline. Before anyone looks for oil, it answers three questions about a radar scene:

1. What radiometry does this scene actually carry?
2. Is the wind right for seeing slicks at the time of the satellite pass?
3. Where are the dark-spot candidates worth passing on?

Stage 1 is **report-only**. It does not change what the detector (M1) finds. Anything it cannot check is reported as `unavailable` with a reason, never guessed.

---

## 1. What changed

| File | Change | Owner of file |
|---|---|---|
| `app/stage1.py` | **New.** All Stage 1 logic | M2 |
| `tests/test_stage1.py` | **New.** 18 tests, synthetic and offline | M2 |
| `scripts/m2_run_stage1.py` | **New.** Runs Stage 1 on every indexed scene and writes results | M2 |
| `app/pipeline.py` | **Shared file, 8-line hook** (see section 5). Needs agreement from M4 and M5 before merging | Shared |
| `tests/test_vision_fallback.py` | 3-line skip so one test no longer fails on machines without torch. Needs M1's OK | M1 |

Generated outputs (not source code), in `data/m2_out/`:
- `<scene>.stage1.json` for each scene, and `stage1_summary.csv`
- `golden_case_manifest.json` and `gom_cfar_overlay.png` for the Gulf of Mexico Golden Case

---

## 2. What Stage 1 does (`app/stage1.py`)

| Function | Purpose |
|---|---|
| `classify_product(source)` | Reads the scene's source string. Planetary Computer RTC is **terrain-flattened gamma0**, so it is labelled gamma0 and not GRD sigma0 |
| `normalize_incidence(vv_db, incidence_deg)` | Cosine normalization to a reference angle, done in **linear** power. Returns `unavailable` if no angle is supplied |
| `wind_gate(speed_ms)` / `wind_from_metocean(...)` | 3 to 12 m/s gate on 10 m wind at the acquisition time. Result is `pass`, `fail_low`, `fail_high` or `unknown`. Missing wind is never a pass |
| `cfar_screen(...)` | Averages the image to about 100 m cells (in linear power), then flags cells darker than their local surroundings by the threshold. Returns candidate windows and the measured retained fraction |
| `run_stage1(...)` | Combines the above into one status document (`available`, `partial` or `unavailable`) |
| `for_scene(scene, t_sat)` | Runs Stage 1 for a registry scene. Never raises: a failure becomes `unavailable` with a reason |

### Units rule
The chips store VV and VH in **dB**. Normalization and CFAR averaging happen in **linear** power. dB is used only for the final threshold comparison.

### Provisional parameters (reported in every output)

| Parameter | Value | Status |
|---|---|---|
| Wind window | 3 to 12 m/s | From the roadmap |
| CFAR guard / training cells | 4 / 16 (at ~100 m) | From the roadmap |
| CFAR threshold | -3.5 dB | **Provisional**, not tuned |
| Reference incidence angle | 34 degrees | **Provisional** |
| Cosine exponent | 1.0 | **Provisional** |

---

## 3. Libraries required

Stage 1 adds **no new requirement**. Everything it needs is already in `requirements.txt`.

| Library | Needed for | If missing |
|---|---|---|
| `numpy` | All array maths | Stage 1 cannot run |
| `scipy` | Connected components in the CFAR screen | CFAR returns `unavailable` ("scipy not installed") |
| `pyproj` | Reading UTM scenes (the four demo scenes are UTM) | Scene loading fails with a clear georeference error |
| `rasterio` | Reading and writing the GeoTIFF chips | The built-in reader in `app/geo/tiffio.py` handles simple TIFFs only |
| `pytest` | Running tests | Cannot run tests |

Needed only when **downloading** data (steps from the earlier stages of setup):
- `rasterio` and `requests`: used by `scripts/fetch_sentinel1_scene.py` (Planetary Computer, no login) and `scripts/build_metocean_cache.py` (Open-Meteo, no login).
- `copernicusmarine` (optional): CMEMS currents. Needs a free account and two environment variables. Not used in our runs.

Install in one go:

```
pip install -r requirements.txt
```

Optional, only if you want to redraw the overlay image: `matplotlib`. It is not part of the repo.

---

## 4. How to run

**Download the data (internet needed, once):**

```
python scripts/fetch_sentinel1_scene.py --preset mc20
python scripts/fetch_sentinel1_scene.py --preset arabian_sea
python scripts/fetch_sentinel1_scene.py --preset caspian_baku
python scripts/fetch_sentinel1_scene.py --preset santa_barbara

python scripts/build_metocean_cache.py --scene gom_mc20_chronic_slick
python scripts/build_metocean_cache.py --scene arabian_sea_mumbai_offshore
python scripts/build_metocean_cache.py --scene caspian_baku_seeps
python scripts/build_metocean_cache.py --scene santa_barbara_seeps
```

Do not use `--preset all`; it also downloads scenes we do not use.

**Run Stage 1:**

```
python scripts/m2_run_stage1.py
python scripts/m2_run_stage1.py --scene gom_mc20_chronic_slick
```

**Run tests:**

```
python -m pytest tests/test_stage1.py -q
python -m pytest -q
```

Last full run on the team laptop: 165 passed, 10 skipped, 0 failed.

---

## 5. Pipeline hook (proposal, needs M4 and M5 agreement)

`app/pipeline.py`, inside `run()`, after the document is created:

```python
s1 = stage1_mod.for_scene(scene, t_obs)
doc["stage1"] = s1
doc["stage_status"] = {"ingest": s1["status"]}
```

and the final warnings line becomes:

```python
doc["warnings"] = list(s1.get("warnings", [])) + warnings
```

plus one import: `from . import config, scenes as scenes_mod, stage1 as stage1_mod`.

`stage_status` currently has only the `ingest` key. The other stages' keys still need adding by their owners.

---

## 6. Results on the four scenes

Measured with the provisional thresholds above, on these scenes only.

| Scene | Acquired (UTC) | Wind at pass | Wind gate | CFAR windows | Retained fraction |
|---|---|---|---|---|---|
| Gulf of Mexico (MC20) | 2023-09-24 | 3.25 m/s | pass (marginal) | 78 | 2.71% |
| Mumbai offshore | 2024-03-13 | 7.01 m/s | pass | 0 | 0% |
| Caspian / Baku | 2023-10-14 | 0.40 m/s | **fail_low** | 40 | 3.43% |
| Santa Barbara | 2023-08-29 | 1.53 m/s | **fail_low** | 57 | 10.01% |

All four report overall status `partial`, because the RTC chips carry no incidence angle.

Gulf of Mexico visual check (`gom_cfar_overlay.png`):
- Windows sit on the large dark patches in the centre-right. Clear sea is left alone.
- Thin linear dark features on the left are **not** caught at the 100 m level.
- Several windows touch the image edge; real or edge effect is not confirmed.
- Bright point targets (likely vessels or platforms) are correctly ignored.

---

## 7. Known limits (say these in the report)

- Windows are **dark-spot candidates, not confirmed oil.** At about 3 m/s wind, large dark areas can be low-wind smoothing or natural surface films.
- Incidence normalization is **not applied** to the current scenes: RTC chips carry no incidence angle.
- Thresholds are **provisional**. The retained fraction and pixel reduction are measured on one scene each, not a general claim.
- Averaging to 100 m blurs narrow features such as thin slicks and ship tracks.
- The scene downloader chose each image for slick contrast, not wind. Two of the four scenes (Caspian, Santa Barbara) fail the wind gate and should be shown as low confidence.
- Wind is ERA5 10 m wind via Open-Meteo, sampled at the chip centre and acquisition time.
- Currents are from the Open-Meteo marine model, not CMEMS. Wave forcing was unavailable, so Stokes drift is omitted (affects M3's drift work, not Stage 1).
- The ">95% pixel reduction" target from the roadmap is met on the Gulf of Mexico scene (97.3%) and on Mumbai and Caspian, but not on Santa Barbara (90.0%). It has not been shown to hold in general.

---

## 8. Open items

1. M4 and M5 to agree the `stage1` and `stage_status` field names before `pipeline.py` is changed.
2. M1 to confirm the `test_vision_fallback.py` skip, and whether she needs cropped chips from Stage 1 (it currently reports windows only).
3. Decide whether to keep the two failed-wind scenes as "low confidence" or replace them with better-wind dates.
4. Tune the CFAR threshold and `min_cells` on the Golden Case once a labelled reference is available.
