# Pre-submission Phase — M3 Stability and Reproducibility Audit

**Project:** TideTrace / SentinelTrace (`Oil_Spill`)
**Audit date:** 2026-11-06
**Scope:** repository state, M3 regression checks, saved NORSE2019 artifacts, scientific claims, and reproducibility. No M3 algorithms, parameters, forcing, or saved validation results were changed or regenerated. Pytest used ignored scratch directories under `.pytest_cache/`.

## Executive decision

| Use | Recommendation | Reason |
|---|---|---|
| Controlled prototype/demo | **NO-GO until the normal-scene offline end-to-end test completes successfully.** The focused M3 and profile-routing tests pass, but the full offline pipeline test did not finish within a two-minute bounded run. | The full demo path has not been verified by this audit. This is an incomplete test, not a demonstrated code failure. |
| Hackathon submission as a scientifically validated M3 system | **NO-GO in the current state.** | The full app regression is incomplete, the Phase 5B Markdown summary has stale rounded IoU values and an unqualified “GO for additional validation” recommendation, and Phase 7C explicitly keeps Phase 7D drifter scoring at NO-GO. |
| Submission as a clearly labelled prototype with qualified retrospective results | **Conditional GO after review of the blocking items below.** | Existing evidence supports numerical/adapter behavior and a historical mask comparison, but not completed independent drifter validation, calibrated uncertainty, release-origin accuracy, or real-time prediction. |

## 1. Repository state

- Current branch: `roadmap`; `HEAD` is `ccded7e` (`Merge pull request #2 from Radhika-Sabale/roadmap`). It is one commit ahead of `origin/roadmap` and equals `main`/`origin/main` at the inspected point. No commit or push was made during this audit.
- Git status showed **no staged changes**. Existing unstaged changes: `app/api/drift.py`, `app/api/pipeline.py`, `app/pipeline.py`, and `app/schemas.py`.
- Existing untracked work is M3/NORSE-focused: `scripts/norse2019_adapter.py`, `scripts/run_norse2019_obs_hindcast.py`, `scripts/diagnose_norse2019_errors.py`, `tests/test_norse2019_adapter.py`, `tests/test_norse2019_pipeline.py`, and `data/norse2019_forcing/` plus `data/norse2019_validation/`. No unrelated code changes were apparent from the status and diff review. Their ownership/provenance is not established by Git because these files are untracked.
- The latest merge commit is based on `origin/main`; its `origin/roadmap` parent history includes an inappropriate profane commit subject. This is a history/presentation concern, not a source-code defect. No history was rewritten.
- `git diff --check` completed with no whitespace errors in the tracked diff. No source edits were made. The requested audit document is the only project deliverable from this turn.
- `PROJECT_JOURNAL.md` contains generic `C:\Users\USER\...` setup examples. A workstation-specific temporary-directory detail from an earlier pytest setup failure is intentionally omitted from this copy. The committed-credential test passed; no obvious credential value was found in the scan. No tracked file above 25 MB was found. The prepared forcing files are about 0.27 MB and 1.47 MB; the other NORSE outputs are small reports/plots/JSON/CSV.

### Existing worktree changes reviewed

The four modified tracked files implement the opt-in `metocean_profile="norse2019"` path, pass that field through API schemas/routes, load through the checksum-pinned adapter, and enforce time/space coverage rather than using the default synthetic-capable scene loader. Default profile routing remains separate. These are existing local edits and were not changed in this audit.

## 2. Tests executed

### Completed successfully

