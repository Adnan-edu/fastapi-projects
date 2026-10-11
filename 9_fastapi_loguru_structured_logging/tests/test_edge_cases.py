class TestEdgeCases:
    def test_create_payment_with_unicode_customer(self, client):
        response = client.post(
            "/api/v1/payments/",
            json={"customer": "Müller", "amount": 10.00, "card_number": "4242424242424242"},
        )
        assert response.status_code == 201
        assert response.json()["customer"] == "Müller"

    def test_create_payment_with_large_amount(self, client):
        response = client.post(
            "/api/v1/payments/",
            json={"customer": "Whale", "amount": 999999.99, "card_number": "4242424242424242"},
        )
        assert response.status_code == 201
        assert response.json()["amount"] == 999999.99

    def test_create_payment_with_minimum_card_number(self, client):
        response = client.post(
            "/api/v1/payments/",
            json={"customer": "Min", "amount": 1.00, "card_number": "1234"},
        )
        assert response.status_code == 201
        assert response.json()["card_last_four"] == "1234"

    def test_list_payments_after_multiple_creates(self, client):
        for i in range(5):
            client.post(
                "/api/v1/payments/",
                json={"customer": f"Customer{i}", "amount": (i + 1) * 10.0, "card_number": "4242424242424242"},
            )
        response = client.get("/api/v1/payments/")
        assert len(response.json()["payments"]) == 8

    def test_get_payment_not_confused_with_named_routes(self, client):
        response = client.post(
            "/api/v1/payments/failed",
        )
        assert response.status_code == 500

    def test_create_payment_post_to_existing_id_url(self, client):
        response = client.post(
            "/api/v1/payments/1",
        )
        assert response.status_code == 405

    def test_ensure_no_sensitive_data_in_list_response(self, client):
        response = client.get("/api/v1/payments/")
        text = response.text
        assert "card_number" not in text

    def test_ensure_no_sensitive_data_in_get_response(self, client):
        response = client.get("/api/v1/payments/1")
        data = response.json()
        assert "card_number" not in data
        assert "card_last_four" in data


class TestLoggingOutput:
    def test_failed_payment_still_returns_request_id(self, client):
        custom_id = "fail-correlation-id"
        response = client.post(
            "/api/v1/payments/failed",
            headers={"X-Request-ID": custom_id},
        )
        assert response.headers["X-Request-ID"] == custom_id
        assert response.status_code == 500

    def test_404_with_request_id(self, client):
        custom_id = "not-found-id"
        response = client.get(
            "/api/v1/payments/9999",
            headers={"X-Request-ID": custom_id},
        )
        assert response.status_code == 404
        assert response.headers["X-Request-ID"] == custom_id


class TestResponseModel:
    def test_create_payment_response_matches_schema(self, client):
        response = client.post(
            "/api/v1/payments/",
            json={"customer": "SchemaTest", "amount": 42.50, "card_number": "4111111111111111"},
        )
        data = response.json()
        assert isinstance(data["id"], int)
        assert isinstance(data["customer"], str)
        assert isinstance(data["amount"], float)
        assert isinstance(data["card_last_four"], str)
        assert isinstance(data["status"], str)
        assert isinstance(data["created_at"], str)
        assert len(data["card_last_four"]) == 4

    def test_seed_data_payment_1_fields(self, client):
        response = client.get("/api/v1/payments/1")
        data = response.json()
        assert data["customer"] == "Alice"
        assert data["amount"] == 99.50
        assert data["card_last_four"] == "4242"
        assert data["status"] == "completed"

    def test_seed_data_payment_2_fields(self, client):
        response = client.get("/api/v1/payments/2")
        data = response.json()
        assert data["customer"] == "Bob"
        assert data["status"] == "pending"

    def test_seed_data_payment_3_fields(self, client):
        response = client.get("/api/v1/payments/3")
        data = response.json()
        assert data["customer"] == "Carol"
        assert data["status"] == "failed"