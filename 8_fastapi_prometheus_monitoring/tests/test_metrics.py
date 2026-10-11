class TestMetricsEndpoint:
    def test_metrics_returns_200(self, client):
        response = client.get("/metrics")
        assert response.status_code == 200

    def test_metrics_content_type(self, client):
        response = client.get("/metrics")
        assert "text/plain" in response.headers["content-type"]

    def test_metrics_contains_http_request_duration(self, client):
        client.get("/api/v1/orders/")
        response = client.get("/metrics")
        assert "http_request_duration_seconds" in response.text

    def test_metrics_contains_http_requests_total(self, client):
        client.get("/api/v1/orders/")
        response = client.get("/metrics")
        assert "http_requests_total" in response.text

    def test_metrics_records_request_data(self, client):
        client.get("/api/v1/orders/")
        response = client.get("/metrics")
        found = False
        for line in response.text.split("\n"):
            if line.startswith("http_requests_total") and "GET" in line:
                found = True
                break
        assert found

    def test_metrics_records_status_codes(self, client):
        client.get("/api/v1/orders/")
        client.get("/api/v1/orders/999")
        response = client.get("/metrics")
        text = response.text
        has_status_label = False
        for line in text.split("\n"):
            if line.startswith("http_requests_total") and "status" in line:
                has_status_label = True
                break
        assert has_status_label

    def test_metrics_not_in_openapi_schema(self, client):
        response = client.get("/openapi.json")
        paths = response.json().get("paths", {})
        assert "/metrics" not in paths

    def test_health_excluded_from_metrics(self, client):
        client.get("/health")
        response = client.get("/metrics")
        text = response.text
        for line in text.split("\n"):
            if line.startswith("http_requests_total") and "health" in line:
                assert False, "/health should be excluded from metrics"


class TestCustomBusinessMetric:
    def test_orders_created_total_exists_after_creation(self, client):
        client.post(
            "/api/v1/orders/",
            json={"customer": "Dave", "item": "TestWidget", "quantity": 2},
        )
        response = client.get("/metrics")
        assert "orders_created_total" in response.text

    def test_orders_created_total_records_item_label(self, client):
        client.post(
            "/api/v1/orders/",
            json={"customer": "Dave", "item": "UniqueWidget123", "quantity": 2},
        )
        response = client.get("/metrics")
        assert "UniqueWidget123" in response.text

    def test_get_requests_do_not_increment_orders_created(self, client):
        metrics_before = client.get("/metrics").text
        count_before = _count_orders_created(metrics_before)
        client.get("/api/v1/orders/")
        metrics_after = client.get("/metrics").text
        count_after = _count_orders_created(metrics_after)
        assert count_after == count_before

    def test_failed_create_does_not_increment_orders_created(self, client):
        metrics_before = client.get("/metrics").text
        count_before = _count_orders_created(metrics_before)
        client.post(
            "/api/v1/orders/",
            json={"customer": "", "item": "Widget", "quantity": 1},
        )
        metrics_after = client.get("/metrics").text
        count_after = _count_orders_created(metrics_after)
        assert count_after == count_before


def _count_orders_created(metrics_text: str) -> int:
    total = 0
    for line in metrics_text.split("\n"):
        if line.startswith("orders_created_total{") and not line.startswith("#"):
            parts = line.rsplit(" ", 1)
            if len(parts) == 2:
                try:
                    total += float(parts[-1])
                except ValueError:
                    pass
    return total