| Command | Result | Coverage |
|---|---:|---|
| `venv\Scripts\python.exe -m pytest -q --basetemp=.pytest_cache/phase7a_core_audit tests/test_m3_hindcast.py tests/test_norse2019_adapter.py tests/test_norse2019_pipeline.py` | **26 passed in 19.18s** | 9 numerical/hindcast tests, 6 adapter tests, 11 NORSE pipeline/API integration tests. Includes opt-in routing, no synthetic fallback on NORSE, invalid/missing forcing rejection, insufficient coverage rejection, and the default non-NORSE loader selection test. |
| `venv\Scripts\python.exe -m pytest -q -rs --basetemp=.pytest_cache/phase7a_m3_skip_reasons tests/test_advection.py tests/test_conformance_fixes.py tests/test_land_mask.py` | **19 passed, 4 skipped in 2.04s** | Additional advection, metocean mode/fallback, and coast/land M3 checks. All four skips are land-mask checks because no land mask is cached; pytest recommends `scripts/fetch_land_mask.py --all`. This audit did not fetch it. |
| `venv\Scripts\python.exe -m pytest -q --basetemp=.pytest_cache/phase7a_offline_audit tests/test_offline_boundary.py` | **9 passed in 3.33s** | Network-client import boundary, script parsing, no committed credentials, and dependency-boundary checks. |

### Not completed / environment issue

1. Initial combined invocation using pytest's default temp directory:
   ```powershell
   .\venv\Scripts\python.exe -m pytest -q tests/test_m3_hindcast.py tests/test_norse2019_adapter.py tests/test_norse2019_pipeline.py tests/test_pipeline_offline.py tests/test_offline_boundary.py
   ```
   Result: **40 setup errors**. All failed before test logic because pytest could not create its default numbered temp directory under the sandboxed Windows Temp path (`OSError: could not create numbered dir ... after 10 tries`). This is an environment setup failure, not 40 independent application failures.
2. Combined rerun with `.pytest_cache` as `--basetemp` began executing but produced no final summary; it was interrupted after stalling in the broad offline full-pipeline portion. No reliable pass/fail count is available for that invocation.
3. Isolated normal-scene test:
   ```powershell
   .\venv\Scripts\python.exe -m pytest -vv --basetemp=.pytest_cache/phase7a_fullrun_audit tests/test_pipeline_offline.py::test_full_pipeline_runs_offline
   ```
   Pytest collected the single test and entered execution, but it produced no result for 120 seconds and was interrupted. **Status: incomplete/unknown, not counted as pass or assertion failure.**

### Regression conclusion

The selected M3 and adjacent metocean tests total **45 passed, 4 skipped**. All skips are land-mask tests requiring an uncached file. The offline boundary suite passed. The broader full-app normal-scene regression is **not verified** because its test did not complete in this environment. No live forcing or NORSE hindcast was run as part of this audit.

## 3. Validation artifact consistency

### Checks that agree

- `validation_results.json` records separate successful mineral and soybean historical backward runs, `metocean_profile="norse2019"`, the 21-hour real-forcing interval, disabled Stokes drift, and the endpoint/run configurations.
- `per_observation_metrics.csv` has 31 scored rows: 17 mineral and 14 soybean. Its per-row displacement, IoU, precision, and recall values match the corresponding JSON rows exactly in the audit comparison.
- The JSON aggregate displacement and hull-IoU statistics match `phase6_error_diagnosis.json`. Phase 6's 17 mineral and 14 soybean per-observation rows also match the diagnostic CSV row counts and sample values. The Phase 6 diagnostics explicitly describe corrected metrics and supersede earlier overlap values.
- The forcing files' measured SHA-256 values match `data/norse2019_forcing/manifest.json` and the adapter's pinned input hashes: MEPS `22a41dad2d5af3308bf26b82d5fb833385c3c1ebd7c21ea353ab25cc372d314f`; NorKyst800 `8749cedd3db73e512b745757e7695feae7b18813b561115c12730ad1141431f2`.
- Both stored and corrected diagnostics are descriptive historical-mask comparisons. The saved JSON records no release-origin accuracy claim and identifies Stokes drift as unavailable/disabled.

### Findings needing correction or clarification

- At initial audit, `M3_VALIDATION_REPORT.md` had stale aggregate IoU and precision figures and several stale per-observation IoUs. The authoritative values and corrections are recorded in Remediation Pass 1 below.
- The Phase 5B report said **“GO for additional, carefully scoped observational validation.”** Read alone, this could imply the next drifter comparison is approved. Remediation Pass 1 now records Phase 7C completion and the continuing **Phase 7D NO-GO** pending datum/CRS and local-file provenance verification.
- The output JSON/CSVs and plots are historical artifacts from the prior Phase 5B run. This audit checked internal consistency only and did not re-execute or regenerate them.

