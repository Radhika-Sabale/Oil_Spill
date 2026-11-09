# Missing Scene TIFF Recovery Investigation

**Project:** `E:\OneDrive\Desktop\Hackathon material\PCCOE IGC\Oil_Spill`  
**Status:** Investigation complete; no exact source TIFFs were recoverable from searched local locations. No files were downloaded or restored.

## Findings summary

The scene registry indexes four georeferenced Sentinel-1 RTC scene chips under `data/sar/`. The expected files are absent. The project's fetch script identifies Microsoft Planetary Computer's public `sentinel-1-rtc` STAC collection as the source and documents how it creates local chips. The scene registry records exact source item identifiers, acquisition timestamps, and target CRS for each expected chip.

The missing files are not tracked in Git or Git LFS. `.gitignore` intentionally excludes `data/sar/*.tif` and `*.tiff`, while retaining `data/sar/scenes.json`. Existing TIFFs found under `data/m1_out` are generated segmentation masks for two scenes, not source SAR imagery; they cannot substitute for the missing input chips.

## Four indexed files

| Scene ID | Expected filename and relative path | Expected absolute path | Source item ID and acquisition time | Known raster metadata |
|---|---|---|---|---|
| `gom_mc20_chronic_slick` | `data/sar/gom_mc20_chronic_slick.tif` | `E:\OneDrive\Desktop\Hackathon material\PCCOE IGC\Oil_Spill\data\sar\gom_mc20_chronic_slick.tif` | `S1A_IW_GRDH_1SDV_20230924T000215_20230924T000240_050462_0613BB_rtc`; registry `t_sat`: `2023-09-24T00:02:27.804136Z` | EPSG:32616; bounds (lon/lat) [-89.086792, 28.835617, -88.853793, 29.040577]. Registry does not record dimensions or pixel resolution. Expected source chip is two polarization bands (VV, VH), float32 dB, georeferenced RTC imagery. |
| `arabian_sea_mumbai_offshore` | `data/sar/arabian_sea_mumbai_offshore.tif` | `E:\OneDrive\Desktop\Hackathon material\PCCOE IGC\Oil_Spill\data\sar\arabian_sea_mumbai_offshore.tif` | `S1A_IW_GRDH_1SDV_20240313T010329_20240313T010354_052956_066912_rtc`; registry `t_sat`: `2024-03-13T01:03:42.419107Z` | EPSG:32643; bounds [71.491372, 18.946853, 71.708384, 19.153216]. Expected VV/VH float32 dB chip; dimensions and final pixel resolution are not recorded. |
| `caspian_baku_seeps` | `data/sar/caspian_baku_seeps.tif` | `E:\OneDrive\Desktop\Hackathon material\PCCOE IGC\Oil_Spill\data\sar\caspian_baku_seeps.tif` | `S1A_IW_GRDH_1SDV_20231014T024432_20231014T024457_050755_061DC6_rtc`; registry `t_sat`: `2023-10-14T02:44:45.075839Z` | EPSG:32639; bounds [50.348997, 40.089884, 50.610242, 40.290235]. Expected VV/VH float32 dB chip; dimensions and final pixel resolution are not recorded. |
| `santa_barbara_seeps` | `data/sar/santa_barbara_seeps.tif` | `E:\OneDrive\Desktop\Hackathon material\PCCOE IGC\Oil_Spill\data\sar\santa_barbara_seeps.tif` | `S1A_IW_GRDH_1SDV_20230829T015857_20230829T015922_050084_0606D7_rtc`; registry `t_sat`: `2023-08-29T01:59:10.443231Z` | EPSG:32611; bounds [-119.996664, 34.270329, -119.744111, 34.479732]. Expected VV/VH float32 dB chip; dimensions and final pixel resolution are not recorded. |

### What is and is not known about the TIFFs

- `data/sar/scenes.json` is the authority for scene IDs, paths, acquisition timestamps, exact item IDs, geographic bounds, and projected CRS.
- `scripts/fetch_sentinel1_scene.py` documents the raster construction: windowed reads of the selected item's `vv` and `vh` COG assets; crop around the scene preset's center to a 22 km square; linear gamma0 converted to dB with `10*log10`; float32 two-band stack; georeferenced GeoTIFF in the source UTM CRS. The crop is capped at 2048 pixels per side; its precise output dimensions depend on the source grid and crop and cannot be recovered from the registry alone.
- Therefore, the application expects **preprocessed local RTC VV/VH dB chips**, not the full raw Sentinel-1 product and not the M1 output masks. The TIFF must carry its own affine transform and CRS; `app/geo/raster.py::load_sar()` rejects missing georeferencing.
- Bounds in the registry are geographic footprints. They do not specify pixel dimensions or ground resolution. No per-file checksums or raster tags were available because the files are missing.

## Search locations and results

1. Project `data/sar/`: checked the scene index and file presence. No four expected TIFFs are present; this directory has no actual indexed scene chips.
2. Project recursively, including TIFF sidecars: the search found the four expected scene TIFFs absent. It found only test-generated synthetic rasters under `.pytest_cache` and two M1 result masks under `data/m1_out`.
3. `data/m1_out/`: `arabian_sea_mumbai_offshore_mask.tif` and `gom_mc20_chronic_slick_mask.tif` are downstream mask products, not VV/VH satellite imagery; they are not valid recoveries.
4. `E:\OneDrive\Desktop\Hackathon material\PCCOE IGC` recursively: no exact source copies found beyond the project test rasters and M1 masks listed above.
5. `%USERPROFILE%\Downloads` recursively: no TIFF candidates found in the search output.

