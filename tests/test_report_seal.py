"""The PDF is stored once, served byte-for-byte, and its SHA-256 matches the downloaded bytes."""
from __future__ import annotations

import hashlib

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("reportlab")
pytest.importorskip("httpx")


def _save_job(job_id):
    from app.jobs import store as job_store

    job_store.save(job_id, {
        "job_id": job_id, "input": {"scene_id": "unit", "t_sat": "2024-02-14T00:00:00Z"},
        "detection": {"polygons": [], "metrics": {"detector": "unit"}},
        "attribution": {"suspects": [], "stage4": {
            "incident_id": job_id, "case_type": "synthetic_demo", "candidates": [],
            "conclusion": "Investigative candidates only; not proof of causation or a finding of guilt",
            "stage4_status": {"h3": "unavailable", "reachability": "implemented",
                              "dark_target": "unavailable", "mass_balance": "unavailable"},
            "h3": {"status": "unavailable", "note": "h3 not installed"}, "slick": {}}},
        "warnings": [],
    })


def test_pdf_hash_matches_bytes_and_is_stable_across_downloads():
    from fastapi.testclient import TestClient
    from app.main import app

    job_id = "job_unit_seal"
    _save_job(job_id)
    with TestClient(app) as client:
        r1 = client.get("/api/report/%s/pdf" % job_id)
        assert r1.status_code == 200
        digest = hashlib.sha256(r1.content).hexdigest()
        assert r1.headers["X-Report-SHA256"] == digest

        r2 = client.get("/api/report/%s/pdf" % job_id)
        assert r2.content == r1.content

        info = client.get("/api/report/%s/sha256" % job_id).json()
        assert info["sha256"] == digest and info["matches_recorded"] is True
        assert info["bytes"] == len(r1.content)


def test_report_text_carries_the_stage4_section_and_caveats():
    from fastapi.testclient import TestClient
    from app.main import app

    job_id = "job_unit_seal_text"
    _save_job(job_id)
    with TestClient(app) as client:
        body = client.get("/api/report/%s" % job_id).text
    assert "STAGE 4 FORENSICS" in body and "finding of guilt" in body and "INTEGRITY" in body


def test_unknown_job_and_bad_id_are_rejected():
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as client:
        assert client.get("/api/report/job_does_not_exist/sha256").status_code == 404
        assert client.get("/api/v1/attribution/job_does_not_exist").status_code == 404