## 4. Scientific claims audit

Use these distinctions in demo narration, slides, and submission text:

| Claim category | Evidence/status | Safe description |
|---|---|---|
| Software/numerical correctness | **Partially supported:** the dedicated M3 numerical tests and focused integration tests passed. Full normal-scene E2E did not complete in this audit. | “Focused RK4, hindcast, adapter, and NORSE fail-closed tests pass; full offline pipeline regression still needs a completed run.” |
| Real environmental forcing integration | **Supported for the saved NORSE2019 experiment:** checksum-pinned MEPS winds and NorKyst800 surface currents were loaded through the adapter; Stokes drift was disabled. | “The saved retrospective experiment used real archived wind/current subsets.” Do not imply all application runs or live operations use these forcing products. |
| Historical oil-mask comparison | **Completed:** 31 earlier masks compared with backward ensemble outputs. It is an observation-seeded retrospective reconstruction diagnostic. | “M3 hindcasts were compared with historical NORSE2019 oil masks; results are descriptive and confounded by slick spreading, masks, and finite ensembles.” |
| Independent drifter validation | **Not completed. Phase 7D NO-GO.** Phase 7C cannot verify local CSV provenance or authoritative datum/CRS. | Do not say the iSphere or CODE drifter comparison was run or validated. |
| Release-origin accuracy | **Not established:** exact release coordinates are unavailable for this validation; the evaluation intentionally excludes origin-position error. | Do not claim release-origin location or timing accuracy. |
| Calibrated uncertainty | **Not established:** ensemble percentiles/hulls are algorithm outputs, not empirically calibrated probabilities. | Do not call the envelope a calibrated 90/95% confidence region. |
| Real-time operational prediction | **Not demonstrated by NORSE2019:** the benchmark is a June 2019 retrospective hindcast with archived forcing and no wave/Stokes input. The general app README documents optional live metocean/AIS paths, but that is separate from the benchmark and the satellite path is archive imagery. | Label the NORSE result “historical hindcast,” not “real-time validated prediction.” |

The Phase 7C report remains the controlling decision for drifters. Do not use drifter agreement as evidence for oil-specific spreading even if a later comparison proceeds.

## 5. Reproducibility review

### Available

- Python package metadata specifies Python `>=3.11`; this local environment ran Python `3.14.3`.
- `pyproject.toml` and `requirements.txt` describe core and recommended dependencies. The adapter imports SciPy (`scipy.interpolate` and `scipy.io`), and the hindcast runner imports NumPy, Rasterio, pyproj, Shapely, and Pillow; these are listed as recommended rather than base requirements. A clean reproduction must install them explicitly (for example, `pip install -e ".[recommended,dev]"`). Dependency ranges are not pinned in a complete M3 lock file.
- `data/norse2019_forcing/manifest.json` records the forcing time window, regional bounds, dimensions, units, variables, and SHA-256 hashes. `M3_ADAPTER_REPORT.md` documents source-to-M3 mappings and the Phase 4B fail-closed behavior.
- `M3_VALIDATION_REPORT.md` gives the hindcast command:
  ```powershell
  .\venv\Scripts\python.exe scripts\run_norse2019_obs_hindcast.py
  ```
  The runner writes its JSON, CSV, and PNG outputs to `data/norse2019_validation/`; `scripts/diagnose_norse2019_errors.py` reads the saved run output to produce Phase 6 diagnostics.
- Adapter and pipeline commands are recorded in `M3_ADAPTER_REPORT.md`, and the focused test command used in this audit is listed above.

### Gaps

