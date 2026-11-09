"""Repeatable, offline M3 performance and reliability measurements.

Examples:
    python benchmarks/benchmark_m3.py --output .pytest_cache/phase5_baseline.json
    python benchmarks/benchmark_m3.py --smoke

The benchmark creates all scene, forcing, job, and cache data in a temporary
directory. It never fetches data or binds a network port. API timings use
FastAPI's in-process TestClient; wall-clock thresholds are intentionally absent.
"""
from __future__ import annotations

import argparse
import cProfile
import gc
import importlib.metadata
import io
import json
import os
import platform
import pstats
import statistics
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
T0 = datetime(2024, 2, 14, 6, 0, tzinfo=timezone.utc)
MIB = 1024 * 1024


def _windows_memory_status():
    import ctypes

    class MemoryStatus(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MemoryStatus()
    status.dwLength = ctypes.sizeof(status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return None
    return {"total": int(status.ullTotalPhys), "available": int(status.ullAvailPhys)}


def _system_memory_status():
    if os.name == "nt":
        return _windows_memory_status()
    try:
        page = os.sysconf("SC_PAGE_SIZE")
        return {
            "total": int(os.sysconf("SC_PHYS_PAGES") * page),
            "available": int(os.sysconf("SC_AVPHYS_PAGES") * page),
        }
    except (AttributeError, OSError, ValueError):
        return None


def _process_rss_bytes():
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel32.GetCurrentProcess.argtypes = []
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(ProcessMemoryCounters), wintypes.DWORD,
        ]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        handle = kernel32.GetCurrentProcess()
        ok = psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb)
        return int(counters.WorkingSetSize) if ok else None
    try:
        pages = int(Path("/proc/self/statm").read_text(encoding="ascii").split()[1])
        return pages * os.sysconf("SC_PAGE_SIZE")
    except (OSError, ValueError, IndexError):
        try:
            import resource
            value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            return int(value if sys.platform == "darwin" else value * 1024)
        except (ImportError, OSError, ValueError):
            return None


class ResourceSampler:
    """Sample process RSS and system free memory during a single operation."""

    def __init__(self, interval_seconds: float = 0.05):
        self.interval_seconds = interval_seconds
        self.stop_event = threading.Event()
        self.thread = None
        self.rss_start = _process_rss_bytes()
        self.rss_peak = self.rss_start
        status = _system_memory_status()
        self.available_start = status["available"] if status else None
        self.available_min = self.available_start

    def _sample(self):
        while not self.stop_event.wait(self.interval_seconds):
            rss = _process_rss_bytes()
            if rss is not None:
                self.rss_peak = max(self.rss_peak or rss, rss)
            status = _system_memory_status()
            if status:
                value = status["available"]
                self.available_min = value if self.available_min is None else min(
                    self.available_min, value)

    def __enter__(self):
        self.thread = threading.Thread(target=self._sample, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *_exc):
        self.stop_event.set()
        self.thread.join(timeout=1)
        rss_end = _process_rss_bytes()
        if rss_end is not None:
            self.rss_peak = max(self.rss_peak or rss_end, rss_end)

    def as_dict(self):
        return {
            "process_rss_start_mib": _mib(self.rss_start),
            "process_rss_peak_mib_sampled": _mib(self.rss_peak),
            "process_rss_peak_delta_mib_sampled": _mib(
                max(0, self.rss_peak - self.rss_start)
                if self.rss_peak is not None and self.rss_start is not None else None),
            "system_available_start_mib": _mib(self.available_start),
            "system_available_min_mib": _mib(self.available_min),
        }


def _mib(value):
    return round(value / MIB, 2) if value is not None else None


def _measure(fn: Callable[[], dict]) -> dict:
    wall_start = time.perf_counter()
    cpu_start = time.process_time()
    with ResourceSampler() as sampler:
        output = fn()
    elapsed = time.perf_counter() - wall_start
    cpu = time.process_time() - cpu_start
    return {
        "wall_ms": round(elapsed * 1000.0, 3),
        "process_cpu_seconds": round(cpu, 4),
        "cpu_core_equivalents_percent": round(cpu / elapsed * 100.0, 1) if elapsed else 0.0,
        "resources": sampler.as_dict(),
        "output": output,
    }


