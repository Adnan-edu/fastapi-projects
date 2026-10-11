"""Prometheus metrics for the export job system.

Because the API and worker are separate OS processes (Rule #7), they
also have separate ``prometheus_client`` registries. A counter the
worker bumps is invisible to the API's ``/metrics`` endpoint unless
we use the library's **multiprocess mode**.

To enable it, both processes start with ``PROMETHEUS_MULTIPROC_DIR``
pointing at a shared directory. Each metric write is persisted as a
small file there; the API's ``/metrics`` handler builds a
``MultiProcessCollector`` over that directory at scrape time and
aggregates across processes.

In single-process mode (env var unset) the same metric objects work
as a plain in-memory registry — useful for unit tests.

Why these four:
- ``JOBS_STARTED`` — total work received, sliced by filter.status.
- ``JOBS_COMPLETED`` — sliced by outcome (``ok``/``skipped``/``failed``).
- ``JOB_DURATION`` — wall-clock seconds histogram for latency SLOs.
- ``QUEUE_DEPTH`` — live gauge of pending jobs (``livesum`` across
  worker processes).
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

JOBS_STARTED = Counter(
    "export_jobs_started_total",
    "Export jobs started",
    ["status_filter"],
)

JOBS_COMPLETED = Counter(
    "export_jobs_completed_total",
    "Export jobs completed",
    ["outcome"],
)

JOB_DURATION = Histogram(
    "export_job_duration_seconds",
    "Export duration seconds",
)

# ``multiprocess_mode='livesum'`` is required for Gauges under multiproc
# mode — the library refuses a bare Gauge there. Sum is the right
# semantic for queue depth aggregated across worker processes.
QUEUE_DEPTH = Gauge(
    "export_queue_depth",
    "Pending export jobs",
    multiprocess_mode="livesum",
)
