class TestMetricsBeforeRequests:
    def test_metrics_available_on_startup(self, client):
        response = client.get("/metrics")
        assert response.status_code == 200

    def test_metrics_has_process_info_on_startup(self, client):
        response = client.get("/metrics")
        text = response.text
        assert "process_" in text or "python_" in text


class TestMetricsAfterErrors:
    def test_error_endpoint_records_metric(self, client):
        client.get("/api/v1/orders/error")
        response = client.get("/metrics")
        assert "http_requests_total" in response.text

    def test_404_records_metric(self, client):
        client.get("/api/v1/orders/999")
        response = client.get("/metrics")
        assert "http_requests_total" in response.text

    def test_error_endpoint_latency_recorded(self, client):
        client.get("/api/v1/orders/error")
        response = client.get("/metrics")
        assert "http_request_duration_seconds" in response.text


class TestMetricsAfterSlowEndpoint:
    def test_slow_endpoint_produces_latency_metric(self, client):
        client.get("/api/v1/orders/slow")
        response = client.get("/metrics")
        text = response.text
        assert "http_request_duration_seconds" in text

    def test_slow_endpoint_duration_recorded(self, client):
        client.get("/api/v1/orders/slow")
        response = client.get("/metrics")
        text = response.text
        found_duration = False
        for line in text.split("\n"):
            if "http_request_duration_seconds_sum" in line and "GET" in line:
                parts = line.rsplit(" ", 1)
                if len(parts) == 2:
                    try:
                        duration = float(parts[-1])
                        if duration >= 0.4:
                            found_duration = True
                    except ValueError:
                        pass
        assert found_duration


class TestEdgeCases:
    def test_get_order_not_confused_with_named_routes(self, client):
        response = client.get("/api/v1/orders/slow")
        assert response.status_code == 200
        assert "delay_seconds" in response.json()

    def test_create_order_with_unicode_customer(self, client):
        response = client.post(
            "/api/v1/orders/",
            json={"customer": "Müller", "item": "Gear", "quantity": 3},
        )
        assert response.status_code == 201
        assert response.json()["customer"] == "Müller"

    def test_create_order_with_large_quantity(self, client):
        response = client.post(
            "/api/v1/orders/",
            json={"customer": "Bulk", "item": "Screw", "quantity": 99999},
        )
        assert response.status_code == 201
        assert response.json()["quantity"] == 99999

    def test_create_order_with_missing_body_returns_422(self, client):
        response = client.post(
            "/api/v1/orders/",
        )
        assert response.status_code == 422

    def test_list_orders_after_multiple_creates(self, client):
        for i in range(5):
            client.post(
                "/api/v1/orders/",
                json={"customer": f"Customer{i}", "item": f"Item{i}", "quantity": i + 1},
            )
        response = client.get("/api/v1/orders/")
        assert len(response.json()["orders"]) == 8

    def test_metrics_gzip_compression(self, client):
        response = client.get("/metrics", headers={"Accept-Encoding": "gzip"})
        assert response.status_code == 200

    def test_orders_created_increments_on_each_create(self, client):
        metrics_before = client.get("/metrics").text
        count_before = _count_orders_created(metrics_before)
        client.post(
            "/api/v1/orders/",
            json={"customer": "A", "item": "Bolt", "quantity": 1},
        )
        client.post(
            "/api/v1/orders/",
            json={"customer": "B", "item": "Bolt", "quantity": 2},
        )
        metrics_after = client.get("/metrics").text
        count_after = _count_orders_created(metrics_after)
        assert count_after - count_before == 2.0


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