def _distribution(samples: List[dict]) -> dict:
    values = [row["wall_ms"] for row in samples]
    mean = statistics.mean(values)
    return {
        "samples": samples,
        "count": len(values),
        "median_ms": round(statistics.median(values), 3),
        "min_ms": round(min(values), 3),
        "max_ms": round(max(values), 3),
        "stdev_ms": round(statistics.stdev(values), 3) if len(values) > 1 else 0.0,
        "coefficient_of_variation_percent": round(
            statistics.stdev(values) / mean * 100.0, 2) if len(values) > 1 and mean else 0.0,
    }


def _make_cache(fields, config, scene_id: str, grid: int, hours: int):
    import numpy as np

    times = T0.timestamp() + np.arange(-48, hours + 49, dtype=float) * 3600.0
    lats = np.linspace(18.0, 20.0, grid)
    lons = np.linspace(70.5, 72.5, grid)
    yy, xx = np.meshgrid(lats, lons, indexing="ij")
    shape = (times.size, grid, grid)
    data = {
        "u_current": np.broadcast_to(0.14 + (xx - 71.5) * 0.006, shape).copy(),
        "v_current": np.broadcast_to(0.04 + (yy - 19.0) * 0.004, shape).copy(),
        "u_wind10": np.broadcast_to(3.8 + (yy - 19.0) * 0.02, shape).copy(),
        "v_wind10": np.broadcast_to(1.2 + (xx - 71.5) * 0.01, shape).copy(),
    }
    field = fields._from_arrays(
        times, lats, lons, data, "deterministic local M3 performance field", "n/a", scene_id)
    path = Path(config.METOCEAN_DIR) / (scene_id + ".npz")
    fields.save_npz(path, field)
    return {"scene_id": scene_id, "grid_lat_lon": [grid, grid], "time_steps": int(times.size),
            "estimated_uncompressed_forcing_mib": round(
                sum(a.nbytes for a in field.data.values()) / MIB, 2),
            "cache_file_bytes": path.stat().st_size}


def _run_drift(pipeline, *, scene_id, hindcast, forecast, ensemble):
    result = pipeline.run_drift(
        ring=None,
        centroid=(71.5, 19.0),
        t_sat=T0,
        hindcast_hours=hindcast,
        forecast_hours=forecast,
        ensemble_n=ensemble,
        scene_id=scene_id,
    )
    back = result["_runs"]["back"]
    fwd = result["_runs"]["forward"]
    origin = result["origin"]
    return {
        "origin_time": origin["t"],
        "origin_lon": origin["lon"],
        "origin_lat": origin["lat"],
        "hindcast_shape": list(back.lon.shape),
        "forecast_shape": list(fwd.lon.shape),
        "hindcast_start": back.times[0].isoformat(),
        "hindcast_end": back.times[-1].isoformat(),
        "forecast_start": fwd.times[0].isoformat(),
        "forecast_end": fwd.times[-1].isoformat(),
        "hindcast_cone_area_km2": result["cone_back"]["properties"]["area_km2"],
        "forecast_cone_area_km2": result["cone_fwd"]["properties"]["area_km2"],
        "threatened_bbox": result["threatened_bbox"],
        "forcing_source": result["metocean"]["source"],
    }


def _profile(pipeline, case):
    profiler = cProfile.Profile()
    profiler.enable()
    _run_drift(pipeline, **case)
    profiler.disable()
    stream = io.StringIO()
    pstats.Stats(profiler, stream=stream).strip_dirs().sort_stats("cumulative").print_stats(18)
    rows = []
    for line in stream.getvalue().splitlines()[5:]:
        parts = line.split()
        if len(parts) >= 6:
            rows.append({"profile_line": line.strip()})
    return rows


