# When to Use Which

- **Use Uvicorn** when you want the most mature ecosystem, need `--reload` during development, or plan to use Gunicorn's process management in production.
- **Use Granian** when you want maximum single-server throughput, prefer a zero-config multi-worker setup, or want to avoid the Gunicorn dependency chain.

Granian handles multi-worker natively — no need for Gunicorn. Each worker gets its own Rust runtime thread.


Switching to Granian gives you a meaningful boost only in some scenarios. Don't assume "Granian = always faster":
---

## Will Granian Actually Help? (Workload Cheat Sheet)

Switching to Granian gives you a meaningful boost **only in some scenarios**. Don't assume "Granian = always faster":

| Workload | Will Granian help? |
|---|---|
| Tons of small, fast requests (e.g. `/health`-style, JSON-in / JSON-out, low payload) | **Yes** — this is where the Rust HTTP parser and tokio scheduler shine. Often 20–50%+ RPS uplift over Uvicorn (workload-dependent). |
| WebSocket / streaming-heavy | **Yes**, often noticeably. |
| HTTP/2-heavy (gRPC-style, many multiplexed streams) | **Yes** — better out-of-the-box. |
| IO-bound where your bottleneck is the DB / external API | **No** — your Postgres or Stripe call is the bottleneck. Both servers will look identical. |
| CPU-bound endpoints (your `compute/light` fibonacci, ML inference, image processing) | **No** — both servers off-load to a threadpool, and the GIL/CPU is the wall. Adding `--workers N` matters far more than which server you picked. |
| Behind a slow client / mobile / lossy network | **Marginal** — RTT dominates. |

So the rule of thumb is:

> **Measure first, then switch.** The `wrk` / `hey` recipes in §10 of `README.md` exist for exactly this. Run them on your hot endpoints under realistic concurrency, on the same hardware, with the same `--workers`.

> If Granian wins by enough to matter, change the CMD line. If not, stick with Uvicorn for the ecosystem.

### Where Granian Helps Most (Yes/No Summary)

| Workload | Will Granian help? |
|---|---|
| WebSocket / streaming-heavy | **Yes**, often noticeably. |
| HTTP/2-heavy (gRPC-style, many multiplexed streams) | **Yes** — better out-of-the-box. |
| IO-bound where your bottleneck is the DB / external API | **No** — your Postgres or Stripe call is the bottleneck. Both servers will look identical. |
| CPU-bound endpoints (your `compute/light` fibonacci, ML inference, image processing) | **No** — both servers off-load to a threadpool, and the GIL/CPU is the wall. Adding `--workers N` matters far more than which server you picked. |
| Behind a slow client / mobile / lossy network | **Marginal** — RTT dominates. |

So the rule of thumb is:

> **Measure first, then switch.** The `wrk` / `hey` recipes in §10 of `README.md` exist for exactly this. Run them on your hot endpoints under realistic concurrency, on the same hardware, with the same `--workers`.

> If Granian wins by enough to matter, change the CMD line. If not, stick with Uvicorn for the ecosystem.
