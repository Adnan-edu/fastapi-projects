import pytest


class TestCustom429Response:
    def test_429_returns_json_error_body(self, client):
        for _ in range(10):
            client.get("/api/v1/quotes/")
        response = client.get("/api/v1/quotes/")
        assert response.status_code == 429
        data = response.json()
        assert "error" in data
        assert data["error"] == "Rate limit exceeded"
        assert "detail" in data

    def test_429_includes_error_detail(self, client):
        for _ in range(5):
            client.get("/api/v1/quotes/random")
        response = client.get("/api/v1/quotes/random")
        assert response.status_code == 429
        data = response.json()
        assert "error" in data
        assert "5" in data["detail"] or "minute" in data["detail"]


class TestMissingApiKeyFallback:
    def test_quote_by_id_without_key_uses_ip(self, client):
        for _ in range(5):
            response = client.get("/api/v1/quotes/1")
            assert response.status_code == 200
        response = client.get("/api/v1/quotes/1")
        assert response.status_code == 429

    def test_premium_without_key_uses_free_plan(self, client):
        for _ in range(3):
            response = client.get("/api/v1/quotes/premium")
            assert response.status_code == 200
        response = client.get("/api/v1/quotes/premium")
        assert response.status_code == 429


class TestDifferentRoutesDifferentLimits:
    def test_list_quotes_higher_limit_than_random(self, client):
        for _ in range(5):
            assert client.get("/api/v1/quotes/random").status_code == 200
        assert client.get("/api/v1/quotes/random").status_code == 429
        assert client.get("/api/v1/quotes/").status_code == 200

    def test_exhausting_one_limit_does_not_affect_another(self, client):
        headers = {"X-API-Key": "free_isolated_key"}
        for _ in range(3):
            client.get("/api/v1/quotes/premium", headers=headers)
        response = client.get("/api/v1/quotes/premium", headers=headers)
        assert response.status_code == 429
        response = client.get("/api/v1/quotes/1", headers=headers)
        assert response.status_code == 200


class TestQuoteNotFound:
    def test_nonexistent_quote_id(self, client):
        response = client.get(
            "/api/v1/quotes/999",
            headers={"X-API-Key": "free_edge_key"},
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "Quote not found"

    def test_zero_quote_id(self, client):
        response = client.get(
            "/api/v1/quotes/0",
            headers={"X-API-Key": "free_edge_key"},
        )
        assert response.status_code == 404

    def test_negative_quote_id(self, client):
        response = client.get(
            "/api/v1/quotes/-1",
            headers={"X-API-Key": "free_edge_key"},
        )
        assert response.status_code == 404


class TestRetryAfterHeader:
    def test_successful_response_includes_retry_after(self, client):
        response = client.get("/api/v1/quotes/")
        assert response.status_code == 200
        assert "retry-after" in response.headers