The search was scoped to these project and likely download locations; it was not an exhaustive scan of every drive or cloud-synced directory.

## Git and LFS

- `git ls-files data/sar data/m1_out` lists `data/sar/scenes.json` and the two M1 output mask TIFFs; it lists none of the four expected input TIFFs.
- `git log --all --name-status -- data/sar` shows only the scene index; no scene TIFF was added, removed, or tracked in repository history.
- `.gitignore` excludes `data/sar/*.tif` and `data/sar/*.tiff`; `!data/sar/scenes.json` explicitly retains the registry.
- No `.gitattributes` exists in the repository root.
- `git lfs ls-files` returned no tracked LFS objects.

**Conclusion:** there is no repository or LFS copy to restore. A Git history lookup cannot recover these files.

## Original source and exact product references

The project acquisition script names the Microsoft Planetary Computer `sentinel-1-rtc` STAC collection and records each exact item ID in `data/sar/scenes.json`. The public [Planetary Computer Sentinel-1 RTC explorer](https://planetarycomputer.microsoft.com/explore?c=124.0274%2C-16.494&d=sentinel-1-rtc&z=9) exposes this collection. Microsoft's [Planetary Computer documentation](https://planetarycomputer.microsoft.com/docs/) describes its public STAC access. The project script's source endpoint is `https://planetarycomputer.microsoft.com/api/stac/v1/search`, and it retrieves signed VV/VH COG asset links from STAC results.

Exact item references recorded by the project:

- [MC20 item](https://planetarycomputer.microsoft.com/api/stac/v1/collections/sentinel-1-rtc/items/S1A_IW_GRDH_1SDV_20230924T000215_20230924T000240_050462_0613BB_rtc)
- [Arabian Sea item](https://planetarycomputer.microsoft.com/api/stac/v1/collections/sentinel-1-rtc/items/S1A_IW_GRDH_1SDV_20240313T010329_20240313T010354_052956_066912_rtc)
- [Caspian item](https://planetarycomputer.microsoft.com/api/stac/v1/collections/sentinel-1-rtc/items/S1A_IW_GRDH_1SDV_20231014T024432_20231014T024457_050755_061DC6_rtc)
- [Santa Barbara item](https://planetarycomputer.microsoft.com/api/stac/v1/collections/sentinel-1-rtc/items/S1A_IW_GRDH_1SDV_20230829T015857_20230829T015922_050084_0606D7_rtc)

The web inspection tool could not open the direct item JSON endpoints in this investigation. The item IDs and provenance are nonetheless explicitly recorded in the local scene registry, and the project's fetch script names the collection and asset-processing procedure. No external record was used to assert additional item-specific dimensions or resolutions.

### Recovery route and exactness caution

The repository's documented acquisition mechanism is `scripts/fetch_sentinel1_scene.py` (also invoked by `scripts/bootstrap_demo.py`). Its supported commands include:

```powershell
python scripts/fetch_sentinel1_scene.py --preset mc20 --candidates 8
python scripts/fetch_sentinel1_scene.py --preset arabian_sea --candidates 8
python scripts/fetch_sentinel1_scene.py --preset caspian_baku --candidates 8
python scripts/fetch_sentinel1_scene.py --preset santa_barbara --candidates 8
```

These commands were **not run**. The script searches the date window and may screen candidates and select a different acquisition. Before treating a newly fetched chip as an exact recovery, its reported `item_id` and acquisition time must match the row above. If the current script cannot select a pinned item ID, a controlled exact-item extraction would be needed; no substitute scene should be indexed under these scene IDs.

## Recovery status

| Scene | Exact local copy found? | Restored? | Status |
|---|---:|---:|---|
| `gom_mc20_chronic_slick` | No | No | Missing; exact RTC item is identified in registry, but the item endpoint was not independently inspectable here. |
| `arabian_sea_mumbai_offshore` | No | No | Missing; exact RTC item is identified in registry, but the item endpoint was not independently inspectable here. |
| `caspian_baku_seeps` | No | No | Missing; exact RTC item is identified in registry, but the item endpoint was not independently inspectable here. |
| `santa_barbara_seeps` | No | No | Missing; exact RTC item is identified in registry, but the item endpoint was not independently inspectable here. |

No files were downloaded, generated, copied, or overwritten during this investigation.

## Exact remaining actions

1. If an original acquisition workstation or teammate storage is available, search for the four filenames or these exact STAC item IDs; verify TIFF bands, transform, CRS, acquisition metadata, and checksums before copying anything.
2. Otherwise, retrieve each pinned item from the Microsoft Planetary Computer `sentinel-1-rtc` collection using the existing project chip recipe. Require exact item-ID and timestamp matches before writing to the expected `data/sar/<scene_id>.tif` path.
3. Validate each restored TIFF with raster metadata inspection: two bands (VV/VH), dimensions, float32 values in dB, affine georeferencing, CRS matching the registry, and footprint/timestamp consistent with the indexed scene. Then compare updated file identity and scene metadata before using the UI.
4. Keep any acquired chips local; the repository's ignore rules intentionally prevent those rasters from being committed.

Until these steps succeed, the four indexed scenes remain unavailable for normal UI analysis.
