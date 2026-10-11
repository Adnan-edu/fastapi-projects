from prometheus_client import Counter
from prometheus_fastapi_instrumentator import Instrumentator, metrics

ORDERS_CREATED = Counter(
    "orders_created_total",
    "Total number of orders created.",
    labelnames=("item",),
)


def increment_orders_created(item: str) -> None:
    ORDERS_CREATED.labels(item=item).inc()


def setup_monitoring(app) -> Instrumentator:
    instrumentator = Instrumentator(
        should_group_status_codes=True,
        excluded_handlers=["/health", "/metrics"],
    )
    instrumentator.add(
        metrics.latency(
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
        )
    )
    instrumentator.add(metrics.request_size())
    instrumentator.add(metrics.response_size())
    instrumentator.add(metrics.requests())
    instrumentator.instrument(app).expose(
        app,
        endpoint="/metrics",
        include_in_schema=False,
        should_gzip=True,
    )
    return instrumentator