- The oil-mask GeoTIFFs used by the run are read from `ROOT.parent` in the runner, i.e. from a sibling folder outside this repository. Those inputs are not included in the repository. Although their names and checksums are stored in `validation_results.json`, a fresh checkout needs an explicit acquisition/placement instruction and checksum verification step to reproduce the run.
- There is no dedicated documented one-command adapter-only validation outside pytest; `scripts/norse2019_adapter.py` exposes a loader, while successful preparation is mainly exercised through tests and the main hindcast runner.
- The broad offline full-app test has not completed in this audit. The earlier “30 to 45 seconds on CPU” README note is not a substitute for an observed test result; the isolated regression exceeded 120 seconds here. Investigate runtime/environment causes before relying on that timing for the demo.
- The local drifter CSV is outside the repository and its provenance/CRS remains unresolved in `phase7c_source_reconciliation.md`. It is not a reproducible validation input yet, and must not be included in a Phase 7D scoring workflow until that gate is passed.
- The reproducibility commands assume a Windows `venv` path in the validation report; provide equivalent clean setup instructions for contributors not using this machine, including required optional dependencies and mask dataset retrieval.

## 6. Issues by priority

### Blocking before a confident demo/submission

1. Complete the offline normal-scene full-pipeline regression and record its outcome. The initial run was blocked by pytest's default Temp path; Remediation Pass 1 identified a Windows loopback socketpair stall before application code starts. This remains unverified on this host.
2. Correct stale aggregate and per-observation metrics in `M3_VALIDATION_REPORT.md` and qualify its prior recommendation with the Phase 7C **NO-GO for Phase 7D**. Completed in Remediation Pass 1.
3. In all pitch/demo material, distinguish historical mask comparison from independent drifter validation, release-origin accuracy, calibrated uncertainty, and real-time performance.

### Non-blocking but important

- Add clean-checkout instructions for acquiring/verifying the external oil-mask inputs and a reproducible adapter-only check.
- Pin or record the exact Python/dependency versions for the NORSE adapter and hindcast environment.
- Review the profane commit subject already present in `origin/roadmap` before presenting repository history to judges; do not rewrite shared history without team coordination.
- After fixing any issues, rerun the full test suite and capture a fresh report; do not regenerate existing scientific outputs unless separately approved.

## 7. Initial recommendation (superseded by section 9)

**Demo readiness: NO-GO pending a completed normal-scene offline end-to-end test.** The focused tests support the M3 integration path, but they do not establish the full application path for a live demo.

**Submission readiness: NO-GO as a validated scientific system.** A clearly labelled prototype submission may become ready after the blocking test/report corrections are reviewed. Keep Phase 7D at **NO-GO** until datum/CRS and local drifter provenance are verified. Present the existing NORSE2019 results only as retrospective, real-wind/current, oil-mask comparison diagnostics with Stokes drift disabled and no release-origin accuracy claim.

## 8. Remediation Pass 1 — 2026-11-07

### Validation report corrections

Updated `M3_VALIDATION_REPORT.md` from authoritative `validation_results.json` and `per_observation_metrics.csv` values. No JSON, CSV, plot, mask, or forcing artifacts were regenerated or changed.

- Mineral / soybean mean hull IoU corrected from `0.027 / 0.156` to `0.028 / 0.158` (3 decimal places; exact means `0.0278228188 / 0.1576657574`).
- Mean hull precision corrected from `0.047 / 0.193` to `0.048 / 0.195`; mean mask recall and raster-footprint fractions were already consistent (`0.295 / 0.407` and `0.848 / 0.879`).
- Per-observation table checked against every scored row. IoU corrections were applied at 06:10:21, 06:18:44, 06:24:40, 06:32:45, 10:58:07, 11:10:58, and 11:24:23 UTC (the 06:32:45 entry applies to both oils). All displayed centroid displacements and the remaining IoUs agree with the corresponding CSV/JSON values at their displayed precision.
- Added explicit wording: Phase 7C source reconciliation is complete; Phase 7D remains NO-GO because the local drifter datum/CRS and provenance are unverified; independent drifter spatial validation has not been performed.

### Normal-scene regression timeout diagnosis

The audit's isolated command was rerun with faulthandler diagnostics:

