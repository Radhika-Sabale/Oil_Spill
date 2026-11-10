"""Read-only AIS availability checks for scene and run reporting."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple

from .. import config
from ..geo.crs import meters_per_degree


def _kind(source: Optional[str]) -> str:
    value = (source or "").strip().lower()
    if any(token in value for token in ("simulat", "synthetic", "selftest")):
        return "simulated"
    if value and value != "unknown":
        return "real"
    return "unknown"


def _connect_readonly(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)


def _empty(status: str, label: str) -> Dict[str, Any]:
    return {"status": status, "label": label, "real_records": 0,
            "simulated_records": 0, "unknown_records": 0}


def inspect(path: Path = None,
            bbox: Sequence[float] = None,
            window: Tuple[int, int] = None,
            candidates: Optional[int] = None) -> Dict[str, Any]:
    """Report AIS rows globally and, if supplied, within a scene/query scope.

    The file is opened read-only; missing stores are never created as a side
    effect of listing scenes or reporting a run.
    """
    path = Path(path or config.AIS_SQLITE)
    if not path.is_file():
        return _empty("database_missing", "AIS database missing")

    conn = None
    try:
        conn = _connect_readonly(path)
        table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='positions'"
        ).fetchone()
        if not table:
            return _empty("database_missing", "AIS positions table missing")
        cols = {row[1] for row in conn.execute("PRAGMA table_info(positions)")}
        if not {"mmsi", "ts", "lat", "lon"}.issubset(cols):
            return _empty("database_unreadable", "AIS database schema is not recognized")
        source_col = "source" if "source" in cols else "NULL"
        rows = conn.execute(
            "SELECT COALESCE(" + source_col + ", '') AS source, COUNT(*) AS n "
            "FROM positions GROUP BY source"
        ).fetchall()
        global_counts = {"real": 0, "simulated": 0, "unknown": 0}
        for source, count in rows:
            global_counts[_kind(source)] += int(count)
        total = sum(global_counts.values())
        if total == 0:
            return _empty("database_empty", "AIS database empty")

        scope_counts = dict(global_counts)
        if bbox is not None and window is not None:
            west, south, east, north = [float(v) for v in bbox]
            t0, t1 = [int(v) for v in window]
            scoped_rows = conn.execute(
                "SELECT COALESCE(" + source_col + ", '') AS source, COUNT(*) AS n "
                "FROM positions WHERE ts BETWEEN ? AND ? AND lat BETWEEN ? AND ? "
                "AND lon BETWEEN ? AND ? GROUP BY source",
                (t0, t1, south, north, west, east),
            ).fetchall()
            scope_counts = {"real": 0, "simulated": 0, "unknown": 0}
            for source, count in scoped_rows:
                scope_counts[_kind(source)] += int(count)

        result = {
            "status": "available", "label": "AIS data available",
            "real_records": scope_counts["real"],
            "simulated_records": scope_counts["simulated"],
            "unknown_records": scope_counts["unknown"],
            "database_real_records": global_counts["real"],
            "database_simulated_records": global_counts["simulated"],
            "database_unknown_records": global_counts["unknown"],
        }
        has_real = scope_counts["real"] > 0
        has_sim = scope_counts["simulated"] > 0
        if has_real and has_sim:
            if candidates == 0:
                result.update(status="mixed_no_candidates",
                              label="Real and simulated AIS queried; no matching vessels")
            else:
                result.update(status="mixed_sources", label="Real and simulated AIS data")
        elif has_real:
            status = "real_queried" if candidates is not None and candidates > 0 else "real_available"
            label = "Real AIS queried" if candidates is not None and candidates > 0 else "Real AIS available locally"
            if candidates == 0:
                status, label = "real_no_candidates", "Real AIS queried; no matching vessels"
            result.update(status=status, label=label)
        elif has_sim:
            status = "simulated_queried" if candidates is not None and candidates > 0 else "simulated_available"
            label = "Simulated AIS queried" if candidates is not None and candidates > 0 else "Simulated AIS available"
            if candidates == 0:
                status, label = "simulated_no_candidates", "Simulated AIS queried; no matching vessels"
            result.update(status=status, label=label)
        elif global_counts["real"]:
            result.update(status="real_no_matches", label="No real AIS records match this scene and time")
        elif global_counts["simulated"]:
            result.update(status="simulated_no_matches", label="No simulated AIS records match this scene and time")
        else:
            result.update(status="unclassified_only", label="AIS records have unknown provenance")
        return result
    except (sqlite3.Error, OSError, ValueError):
        return _empty("database_unreadable", "AIS database could not be read")
    finally:
        if conn is not None:
            conn.close()


def scene_status(scene, path: Path = None) -> Dict[str, Any]:
    """Check locally stored AIS around the scene's broad possible run window."""
    try:
        t_sat = datetime.fromisoformat(str(scene.t_sat).replace("Z", "+00:00"))
        if t_sat.tzinfo is None:
            t_sat = t_sat.replace(tzinfo=timezone.utc)
        before = int(config.HINDCAST_H + config.ORIGIN_WINDOW_H)
        after = int(config.ORIGIN_WINDOW_H)
        window = (int((t_sat - timedelta(hours=before)).timestamp()),
                  int((t_sat + timedelta(hours=after)).timestamp()))
        west, south, east, north = [float(v) for v in scene.bounds]
        meters_lon, meters_lat = meters_per_degree((south + north) / 2.0)
        pad_m = (config.SEARCH_RADIUS_KM * 1.6 + 5.0) * 1000.0
        pad_lon, pad_lat = pad_m / meters_lon, pad_m / meters_lat
        bbox = (west - pad_lon, south - pad_lat, east + pad_lon, north + pad_lat)
        return inspect(path, bbox, window)
    except (AttributeError, TypeError, ValueError):
        return _empty("database_unavailable", "AIS availability could not be checked")
