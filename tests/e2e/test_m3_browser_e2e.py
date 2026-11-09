"""Real Chromium journeys for M3 using isolated, generated test data only."""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import pytest
from playwright.sync_api import expect, sync_playwright

pytestmark = pytest.mark.synthetic_data


ROOT = Path(__file__).resolve().parents[2]
SCENE_ID = "browser_m3_selftest"


@pytest.fixture(scope="module")
def local_app(tmp_path_factory):
    """Start Uvicorn against an isolated data/model store and no public bind."""
    data_dir = tmp_path_factory.mktemp("tidetrace_browser_data")
    models_dir = data_dir / "models"
    models_dir.mkdir()
    (data_dir / "sar").mkdir()
    (data_dir / "sar" / "scenes.json").write_text(
        json.dumps({"scenes": []}), encoding="utf-8")

    env = os.environ.copy()
    env.update({
        "TIDETRACE_DATA": str(data_dir),
        "TIDETRACE_MODELS": str(models_dir),
        "TIDETRACE_ALLOW_SELFTEST_SCENES": "1",
        "TIDETRACE_OFFLINE": "1",
        "TIDETRACE_OPEN_METEO_LIVE": "0",
    })

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base_url = "http://127.0.0.1:%d" % port
    log_path = data_dir / "uvicorn.log"
    log_file = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=ROOT,
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )

    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("Uvicorn exited during startup:\n" + log_path.read_text(encoding="utf-8"))
            try:
                with urlopen(base_url + "/api/health", timeout=1) as response:
                    if response.status == 200:
                        break
            except (URLError, TimeoutError, OSError):
                time.sleep(0.25)
        else:
            raise RuntimeError("Uvicorn did not become ready:\n" + log_path.read_text(encoding="utf-8"))

        yield {"base_url": base_url, "data_dir": data_dir, "env": env, "log_path": log_path}
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        log_file.close()


def _run_generator(app):
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "make_selftest_scene.py"),
         "--id", SCENE_ID, "--size", "768"],
        cwd=ROOT,
        env=app["env"],
        check=True,
        timeout=45,
        capture_output=True,
        text=True,
    )


