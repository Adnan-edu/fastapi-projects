class TestIPLimitExceeded:
    def test_list_quotes_returns_429_after_limit(self, client):
        for _ in range(10):
            response = client.get("/api/v1/quotes/")
            assert response.status_code == 200
        response = client.get("/api/v1/quotes/")
        assert response.status_code == 429

    def test_random_quote_returns_429_after_limit(self, client):
        for _ in range(5):
            response = client.get("/api/v1/quotes/random")
            assert response.status_code == 200
        response = client.get("/api/v1/quotes/random")
        assert response.status_code == 429


class TestKeyBasedLimitExceeded:
    def test_get_quote_returns_429_after_limit(self, client):
        headers = {"X-API-Key": "free_test_key"}
        for _ in range(5):
            response = client.get("/api/v1/quotes/1", headers=headers)
            assert response.status_code == 200
        response = client.get("/api/v1/quotes/1", headers=headers)
        assert response.status_code == 429

    def test_premium_returns_429_for_free_plan(self, client):
        headers = {"X-API-Key": "free_test_key"}
        for _ in range(3):
            response = client.get("/api/v1/quotes/premium", headers=headers)
            assert response.status_code == 200
        response = client.get("/api/v1/quotes/premium", headers=headers)
        assert response.status_code == 429


class TestKeyIsolation:
    def test_different_api_keys_get_separate_limits(self, client):
        headers_a = {"X-API-Key": "free_key_a"}
        headers_b = {"X-API-Key": "free_key_b"}
        for _ in range(5):
            response = client.get("/api/v1/quotes/1", headers=headers_a)
            assert response.status_code == 200
        response_a = client.get("/api/v1/quotes/1", headers=headers_a)
        assert response_a.status_code == 429
        response_b = client.get("/api/v1/quotes/1", headers=headers_b)
        assert response_b.status_code == 200


class TestRateLimitHeaders:
    def test_successful_response_includes_ratelimit_headers(self, client):
        response = client.get("/api/v1/quotes/")
        assert "x-ratelimit-limit" in response.headers
        assert "x-ratelimit-remaining" in response.headers
        assert "x-ratelimit-reset" in response.headers

    def test_ratelimit_headers_decrement(self, client):
        first = client.get("/api/v1/quotes/")
        second = client.get("/api/v1/quotes/")
        first_remaining = int(first.headers["x-ratelimit-remaining"])
        second_remaining = int(second.headers["x-ratelimit-remaining"])
        assert second_remaining < first_remaining


class TestPerPlanLimits:
    def test_admin_plan_allows_many_requests(self, client):
        headers = {"X-API-Key": "admin_superuser"}
        for _ in range(10):
            response = client.get("/api/v1/quotes/premium", headers=headers)
            assert response.status_code == 200

    def test_pro_plan_allows_more_than_free(self, client):
        free_headers = {"X-API-Key": "free_user"}
        pro_headers = {"X-API-Key": "pro_developer"}
        for _ in range(3):
            response = client.get("/api/v1/quotes/premium", headers=free_headers)
            assert response.status_code == 200
        assert client.get("/api/v1/quotes/premium", headers=free_headers).status_code == 429

        for _ in range(10):
            response = client.get("/api/v1/quotes/premium", headers=pro_headers)
            assert response.status_code == 200