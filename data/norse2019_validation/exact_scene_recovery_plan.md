# Exact Sentinel-1 RTC Scene Recovery Plan

**Status:** No raster data was downloaded. Exact STAC item existence, VV/VH asset presence, and asset accessibility could not be verified from this environment because the Planetary Computer hostname did not resolve. Recovery is therefore **not yet approved to execute**; the item IDs below remain those recorded in the local registry.

## Inspection findings

Reviewed:

- `scripts/fetch_sentinel1_scene.py`
- `scripts/bootstrap_demo.py`
- `data/sar/scenes.json`
- `app/geo/raster.py::write_geotiff`

### Current fetch behavior

`fetch_sentinel1_scene.py` does **not** support exact-item retrieval. It only supports a named preset or a latitude/longitude query. `search()` posts a geographic box, date interval, and collection to the STAC `/search` endpoint. `fetch()` takes the first candidates, may rank them based on an image-derived screen score, and then writes the first usable candidate. It does not accept a requested item ID or check that a selected item's ID equals the registry's recorded source ID. Re-running the current script could therefore select a different acquisition and overwrite the expected scene filename.

`bootstrap_demo.py` calls that candidate-search path for its presets, by default `mc20` and `arabian_sea`; it cannot pin the four registry item IDs. Do not use the current preset/bootstrap commands for exact recovery.

### Smallest safe implementation to add

Add an explicit `--item-id` mode to `fetch_sentinel1_scene.py`, separate from preset/date-window search:

1. Require exactly one mode: `--item-id` or existing `--preset` / `--lat --lon`. Reject ambiguous combinations.
2. Fetch the item directly from `https://planetarycomputer.microsoft.com/api/stac/v1/collections/sentinel-1-rtc/items/{URL-encoded-item-id}`.
3. Before opening assets, require the response `collection` to equal `sentinel-1-rtc` (if present) and `item["id"] == requested_item_id` exactly. Any mismatch, 404, parse error, or missing VV/VH key is a hard failure. Do not call `search()` or try another item on this path.
4. Require both `vv` and `vh` assets. Obtain the collection's SAS token as today, then use the existing `cut_chip()` windowed VV/VH COG read and conversion procedure with the matching preset center, 22 km size, and existing `max_side=2048` limit.
5. Check the returned chip metadata `item_id` against the requested ID again before writing. Also check the STAC datetime against the registry acquisition (same exact acquisition time; the registry `t_sat` is a derived value and may differ by a few seconds from product-start time, so validate against the product ID/acquisition interval and retain the existing indexed `t_sat` unless the original generator's `datetime` provenance can be confirmed).
6. Preserve output names `data/sar/<scene_id>.tif` and the source COG's projected CRS/affine from the current `cut_chip()` logic. Write to a temporary sibling file, inspect it, then atomically move it into place only if the expected destination is absent. Refuse overwrite by default. This prevents partial output and accidental replacement.
7. Preserve the existing registry scene ID, title, `t_sat`, bounds, and related metadata; set `source` to the exact item ID. Do not update `scenes.json` until output validation succeeds. If source-provided CRS differs from the registry CRS, abort rather than reprojecting or silently changing the scene.
8. Report returned item ID, asset keys, output path, dimensions, CRS, affine, and byte size. No retry may switch item IDs.

The fetch script already contains the intended chip processing: center-based 22 km window, native projected COG grid, conversion of linear gamma0 to dB via `10*log10`, float32, VV then VH band order, georeferenced GeoTIFF. The local scene registry supplies centers, output names, expected CRS, and source item IDs.

## Item verification gate

Attempted a metadata-only GET for each official item endpoint:

`https://planetarycomputer.microsoft.com/api/stac/v1/collections/sentinel-1-rtc/items/{item-id}`

The request failed before reaching the service with `No such host is known. (planetarycomputer.microsoft.com:443)` for all four items. The browser search/open tool also could not retrieve the direct item JSON, and exact-ID search returned no indexed results. Therefore this investigation cannot claim that the items currently exist, that their STAC records contain both `vv` and `vh` assets, or that their assets are accessible. No asset URL or file-size metadata was available.

Before running any extraction, on a network where DNS/service access works, query all four item endpoints and require:

- HTTP success for the exact item endpoint;
- returned item ID exactly equals the requested ID;
- returned collection is `sentinel-1-rtc`;
- both `vv` and `vh` assets are present and have accessible COG URLs;
- source item geometry/CRS covers the intended 22 km crop;
- COG metadata confirms each asset's CRS, pixel size and nodata conventions.

The two bands are cloud-optimized GeoTIFF assets. A metadata/HEAD or small byte-range probe can verify access without downloading the full COG. The later `cut_chip()` windowed read will transfer COG ranges needed for the requested chip; that is the actual chip acquisition and must wait until explicitly authorized.

## Scene manifest and planned output commands

The following commands are **future commands**, valid only after implementing the `--item-id` mode above and verifying all four STAC item records and assets. They are not executable against the current script, and they were not run. Each command should load its scene center/metadata from the registry or use these documented preset centers. Proposed argument names include `--item-id` and `--scene-id`; the implementation should reject missing or mismatched registry entries.

Run from the repository root in PowerShell:

```powershell
python scripts/fetch_sentinel1_scene.py --item-id S1A_IW_GRDH_1SDV_20230924T000215_20230924T000240_050462_0613BB_rtc --scene-id gom_mc20_chronic_slick
python scripts/fetch_sentinel1_scene.py --item-id S1A_IW_GRDH_1SDV_20240313T010329_20240313T010354_052956_066912_rtc --scene-id arabian_sea_mumbai_offshore
python scripts/fetch_sentinel1_scene.py --item-id S1A_IW_GRDH_1SDV_20231014T024432_20231014T024457_050755_061DC6_rtc --scene-id caspian_baku_seeps
python scripts/fetch_sentinel1_scene.py --item-id S1A_IW_GRDH_1SDV_20230829T015857_20230829T015922_050084_0606D7_rtc --scene-id santa_barbara_seeps
```

Expected outputs:

- `E:\OneDrive\Desktop\Hackathon material\PCCOE IGC\Oil_Spill\data\sar\gom_mc20_chronic_slick.tif`
- `E:\OneDrive\Desktop\Hackathon material\PCCOE IGC\Oil_Spill\data\sar\arabian_sea_mumbai_offshore.tif`
- `E:\OneDrive\Desktop\Hackathon material\PCCOE IGC\Oil_Spill\data\sar\caspian_baku_seeps.tif`
- `E:\OneDrive\Desktop\Hackathon material\PCCOE IGC\Oil_Spill\data\sar\santa_barbara_seeps.tif`

Expected CRS in the existing registry, in the same order: EPSG:32616, EPSG:32643, EPSG:32639, EPSG:32611. Expected data are two float32 dB bands (VV, VH), with native projected georeferencing, cropped around the existing scene centers. Actual dimensions/resolution are determined by the exact assets and window and are not in the registry.

## Transfer-size estimate

No actual remote size metadata was obtained. The source script says a windowed 2048-pixel chip costs “a few megabytes,” but this is a code comment, not a measured transfer for these specific items. The output chip is capped at 2048 by 2048 pixels and has two float32 bands; an uncompressed full-size pixel array would be up to 32 MiB, before TIFF overhead/compression. Typical transferred COG byte ranges may be lower or higher depending on tiling/overviews and the chip's actual dimensions. Do not treat any of these figures as verified product sizes. Exact output and transferred byte counts can only be reported after the authorized acquisition.

## Sources

- Project's exact item IDs and per-scene metadata: `data/sar/scenes.json`.
- Project's windowed chip construction, collection, asset keys, and SAS token flow: `scripts/fetch_sentinel1_scene.py`.
- Project's preset bootstrap calls: `scripts/bootstrap_demo.py`.
- Provider's public [Sentinel-1 RTC explorer](https://planetarycomputer.microsoft.com/explore?c=124.0274%2C-16.494&d=sentinel-1-rtc&z=9) and [Planetary Computer documentation](https://planetarycomputer.microsoft.com/docs/).
- Direct STAC item URL form: `https://planetarycomputer.microsoft.com/api/stac/v1/collections/sentinel-1-rtc/items/{item-id}`. Direct requests were blocked by DNS in this environment; item validity remains unverified.

## Decision and next action

**Decision: NO-GO for downloading at this point.** The existing fetcher cannot pin IDs, and the required exact-item existence/asset-access verification failed due to DNS resolution. Do not run `--preset`, `bootstrap_demo.py`, or any date-window selector for recovery. Once metadata-only STAC access is available, verify all four items and VV/VH assets; then implement and test the fail-closed exact-item path. Only after that gate should the four listed commands be run.
