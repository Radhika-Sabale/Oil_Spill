"""GET /api/report/{job_id} - Maritime Pollution Attribution Note.

Optional by design. HTML is always available because it needs nothing beyond the
standard library. PDF is produced only if reportlab happens to be installed; if
it is not, the endpoint says so instead of failing the demo.

Integrity: the PDF is generated once per job, stored under data/reports/, and
every later download serves those exact bytes. Its SHA-256 is returned in the
X-Report-SHA256 header and at /api/report/{job_id}/sha256, and written to a
sidecar .sha256 file. A file cannot contain its own hash, so the digest lives
next to the PDF. A matching hash shows the bytes are unchanged since they were
generated; it does not show authenticity, legal admissibility, causation or guilt.
"""
from __future__ import annotations

import hashlib
import html
import io
import re
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, Response

from .. import config
from ..jobs import store as job_store

router = APIRouter()


def _rows(doc: Dict[str, Any]) -> Dict[str, Any]:
    det = doc.get("detection") or {}
    drift = doc.get("drift") or {}
    attr = doc.get("attribution") or {}
    poly = doc.get("primary_polygon") or (det.get("polygons") or [None])[0]
    props = (poly or {}).get("properties", {})
    return {"det": det, "drift": drift, "attr": attr, "props": props}


def _fmt(v: Any, unit: str = "") -> str:
    return "n/a" if v is None else ("%s%s" % (v, unit))


def _range(r: Dict[str, Any], unit: str) -> str:
    r = r or {}
    if r.get("nominal") is None:
        return "n/a (unavailable)"
    return "%s to %s %s (nominal %s)" % (r.get("min"), r.get("max"), unit, r.get("nominal"))


def _wrap(text: str, indent: str = "") -> List[str]:
    return textwrap.wrap(text, width=104, initial_indent=indent, subsequent_indent=indent + "  ") or [indent]


def _stage4_lines(attr: Dict[str, Any]) -> List[str]:
    st = attr.get("stage4")
    out = ["", "STAGE 4 FORENSICS (candidate evidence, not proof)"]
    if not st:
        return out + ["Not available for this job (run it again with a Stage 4 build)."]
    if st.get("error") or st.get("status") == "unavailable" and not st.get("candidates"):
        return out + _wrap("Stage 4 did not complete: %s" % (st.get("error") or "unavailable"))

    status = st.get("stage4_status") or {}
    out.append("Case type: %s   Incident: %s" % (st.get("case_type"), st.get("incident_id")))
    out.append("Feature status: " + ", ".join("%s=%s" % (k, v) for k, v in sorted(status.items())))
    h3 = st.get("h3") or {}
    if h3.get("status") == "implemented":
        out += _wrap("H3 res %s check: %s vessels, direct filter kept %s, H3 kept %s, missed by H3 %s "
                     "(consistent: %s)." % (h3.get("resolution"), h3.get("vessels"), h3.get("exact_kept"),
                                            h3.get("h3_kept"), len(h3.get("missed_by_h3") or []),
                                            "yes" if h3.get("consistent") else "NO"))
    else:
        out += _wrap("H3 check: %s" % (h3.get("note") or "unavailable"))
    slick = st.get("slick") or {}
    out += _wrap("Slick area: %s km2. Volume range: %s." % (_fmt(slick.get("area_km2")),
                                                            _range(slick.get("volume_m3"), "m3")))

    assumptions: List[str] = []
    unavailable: List[str] = []
    for c in st.get("candidates", [])[:10]:
        ev = c.get("evidence") or {}
        reach = ev.get("reachability") or {}
        out.append("")
        out += _wrap("#%s %s (MMSI %s): score %s of 1, evidence quality %s"
                     % (ev.get("rank"), c.get("vessel_name") or "UNKNOWN", c.get("mmsi"),
                        c.get("score"), c.get("evidence_quality")))
        out += _wrap("Minutes within search radius: %s (received: %s). Distance to origin: %s. "
                     "Speed change: %s. H3 cells: %d."
                     % (_fmt(c.get("time_overlap_minutes")), _fmt(ev.get("time_overlap_received_minutes")),
                        _fmt(c.get("distance_to_origin_km"), " km"), _fmt(c.get("speed_change_knots"), " kn"),
                        len(c.get("h3_cells") or [])), "  ")
        out += _wrap("Gap reachability: %s. Dark target: %s. Derived flow: %s."
                     % (reach.get("status"), (c.get("dark_target_match") or {}).get("status"),
                        _range(c.get("derived_flow_m3_h"), "m3/h")), "  ")
        out += _wrap("Why: " + (c.get("score_explanation") or ""), "  ")
        for a in c.get("assumptions") or []:
            if a not in assumptions:
                assumptions.append(a)
        for u in c.get("unavailable_features") or []:
            if u not in unavailable:
                unavailable.append(u)

    if assumptions:
        out += ["", "STAGE 4 ASSUMPTIONS"]
        for a in assumptions:
            out += _wrap("- " + a)
    if unavailable:
        out += ["", "STAGE 4 UNAVAILABLE"]
        for u in unavailable:
            out += _wrap("- " + u)
    out += ["", *_wrap(st.get("conclusion") or "")]
    return out


