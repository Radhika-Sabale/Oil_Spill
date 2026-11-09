# Phase 10A — Remote Sentinel-1 Asset Accessibility

**Project:** Oil_Spill / SentinelTrace  
**Environment:** Windows PowerShell, project `venv`, Python 3.14.3, Rasterio 1.5.2  
**Run time:** 2026-11-07 10:54:11–10:54:29 Asia/Calcutta (UTC+05:30)

## Summary

The Python environment could not resolve `planetarycomputer.microsoft.com` (`socket.getaddrinfo`: `[Errno 11001] getaddrinfo failed`). Consequently, exact STAC item requests and the Planetary Computer SAS-token request failed before HTTP. No item JSON, signed URL, or raster asset URL was obtained in this run. There was no HTTP authorization attempt and no asset byte-range request. Rasterio was installed, but a pixel-window read was not attempted because no verified signed COG URL was available.

This is a Python/Windows environment DNS failure before connection, not evidence that the STAC API, SAS service, blob assets, or COG ranges are unavailable. No whole asset or chip was downloaded or written.

## Existing project flow and dependencies

Inspected `scripts/fetch_sentinel1_scene.py`. It uses:

1. Python `urllib.request.urlopen` to call Microsoft Planetary Computer's STAC `/search` and `/api/sas/v1/token/sentinel-1-rtc` endpoints.
2. A `token` returned by that SAS endpoint, appended to each `vv`/`vh` asset href.
3. Rasterio/GDAL `/vsicurl/` to read a crop from the signed COG.

The script does not use the `planetary_computer` Python SDK or `pystac`. In the project venv, Python 3.14.3, Rasterio 1.5.2, Requests, and urllib3 were present; `planetary_computer` and `pystac` were absent. No packages were installed or changed.

## Connectivity evidence

### Python DNS and service requests

The diagnostic invoked the project interpreter with an inline, read-only Python check piped to `venv\Scripts\python.exe`. It attempted:

- `socket.getaddrinfo('planetarycomputer.microsoft.com', 443)`
- `GET https://planetarycomputer.microsoft.com/api/sas/v1/token/sentinel-1-rtc`
- For each exact ID: `GET https://planetarycomputer.microsoft.com/api/stac/v1/collections/sentinel-1-rtc/items/{item-id}`

Observed output:

```text
RUN_START 2026-11-07T10:54:11+05:30
PYTHON 3.14.3
RASTERIO 1.5.2
DNS_ERROR gaierror [Errno 11001] getaddrinfo failed
SAS_REQUEST_START 2026-11-07T10:54:17+05:30
SAS_ERROR URLError <urlopen error [Errno 11001] getaddrinfo failed>
```

All four STAC item calls returned the same `URLError <urlopen error [Errno 11001] getaddrinfo failed>`. No HTTP response/status was obtained for the SAS or STAC requests.

### TCP 443

PowerShell command:

```powershell
Test-NetConnection planetarycomputer.microsoft.com -Port 443 -InformationLevel Detailed
```

Run time: `2026-11-07T10:54:27.7720662+05:30` through `2026-11-07T10:54:29.8706977+05:30`.

Relevant result:

```text
ComputerName            : planetarycomputer.microsoft.com
RemoteAddress           :
RemotePort              : 0
NameResolutionSucceeded : False
TcpTestSucceeded        : False
```

The TCP test could not reach the connection stage because it had no resolved address. This is not a TCP refusal/timeout result.

## Four scenes × two bands

“FAILED” below means the attempted operation failed locally at DNS resolution before its target service could respond. It does **not** assert that the item, token service, or asset is invalid or unavailable. “NOT TESTED” means the step was intentionally not attempted because the prior prerequisite (a returned item/asset URL) was absent.

| Exact item ID | Band | STAC metadata retrieval | SAS signing | HTTP range access | Rasterio/GDAL pixel-window read |
|---|---|---|---|---|---|
| `S1A_IW_GRDH_1SDV_20230924T000215_20230924T000240_050462_0613BB_rtc` | VV | **FAILED** — DNS before HTTP | **FAILED** — SAS endpoint DNS before HTTP | **NOT TESTED** — no signed asset URL | **NOT TESTED** — no signed asset URL |
| same item | VH | **FAILED** — DNS before HTTP | **FAILED** — SAS endpoint DNS before HTTP | **NOT TESTED** — no signed asset URL | **NOT TESTED** — no signed asset URL |
| `S1A_IW_GRDH_1SDV_20240313T010329_20240313T010354_052956_066912_rtc` | VV | **FAILED** — DNS before HTTP | **FAILED** — SAS endpoint DNS before HTTP | **NOT TESTED** — no signed asset URL | **NOT TESTED** — no signed asset URL |
| same item | VH | **FAILED** — DNS before HTTP | **FAILED** — SAS endpoint DNS before HTTP | **NOT TESTED** — no signed asset URL | **NOT TESTED** — no signed asset URL |
| `S1A_IW_GRDH_1SDV_20231014T024432_20231014T024457_050755_061DC6_rtc` | VV | **FAILED** — DNS before HTTP | **FAILED** — SAS endpoint DNS before HTTP | **NOT TESTED** — no signed asset URL | **NOT TESTED** — no signed asset URL |
| same item | VH | **FAILED** — DNS before HTTP | **FAILED** — SAS endpoint DNS before HTTP | **NOT TESTED** — no signed asset URL | **NOT TESTED** — no signed asset URL |
| `S1A_IW_GRDH_1SDV_20230829T015857_20230829T015922_050084_0606D7_rtc` | VV | **FAILED** — DNS before HTTP | **FAILED** — SAS endpoint DNS before HTTP | **NOT TESTED** — no signed asset URL | **NOT TESTED** — no signed asset URL |
| same item | VH | **FAILED** — DNS before HTTP | **FAILED** — SAS endpoint DNS before HTTP | **NOT TESTED** — no signed asset URL | **NOT TESTED** — no signed asset URL |

No HTTP status, `Content-Range`, response bytes, asset metadata, or pixel values exist for this attempt. In particular, Chrome's prior metadata access is not counted as proof that Python/GDAL can access these assets.

## Safety and data changes

- No fetcher, bootstrap, preset, or date-window scene selection was run.
- No COG was downloaded or opened.
- No TIFF chip was generated or overwritten.
- No registry, source, M1/M2/M3, solver, or benchmark files were changed.
- No dependencies were installed or upgraded.
- SAS token values and signed URLs were not produced or logged.

## Recommendation

**NO-GO for Phase 10B at present.** The required Python-side path cannot reach the provider because hostname resolution fails, so exact-item retrieval, SAS signing, range reads, and remote Rasterio/GDAL reads remain unverified. Re-run from a Windows environment where Python DNS resolution succeeds; then execute the exact-ID STAC/SAS flow and the eight small range and window-read checks before implementing remote window retrieval.
