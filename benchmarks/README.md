# M3 performance benchmark

Run from the repository root with the project's installed environment:

```powershell
python benchmarks/benchmark_m3.py --smoke
python benchmarks/benchmark_m3.py --runs 3 --concurrency 2 --sustained 5 `
  --output .pytest_cache/phase5-results.json
```

The smoke run measures one small and one typical offline drift workload and one
in-process M3 API request. The full run also measures a larger workload,
concurrency, repeated API requests, saved-job retrieval, a representative
`/api/run`, and a cProfile sample. It writes the detailed environment, timings,
resource samples, and output summaries to JSON when `--output` is supplied.

All forcing fields and the self-test scene are generated locally in a temporary
application data root. No external data is fetched, no public listener is
started, and no original project data is used. Results are synthetic workload
measurements and should not be treated as production latency estimates.

The benchmark separates import and application startup from analysis timings.
RSS and available system memory are sampled every 50 ms, so short peaks can be
missed. CPU usage is process CPU time divided by wall time, expressed as
core-equivalents. API requests use FastAPI's in-process `TestClient`, not a
networked server. Concurrency is capped at two and sustained requests at eight;
the run stops escalating below the configurable free-memory floor (400 MiB by
default). There are no timing pass/fail thresholds because shared CI runners
vary. Compare repeated runs on the same machine and configuration.