```powershell
.\venv\Scripts\python.exe -m pytest -vv -o faulthandler_timeout=60 --basetemp=.pytest_cache/remediation_fullrun tests/test_pipeline_offline.py::test_full_pipeline_runs_offline
```

**Observed result:** no assertion result after approximately 120 seconds; the process was stopped. Pytest entered the test, but the faulthandler stack showed the test blocked in `TestClient.__enter__()` while AnyIO created a Windows asyncio event loop: Python 3.14.3 `asyncio.ProactorEventLoop._make_self_pipe()` -> `socket.socketpair()` -> `socket._fallback_socketpair()` -> blocking `accept()`. A separate read-only probe of `socket.socketpair()` also failed to return within 10 seconds in this environment. This locates the stall before the `/api/run` request and before M3/data processing.

**Classification:** environment/runtime loopback socket setup stall. The trace does not show dependency installation/download, external data access, numerical drift work, or an application assertion failure. Because the fallback's `accept()` has no timeout and the standalone socketpair probe reproduced the stall, waiting longer (up to 10 minutes) is not a useful or safe way to test the unchanged case here. The normal-scene regression remains **incomplete/unknown**, not passed and not a proven code defect. Rerun it on an environment where Windows loopback socketpair completes before calling the full demo verified.

### Verification commands and results

| Command | Duration/result |
|---|---|
| `venv\Scripts\python.exe -m pytest -q -rs --basetemp=.pytest_cache/remediation_m3_audit tests/test_m3_hindcast.py tests/test_norse2019_adapter.py tests/test_norse2019_pipeline.py tests/test_advection.py tests/test_conformance_fixes.py tests/test_land_mask.py` | **45 passed, 4 skipped in 41.70s.** The four skips are `test_land_mask.py` checks requiring an uncached land mask. |
| `venv\Scripts\python.exe -m pytest -q --basetemp=.pytest_cache/remediation_offline_audit tests/test_offline_boundary.py` | **9 passed in 5.06s.** |
| Read-only inline Python artifact consistency check over the Markdown report, JSON, CSV and forcing manifest | **PASS in about 1.4s.** Recomputed aggregate displacement, IoU, precision, recall, and footprint fraction; matched the 31 observation keys and audited displacement/IoU/precision/recall values across JSON/CSV; matched all 17 displayed timestamp rows/cells to saved metrics; confirmed forcing subset sizes and SHA-256 values; checked Phase 7C/7D wording. |
| `git diff --check` | **PASS.** No whitespace errors in the tracked diff. |

The previously passing full suite counts are not a substitute for the blocked full-pipeline regression. No live-forcing experiment or NORSE hindcast was run. No source code, numerical parameters, forcing, or saved validation outputs were changed.

## 9. Final GO / NO-GO recommendation

**Controlled demo on this audited environment: NO-GO.** The normal-scene end-to-end regression cannot start its TestClient because loopback socketpair setup blocks before the request. The focused M3 tests pass, but they do not establish this full path. A demo on another machine may be reassessed only after this same test completes there.

**Submission as a scientifically validated M3 system: NO-GO.** Phase 7C source reconciliation is complete, but Phase 7D is explicitly **NO-GO** and independent drifter spatial validation has not been performed. The only real-world M3 evidence in this package is a retrospective NORSE2019 oil-mask comparison with archived MEPS winds, NorKyst800 currents, and Stokes drift disabled; it does not establish release-origin accuracy, calibrated uncertainty, full slick-spread accuracy, or real-time performance.

**Documentation remediation: GO.** The Phase 5B Markdown aggregates and per-observation table now match the authoritative JSON/CSV at the displayed precision, and its Phase 7C/7D status is explicit. A green documentation check does not change the two NO-GO decisions above.

## 10. M3 Regression Verification — Windows Loopback Workaround (2026-11-07)

### Runtime and dependency versions

| Component | Detected version/platform |
|---|---|
| OS | Windows 11, build `10.0.26200`, 64-bit |
| Python | CPython `3.14.3`, 64-bit; `py -0p` reports no additional installed Python interpreters |
| FastAPI | `0.162.0` |
| Starlette | `1.10.0` |
| HTTPX | `0.28.1` |
| pytest | `9.2.0` |
| AnyIO | `4.16.0` |
| Uvicorn | `0.54.0` |

