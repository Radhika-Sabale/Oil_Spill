"""Ingest REAL AIS from MarineCadastre for a scene footprint.

MarineCadastre publishes one nationwide CSV per day, zipped, tens of millions of
rows. The problem statement is explicit that you do not download nationwide US
days into the repo, so this script streams the archive, clips to the scene box
and time window while it reads, ingests the survivors into SQLite, and then
deletes the raw download unless you ask it to keep it.

Coverage: US waters only (Gulf of Mexico, East and West coasts, Alaska, Hawaii,
Puerto Rico). `app/scenes.py` already decides per scene whether the footprint is
inside that coverage, and this script refuses scenes that are not, because
inventing Indian or European AIS would be exactly the kind of fabrication the
spec forbids.

Source: https://coast.noaa.gov/htdata/CMSP/AISDataHandler/<year>/AIS_<Y>_<M>_<D>.zip
Licence: US Government work, public domain. Cite MarineCadastre.gov.

Usage:
    python scripts/fetch_marinecadastre_ais.py --scene gom_mc20_chronic_slick
    python scripts/fetch_marinecadastre_ais.py --scene X --pad-km 40 --days 2
"""
from __future__ import annotations

import argparse
import csv
import io
import sys
import time
import urllib.request
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config, scenes as scenes_mod   # noqa: E402
from app.ais import ingest as ais_ingest       # noqa: E402

BASE = "https://coast.noaa.gov/htdata/CMSP/AISDataHandler"
LICENSE = "MarineCadastre.gov / NOAA + BOEM, US Government work, public domain"
SOURCE_TAG = "marinecadastre"


def url_for(day: datetime) -> str:
    return "%s/%d/AIS_%d_%02d_%02d.zip" % (BASE, day.year, day.year, day.month, day.day)


def pad_bbox(bounds: List[float], pad_km: float) -> Tuple[float, float, float, float]:
    from app.geo.crs import meters_per_degree

    w, s, e, n = [float(v) for v in bounds]
    m_lon, m_lat = meters_per_degree((s + n) / 2.0)
    return (w - pad_km * 1000 / m_lon, s - pad_km * 1000 / m_lat,
            e + pad_km * 1000 / m_lon, n + pad_km * 1000 / m_lat)


def download(day: datetime, dest_dir: Path) -> Optional[Path]:
    url = url_for(day)
    dest = dest_dir / Path(url).name
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and zipfile.is_zipfile(dest):
        print("   already downloaded: %s (%.0f MB)" % (dest.name, dest.stat().st_size / 1e6))
        return dest

    print("   GET %s" % url)
    expected = None
    try:
        head = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(head, timeout=60) as resp:
            expected = int(resp.headers.get("Content-Length") or 0) or None
    except Exception as exc:
        print("   archive size lookup failed (%s); will use range response headers" % exc)

    done = dest.stat().st_size if dest.exists() else 0
    if expected is not None and done > expected:
        dest.unlink()
        done = 0

    # NOAA connections can end early without raising an exception. Download in
    # bounded byte ranges, resume from the actual file length, and only hand a
    # ZIP to the CSV reader after the archive directory is present.
    attempts_without_progress = 0
    chunk_size = 8 << 20
    last_pct = -1
    while expected is None or done < expected:
        start = done
        end = start + chunk_size - 1 if expected is None else min(start + chunk_size, expected) - 1
        req = urllib.request.Request(url, headers={"Range": "bytes=%d-%d" % (start, end)})
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                if resp.status != 206:
                    raise IOError("server did not honor the byte-range request (HTTP %s)" % resp.status)
                content_range = resp.headers.get("Content-Range", "")
                try:
                    range_spec, total_spec = content_range.split(" ", 1)[1].split("/", 1)
                    range_start, range_end = [int(v) for v in range_spec.split("-", 1)]
                    response_total = int(total_spec)
                except (IndexError, ValueError):
                    raise IOError("NOAA response did not include a valid Content-Range")
                if range_start != start:
                    raise IOError("NOAA returned byte range starting at %d, expected %d"
                                  % (range_start, start))
                if expected is None:
                    expected = response_total
                elif response_total != expected:
                    raise IOError("NOAA archive size changed during download")
                remaining = range_end - range_start + 1
                mode = "ab" if start else "wb"
                with dest.open(mode) as fh:
                    while remaining:
                        block = resp.read(min(1 << 20, remaining))
                        if not block:
                            break
                        fh.write(block)
                        done += len(block)
                        remaining -= len(block)
            if done == start:
                attempts_without_progress += 1
                if attempts_without_progress >= 8:
                    print("   download failed: NOAA made no progress after 8 range retries")
                    return None
                time.sleep(min(2 ** attempts_without_progress, 15))
            else:
                attempts_without_progress = 0
                pct = int(100 * done / expected) if expected else 0
                if expected and pct >= last_pct + 10:
                    print("      %3d%%  %.0f / %.0f MB" % (pct, done / 1e6, expected / 1e6))
                    last_pct = pct
        except Exception as exc:
            attempts_without_progress += 1
            if attempts_without_progress >= 8:
                print("   download failed after 8 range retries: %s" % exc)
                return None
            time.sleep(min(2 ** attempts_without_progress, 15))

    if not dest.exists() or dest.stat().st_size != expected or not zipfile.is_zipfile(dest):
        print("   download failed: incomplete ZIP archive; partial file kept for resume")
        return None
    print("   saved %.0f MB" % (dest.stat().st_size / 1e6))
    return dest