def test_m3_analysis_drift_map_navigation_reports_and_error_states(local_app, tmp_path):
    artifact_dir = Path(os.environ.get("TIDETRACE_E2E_ARTIFACTS", tmp_path / "evidence"))
    artifact_dir.mkdir(parents=True, exist_ok=True)
    diagnostics = {
        "console_errors": [],
        "page_errors": [],
        "failed_requests": [],
        "http_errors": [],
        "expected_http_errors": [],
        "run_requests": [],
    }
    page = None

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
        page = context.new_page()
        page.set_default_timeout(15_000)
        page.on("console", lambda msg: diagnostics["console_errors"].append(msg.text)
                if msg.type == "error" and not msg.text.startswith(
                    "Failed to load resource: the server responded with a status of 404")
                and not msg.text.startswith(
                    "Failed to load resource: the server responded with a status of 503")
                else None)
        page.on("pageerror", lambda error: diagnostics["page_errors"].append(str(error)))
        page.on("requestfailed", lambda req: diagnostics["failed_requests"].append(
            {"url": req.url, "error": req.failure}))
        page.on("request", lambda req: diagnostics["run_requests"].append(req.url)
                if req.method == "POST" and req.url.endswith("/api/run") else None)

        def record_response(response):
            if response.status >= 400:
                item = {"url": response.url, "status": response.status}
                if response.status == 404 and any(path in response.url for path in (
                        "/data/optical/", "/data/land/world_land_",
                        "/data/basemap/manifest.json")):
                    diagnostics["expected_http_errors"].append(item)
                elif response.status == 503 and "/api/run" in response.url:
                    diagnostics["expected_http_errors"].append(item)
                elif response.status == 503 and "/api/report/" in response.url:
                    diagnostics["expected_http_errors"].append(item)
                else:
                    diagnostics["http_errors"].append(item)

        page.on("response", record_response)

        try:
            page.goto(local_app["base_url"], wait_until="networkidle")
            expect(page).to_have_title(re.compile("TideTrace"))
            expect(page.locator("#map")).to_be_visible()
            expect(page.locator("#scene-info")).to_contain_text("No scenes indexed.")
            expect(page.get_by_role("button", name="Run analysis")).to_be_disabled()

            # Generate the project-provided synthetic scene inside this test's
            # temporary data root; the actual indexed project data stays read-only.
            _run_generator(local_app)
            page.reload(wait_until="networkidle")
            scene = page.locator(".scene-row").filter(has_text="SELF TEST synthetic scene")
            expect(scene).to_be_visible()
            scene.click()
            expect(scene).to_have_attribute("aria-current", "true")

            # Exercise map controls and confirm the map frames the selected scene.
            zoom_before = page.evaluate("window.__tidetrace.map.getZoom()")
            page.get_by_title("Zoom in").click()
            page.wait_for_function(
                "expected => window.__tidetrace.map.getZoom() === expected",
                arg=zoom_before + 1,
            )
            bounds_contain_scene = page.evaluate("""() => {
              const b = window.__tidetrace.map.getBounds();
              return b.contains([19.05, 71.60]);
            }""")
            assert bounds_contain_scene

            page.locator("#hind").fill("6")
            page.locator("#fore").fill("6")
            page.locator("#radius").fill("10")
            page.locator("#window").fill("3")

            run_button = page.get_by_role("button", name="Run analysis")
            box = run_button.bounding_box()
            assert box is not None
            with page.expect_response(lambda r: r.url.endswith("/api/run"), timeout=120_000) as run_response:
                # Two real mouse clicks exercise the disabled-while-running guard.
                page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                expect(run_button).to_be_disabled()
                expect(page.locator("#busy")).to_have_class(re.compile(r"\bon\b"))
            response = run_response.value
            assert response.status == 200, response.text()
            job = response.json()
            assert job["input"]["scene_id"] == SCENE_ID
            assert job["input"]["hindcast_hours"] == 6
            assert job["input"]["forecast_hours"] == 6
            assert job.get("drift"), "the detected self-test slick should exercise M3 drift"
            assert len(diagnostics["run_requests"]) == 1, "double-click submitted more than one run"
            assert len([r for r in diagnostics["http_errors"] if r["url"].endswith("/api/run")]) == 0

            expect(run_button).to_be_enabled()
            expect(page.locator("#busy")).not_to_have_class(re.compile(r"\bon\b"))
            expect(page.locator("#trace")).to_contain_text("HINDCAST")
            expect(page.locator("#trace")).to_contain_text("FORECAST")
            expect(page.locator("#spreadchart svg")).to_be_visible()
            expect(page.locator("#metocean .env")).to_be_visible()
            assert "SYNTHETIC CONSTANT FIELD" in job["drift"]["metocean"]["source"]
            expect(page.locator("#notices")).to_contain_text("NOT satisfied")
            page.screenshot(path=str(artifact_dir / "m3-browser-success.png"), full_page=True)

            origin = job["drift"]["origin"]
            origin_row = page.locator("#origin .kv").filter(has_text="Origin position")
            expect(origin_row.locator(".v")).to_have_text(
                "%.4f, %.4f" % (origin["lat"], origin["lon"]))
            expect(page.locator("#origin")).to_contain_text("Threatened box")

            # Toggle a real forecast layer and verify the Leaflet map reflects it.
            forecast_layer = page.locator("#layers label").filter(has_text="Forecast cone")
            forecast_toggle = forecast_layer.locator("input")
            expect(forecast_toggle).to_be_checked()
            has_forecast = page.evaluate("window.__tidetrace.layers.cone_fwd.getLayers().length > 0")
            assert has_forecast
            forecast_toggle.uncheck()
            assert page.evaluate("window.__tidetrace.map.hasLayer(window.__tidetrace.layers.cone_fwd)") is False
            forecast_toggle.check()
            assert page.evaluate("window.__tidetrace.map.hasLayer(window.__tidetrace.layers.cone_fwd)") is True

            # Navigate through the M3 view and the no-candidate evidence state.
            page.get_by_role("tab", name="Drift").click()
            expect(page.locator('.view[data-view="drift"]')).to_be_visible()
            expect(page.locator("#origin")).to_contain_text("Origin time")
            page.get_by_role("tab", name="Vessels").click()
            expect(page.locator('.view[data-view="vessels"]')).to_be_visible()
            expect(page.locator("#vessels-count")).to_have_text(
                "" if not job["attribution"]["suspects"]
                else str(len(job["attribution"]["suspects"])) + " ranked")
            expect(page.locator("#evidence")).to_contain_text("Pipeline steps")

            # Generate and inspect the actual HTML report in its popup.
            page.get_by_role("tab", name="Method").click()
            with page.expect_popup() as report_popup:
                page.get_by_role("button", name="Attribution note").click()
            report_page = report_popup.value
            report_page.wait_for_load_state("domcontentloaded")
            expect(report_page.get_by_role("heading", name="Maritime Pollution Attribution Note")).to_be_visible()
            expect(report_page.locator("body")).to_contain_text(job["job_id"])
            expect(report_page.locator("body")).to_contain_text("Origin")
            report_page.close()

            # Refresh through a saved-job link and verify M3 output is restored.
            linked_page = context.new_page()
            linked_page.set_default_timeout(15_000)
            linked_page.on("console", lambda msg: diagnostics["console_errors"].append(msg.text)
                           if msg.type == "error" and not msg.text.startswith(
                               "Failed to load resource: the server responded with a status of 404")
                           and not msg.text.startswith(
                               "Failed to load resource: the server responded with a status of 503")
                           else None)
            linked_page.on("pageerror", lambda error: diagnostics["page_errors"].append(str(error)))
            linked_page.on("requestfailed", lambda req: diagnostics["failed_requests"].append(
                {"url": req.url, "error": req.failure}))
            linked_page.on("request", lambda req: diagnostics["run_requests"].append(req.url)
                           if req.method == "POST" and req.url.endswith("/api/run") else None)
            linked_page.on("response", record_response)
            linked_page.goto(local_app["base_url"] + "/#job=%s&view=drift" % job["job_id"],
                             wait_until="networkidle")
            expect(linked_page.locator('.view[data-view="drift"]')).to_be_visible()
            expect(linked_page.locator("#origin")).to_contain_text("Origin position")
            page.close()
            page = linked_page

            # A failed report is rendered by the browser as a visible error
            # response rather than leaving a blank popup.
            context.route("**/api/report/" + job["job_id"], lambda route: route.fulfill(
                status=503, content_type="application/json",
                body=json.dumps({"detail": "E2E report failure"})))
            page.get_by_role("tab", name="Method").click()
            with page.expect_popup() as failed_report_popup:
                page.get_by_role("button", name="Attribution note").click()
            failed_report = failed_report_popup.value
            failed_report.wait_for_load_state("domcontentloaded")
            expect(failed_report.locator("body")).to_contain_text("E2E report failure")
            failed_report.close()
            context.unroute("**/api/report/" + job["job_id"])

            # Simulate a local API outage and verify visible error/recovery state.
            page.route("**/api/run", lambda route: route.fulfill(
                status=503, content_type="application/json",
                body=json.dumps({"detail": "E2E run failure"})))
            page.get_by_role("button", name="Run analysis").click()
            expect(page.locator("#notices")).to_contain_text("Run failed: 503")
            expect(page.locator("#notices")).to_contain_text("E2E run failure")
            expect(page.get_by_role("button", name="Run analysis")).to_be_enabled()
            expect(page.locator("#busy")).not_to_have_class(re.compile(r"\bon\b"))
            page.unroute("**/api/run")
            assert len(diagnostics["run_requests"]) == 2

            page.screenshot(path=str(artifact_dir / "m3-browser-api-error.png"), full_page=True)

            diagnostics["job_id"] = job["job_id"]
            diagnostics["status"] = job["status"]
            diagnostics["drift_origin"] = origin
            diagnostics["scene_id"] = job["input"]["scene_id"]
            diagnostics["report_status"] = response.status
            assert diagnostics["console_errors"] == []
            assert diagnostics["page_errors"] == []
            assert diagnostics["failed_requests"] == []
            assert diagnostics["http_errors"] == [], diagnostics["http_errors"]
        finally:
            if page and not page.is_closed():
                page.screenshot(path=str(artifact_dir / "m3-browser-final.png"), full_page=True)
            (artifact_dir / "diagnostics.json").write_text(
                json.dumps(diagnostics, indent=2, default=str), encoding="utf-8")
            context.close()
            browser.close()