def _lines(doc: Dict[str, Any]) -> List[str]:
    r = _rows(doc)
    props, drift, attr = r["props"], r["drift"], r["attr"]
    origin = drift.get("origin") or {}
    det_metrics = r["det"].get("metrics") or {}

    out = [
        "Job: %s" % doc.get("job_id"),
        "Generated: %s" % datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "Scene: %s" % ((doc.get("scene") or {}).get("title") or (doc.get("input") or {}).get("scene_id")),
        "Observation time: %s" % (doc.get("input") or {}).get("t_sat"),
        "Detector: %s" % det_metrics.get("detector"),
        "",
        "SLICK GEOMETRY",
    ]

    if not props:
        out += [
            "No oil polygon above the area threshold on this scene.",
            "Look-alike polygons found: %s." % det_metrics.get("lookalike_polygons_found", 0),
            "This is a reported result, not a failure. A clean scene has no slick to",
            "characterise and no origin to trace, so drift and attribution were not run.",
        ]
    else:
        out += [
            "Area: %s km2" % props.get("area_km2"),
            "Length: %s km, width: %s km" % (props.get("length_km"), props.get("width_km")),
            "Perimeter: %s km" % props.get("perimeter_km"),
            "Orientation: %s deg" % props.get("orientation_deg"),
            "Compactness: %s" % props.get("compactness"),
            "Contrast against local sea: %s dB" % props.get("contrast_db"),
            "Centroid: %s, %s" % (props.get("centroid_lat"), props.get("centroid_lon")),
            "Detection confidence: %s" % props.get("confidence"),
        ]

    out += ["", "DRIFT"]
    if not drift:
        out.append("Not run: there was no slick to trace back.")
    else:
        out += [
            "Origin estimate: %s, %s at %s" % (origin.get("lat"), origin.get("lon"), origin.get("t")),
            "Estimated origin zone: approximate 95 percent KDE region, not a calibrated probability; buffered %s km."
            % (origin.get("buffer_km")),
            "90th-percentile ensemble spread radius: %s km"
            % origin.get("spread_km"),
            "Origin zone area: %s km2" % origin.get("area_km2"),
            "Age since origin: %s hours (drift proxy, not a laboratory age)" % doc.get("age_hours_proxy"),
            "Metocean source: %s" % (drift.get("metocean") or {}).get("source"),
            "Wind drift factor: %s, Stokes drift off" % config.ALPHA_WIND,
        ]

    out += ["", "RANKED SUSPECTS"]
    for s in attr.get("suspects", [])[:10]:
        out.append("%2d. %-24s MMSI %-10s %-18s %5.1f%%  %s"
                   % (s["rank"], (s["name"] or "UNKNOWN")[:24], s["mmsi"],
                      s["type"], s["score"], ", ".join(s["reasons"][:4])))
    if not attr.get("suspects"):
        out.append("No vessel passed the spatio-temporal filter.")
    out += _stage4_lines(attr)
    out += [
        "",
        "LIMITATIONS",
        "Candidate ranking only; not a finding of guilt. An AIS gap is a missing broadcast, not proof",
        "of intent.",
        "Ranked likelihood for investigation, not legal proof of discharge.",
        "Age is a drift time proxy. No chemical weathering model is used.",
        "Look-alike class polygons are excluded from attribution.",
    ]
    for w in doc.get("warnings", []):
        out.append("Note: %s" % w)
    out += ["",
            "INTEGRITY",
            "The SHA-256 of the PDF is served with the download (X-Report-SHA256) and at",
            "/api/report/%s/sha256. A file cannot contain its own hash." % doc.get("job_id")]
    return out