def clip_and_ingest(zip_path: Path, bbox: Tuple[float, float, float, float],
                    t_start: int, t_end: int, conn) -> int:
    """Stream the CSV out of the zip and keep only rows inside the box."""
    w, s, e, n = bbox
    kept: List[tuple] = []
    total = 0
    with zipfile.ZipFile(zip_path) as zf:
        names = [x for x in zf.namelist() if x.lower().endswith(".csv")]
        if not names:
            print("   no CSV inside the archive")
            return 0
        with zf.open(names[0]) as raw:
            reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
            for rec in reader:
                total += 1
                try:
                    lat = float(rec.get("LAT") or "nan")
                    lon = float(rec.get("LON") or "nan")
                except ValueError:
                    continue
                if not (s <= lat <= n and w <= lon <= e):
                    continue
                row = ais_ingest.row_from_csv(rec, SOURCE_TAG)
                if row is None:
                    continue
                if not (t_start <= row[1] <= t_end):
                    continue
                kept.append(row)
                if len(kept) >= 20000:
                    ais_ingest.ingest_rows(conn, kept, SOURCE_TAG)
                    kept = []
                if total % 2_000_000 == 0:
                    print("      scanned %.1fM rows" % (total / 1e6))
    if kept:
        ais_ingest.ingest_rows(conn, kept, SOURCE_TAG)
    print("   scanned %d rows in the national file" % total)
    return total


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scene", action="append", default=[], required=False)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--pad-km", type=float, default=45.0,
                    help="margin around the scene box, so approaches are captured")
    ap.add_argument("--days", type=int, default=3,
                    help="days centred on the acquisition, to cover the hindcast window")
    ap.add_argument("--keep-zip", action="store_true")
    ap.add_argument("--force", action="store_true", help="re-ingest even if rows exist")
    args = ap.parse_args()

    wanted = set(args.scene)
    targets = [s for s in scenes_mod.all_scenes(include_selftest=True)
               if (s.id in wanted) or (args.all and not wanted)]
    if not targets:
        ap.error("no matching scenes; pass --scene ID or --all")

    conn = ais_ingest.connect()
    try:
        if args.force:
            removed = ais_ingest.clear_source(conn, SOURCE_TAG)
            print("cleared %d previously ingested real AIS rows" % removed)

        for scene in targets:
            if scene.ais_mode != "real":
                print("[%s] footprint is outside MarineCadastre coverage. Real AIS does "
                      "not exist for it. Use scripts/build_synthetic_ais.py." % scene.id)
                continue

            t_sat = datetime.fromisoformat(scene.t_sat.replace("Z", "+00:00"))
            bbox = pad_bbox(scene.bounds, args.pad_km)
            half = args.days // 2
            days = [t_sat.date() - timedelta(days=half) + timedelta(days=i)
                    for i in range(args.days)]
            t_start = int((t_sat - timedelta(days=half + 1)).timestamp())
            t_end = int((t_sat + timedelta(days=half + 1)).timestamp())

            print("[%s] real AIS for %s, box %s, %d day(s)"
                  % (scene.id, t_sat.date(), [round(v, 3) for v in bbox], len(days)))
            before = ais_ingest.stats(conn).rows
            for d in days:
                day = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
                zp = download(day, Path(config.CACHE_DIR) / "marinecadastre")
                if zp is None:
                    continue
                clip_and_ingest(zp, bbox, t_start, t_end, conn)
                if not args.keep_zip:
                    zp.unlink(missing_ok=True)
                    print("   removed the national archive, kept only the clipped rows")
            after = ais_ingest.stats(conn)
            print("   ingested %d rows for this scene" % (after.rows - before))
            print("   store: %d rows, %d vessels, %s .. %s"
                  % (after.rows, after.vessels, after.t_start, after.t_end))
    finally:
        conn.close()

    print("\nCite in the README: %s" % LICENSE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
