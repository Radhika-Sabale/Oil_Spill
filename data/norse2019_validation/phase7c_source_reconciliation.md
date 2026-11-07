# Phase 7C — NORSE2019 Drifter Source Reconciliation

**Prepared:** 2026-11-06
**Scope:** source, schema, and coordinate metadata reconciliation only. No coordinate transforms, spatial distances, trajectory errors, or hindcasts were performed.

## Decision

**NO-GO for Phase 7D spatial scoring at this time.** The Scripps LDL catalogue lists `LDL_NORSE`, and the NORSE2019 paper describes the selected iSphere and CODE drifters. However, the authoritative ERDDAP variable metadata, ISO record body, and filtered source records could not be retrieved in this environment. Consequently, the coordinate datum/reference system and a row-by-row local-to-authoritative match are not established. The local CSV's provenance therefore remains unverified. Decimal-degree values alone are not sufficient to infer a datum.

## Sources inspected and access status

| Source | Access/result | What it establishes |
|---|---|---|
| [LDL ERDDAP catalogue](https://erddap.ldl.ucsd.edu/erddap/info/) | Catalogue page indexed and readable through web search. It lists dataset ID `LDL_NORSE`, title “Lagrangian Drifter Laboratory at Scripps Institution of Oceanography NORSE Drifter Data.” | Dataset exists in the LDL ERDDAP catalogue. This alone does not establish local file provenance or the dataset's coordinate datum. |
| [LDL_NORSE ISO 19115 XML](https://erddap.ldl.ucsd.edu/erddap/metadata/iso19115/xml/LDL_NORSE_iso19115.xml) | The XML endpoint was identified in the catalogue's ISO metadata listing (listed size 66,733 bytes), but the web retrieval tool rejected the `application/xml` response type. The local shell has no DNS/network route to the host. XML content was not inspected. | The metadata record is available at the stated endpoint, but its contents and CRS declarations could not be verified in this run. |
| `LDL_NORSE` ERDDAP info and tabledap endpoints | Direct info endpoint fetch failed with cache/access errors; tabledap data form returned HTTP 401 through the browser retrieval tool. Shell requests failed DNS resolution. No source records were retrieved. | No variable attributes, identifiers, or authoritative observation rows are confirmed here. |
| [NORSE2019 research paper](https://agupubs.onlinelibrary.wiley.com/doi/10.1029/2020JC016499) | Readable. The paper's data availability statement cites [Zenodo DOI 10.5281/zenodo.3898521](https://doi.org/10.5281/zenodo.3898521) for MetOcean drifter data. | The paper documents an iSphere surface drifter associated with the soybean release and CODE drifter(s) associated with mineral release. It describes iSphere as surface-following and affected by wind, waves, and currents; CODE as following currents at an effective depth of 0.6 m with little wind/wave drag. It does not, in the inspected text, establish the datum/CRS for this local CSV. |
| Zenodo record 10.5281/zenodo.3898521 | DOI/API and record pages could not be retrieved with the available web tool; no record metadata or files were inspected. | No file identity, export lineage, schema, or CRS assertion from Zenodo was verified. |
| Local `PCCOE IGC\drifters_OPV2019.csv` | Read locally; size 179,709 bytes; SHA-256 `32ee8434d3841030f4e8476b3b34ac1df40758a140b4250e68a586a5e4be3365`. | Local structure and observations summarized below. The file itself does not declare a coordinate datum or CRS. |

The paper supports the experiment/drifter-type context, not the identity of this particular local CSV export. The catalogue listing supports the existence and title of an authoritative dataset, not that the local records came from it.

## Local CSV inventory

The CSV has 21 columns, including `Asset Name`, `Asset Id`, `Data Date (UTC)`, `LATITUDE`, `LONGITUDE`, GPS date/time components, instrument/status fields, and `Report Body`. Four repeated header records occur within the file (CSV input lines 434, 771, 844, and 918); they were excluded from the observation counts below. The latitude and longitude fields are decimal-degree numbers with leading spaces. There is no explicit CRS/datum field or file-level source citation in the inspected file.

| Candidate | Local identifier | Dated rows | Local timestamp extent | June 12, 2019 rows | First and last June 12 positions (lat, lon; untransformed) |
|---|---:|---:|---|---:|---|
| `OPV-2019-ISPHERE-2` | `300234067055570` | 72 | 2019-06-12 06:18 through 2019-06-15 05:00 UTC | 18 | 06:18 `(59.859600, 2.512000)`; 23:00 `(59.731600, 2.349400)` |
| `OPV-2019-CODE-1` | `300234067050940` | 432 | 2019-06-12 05:47 through 2019-06-15 05:30 UTC | 110 | 05:47 `(59.865148, 2.478412)`; 23:50 `(59.805120, 2.324472)` |

All values in the final column are copied from local CSV fields without datum interpretation or transformation. Asset labels/IDs and timestamps are local observations only; they are not proof of match to the ERDDAP or Zenodo source.

## Authoritative metadata findings

The accessible catalogue record provides the dataset identifier and title. The ERDDAP standard convention for its geographic/time axis fields cannot substitute for inspecting this dataset's own variable metadata, and standard longitude/latitude unit labels would not, by themselves, prove the geodetic datum. Because the `LDL_NORSE` info response and ISO XML body were not readable here, this audit could not confirm:

- the actual variable names and per-variable attributes in `LDL_NORSE`;
- declared coordinate units, axis conventions, datum, CRS, or reference system;
- the dataset's time variable attributes and UTC/timestamp representation;
- the authoritative platform/asset identifier fields and whether both selected IDs occur;
- data lineage, source files, processing steps, or how this local CSV was exported/transformed.

The paper confirms the existence and roles of the iSphere and CODE drifter tracks within NORSE2019, but does not connect those paper labels to the local CSV's exact rows or ID values. The paper names Zenodo DOI 10.5281/zenodo.3898521 as its MetOcean drifter data source; the Zenodo record itself was inaccessible in this run.

## Local-to-authoritative comparison

| Check | Result |
|---|---|
| Candidate names appear in local CSV | Yes: `OPV-2019-ISPHERE-2` and `OPV-2019-CODE-1`. |
| Candidate ID values in local CSV | Yes: `300234067055570` and `300234067050940`, respectively. |
| Candidate tracks described by the paper | Yes at the experiment/type level: soybean iSphere; mineral CODE. This is contextual corroboration only. |
| Candidate names/IDs found in authoritative ERDDAP rows | Not verified: no ERDDAP observation rows were retrieved. |
| Timestamp and coordinate equality against authoritative rows | Not tested: no source records were retrieved. |
| Original export versus processed derivative | Undetermined. The expanded CSV includes telemetry/status and report-body columns and repeated embedded headers, which describes its shape but does not identify its source or processing history. |
| Provenance of local CSV | Unverified. Similar names, IDs, timing, and experiment context are insufficient to claim that it is an ERDDAP/Zenodo export. |

## Datum and CRS conclusion

**Unresolved.** The local CSV has no declared datum/CRS. The specific ERDDAP metadata body and Zenodo record metadata were not successfully inspected, and the paper's reviewed text does not declare the CRS for these records. The fact that the local coordinates look like decimal degrees is not evidence that the datum is WGS84 or that the CRS is EPSG:4326. No coordinate conversion or spatial distance was calculated.

## Unresolved discrepancies and access limitations

1. The ERDDAP catalogue is accessible, but its dataset-specific info/data endpoints did not provide usable content in this environment. The ISO XML endpoint's content type was not supported by the retrieval tool; the local shell could not resolve the ERDDAP host.
2. Zenodo DOI 10.5281/zenodo.3898521 and its API record could not be opened. Thus the file list, version, metadata, and checksums cannot be compared with the local CSV.
3. No row-level comparison is possible without authoritative source rows. In particular, this audit cannot establish whether the local file is original, re-exported, or otherwise transformed.
4. Neither the local file nor inspected paper text resolves the coordinate datum/CRS. This is a blocking issue for metric spatial comparison.

## Required verifiable route to resume

Obtain one of the following from an accessible/authorized network and preserve its URL, retrieval time, and file checksum:

1. The full LDL `LDL_NORSE` ISO 19115 XML body and ERDDAP dataset info metadata (including coordinate variable attributes), plus filtered authoritative data rows for both platform IDs and the relevant timestamps; or
2. The Zenodo record metadata and original source files for the two tracks, including any readme/data dictionary stating datum and coordinate semantics.

Then compare the authoritative identifiers, timestamps, and untransformed coordinate fields directly to the local CSV. Only after the CRS/datum and local file lineage are documented should Phase 7D perform projection and distance calculations. Do not replace the local file as part of that reconciliation.

**Final Phase 7D decision: NO-GO pending authoritative datum/CRS evidence and record-level provenance reconciliation.**
