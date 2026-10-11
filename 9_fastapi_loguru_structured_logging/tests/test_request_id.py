class TestRequestIdGenerated:
    def test_request_id_in_response_when_not_provided(self, client):
        response = client.get("/api/v1/payments/")
        assert "X-Request-ID" in response.headers
        request_id = response.headers["X-Request-ID"]
        assert len(request_id) == 36
        assert request_id.count("-") == 4

    def test_request_id_is_uuid_format(self, client):
        response = client.get("/api/v1/payments/")
        request_id = response.headers["X-Request-ID"]
        parts = request_id.split("-")
        assert len(parts) == 5
        assert len(parts[0]) == 8
        assert len(parts[1]) == 4
        assert len(parts[2]) == 4
        assert len(parts[3]) == 4
        assert len(parts[4]) == 12

    def test_process_time_header_present(self, client):
        response = client.get("/api/v1/payments/")
        assert "X-Process-Time" in response.headers
        process_time = float(response.headers["X-Process-Time"])
        assert process_time >= 0

    def test_different_requests_get_different_ids(self, client):
        r1 = client.get("/api/v1/payments/")
        r2 = client.get("/api/v1/payments/")
        assert r1.headers["X-Request-ID"] != r2.headers["X-Request-ID"]


class TestRequestIdPassThrough:
    def test_provided_request_id_is_echoed_back(self, client):
        custom_id = "test-correlation-id-12345"
        response = client.get(
            "/api/v1/payments/",
            headers={"X-Request-ID": custom_id},
        )
        assert response.headers["X-Request-ID"] == custom_id

    def test_provided_request_id_used_as_is(self, client):
        custom_id = "my-custom-trace-id"
        response = client.get(
            "/api/v1/payments/1",
            headers={"X-Request-ID": custom_id},
        )
        assert response.headers["X-Request-ID"] == custom_id

    def test_request_id_persists_on_error(self, client):
        custom_id = "error-trace-id"
        response = client.get(
            "/api/v1/payments/999",
            headers={"X-Request-ID": custom_id},
        )
        assert response.status_code == 404
        assert response.headers["X-Request-ID"] == custom_id

    def test_request_id_persists_on_422(self, client):
        custom_id = "validation-trace-id"
        response = client.post(
            "/api/v1/payments/",
            json={},
            headers={"X-Request-ID": custom_id},
        )
        assert response.status_code == 422
        assert response.headers["X-Request-ID"] == custom_id

    def test_request_id_persists_on_500(self, client):
        custom_id = "server-error-trace-id"
        response = client.post(
            "/api/v1/payments/failed",
            headers={"X-Request-ID": custom_id},
        )
        assert response.status_code == 500
        assert response.headers["X-Request-ID"] == custom_id


class TestRequestIdOnHealth:
    def test_health_endpoint_has_request_id(self, client):
        response = client.get("/health")
        assert "X-Request-ID" in response.headers

    def test_health_endpoint_has_process_time(self, client):
        response = client.get("/health")
        assert "X-Process-Time" in response.headers