def _response_summary(response):
    try:
        doc = response.json()
    except Exception:
        doc = {}
    drift = doc.get("drift") or doc
    if "_runs" not in drift:
        origin = drift.get("origin") or {}
        def track_tail(name):
            coordinates = ((drift.get(name) or {}).get("geometry") or {}).get("coordinates") or []
            return coordinates[-1] if coordinates else None

        def cone_summary(name):
            feature = drift.get(name) or {}
            geometry = feature.get("geometry") or {}
            rings = geometry.get("coordinates") or []
            ring = rings[0] if rings else []
            return {
                "area_km2": (feature.get("properties") or {}).get("area_km2"),
                "bounds_lonlat": ([min(p[0] for p in ring), min(p[1] for p in ring),
                                   max(p[0] for p in ring), max(p[1] for p in ring)]
                                  if ring else None),
            }

        return {
            "status_code": response.status_code,
            "body_bytes": len(response.content),
            "job_id": doc.get("job_id"),
            "origin": {"time": origin.get("t"), "lon": origin.get("lon"),
                       "lat": origin.get("lat")},
            "hindcast_start": track_tail("hindcast_track"),
            "forecast_end": track_tail("forecast_track"),
            "cone_back": cone_summary("cone_back"),
            "cone_forecast": cone_summary("cone_fwd"),
            "threatened_bbox": drift.get("threatened_bbox"),
            "metocean_source": (drift.get("metocean") or {}).get("source"),
        }
    return {"status_code": response.status_code, "body_bytes": len(response.content)}


def _percentile(values, pct):
    if not values:
        return None
    return round(float(np_percentile(values, pct)), 3)


def np_percentile(values, pct):
    import numpy as np
    return np.percentile(values, pct)