The installed metadata constraints are satisfied: FastAPI requires Starlette `>=0.46.0`; Starlette's `full` extra constrains HTTPX to `>=0.27.0,<0.29.0` (the installed `0.28.1` qualifies) and AnyIO to `>=4.0.0,<5` (the installed `4.16.0` qualifies). The project's Python floor is `>=3.11`. This does not prove the absence of every library bug, but there is no version-constraint conflict explaining this stall.

### Test scope and execution

The original regression is the single end-to-end case `tests/test_pipeline_offline.py::test_full_pipeline_runs_offline`. It uses the real FastAPI app and `TestClient`, blocks non-loopback network access, creates a self-test SAR scene and cached metocean fixture, seeds AIS from a generated track, posts to `/api/run`, and asserts pipeline stages and output content. This is the original assertion scope; it has not been changed or mocked out.

The two exact Windows attempts recorded in Pass 1 were:

```powershell
.\venv\Scripts\python.exe -m pytest -vv --basetemp=.pytest_cache/phase7a_fullrun_audit tests/test_pipeline_offline.py::test_full_pipeline_runs_offline
```

```powershell
.\venv\Scripts\python.exe -m pytest -vv -o faulthandler_timeout=60 --basetemp=.pytest_cache/remediation_fullrun tests/test_pipeline_offline.py::test_full_pipeline_runs_offline
```

Both entered the single test and were stopped after approximately 120 seconds without a pass/fail assertion result. The second attempt's faulthandler evidence is retained in section 8. The relevant stack frames were:

```text
socket.py:298                  accept
socket.py:633                  _fallback_socketpair
asyncio/proactor_events.py:786 _make_self_pipe
starlette/testclient.py:559    TestClient.__enter__
tests/test_pipeline_offline.py:103  test_full_pipeline_runs_offline
```

The same Python standard-library `socket.socketpair()` call had separately failed to return within 10 seconds when invoked without FastAPI, Starlette, HTTPX, or pytest. The active implementation is `socket._fallback_socketpair`, which creates a TCP pair on loopback and blocks in `accept()`. The test stack therefore stops while Windows Proactor asyncio initializes its self-pipe, before `TestClient` issues `/api/run`; this is not slow M3 work or a data download.

### Linux/WSL and CI availability

- `wsl.exe --status` and `wsl.exe --list --verbose` report that Windows Subsystem for Linux is not installed. No alternate Python interpreter is registered (`py -0p`), and Docker/Podman/Bash are not available from this environment. No Linux execution was possible.
- The current repository tree at `HEAD` (`ccded7ee4ec874048cb8c01c97900f6482909982`) is identical to `origin/main`; `git ls-tree` found no `.github/workflows/` files or other CI workflow configuration. The repository has no existing GitHub Actions Ubuntu job to run. Read-only GitHub checks found no matching workflows in code search; requests for common workflow filenames returned 404. No workflow was created, dispatched, or pushed.
- The Python package metadata and `pyproject.toml` provide a Linux-capable dependency/test setup in principle, but that is not the same as an existing CI run. Adding an Ubuntu workflow would require a repository change and push, so it was outside this investigation's restrictions.

### Decision

**The full normal-scene regression is still NOT VERIFIED.** The evidence strongly localizes the observed stall to this Windows 11 / CPython 3.14.3 loopback fallback path, independently of the installed FastAPI/Starlette/HTTPX constraint set. Because no Linux/WSL runtime or existing Ubuntu GitHub Actions workflow is available, there is no cross-platform run here to prove that Linux passes or that all Windows installations are affected. Do not label this regression as passed. The next verifiable route is to run the exact test command above on a working Linux runner, or on Windows where standalone `socket.socketpair()` completes.

Only this audit document was updated in this pass. Project code, tests, dependencies, workflow configuration, M3 parameters, and validation outputs were left unchanged; no commit or push was made.
