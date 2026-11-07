# NORSE2019 M3 Forcing Integration — Pre-Hindcast Report

## Status

**Adapter and focused pre-hindcast checks complete. Full hindcast not run.**

The adapter returns an `app.drift.fields.MetoceanField` with `synthetic=False`, `live=False`, and the four components required by M3. It reads only the two checksum-pinned NORSE2019 subset files listed below. Missing inputs, checksum changes, incompatible timestamps, and incomplete common-grid coverage raise `ForcingCompatibilityError`; the adapter has no fallback path.

The Phase 4B integration now exposes `metocean_profile="norse2019"` on the normal `/api/run` and direct `/api/drift` paths. In that mode, `run_drift()` calls the adapter directly, never calls `load_for_scene()`, requires `synthetic=False`, and fails closed on checksum, time, footprint, or later trajectory coverage errors. The default profile continues through `load_for_scene()` unchanged.

## Input integrity and coverage

| Source | Variables used | Source dimensions | Time coverage | SHA-256 |
|---|---|---|---|---|
| MEPS prepared subset | `eastward_wind_10m`, `northward_wind_10m` | time 21 × y 29 × x 27 | 2019-06-12 04:00–2019-06-13 00:00 UTC, hourly | `22a41dad2d5af3308bf26b82d5fb833385c3c1ebd7c21ea353ab25cc372d314f` |
| NorKyst800 prepared subset | `u_eastward`, `v_northward`, depth index 0 (0 m) | time 21 × Y 90 × X 93 | 2019-06-12 04:00–2019-06-13 00:00 UTC, hourly | `8749cedd3db73e512b745757e7695feae7b18813b561115c12730ad1141431f2` |

The adapter pins these checksums in code and also requires them to match the input manifest. It verifies exact time-array equality between the sources and uses UTC Unix epoch seconds, matching M3's `MetoceanField.times` convention. The original prepared files remain unchanged.

## Source-to-M3 mapping

| Source value | M3 field | Units / interpretation |
|---|---|---|
| MEPS `eastward_wind_10m` | `data["u_wind10"]` | m s⁻¹, eastward, 10 m |
| MEPS `northward_wind_10m` | `data["v_wind10"]` | m s⁻¹, northward, 10 m |
| NorKyst `u_eastward` at depth index 0 | `data["u_current"]` | m s⁻¹, eastward surface current |
| NorKyst `v_northward` at depth index 0 | `data["v_current"]` | m s⁻¹, northward surface current |
| Source Unix timestamps | `times` | UTC epoch seconds; 21 hourly points |
| Curvilinear source longitude/latitude arrays | `lons`, `lats` | Regridded to ascending regular 1D axes required by M3 |

MEPS grid winds were already rotated into east/north components during subset preparation. NorKyst's named components are earth-oriented. The adapter does not rotate either set a second time. Wind and current values remain in m s⁻¹. No CODE drifter observations are read or used to build the current field.

## Regridding and M3 output

M3's current schema describes a regular `(time, lat, lon)` grid. The two source products are curvilinear, have different native grid resolutions, and do not share a grid, so direct loading is incompatible. The adapter linearly interpolates each source field from its valid curvilinear points in local metric coordinates onto a regular 0.01° latitude/longitude grid, then retains the largest axis-aligned region with finite values from all four components at all times. It does not extrapolate source fields into the target grid; incomplete target points are discarded before constructing the `MetoceanField`.

- Output dimensions: **time 21 × latitude 50 × longitude 88**.
- Output bounds: **west 2.00°, south 59.56°, east 2.87°, north 60.05°**.
- Output arrays are finite throughout; target domain is within the approved buffered ROI.
- All four components are nonzero at all target grid/time positions in this output. Range checks passed: current speed maximum < 3 m s⁻¹ and wind speed maximum < 50 m s⁻¹.
- Mean speed over the M3 output grid: **0.3733 m s⁻¹ current**, **8.071 m s⁻¹ wind**.

The output grid is a regridded M3 input representation, not a replacement for the native source subsets. It is constructed in memory; no regridded forcing cache is written.

## Interpolation and boundary behavior

Focused checks confirmed that linear scattered interpolation reproduces values at known source-grid nodes within float precision. M3's `MetoceanField.sample()` performs bilinear spatial and linear temporal interpolation. At a cell center and half-hour time, the returned values match the arithmetic midpoint of adjacent hourly samples. Exact first and last timestamps and spatial edges are covered. Just-outside queries are reported as uncovered by `covers()`; M3's sampler clamps them to the nearest boundary. M3 advection separately records such out-of-coverage evaluations. The adapter itself does not silently extrapolate while building its grid.

## Wave/Stokes status

Wave height, period, and direction were not supplied and remain absent. The returned field contains no wave keys, `has_stokes` is false, and `wave_stokes_enabled` is false. M3 therefore omits Stokes drift for this experiment; no substitute wave product was introduced.

## Focused tests

Command:

```powershell
venv\Scripts\python.exe -m pytest -q --basetemp=data\norse2019_forcing\.pytest-tmp tests\test_norse2019_adapter.py
```

Phase 4A adapter checks: **6 passed**. They cover the M3 schema, source-node interpolation, hourly time interpolation, spatial and temporal coverage edges, real nonzero/plausible forcing, disabled waves, pinned checksums, and fail-closed missing/altered-input handling.

## Compatibility findings and next gate

1. `app.drift.fields.load_netcdf()` expects canonical M3 variable names (`u_current`, `v_current`, `u_wind10`, `v_wind10`) and 1D `lat`/`lon` axes. The prepared files instead have source-specific names and curvilinear 2D coordinates. They cannot be passed directly to that loader.
2. The existing `_from_arrays()` path converts NaNs to zero and sorts coordinates as independent axes. It must not be used to load these masked curvilinear source grids directly.
3. The standalone adapter addresses those schema issues and returns the M3 dataclass. The explicit NORSE profile now bypasses the default loader and rejects any field marked synthetic. It also requires full requested time coverage, checks the initial footprint, and rejects solver results that recorded clamped out-of-coverage samples.
4. The field profile is opt-in through `RunRequest.metocean_profile` and `DriftRequest.metocean_profile`, defaulting to `default`. The `/api/run` response records the profile and adapter metadata in its input/drift records and METOCEAN trace.
5. No RK2/RK4, advection, diffusion, origin estimation, KDE, or other M3 numerical algorithm was changed. No CODE drifter was used. No full hindcast was run.

## Phase 4B integration checks

The normal `run_drift()` path accepts `metocean_profile="norse2019"`. `/api/run` and `/api/drift` expose the same explicit option; omitted values preserve the existing default loader path. For NORSE, adapter failures are surfaced as a hard integration error (HTTP 422 at those routes). Preflight rejects any requested hindcast/forecast time outside the 21-hour forcing window and any initial slick footprint outside the M3 field bounds. A per-field sample guard raises before M3 can use an edge-clamped value; post-step coverage metadata is also checked as a second guard.

Focused integration plus adapter tests and M3 regressions: **26 passed** (11 pipeline-injection cases, 6 adapter cases, 9 existing `test_m3_hindcast.py` regressions). Tests prove that the adapter's exact field object reaches M3, the default/synthetic loaders are not called or accepted in NORSE mode, bad/missing inputs and inadequate coverage fail closed, API routes forward the opt-in profile, and the default non-NORSE loader remains selected. The integration tests stop at the solver boundary or use a stub coverage result; they do not perform the NORSE hindcast.
