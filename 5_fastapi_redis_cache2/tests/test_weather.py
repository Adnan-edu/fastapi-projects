import time

from app.services import weather_service


class TestWeatherEndpoint:
    def test_get_weather_returns_data(self, client):
        response = client.get("/api/v1/weather/london")
        assert response.status_code == 200
        data = response.json()
        assert data["city"] == "London"
        assert "temperature_c" in data
        assert "condition" in data
        assert "humidity" in data
        assert "wind_speed_kph" in data
        assert "fetched_at" in data
        assert "response_time_ms" in data

    def test_first_request_is_slow(self, client):
        start = time.perf_counter()
        response = client.get("/api/v1/weather/tokyo")
        elapsed = time.perf_counter() - start
        assert response.status_code == 200
        assert elapsed >= 0.05

    def test_second_request_is_fast_cache_hit(self, client):
        first = client.get("/api/v1/weather/paris")
        assert first.status_code == 200

        start = time.perf_counter()
        second = client.get("/api/v1/weather/paris")
        elapsed = time.perf_counter() - start
        assert second.status_code == 200
        assert elapsed < 0.05

    def test_cache_status_header(self, client):
        response = client.get("/api/v1/weather/berlin")
        assert response.status_code == 200
        assert "x-cache-status" in response.headers or "X-Cache-Status" in response.headers

    def test_different_cities_cached_independently(self, client):
        r1 = client.get("/api/v1/weather/london")
        r2 = client.get("/api/v1/weather/tokyo")
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["city"] == "London"
        assert r2.json()["city"] == "Tokyo"

    def test_unknown_city_returns_default(self, client):
        response = client.get("/api/v1/weather/mumbai")
        assert response.status_code == 200
        data = response.json()
        assert data["city"] == "Mumbai"
        assert data["temperature_c"] == 20

    def test_service_called_once_per_city(self, client):
        client.get("/api/v1/weather/london")
        client.get("/api/v1/weather/london")
        client.get("/api/v1/weather/london")
        assert weather_service.get_call_count("london") == 1

    def test_second_request_returns_same_fetched_at(self, client):
        first = client.get("/api/v1/weather/london")
        second = client.get("/api/v1/weather/london")
        assert first.json()["fetched_at"] == second.json()["fetched_at"]


class TestCacheClear:
    def test_clear_cache_for_city(self, client):
        r1 = client.get("/api/v1/weather/london")
        assert r1.status_code == 200

        clear = client.delete("/api/v1/weather/cache/london")
        assert clear.status_code == 200

        start = time.perf_counter()
        r2 = client.get("/api/v1/weather/london")
        elapsed = time.perf_counter() - start
        assert r2.status_code == 200
        assert elapsed >= 0.05

    def test_clear_one_city_does_not_affect_another(self, client):
        client.get("/api/v1/weather/london")
        client.get("/api/v1/weather/tokyo")

        clear = client.delete("/api/v1/weather/cache/london")
        assert clear.status_code == 200

        start = time.perf_counter()
        r_tokyo = client.get("/api/v1/weather/tokyo")
        elapsed = time.perf_counter() - start
        assert r_tokyo.status_code == 200
        assert elapsed < 0.05

    def test_clear_all_cache(self, client):
        client.get("/api/v1/weather/london")
        client.get("/api/v1/weather/tokyo")

        clear = client.delete("/api/v1/weather/cache")
        assert clear.status_code == 200

        start = time.perf_counter()
        r1 = client.get("/api/v1/weather/london")
        elapsed = time.perf_counter() - start
        assert r1.status_code == 200
        assert elapsed >= 0.05

    def test_clear_nonexistent_city_no_error(self, client):
        response = client.delete("/api/v1/weather/cache/nonexistent")
        assert response.status_code == 200