def run_benchmarks(args):
    import numpy as np

    temporary_root = Path(args.temporary_root).resolve() if args.temporary_root else ROOT / ".pytest_cache"
    temporary_root.mkdir(parents=True, exist_ok=True)
    initial_memory = _system_memory_status()
    safe_floor = args.min_free_mib * MIB
    if initial_memory and initial_memory["available"] < safe_floor:
        raise RuntimeError("available RAM is below the configured safety floor; no workload started")

    with tempfile.TemporaryDirectory(prefix="m3_perf_", dir=temporary_root) as temp_name:
        sandbox = Path(temp_name)
        app_data = sandbox / "data"
        app_models = sandbox / "models"
        app_data.mkdir()
        app_models.mkdir()
        os.environ.update({
            "TIDETRACE_DATA": str(app_data),
            "TIDETRACE_MODELS": str(app_models),
            "TIDETRACE_ALLOW_SELFTEST_SCENES": "1",
            "TIDETRACE_OFFLINE": "1",
            "TIDETRACE_OPEN_METEO_LIVE": "0",
        })
        sys.path.insert(0, str(ROOT))

        import numpy as np
        core_import_start = time.perf_counter()
        from app import config, pipeline
        from app.drift import fields
        core_import_ms = round((time.perf_counter() - core_import_start) * 1000.0, 3)

        app_import_start = time.perf_counter()
        from app.main import app
        app_import_ms = round((time.perf_counter() - app_import_start) * 1000.0, 3)

        definitions = {
            "small": {"grid": 17, "forcing_future_hours": 24,
                      "hindcast": 6, "forecast": 12, "ensemble": 12},
            "typical": {"grid": 33, "forcing_future_hours": 48,
                        "hindcast": 18, "forecast": 36, "ensemble": 50},
            "large": {"grid": 49, "forcing_future_hours": 120,
                      "hindcast": 18, "forecast": 96, "ensemble": 200},
        }
        if args.smoke:
            definitions = {key: definitions[key] for key in ("small", "typical")}

        dataset_manifest = {}
        for name, spec in definitions.items():
            dataset_manifest[name] = _make_cache(
                fields, config, "perf_" + name, spec["grid"], spec["forcing_future_hours"])
        persistence_cache = _make_cache(fields, config, "perf_persistence", 17, 24)
        dataset_manifest["persistence_scene"] = persistence_cache

        result = {
            "metadata": {
                "python": sys.version,
                "platform": platform.platform(),
                "processor": platform.processor(),
                "logical_cpus": os.cpu_count(),
                "system_memory_start_mib": {
                    "total": _mib(initial_memory["total"]) if initial_memory else None,
                    "available": _mib(initial_memory["available"]) if initial_memory else None,
                },
                "dependencies": {},
                "config": {
                    "rk4_hindcast_dt_seconds": config.HINDCAST_RK4_DT_SECONDS,
                    "forecast_dt_seconds": config.DT_SECONDS,
                    "hindcast_cap_hours": config.HINDCAST_RK4_MAX_H,
                    "default_ensemble": config.ENSEMBLE_N,
                    "offline": config.OFFLINE,
                },
                "startup": {"core_import_ms": core_import_ms,
                            "app_module_import_ms": app_import_ms},
                "workload_data": dataset_manifest,
                "notes": [
                    "Synthetic deterministic forcing, no external data or services.",
                    "Process RSS is sampled every 50 ms and can miss shorter peaks.",
                    "CPU metric is process CPU time divided by wall time (core-equivalent percent), not system-wide utilization.",
                ],
            },
            "workloads": {},
            "api": {},
            "concurrency": {},
            "sustained": {},
            "profile_typical": [],
        }
        for name in ("numpy", "scipy", "rasterio", "pyproj", "fastapi", "starlette",
                     "pydantic", "uvicorn", "httpx"):
            try:
                result["metadata"]["dependencies"][name] = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                result["metadata"]["dependencies"][name] = None

        run_count = 1 if args.smoke else args.runs
        for name, spec in definitions.items():
            free = _system_memory_status()
            if free and free["available"] < safe_floor:
                result["workloads"][name] = {"status": "skipped", "reason": "RAM safety floor"}
                result["metadata"]["safety_stop"] = "available RAM fell below safety floor"
                break
            case = {"scene_id": "perf_" + name, "hindcast": spec["hindcast"],
                    "forecast": spec["forecast"], "ensemble": spec["ensemble"]}
            cold = _measure(lambda: _run_drift(pipeline, **case))
            warm = [_measure(lambda: _run_drift(pipeline, **case))
                    for _ in range(max(run_count - 1, 0))]
            result["workloads"][name] = {
                "configuration": spec,
                "cold_first_run": cold,
                "warm_runs": _distribution(warm) if warm else {"count": 0, "samples": []},
                "representative_output": cold["output"],
            }
            if name == "typical" and not args.smoke:
                result["profile_typical"] = _profile(pipeline, case)

        free = _system_memory_status()
        if free and free["available"] < safe_floor:
            result["metadata"]["safety_stop"] = "API, concurrency, and sustained phases skipped below RAM safety floor"
            result["api"]["status"] = "skipped"
            return result

        try:
            from fastapi.testclient import TestClient
            client = TestClient(app)
        except Exception as exc:
            result["api"]["status"] = "unavailable"
            result["api"]["reason"] = str(exc)
            return result

        startup = time.perf_counter()
        client.__enter__()
        result["metadata"]["startup"]["app_lifespan_ms"] = round(
            (time.perf_counter() - startup) * 1000.0, 3)
        try:
            spec = definitions.get("typical", definitions["small"])
            api_scene = "perf_typical" if "typical" in definitions else "perf_small"
            payload = {
                "centroid": [71.5, 19.0], "t_sat": T0.isoformat(),
                "hours_back": spec["hindcast"], "hours_fwd": spec["forecast"],
                "ensemble_n": spec["ensemble"], "scene_id": api_scene,
            }
            api_count = 1 if args.smoke else args.runs
            api_samples = []
            api_errors = []
            for _ in range(api_count):
                measured = _measure(lambda: _response_summary(
                    client.post("/api/drift", json=payload)))
                if measured["output"]["status_code"] != 200:
                    api_errors.append(measured["output"])
                api_samples.append(measured)
            result["api"]["m3_drift_endpoint"] = _distribution(api_samples)
            result["api"]["m3_drift_endpoint"]["errors"] = api_errors

            if not args.smoke and "large" in definitions:
                free = _system_memory_status()
                if free and free["available"] < safe_floor:
                    result["metadata"]["safety_stop"] = "concurrency and sustained phases skipped below RAM safety floor"
                    return result
                concurrent_count = min(max(args.concurrency, 1), 2)
                concurrent_payloads = [dict(payload, scene_id=api_scene) for _ in range(concurrent_count)]
                concurrent_samples = []
                concurrent_errors = []
                batch_start = time.perf_counter()
                concurrent_cpu_start = time.process_time()

                def concurrent_request(row):
                    started = time.perf_counter()
                    try:
                        response = client.post("/api/drift", json=row)
                        summary = _response_summary(response)
                        summary["latency_ms"] = round((time.perf_counter() - started) * 1000.0, 3)
                        return summary
                    except Exception as exc:
                        return {"status_code": 0, "latency_ms": round(
                            (time.perf_counter() - started) * 1000.0, 3),
                            "error": "%s: %s" % (type(exc).__name__, exc)}

                with ResourceSampler() as concurrent_sampler:
                    with ThreadPoolExecutor(max_workers=concurrent_count) as executor:
                        futures = [executor.submit(concurrent_request, row)
                                   for row in concurrent_payloads]
                        for future in as_completed(futures):
                            summary = future.result()
                            concurrent_samples.append(summary)
                            if summary["status_code"] != 200:
                                concurrent_errors.append(summary)
                batch_seconds = time.perf_counter() - batch_start
                concurrent_cpu = time.process_time() - concurrent_cpu_start
                result["concurrency"] = {
                    "concurrency_level": concurrent_count,
                    "completed": len(concurrent_samples),
                    "errors": concurrent_errors,
                    "batch_wall_seconds": round(batch_seconds, 3),
                    "throughput_requests_per_second": round(
                        len(concurrent_samples) / batch_seconds, 3) if batch_seconds else None,
                    "per_request_latency_ms": [row.get("latency_ms") for row in concurrent_samples],
                    "response_body_bytes": [row.get("body_bytes") for row in concurrent_samples],
                    "process_cpu_seconds": round(concurrent_cpu, 4),
                    "cpu_core_equivalents_percent": round(
                        concurrent_cpu / batch_seconds * 100.0, 1) if batch_seconds else 0.0,
                    "resources": concurrent_sampler.as_dict(),
                    "note": "API calls shared one in-process TestClient; no public listener was started.",
                }

                sustained_count = min(max(args.sustained, 1), 8)
                sustained_samples = []
                rss_before = _process_rss_bytes()
                sustained_start = time.perf_counter()
                for _ in range(sustained_count):
                    free = _system_memory_status()
                    if free and free["available"] < safe_floor:
                        result["sustained"]["stopped_early"] = "RAM safety floor"
                        break
                    measured = _measure(lambda: _response_summary(
                        client.post("/api/drift", json=payload)))
                    sustained_samples.append(measured)
                    if measured["output"]["status_code"] != 200:
                        break
                sustained_seconds = time.perf_counter() - sustained_start
                gc.collect()
                rss_after = _process_rss_bytes()
                result["sustained"].update({
                    "requested_repetitions": sustained_count,
                    "completed": len(sustained_samples),
                    "batch_wall_seconds": round(sustained_seconds, 3),
                    "throughput_requests_per_second": round(
                        len(sustained_samples) / sustained_seconds, 3)
                        if sustained_seconds else None,
                    "latency": _distribution(sustained_samples),
                    "process_rss_before_gc_mib": _mib(rss_before),
                    "process_rss_after_gc_mib": _mib(rss_after),
                    "process_rss_change_mib": _mib(rss_after - rss_before)
                        if rss_after is not None and rss_before is not None else None,
                    "error_count": sum(1 for row in sustained_samples
                                        if row["output"]["status_code"] != 200),
                })

            if not args.smoke:
                # Generate the project-provided synthetic SAR scene only inside
                # this benchmark's temporary application data root.
                import subprocess
                generator = ROOT / "scripts" / "make_selftest_scene.py"
                generated = subprocess.run(
                    [sys.executable, str(generator), "--id", "perf_persistence", "--size", "384"],
                    cwd=ROOT, env=os.environ.copy(), capture_output=True, text=True, timeout=60,
                    check=True,
                )
                result["api"]["generated_scene"] = generated.stdout.strip().splitlines()[-1]
                run_payload = {
                    "scene_id": "perf_persistence", "job_id": "job_perf_baseline",
                    "hindcast_hours": 6, "forecast_hours": 6, "ensemble_n": 24,
                    "prefer_model": False, "render_overlays": False,
                }
                run_sample = _measure(lambda: _response_summary(
                    client.post("/api/run", json=run_payload)))
                job_id = run_sample["output"].get("job_id")

                def retrieve_saved_job():
                    response = client.get("/api/jobs/" + job_id)
                    return {"status_code": response.status_code,
                            "body_bytes": len(response.content)}

                get_sample = _measure(retrieve_saved_job) if job_id else None
                job_path = Path(config.JOBS_DIR) / (job_id + ".json") if job_id else None
                result["api"]["full_run_and_persistence"] = {
                    "sample": run_sample,
                    "saved_job_retrieval": get_sample,
                    "saved_job_bytes": job_path.stat().st_size if job_path and job_path.exists() else None,
                }
        finally:
            client.__exit__(None, None, None)

        final_memory = _system_memory_status()
        result["metadata"]["system_memory_end_mib"] = {
            "available": _mib(final_memory["available"]) if final_memory else None,
        }
        return result


