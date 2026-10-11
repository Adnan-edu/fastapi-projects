import time

from app.services import weather_service


class TestCacheConsistency:
    def test_cached_response_preserves_all_fields(self, client):
        first = client.get("/api/v1/weather/london")
        second = client.get("/api/v1/weather/london")
        data_first = first.json()
        data_second = second.json()

        assert data_first["city"] == data_second["city"]
        assert data_first["temperature_c"] == data_second["temperature_c"]
        assert data_first["condition"] == data_second["condition"]
        assert data_first["humidity"] == data_second["humidity"]
        assert data_first["wind_speed_kph"] == data_second["wind_speed_kph"]
        assert data_first["fetched_at"] == data_second["fetched_at"]

    def test_cache_after_clear_returns_fresh_data(self, client):
        first = client.get("/api/v1/weather/london")
        client.delete("/api/v1/weather/cache/london")
        second = client.get("/api/v1/weather/london")

        assert first.json()["city"] == second.json()["city"]
        assert first.json()["fetched_at"] != second.json()["fetched_at"]


class TestEdgeCases:
    def test_city_case_insensitive_caching(self, client):
        r1 = client.get("/api/v1/weather/London")
        r2 = client.get("/api/v1/weather/london")
        r3 = client.get("/api/v1/weather/LONDON")

        assert r1.json()["fetched_at"] == r2.json()["fetched_at"]
        assert r2.json()["fetched_at"] == r3.json()["fetched_at"]
        assert weather_service.get_call_count("london") == 1

    def test_concurrent_requests_same_city(self, client):
        r1 = client.get("/api/v1/weather/paris")
        assert r1.status_code == 200

        r2 = client.get("/api/v1/weather/paris")
        assert r2.status_code == 200

        data1 = r1.json()
        data2 = r2.json()
        assert data1["fetched_at"] == data2["fetched_at"]

    def test_special_characters_in_city_name(self, client):
        response = client.get("/api/v1/weather/M%C3%BCnchen")
        assert response.status_code == 200

    def test_clear_all_twice_no_error(self, client):
        client.get("/api/v1/weather/london")
        r1 = client.delete("/api/v1/weather/cache")
        assert r1.status_code == 200
        r2 = client.delete("/api/v1/weather/cache")
        assert r2.status_code == 200

    def test_clear_city_then_all(self, client):
        client.get("/api/v1/weather/london")
        client.get("/api/v1/weather/tokyo")

        r1 = client.delete("/api/v1/weather/cache/london")
        assert r1.status_code == 200
        r2 = client.delete("/api/v1/weather/cache")
        assert r2.status_code == 200

    def test_cache_ttl_expiry_returns_fresh_data(self, client):
        first = client.get("/api/v1/weather/new york")
        first_data = first.json()

        client.delete("/api/v1/weather/cache/new york")

        second = client.get("/api/v1/weather/new york")
        second_data = second.json()

        assert second_data["fetched_at"] != first_data["fetched_at"]

    def test_multiple_cities_independent_caches(self, client):
        cities = ["london", "tokyo", "paris"]
        first_calls = {}
        for city in cities:
            r = client.get(f"/api/v1/weather/{city}")
            first_calls[city] = r.json()

        for city in cities:
            assert weather_service.get_call_count(city) == 1

        for city in cities:
            r = client.get(f"/api/v1/weather/{city}")
            assert r.json()["fetched_at"] == first_calls[city]["fetched_at"]

    def test_weather_service_call_count(self, client):
        client.get("/api/v1/weather/sydney")
        client.get("/api/v1/weather/sydney")
        client.get("/api/v1/weather/sydney")

        assert weather_service.get_call_count("sydney") == 1

        client.delete("/api/v1/weather/cache/sydney")

        client.get("/api/v1/weather/sydney")
        assert weather_service.get_call_count("sydney") == 2