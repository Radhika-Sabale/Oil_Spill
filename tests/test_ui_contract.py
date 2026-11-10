"""Static guards on the SentinelTrace console contract.

These are cheap checks on files a browser will load. They catch the failures
that unit tests on the pipeline cannot see: a page that reaches the network,
a stage strip that silently loses a stage, a dossier that stops claiming what it
is, and a compliance phrase that should never appear in user-facing text.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"

FORBIDDEN = (
    "iso/iec 27037",
    "iso 27037",
    "chain of custody",
    "chain-of-custody",
    "legally admissible",
    "legal admissibility",
)


def _text(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_five_stages_are_declared_once_in_the_adapter():
    js = _text("js/adapter.js")
    assert 'CONTRACT = "sentineltrace.analysis/1"' in js
    for name in ("Ingest & gate", "Segment", "Hindcast & forecast", "Attribute", "Present & package"):
        assert name in js, "stage %r is missing from the adapter" % name
    # Exactly the five statuses the brief allows, plus the labels they render.
    for status in ('not_started: { label: "Not started"', 'running: { label: "Running"',
                   'done: { label: "Done"', 'failed: { label: "Failed"',
                   'unavailable: { label: "Unavailable"'):
        assert status in js, "stage status %r is missing" % status


def test_console_loads_the_new_modules_and_containers():
    html = _text("index.html")
    for asset in ("js/adapter.js", "js/dossier.js", "js/analysis-ui.js"):
        assert asset in html, "index.html does not load %s" % asset
    for node in ("stage-strip", "route-badge", "input-badges", "data-badges",
                 "uncertainty", "uncertainty-full", "stage-detail", "dossier-card",
                 "dossier-download", "verify-file", "verify-result",
                 "assumptions-panel", "limitations-panel", "unavailable-panel",
                 "not-established", "diagnostics", "legend-status", "map-status"):
        assert 'id="%s"' % node in html, "missing container #%s" % node
    assert 'data-view="stages"' in html and 'data-view="dossier"' in html
    # The digest element is created with the dossier card, so it lives in the module.
    assert 'code.id = "dossier-sha"' in _text("js/analysis-ui.js")


def test_the_pages_do_not_reach_the_network():
    """No CDN, no remote webfont, no remote media, no remote script.

    The landing hero does use a looping video, but it is a file served from
    /static/media by this app, so the page still runs with the network off.
    """
    for name in ("index.html", "landing.html"):
        html = _text(name)
        # Loaded assets only: <link href>, <script src>, <source src>, <img src>.
        loaded = re.findall(r'<(?:link|script|source|img)[^>]*(?:src|href)\s*=\s*"https?://[^"]+"', html)
        assert not loaded, "%s still loads remote assets: %s" % (name, loaded)
        assert "fonts.googleapis" not in html and "fonts.gstatic" not in html
        for attrs in re.findall(r"<video[^>]*>", html):
            src = re.search(r'\bsrc\s*=\s*"([^"]+)"', attrs)
            assert not src or src.group(1).startswith("/static/"), (
                "%s plays a non-local video: %r" % (name, src and src.group(1)))
        for src in re.findall(r'<source[^>]*\bsrc\s*=\s*"([^"]+)"', html):
            assert src.startswith("/static/"), "%s loads a non-local media source: %r" % (name, src)
    for name in ("style.css", "landing.css"):
        css = _text(name)
        assert "http://" not in css and "https://" not in css, "%s references a remote URL" % name


def test_data_status_is_never_colour_only():
    """REAL / SIMULATED / MISSING must carry a word and an icon, not just a hue."""
    js = _text("js/adapter.js")
    for status, label in (("real", "REAL"), ("simulated", "SIMULATED"), ("missing", "MISSING")):
        assert '%s: { label: "%s"' % (status, label) in js
    ui = _text("js/analysis-ui.js")
    assert 'el("span", "badge-ic", def.icon)' in ui
    assert 'el("span", "badge-tx", def.label)' in ui


def test_no_compliance_or_admissibility_claim_in_user_facing_files():
    files = ["index.html", "landing.html", "style.css", "landing.css",
             "js/adapter.js", "js/dossier.js", "js/analysis-ui.js"]
    for name in files:
        low = _text(name).lower()
        for phrase in FORBIDDEN:
            assert phrase not in low, "%s contains a forbidden claim: %r" % (name, phrase)


def test_pdf_a_is_only_ever_negated():
    """The dossier is a plain PDF. Every mention of PDF/A must say it is not claimed."""
    for name in ("index.html", "js/adapter.js", "js/dossier.js", "js/analysis-ui.js"):
        for line in _text(name).splitlines():
            if "PDF/A" in line:
                assert re.search(r"\bnot\b|no PDF/A|never", line, re.I), (
                    "%s mentions PDF/A without saying it is not claimed: %r" % (name, line))


def test_dossier_is_built_from_the_analysis_document_not_the_job():
    """One source of truth: the dossier writer has no fetches and no maths."""
    js = _text("js/dossier.js")
    assert "fetch(" not in js, "the dossier writer must not fetch anything"
    assert "window.SentinelDossier" in js
    ui = _text("js/analysis-ui.js")
    assert "D.build(analysis)" in ui, "the dossier is not built from the analysis document"
    assert "SentinelAdapter" in ui