@router.get("/api/report/{job_id}", response_class=HTMLResponse)
def report_html(job_id: str) -> HTMLResponse:
    doc = job_store.load(job_id)
    if doc is None:
        raise HTTPException(404, "unknown job_id %r" % job_id)
    body = "\n".join(html.escape(line) for line in _lines(doc))
    page = (
        "<!doctype html><meta charset='utf-8'>"
        "<title>Maritime Pollution Attribution Note</title>"
        "<style>body{font:13px/1.5 ui-monospace,Consolas,monospace;max-width:820px;"
        "margin:32px auto;padding:0 20px;color:#0d1b2a}h1{font-size:19px;letter-spacing:.04em}"
        "pre{white-space:pre-wrap}</style>"
        "<h1>Maritime Pollution Attribution Note</h1>"
        "<p>%s &middot; %s</p><pre>%s</pre>"
        % (html.escape(config.UI_TITLE), html.escape(config.SIH_ID), body)
    )
    return HTMLResponse(page)


_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _report_paths(job_id: str):
    if not _SAFE_ID.match(job_id):
        raise HTTPException(400, "invalid job_id")
    folder = Path(config.DATA_DIR) / "reports"
    return folder, folder / ("attribution_%s.pdf" % job_id), folder / ("attribution_%s.pdf.sha256" % job_id)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _build_pdf(doc: Dict[str, Any]) -> bytes:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
    except Exception as exc:
        raise HTTPException(
            501, "reportlab is not installed, so PDF export is unavailable. "
                 "The HTML note at /api/report/%s is always available." % doc.get("job_id")) from exc

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4, invariant=1)   # invariant: no embedded clock or random id
    width, height = A4
    y = height - 60
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, y, "Maritime Pollution Attribution Note")
    y -= 18
    c.setFont("Helvetica", 8)
    c.drawString(50, y, "%s  %s" % (config.UI_TITLE, config.SIH_ID))
    y -= 22
    c.setFont("Courier", 8.5)
    for line in _lines(doc):
        if y < 60:
            c.showPage()
            c.setFont("Courier", 8.5)
            y = height - 60
        c.drawString(50, y, line[:110])
        y -= 11
    c.save()
    return buf.getvalue()


@router.get("/api/report/{job_id}/pdf")
def report_pdf(job_id: str, regenerate: bool = False) -> Response:
    doc = job_store.load(job_id)
    if doc is None:
        raise HTTPException(404, "unknown job_id %r" % job_id)
    folder, pdf_path, sha_path = _report_paths(job_id)

    if regenerate or not pdf_path.exists():
        data = _build_pdf(doc)
        folder.mkdir(parents=True, exist_ok=True)
        tmp = pdf_path.with_suffix(".pdf.part")
        tmp.write_bytes(data)
        tmp.replace(pdf_path)
        sha_path.write_text("%s  %s\n" % (_sha256(data), pdf_path.name), encoding="utf-8")
    else:
        data = pdf_path.read_bytes()

    return Response(data, media_type="application/pdf", headers={
        "Content-Disposition": 'attachment; filename="attribution_%s.pdf"' % job_id,
        "X-Report-SHA256": _sha256(data)})


@router.get("/api/report/{job_id}/sha256")
def report_sha256(job_id: str) -> Dict[str, Any]:
    """Recompute the digest from the stored PDF and compare with the one recorded at generation."""
    if job_store.load(job_id) is None:
        raise HTTPException(404, "unknown job_id %r" % job_id)
    _, pdf_path, sha_path = _report_paths(job_id)
    if not pdf_path.exists():
        raise HTTPException(404, "no PDF has been generated for this job yet; download it first")
    data = pdf_path.read_bytes()
    actual = _sha256(data)
    recorded = None
    if sha_path.exists():
        parts = sha_path.read_text(encoding="utf-8").split()
        recorded = parts[0] if parts else None
    return {
        "job_id": job_id,
        "file": pdf_path.name,
        "bytes": len(data),
        "sha256": actual,
        "recorded_sha256": recorded,
        "matches_recorded": recorded == actual,
        "note": ("A matching digest shows the stored bytes are unchanged since generation. It does not "
                 "establish authenticity, legal admissibility, causation or guilt."),
    }