def _summary(result):
    print("M3 offline performance benchmark")
    metadata = result["metadata"]
    print("Runtime: %s | %s | CPUs=%s | RAM available at start=%s MiB" % (
        metadata["python"].split()[0], metadata["platform"], metadata["logical_cpus"],
        metadata["system_memory_start_mib"]["available"]))
    for name, row in result["workloads"].items():
        if row.get("status") == "skipped":
            print("%-8s skipped: %s" % (name, row["reason"]))
            continue
        warm = row["warm_runs"]
        warm_text = ("warm median=%7.1f ms  warm range=%s ms" % (
            warm["median_ms"], (warm["min_ms"], warm["max_ms"]))
            if warm.get("count") else "warm repeats=not measured")
        print("%-8s first=%7.1f ms  %s  ensemble=%s grid=%s" % (
            name, row["cold_first_run"]["wall_ms"], warm_text,
            row["configuration"]["ensemble"], row["configuration"]["grid"]))
    if "m3_drift_endpoint" in result["api"]:
        api = result["api"]["m3_drift_endpoint"]
        print("API drift median=%s ms p95=%s ms errors=%s" % (
            api["median_ms"], _percentile([s["wall_ms"] for s in api["samples"]], 95),
            len(api["errors"])))
    if result["concurrency"]:
        row = result["concurrency"]
        print("Concurrent API: %s/%s completed at concurrency %s in %.2f s; errors=%s" % (
            row["completed"], row["completed"] + len(row["errors"]),
            row["concurrency_level"], row["batch_wall_seconds"], len(row["errors"])))
    if result["sustained"]:
        row = result["sustained"]
        print("Sustained API: %s/%s requests completed; RSS change after GC=%s MiB" % (
            row["completed"], row["requested_repetitions"], row["process_rss_change_mib"]))
    if result["profile_typical"]:
        print("Top cProfile cumulative-time rows:")
        for row in result["profile_typical"][:8]:
            print("  " + row["profile_line"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=3, help="repeated samples per workload (default: 3)")
    parser.add_argument("--concurrency", type=int, default=2,
                        help="maximum concurrent API calls; safety-capped at 2")
    parser.add_argument("--sustained", type=int, default=5,
                        help="sequential API repetitions; safety-capped at 8")
    parser.add_argument("--min-free-mib", type=int, default=400,
                        help="stop escalating if system free RAM falls below this value")
    parser.add_argument("--temporary-root", help="scratch root; defaults to repository .pytest_cache")
    parser.add_argument("--output", help="optional JSON results path")
    parser.add_argument("--smoke", action="store_true",
                        help="small/typical one-pass smoke only; omit stress and full detect pipeline")
    args = parser.parse_args()
    if args.runs < 1 or args.min_free_mib < 128:
        parser.error("runs must be positive and min-free-mib must be at least 128")
    result = run_benchmarks(args)
    _summary(result)
    encoded = json.dumps(result, indent=2, default=str)
    if args.output:
        destination = Path(args.output).resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(encoded, encoding="utf-8")
        print("JSON results: %s" % destination)
    if args.output is None:
        print(encoded)

    failures = []
    for name, row in result["workloads"].items():
        if row.get("status") == "skipped":
            continue
        if row.get("cold_first_run", {}).get("output", {}).get("status_code", 200) != 200:
            failures.append("%s workload returned a non-200 status" % name)
    api = result.get("api", {})
    endpoint = api.get("m3_drift_endpoint", {})
    if "m3_drift_endpoint" not in api:
        failures.append("M3 drift endpoint did not run")
    if endpoint.get("errors"):
        failures.append("M3 drift endpoint returned errors")
    if api.get("full_run_and_persistence", {}).get("sample", {}).get(
            "output", {}).get("status_code", 200) != 200:
        failures.append("full run endpoint returned a non-200 status")
    if api.get("full_run_and_persistence", {}).get("saved_job_retrieval", {}).get(
            "output", {}).get("status_code", 200) != 200:
        failures.append("saved job retrieval returned a non-200 status")
    if result.get("concurrency", {}).get("errors"):
        failures.append("concurrent requests returned errors")
    if result.get("sustained", {}).get("error_count", 0):
        failures.append("sustained requests returned errors")
    if failures:
        raise SystemExit("Benchmark failure: " + "; ".join(failures))


if __name__ == "__main__":
    main()
