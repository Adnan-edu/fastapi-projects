# FastAPI Prometheus Monitoring - Orders API

A hands-on learning project demonstrating production monitoring in FastAPI using **prometheus-fastapi-instrumentator** with a Simple Orders API.

## Why Monitoring Matters

In development, you know your code works because you tested it. In production, you need to know it *keeps* working and *how well*. Monitoring answers questions like:

- Is the service up and responding?
- How fast are responses?
- Are users hitting errors?
- How much traffic are we handling?
- Which endpoints are slowest?

Without monitoring, you are blind in production. Issues go undetected until users complain, and when they do, you lack the data to diagnose root cause.

## Metrics vs Logs vs Traces

| Pillar | What it captures | Example | When to use |
|---|---|---|---|
| **Metrics** | Numeric measurements aggregated over time | `http_requests_total{status="200"} 42` | Dashboards, alerting, capacity planning |
| **Logs** | Discrete event records with context | `ERROR: Order 5 not found` | Debugging specific failures |
| **Traces** | Request journey across services | Span: API -> DB -> Cache -> Response | Finding latency bottlenecks in distributed systems |

Metrics are the cheapest to store and fastest to query. They power dashboards and alerts. This project focuses on metrics with Prometheus.

## What Prometheus Measures

### Request Latency

How long a request takes from start to finish. Prometheus records latency as a **histogram** with configurable bucket boundaries:

```
http_request_duration_seconds_bucket{le="0.1"} 15    # 15 requests completed in <=0.1s
http_request_duration_seconds_bucket{le="0.5"} 42    # 42 requests completed in <=0.5s
http_request_duration_seconds_bucket{le="1.0"} 50    # 50 requests completed in <=1.0s
http_request_duration_seconds_count           50     # 50 total requests
http_request_duration_seconds_sum           12.5     # 12.5s total time
```

From this histogram, you can compute percentiles like p50, p90, p99 using `histogram_quantile()`:

```promql
histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m]))
```

### HTTP Status Code Metrics

Every request is labeled with its HTTP status group (`2xx`, `4xx`, `5xx`):

```
http_requests_total{method="GET", handler="/api/v1/orders/", status="2xx"} 30
http_requests_total{method="GET", handler="/api/v1/orders/999", status="4xx"} 5
http_requests_total{method="GET", handler="/api/v1/orders/error", status="5xx"} 2
```

This lets you compute error rate:

```promql
sum(rate(http_requests_total{status="5xx"}[5m]))
  /
sum(rate(http_requests_total[5m]))
```

### Throughput

How many requests per second your service handles:

```promql
sum(rate(http_requests_total[5m]))
```

Throughput combined with latency tells you if your service can handle the load.

## Understanding Histograms

A Prometheus histogram divides observations into configurable buckets. Each bucket counts how many observations fell at or below its boundary (`le` = "less than or equal"):

```
Bucket le=0.05  ->  10 observations  (fast requests)
Bucket le=0.1   ->  25 observations
Bucket le=0.5   ->  40 observations
Bucket le=1.0   ->  48 observations
Bucket le=+Inf  ->  50 observations  (all requests)
```

Key properties:
- Buckets are **cumulative**: the `le=0.5` bucket includes all observations in `le=0.1`
- `histogram_quantile()` computes percentiles from bucket boundaries and counts
- Bucket boundaries should be chosen based on your SLO thresholds (e.g., if p99 < 1s is your goal, include `le=1.0`)

This project configures buckets: `0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10`.

## Prometheus Scraping

Prometheus does not receive metrics — it **pulls** them. At a configured interval (default 15s), Prometheus sends an HTTP GET to your `/metrics` endpoint, reads the text-format metrics, and stores them in its time-series database.

```
Prometheus --(GET /metrics every 15s)--> FastAPI App
```

The scrape target is defined in `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: "fastapi_orders"
    metrics_path: "/metrics"
    static_configs:
      - targets: ["host.docker.internal:8000"]
```

## Grafana Visualization

Grafana connects to Prometheus as a data source and renders dashboards. This project includes a pre-built dashboard with panels for:

- Request rate (req/s)
- Request latency percentiles (p50, p90, p99)
- Requests by status code (pie chart)
- Orders created (stat panel)
- Orders by item (bar chart)
- Error rate (gauge)
- Average request and response sizes

```
Prometheus --(PromQL queries)--> Grafana --> Browser
```

Grafana is provisioned automatically via Docker Compose with the Prometheus datasource and dashboard JSON.

## How to Call /metrics

The instrumentator exposes a `GET /metrics` endpoint (hidden from OpenAPI schema):

```bash
curl http://127.0.0.1:8000/metrics
```

Sample output:

```
# HELP http_requests_total Total number of requests by method, handler, status
# TYPE http_requests_total counter
http_requests_total{method="GET",handler="/api/v1/orders/",status="2xx"} 5.0

# HELP http_request_duration_seconds Duration of HTTP requests in seconds
# TYPE http_request_duration_seconds histogram
http_request_duration_seconds_bucket{method="GET",handler="/api/v1/orders/",le="0.005"} 3.0
http_request_duration_seconds_bucket{method="GET",handler="/api/v1/orders/",le="0.01"} 5.0
http_request_duration_seconds_count{method="GET",handler="/api/v1/orders/"} 5.0
http_request_duration_seconds_sum{method="GET",handler="/api/v1/orders/"} 0.023

# HELP orders_created_total Total number of orders created.
# TYPE orders_created_total counter
orders_created_total{item="Widget"} 2.0
```

## Custom Business Metrics

Beyond infrastructure metrics (latency, status codes), this project adds `orders_created_total` — a custom Counter that tracks how many orders have been created, labeled by item name. This demonstrates how to instrument business logic alongside HTTP metrics.

Custom metrics are defined in `app/core/monitoring.py` using the instrumentator's `.add()` API with a closure that receives an `Info` object containing request/response details.

## Architecture

```mermaid
flowchart TD
    Client[Client] --> API[FastAPI App]
    API --> Metrics[Instrumentator Middleware]
    Metrics --> Endpoint[/metrics]
    Prometheus[Prometheus] --> Endpoint
    Prometheus --> Grafana[Grafana Dashboard]
```

## Setup

```bash
uv venv fastapi_prometheus_env
source fastapi_prometheus_env/bin/activate
uv pip install -e ".[dev]"
```

## Running the Server

```bash
uvicorn app.main:app --reload
```

Open the interactive docs at `http://127.0.0.1:8000/docs`.

## Running with Docker Compose

Start Prometheus and Grafana:

```bash
docker compose up -d
```

| Service | URL | Credentials |
|---|---|---|
| FastAPI | http://localhost:8000 | - |
| Prometheus | http://localhost:9090 | - |
| Grafana | http://localhost:3000 | admin / admin |

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check (excluded from metrics) |
| `POST` | `/api/v1/orders/` | Create an order |
| `GET` | `/api/v1/orders/` | List all orders |
| `GET` | `/api/v1/orders/{order_id}` | Get order by ID |
| `GET` | `/api/v1/orders/slow` | Simulated slow endpoint (0.5s delay) |
| `GET` | `/api/v1/orders/error` | Simulated error endpoint (always 500) |
| `GET` | `/metrics` | Prometheus metrics endpoint |

## Example Requests

Create an order:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/orders/ \
  -H "Content-Type: application/json" \
  -d '{"customer": "Alice", "item": "Widget", "quantity": 3}'
```

List all orders:

```bash
curl http://127.0.0.1:8000/api/v1/orders/
```

Get a specific order:

```bash
curl http://127.0.0.1:8000/api/v1/orders/1
```

Trigger the slow endpoint:

```bash
curl http://127.0.0.1:8000/api/v1/orders/slow
```

Trigger the error endpoint:

```bash
curl http://127.0.0.1:8000/api/v1/orders/error
```

Check metrics:

```bash
curl http://127.0.0.1:8000/metrics
```

Query Prometheus for p99 latency:

```bash
curl 'http://localhost:9090/api/v1/query?query=histogram_quantile(0.99,rate(http_request_duration_seconds_bucket[5m]))'
```

## Testing

```bash
pytest -v
```

Tests verify:

- All CRUD endpoints return correct data and status codes
- `/metrics` returns 200 with `text/plain` content type
- Metric names (`http_request_duration_seconds`, `http_requests_total`) appear after requests
- Custom `orders_created_total` metric increments on order creation
- Status code metrics differentiate between 2xx, 4xx, 5xx
- `/metrics` is excluded from the OpenAPI schema
- `/health` is excluded from metrics
- Slow endpoint produces latency histogram data
- Error endpoint produces 5xx metrics
- Validation errors (422) for invalid input
- Unicode and large quantity inputs work correctly

## Project Structure

```text
8_fastapi_prometheus_monitoring/
  app/
    __init__.py
    main.py                    # App factory with instrumentator setup
    api/
      __init__.py
      routes_orders.py         # Order endpoints + slow/error simulation
    core/
      __init__.py
      monitoring.py            # Instrumentator config, custom metrics
    services/
      __init__.py
      order_service.py         # In-memory order store and CRUD
  tests/
    __init__.py
    conftest.py                # Test fixtures with store reset
    test_orders.py             # CRUD endpoint correctness
    test_metrics.py            # /metrics existence, content, custom metrics
    test_edge_cases.py         # Status code metrics, latency, edge inputs
  prometheus/
    prometheus.yml             # Prometheus scrape configuration
  grafana/
    provisioning/
      datasources/
        datasource.yml         # Prometheus datasource for Grafana
      dashboards/
        dashboard.yml          # Dashboard provisioning config
        dashboard.json         # Pre-built FastAPI monitoring dashboard
  docker-compose.yml           # Prometheus + Grafana services
  pyproject.toml
  README.md
```
