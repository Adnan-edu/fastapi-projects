"""Decide whether switching from Uvicorn to Granian would actually help.

Two modes:

  1. Heuristic mode (default):
       python scripts/decide_granian.py
     Asks ~7 questions about your workload, scores them against the cheat-sheet
     in FINAL.md, and prints a verdict (USE_GRANIAN / STAY_ON_UVICORN /
     MEASURE — TOO CLOSE TO CALL).

  2. Benchmark mode:
       python scripts/decide_granian.py --benchmark
     Boots Uvicorn and Granian back-to-back against this project's FastAPI app,
     drives concurrent traffic with httpx, then prints a side-by-side
     comparison (RPS + p50/p95/p99 latency + a verdict).

Run from the project root with the venv activated:
    source fastapi_asgi_env/bin/activate
    python scripts/decide_granian.py
    python scripts/decide_granian.py --benchmark --endpoint /health
    python scripts/decide_granian.py --benchmark --endpoint /api/v1/compute/io-simulated?delay=0.05 --duration 8

The heuristic is intentionally conservative — it pushes you toward "measure"
whenever the answer isn't obvious. If you want a real answer, run --benchmark.
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
import socket
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Heuristic mode
# ---------------------------------------------------------------------------

# Each question's answers map to a score contribution.
#   +N  → Granian is more likely to help
#   -N  → Granian is unlikely to help / Uvicorn is fine
#    0  → neutral
# The weights are deliberately small and additive; this is a rule-of-thumb,
# not a model. The cheat-sheet from FINAL.md is the source of truth.

QUESTIONS = [
    {
        "key": "workload",
        "prompt": "What best describes your typical endpoint?",
        "options": {
            "1": ("Tons of small, fast JSON requests (e.g. /health-style)", +3),
            "2": ("WebSocket / streaming-heavy", +3),
            "3": ("HTTP/2 / gRPC-style with many multiplexed streams", +3),
            "4": ("IO-bound (DB queries, external API calls dominate)", -3),
            "5": ("CPU-bound (ML inference, image processing, heavy compute)", -3),
            "6": ("Mixed / unsure", 0),
        },
    },
    {
        "key": "rps",
        "prompt": "What is your peak sustained requests/sec (per pod / VM)?",
        "options": {
            "1": ("< 100 RPS", -2),
            "2": ("100 – 1,000 RPS", 0),
            "3": ("1,000 – 10,000 RPS", +2),
            "4": ("> 10,000 RPS", +3),
            "5": ("Unknown", 0),
        },
    },
    {
        "key": "latency_sensitive",
        "prompt": "Are p99 latencies a hard SLO you're actively tuning?",
        "options": {
            "1": ("Yes — every millisecond matters", +2),
            "2": ("Somewhat — we care but aren't optimising heavily", 0),
            "3": ("No — internal service / batch / background", -1),
        },
    },
    {
        "key": "downstream",
        "prompt": "Where is your *actual* bottleneck today?",
        "options": {
            "1": ("Database (Postgres / MySQL / Mongo)", -3),
            "2": ("External HTTP API (Stripe, OpenAI, etc.)", -3),
            "3": ("CPU on the Python process", -2),
            "4": ("The web server / connection handling itself", +3),
            "5": ("Don't know yet", 0),
        },
    },
    {
        "key": "gunicorn",
        "prompt": "Do you currently run Gunicorn + UvicornWorker in production?",
        "options": {
            "1": ("Yes, and we depend on Gunicorn's process management / hooks", -2),
            "2": ("Yes, but we don't use Gunicorn-specific features", +1),
            "3": ("No — plain uvicorn or behind an orchestrator (K8s/Nomad)", +1),
            "4": ("Not in production yet", 0),
        },
    },
    {
        "key": "protocols",
        "prompt": "Do you need WebSockets or HTTP/2 today (or within ~6 months)?",
        "options": {
            "1": ("Yes — WebSockets or streaming SSE are core to the product", +2),
            "2": ("Yes — HTTP/2 (gRPC, multiplexing) is on the roadmap", +2),
            "3": ("No — plain HTTP/1.1 JSON only", 0),
        },
    },
    {
        "key": "ecosystem",
        "prompt": "How critical is ecosystem maturity (APM agents, blog posts, hires who know it)?",
        "options": {
            "1": ("Very — we want the safest, most-Googled choice", -2),
            "2": ("Somewhat — we'll adopt newer tech if the win is clear", 0),
            "3": ("Not really — we're comfortable on the bleeding edge", +1),
        },
    },
]


def ask(question: dict) -> int:
    """Prompt the user for one question and return the score contribution."""
    print()
    print(question["prompt"])
    for key, (label, _score) in question["options"].items():
        print(f"  [{key}] {label}")
    while True:
        choice = input("  > ").strip()
        if choice in question["options"]:
            label, score = question["options"][choice]
            return score
        print("  (please enter one of the bracketed numbers)")


def heuristic_verdict(total: int) -> tuple[str, str]:
    """Map a score to (verdict_tag, explanation)."""
    if total >= 5:
        return (
            "USE_GRANIAN",
            "Your workload looks like Granian's sweet spot (server-bound, "
            "high-RPS, latency-sensitive, or WS/HTTP-2-heavy). The Rust core "
            "and built-in worker manager are likely to give a real win.",
        )
    if total <= -3:
        return (
            "STAY_ON_UVICORN",
            "Your bottleneck is almost certainly NOT the ASGI server "
            "(downstream IO, CPU, or low RPS). Switching to Granian will not "
            "move the needle. Stay on the more mature stack.",
        )
    return (
        "MEASURE — TOO CLOSE TO CALL",
        "You're in the zone where the answer depends on your actual numbers. "
        "Run `python scripts/decide_granian.py --benchmark` against your hot "
        "endpoint(s) — that's the only way to know for sure.",
    )


def run_heuristic() -> int:
    print("=" * 70)
    print("  GRANIAN vs UVICORN — heuristic decision tool")
    print("=" * 70)
    print("Answer 7 quick questions about your workload. Ctrl-C to abort.")

    total = 0
    answers: dict[str, int] = {}
    try:
        for q in QUESTIONS:
            score = ask(q)
            total += score
            answers[q["key"]] = score
    except (KeyboardInterrupt, EOFError):
        print("\nAborted.")
        return 130

    verdict, explanation = heuristic_verdict(total)
    print()
    print("=" * 70)
    print(f"  SCORE: {total:+d}    VERDICT: {verdict}")
    print("=" * 70)
    print(explanation)
    print()
    print("Score breakdown (positive = leans Granian, negative = leans Uvicorn):")
    for key, score in answers.items():
        print(f"  {key:<20} {score:+d}")
    print()
    print("Reminder: see FINAL.md for the workload cheat-sheet this is based on.")
    return 0


# ---------------------------------------------------------------------------
# Benchmark mode
# ---------------------------------------------------------------------------


@dataclass
class BenchResult:
    server: str
    requests: int
    errors: int
    duration_s: float
    latencies_ms: list[float]

    @property
    def rps(self) -> float:
        return self.requests / self.duration_s if self.duration_s > 0 else 0.0

    def pct(self, p: float) -> float:
        if not self.latencies_ms:
            return float("nan")
        s = sorted(self.latencies_ms)
        idx = min(len(s) - 1, max(0, int(round(p / 100.0 * (len(s) - 1)))))
        return s[idx]

    @property
    def median(self) -> float:
        return statistics.median(self.latencies_ms) if self.latencies_ms else float("nan")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_port(host: str, port: int, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


async def _drive_load(url: str, concurrency: int, duration_s: float) -> BenchResult:
    """Hit `url` from `concurrency` workers for `duration_s` seconds."""
    try:
        import httpx
    except ImportError:
        print("ERROR: httpx is required for benchmark mode. `uv pip install httpx`.")
        sys.exit(2)

    latencies_ms: list[float] = []
    errors = 0
    requests = 0
    stop_at = time.monotonic() + duration_s

    async def worker(client: "httpx.AsyncClient") -> None:
        nonlocal errors, requests
        while time.monotonic() < stop_at:
            t0 = time.perf_counter()
            try:
                r = await client.get(url, timeout=10.0)
                if r.status_code >= 400:
                    errors += 1
                else:
                    latencies_ms.append((time.perf_counter() - t0) * 1000.0)
                requests += 1
            except Exception:
                errors += 1
                requests += 1

    started = time.monotonic()
    limits = httpx.Limits(max_connections=concurrency * 2, max_keepalive_connections=concurrency)
    async with httpx.AsyncClient(http2=False, limits=limits) as client:
        # warm-up so the first measured request isn't tainted by DNS / TCP
        try:
            await client.get(url, timeout=2.0)
        except Exception:
            pass
        await asyncio.gather(*[worker(client) for _ in range(concurrency)])
    elapsed = time.monotonic() - started

    return BenchResult(
        server="",  # filled in by caller
        requests=requests,
        errors=errors,
        duration_s=elapsed,
        latencies_ms=latencies_ms,
    )


def _bench_one(
    *,
    server: str,
    cmd: list[str],
    port: int,
    path: str,
    concurrency: int,
    duration_s: float,
) -> Optional[BenchResult]:
    """Boot a server, drive load, tear it down. Returns None on boot failure."""
    print(f"\n  starting: {' '.join(cmd)}")
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        if not _wait_for_port("127.0.0.1", port, timeout=10.0):
            print(f"  ! {server} never bound to 127.0.0.1:{port} — skipping")
            return None
        # tiny settle time for the worker to be fully accepting
        time.sleep(0.4)
        url = f"http://127.0.0.1:{port}{path}"
        print(f"  driving {concurrency} workers @ {url} for {duration_s:.1f}s ...")
        result = asyncio.run(_drive_load(url, concurrency, duration_s))
        result.server = server
        return result
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)


def _print_result(r: BenchResult) -> None:
    print(
        f"  {r.server:<8}  "
        f"req={r.requests:<6}  err={r.errors:<3}  "
        f"rps={r.rps:>8.1f}  "
        f"p50={r.median:>6.2f}ms  "
        f"p95={r.pct(95):>6.2f}ms  "
        f"p99={r.pct(99):>6.2f}ms"
    )


def _compare(uv: BenchResult, gr: BenchResult) -> tuple[str, str]:
    """Decide whether Granian beat Uvicorn by enough to bother switching."""
    if uv.rps <= 0 or gr.rps <= 0:
        return ("INCONCLUSIVE", "One of the servers produced no successful requests.")
    delta_rps_pct = (gr.rps - uv.rps) / uv.rps * 100
    delta_p99 = uv.pct(99) - gr.pct(99)  # positive = Granian is faster at tail

    # 15% is a reasonable "worth the migration cost" threshold — below that,
    # benchmark noise + ecosystem cost makes the switch hard to justify.
    if delta_rps_pct >= 15 or delta_p99 >= 5:
        return (
            "USE_GRANIAN",
            f"Granian is {delta_rps_pct:+.1f}% on RPS and "
            f"{delta_p99:+.2f}ms better at p99. Worth switching.",
        )
    if delta_rps_pct <= -5:
        return (
            "STAY_ON_UVICORN",
            f"Granian is {delta_rps_pct:+.1f}% on RPS vs Uvicorn — slower on "
            "this workload. Stay on Uvicorn.",
        )
    return (
        "TOO CLOSE TO CALL",
        f"Δ RPS = {delta_rps_pct:+.1f}%, Δ p99 = {delta_p99:+.2f}ms. "
        "Inside noise margin — pick on ecosystem, not performance.",
    )


def run_benchmark(args: argparse.Namespace) -> int:
    project_root = Path(__file__).resolve().parent.parent
    if not (project_root / "app" / "main.py").exists():
        print(f"ERROR: cannot find app/main.py under {project_root}")
        return 2

    if shutil.which("uvicorn") is None:
        print("ERROR: `uvicorn` not on PATH. Activate the venv first.")
        return 2
    if shutil.which("granian") is None:
        print("ERROR: `granian` not on PATH. Activate the venv first "
              "or `uv pip install granian`.")
        return 2

    path = args.endpoint
    if not path.startswith("/"):
        path = "/" + path

    print("=" * 70)
    print("  GRANIAN vs UVICORN — benchmark")
    print("=" * 70)
    print(f"  endpoint    : {path}")
    print(f"  concurrency : {args.concurrency}")
    print(f"  duration    : {args.duration}s per server")
    print(f"  workers     : {args.workers}")

    # Uvicorn
    uv_port = _free_port()
    uv_cmd = [
        "uvicorn", "app.main:app",
        "--host", "127.0.0.1",
        "--port", str(uv_port),
        "--workers", str(args.workers),
        "--log-level", "warning",
    ]
    uv = _bench_one(
        server="uvicorn",
        cmd=uv_cmd,
        port=uv_port,
        path=path,
        concurrency=args.concurrency,
        duration_s=args.duration,
    )

    # Granian
    gr_port = _free_port()
    gr_cmd = [
        "granian", "--interface", "asgi",
        "--host", "127.0.0.1",
        "--port", str(gr_port),
        "--workers", str(args.workers),
        "--log-level", "warning",
        "app.main:app",
    ]
    gr = _bench_one(
        server="granian",
        cmd=gr_cmd,
        port=gr_port,
        path=path,
        concurrency=args.concurrency,
        duration_s=args.duration,
    )

    print()
    print("-" * 70)
    print("  RESULTS")
    print("-" * 70)
    if uv:
        _print_result(uv)
    if gr:
        _print_result(gr)

    if uv and gr:
        verdict, explanation = _compare(uv, gr)
        print()
        print("=" * 70)
        print(f"  VERDICT: {verdict}")
        print("=" * 70)
        print(explanation)
        print()
        print("Caveats: localhost loopback, single machine, synthetic load. "
              "Reproduce on production-shaped hardware before committing.")
        return 0
    print("\nBenchmark inconclusive — one server failed to start.")
    return 1


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Decide whether switching from Uvicorn to Granian would help.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--benchmark",
        action="store_true",
        help="Run a real load test against Uvicorn and Granian (default: heuristic Q&A).",
    )
    parser.add_argument(
        "--endpoint",
        default="/health",
        help="Path to hit during benchmark mode (default: /health).",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=50,
        help="Number of concurrent httpx workers during benchmark (default: 50).",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=5.0,
        help="Seconds of load per server during benchmark (default: 5.0).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="--workers passed to BOTH servers — keep equal for a fair fight (default: 1).",
    )
    args = parser.parse_args()

    if args.benchmark:
        return run_benchmark(args)
    return run_heuristic()


if __name__ == "__main__":
    sys.exit(main())
