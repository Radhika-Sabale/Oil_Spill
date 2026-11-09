# Exact Sentinel-1 RTC STAC Item Metadata Verification

**Investigation type:** Metadata-only. No COG, raster chip, or other raster data was downloaded or read.

## Result

The four official item endpoint requests could not reach the Microsoft Planetary Computer host from this environment. The local PowerShell requests failed with `No such host is known. (planetarycomputer.microsoft.com:443)`; the browser web tool also reported each endpoint as inaccessible. No HTTP response was received, so no HTTP status code is available. This is a DNS/host access failure in the investigation environment, not evidence of an HTTP error, a missing STAC item, or a missing asset.

Accordingly, the response JSON, returned IDs, collection values, asset keys and properties, geometries, projection metadata, and live URL access could not be verified. Values shown below as “registry says” come only from the project's `data/sar/scenes.json`; they are not represented as newly confirmed STAC metadata.

## Endpoint checks

Official endpoint pattern used:

`https://planetarycomputer.microsoft.com/api/stac/v1/collections/sentinel-1-rtc/items/{item-id}`

| Requested ID / scene | Endpoint result | Valid STAC JSON / returned ID | Collection | `vv` and `vh` asset metadata | Lightweight asset access |
|---|---|---|---|---|---|
| `S1A_IW_GRDH_1SDV_20230924T000215_20230924T000240_050462_0613BB_rtc` / `gom_mc20_chronic_slick` | DNS/host resolution failed (`No such host is known`); no HTTP status | Not obtained; exact returned-ID match cannot be assessed | Not obtained | Presence, media types, roles, and URL fields unknown | Not attempted; no asset URLs obtained |
| `S1A_IW_GRDH_1SDV_20240313T010329_20240313T010354_052956_066912_rtc` / `arabian_sea_mumbai_offshore` | DNS/host resolution failed (`No such host is known`); no HTTP status | Not obtained; exact returned-ID match cannot be assessed | Not obtained | Presence, media types, roles, and URL fields unknown | Not attempted; no asset URLs obtained |
| `S1A_IW_GRDH_1SDV_20231014T024432_20231014T024457_050755_061DC6_rtc` / `caspian_baku_seeps` | DNS/host resolution failed (`No such host is known`); no HTTP status | Not obtained; exact returned-ID match cannot be assessed | Not obtained | Presence, media types, roles, and URL fields unknown | Not attempted; no asset URLs obtained |
| `S1A_IW_GRDH_1SDV_20230829T015857_20230829T015922_050084_0606D7_rtc` / `santa_barbara_seeps` | DNS/host resolution failed (`No such host is known`); no HTTP status | Not obtained; exact returned-ID match cannot be assessed | Not obtained | Presence, media types, roles, and URL fields unknown | Not attempted; no asset URLs obtained |

This status distinguishes the observed DNS failure from an HTTP 4xx/5xx response. There was no response from which to conclude “item not found.” Similarly, the assets are **unverified**, not confirmed missing or accessible.

## Metadata comparison with the scene registry

The registry (`data/sar/scenes.json`) contains these expected records:

| Scene | Registry `source` item ID | Registry `t_sat` | Registry CRS | Registry bounds (lon/lat) | STAC response comparison |
|---|---|---|---|---|---|
| `gom_mc20_chronic_slick` | `S1A_IW_GRDH_1SDV_20230924T000215_20230924T000240_050462_0613BB_rtc` | `2023-09-24T00:02:27.804136Z` | EPSG:32616 | [-89.086792, 28.835617, -88.853793, 29.040577] | Not possible: no item response |
| `arabian_sea_mumbai_offshore` | `S1A_IW_GRDH_1SDV_20240313T010329_20240313T010354_052956_066912_rtc` | `2024-03-13T01:03:42.419107Z` | EPSG:32643 | [71.491372, 18.946853, 71.708384, 19.153216] | Not possible: no item response |
| `caspian_baku_seeps` | `S1A_IW_GRDH_1SDV_20231014T024432_20231014T024457_050755_061DC6_rtc` | `2023-10-14T02:44:45.075839Z` | EPSG:32639 | [50.348997, 40.089884, 50.610242, 40.290235] | Not possible: no item response |
| `santa_barbara_seeps` | `S1A_IW_GRDH_1SDV_20230829T015857_20230829T015922_050084_0606D7_rtc` | `2023-08-29T01:59:10.443231Z` | EPSG:32611 | [-119.996664, 34.270329, -119.744111, 34.479732] | Not possible: no item response |

The item IDs encode product sensing intervals beginning at `00:02:15`, `01:03:29`, `02:44:32`, and `01:58:57` UTC respectively; the registry timestamps are approximately 12–13 seconds after those encoded starts. This is an **unresolved timestamp interpretation discrepancy**, not a proven data error: no STAC `datetime` field was retrieved, and a product interval start need not equal the item `datetime` or the registry's selected scene timestamp. Do not change registry timestamps based only on the identifier strings. Verify the returned STAC `datetime`, the project's original chip metadata, and the intended meaning of `t_sat` before any correction.

Registry footprints and CRS are recorded above, but no STAC geometry or projection fields could be compared. The registry does not record a STAC geometry or asset-level projection metadata.

## Sources and access status

- Local expected IDs and comparison values: `data/sar/scenes.json`.
- Direct endpoints attempted: the four URLs formed using the endpoint pattern above. The official host could not be resolved/accessed in this environment.
- Microsoft Planetary Computer's [Sentinel-1 RTC explorer](https://planetarycomputer.microsoft.com/explore?c=124.0274%2C-16.494&d=sentinel-1-rtc&z=9) is a public collection reference, but it does not establish the status of these four specific item records or assets.

No source item was substituted. No raster or sidecar files were created or changed.

## Next verifiable action

Retry the four exact item JSON GETs from a machine/network where `planetarycomputer.microsoft.com` resolves. Save the HTTP status and response body; parse and compare the returned `id`, `collection`, `datetime`, `geometry`, `proj:*` fields, and `assets.vv`/`assets.vh` `type`, `roles`, and `href`. Only then issue lightweight HTTP `HEAD` or byte-range requests to those returned asset URLs, confirming a successful response and range behavior without reading a complete COG. An asset URL in JSON alone is not proof the object can be accessed.

## Decision

NO-GO — exact items or required assets could not be verified
