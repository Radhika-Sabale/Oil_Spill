from datetime import datetime, timezone
from types import SimpleNamespace

from app.ais import availability, ingest


def _position(ts, lat=34.375, lon=-119.87, source="marinecadastre"):
    return (211234567, ts, "2023-08-29T01:00:00", lat, lon,
            8.0, 90.0, 90.0, "VESSEL", None, None, "70", "Under way",
            100.0, 20.0, 5.0, None, source)


def test_missing_and_empty_ais_stores_are_distinct(tmp_path):
    missing = tmp_path / "missing.sqlite"
    assert availability.inspect(missing)["status"] == "database_missing"

    empty = tmp_path / "empty.sqlite"
    conn = ingest.connect(empty)
    conn.close()
    assert availability.inspect(empty)["status"] == "database_empty"


def test_real_ais_inside_scene_scope_is_reported_as_available(tmp_path):
    path = tmp_path / "ais.sqlite"
    conn = ingest.connect(path)
    ts = int(datetime(2023, 8, 29, 1, tzinfo=timezone.utc).timestamp())
    ingest.ingest_rows(conn, [_position(ts)], "marinecadastre")
    conn.close()

    status = availability.inspect(path, (-120.0, 34.0, -119.0, 35.0), (ts - 3600, ts + 3600))
    assert status["status"] == "real_available"
    assert status["real_records"] == 1


def test_ais_outside_scene_and_time_is_not_reported_as_available(tmp_path):
    path = tmp_path / "ais.sqlite"
    conn = ingest.connect(path)
    ts = int(datetime(2023, 8, 29, 1, tzinfo=timezone.utc).timestamp())
    ingest.ingest_rows(conn, [_position(ts)], "marinecadastre")
    conn.close()

    status = availability.inspect(path, (71.0, 18.0, 72.0, 20.0), (ts - 3600, ts + 3600))
    assert status["status"] == "real_no_matches"
    assert status["real_records"] == 0


def test_query_reports_real_data_even_when_no_vessel_passes_filter(tmp_path):
    path = tmp_path / "ais.sqlite"
    conn = ingest.connect(path)
    ts = int(datetime(2023, 8, 29, 1, tzinfo=timezone.utc).timestamp())
    ingest.ingest_rows(conn, [_position(ts)], "marinecadastre")
    conn.close()

    status = availability.inspect(path, (-120.0, 34.0, -119.0, 35.0), (ts - 3600, ts + 3600), candidates=0)
    assert status["status"] == "real_no_candidates"
    assert status["real_records"] == 1


def test_scene_status_reports_simulated_source_as_simulated(tmp_path):
    path = tmp_path / "ais.sqlite"
    conn = ingest.connect(path)
    ts = int(datetime(2023, 8, 29, 1, tzinfo=timezone.utc).timestamp())
    ingest.ingest_rows(conn, [_position(ts, source="simulated_traffic")], "simulated_traffic")
    conn.close()
    scene = SimpleNamespace(t_sat="2023-08-29T01:00:00Z", bounds=(-120.0, 34.0, -119.0, 35.0))

    status = availability.scene_status(scene, path)
    assert status["status"] == "simulated_available"
    assert status["real_records"] == 0
    assert status["simulated_records"] == 1
