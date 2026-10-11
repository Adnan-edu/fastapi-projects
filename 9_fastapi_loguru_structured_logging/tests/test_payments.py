class TestCreatePayment:
    def test_create_payment_returns_201(self, client):
        response = client.post(
            "/api/v1/payments/",
            json={"customer": "Dave", "amount": 50.00, "card_number": "4111111111111111"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["customer"] == "Dave"
        assert data["amount"] == 50.00
        assert data["card_last_four"] == "1111"
        assert data["status"] == "pending"
        assert "id" in data
        assert "created_at" in data

    def test_create_payment_does_not_expose_full_card_number(self, client):
        response = client.post(
            "/api/v1/payments/",
            json={"customer": "Dave", "amount": 50.00, "card_number": "4111111111111111"},
        )
        data = response.json()
        assert data["card_last_four"] == "1111"
        assert "4111111111111111" not in response.text

    def test_create_payment_auto_increments_id(self, client):
        r1 = client.post(
            "/api/v1/payments/",
            json={"customer": "Eve", "amount": 10.00, "card_number": "4242424242424242"},
        )
        r2 = client.post(
            "/api/v1/payments/",
            json={"customer": "Frank", "amount": 20.00, "card_number": "5555555555554444"},
        )
        assert r1.json()["id"] < r2.json()["id"]

    def test_create_payment_empty_customer_returns_422(self, client):
        response = client.post(
            "/api/v1/payments/",
            json={"customer": "", "amount": 10.00, "card_number": "4242424242424242"},
        )
        assert response.status_code == 422

    def test_create_payment_zero_amount_returns_422(self, client):
        response = client.post(
            "/api/v1/payments/",
            json={"customer": "Eve", "amount": 0, "card_number": "4242424242424242"},
        )
        assert response.status_code == 422

    def test_create_payment_negative_amount_returns_422(self, client):
        response = client.post(
            "/api/v1/payments/",
            json={"customer": "Eve", "amount": -5.00, "card_number": "4242424242424242"},
        )
        assert response.status_code == 422

    def test_create_payment_missing_fields_returns_422(self, client):
        response = client.post(
            "/api/v1/payments/",
            json={},
        )
        assert response.status_code == 422

    def test_create_payment_short_card_number_returns_422(self, client):
        response = client.post(
            "/api/v1/payments/",
            json={"customer": "Eve", "amount": 10.00, "card_number": "42"},
        )
        assert response.status_code == 422


class TestListPayments:
    def test_list_payments_returns_all(self, client):
        response = client.get("/api/v1/payments/")
        assert response.status_code == 200
        data = response.json()
        assert "payments" in data
        assert len(data["payments"]) == 3

    def test_list_payments_has_expected_fields(self, client):
        response = client.get("/api/v1/payments/")
        payment = response.json()["payments"][0]
        for field in ("id", "customer", "amount", "card_last_four", "status", "created_at"):
            assert field in payment

    def test_list_payments_includes_newly_created(self, client):
        client.post(
            "/api/v1/payments/",
            json={"customer": "Dave", "amount": 50.00, "card_number": "4111111111111111"},
        )
        response = client.get("/api/v1/payments/")
        assert len(response.json()["payments"]) == 4

    def test_list_payments_no_full_card_numbers(self, client):
        response = client.get("/api/v1/payments/")
        text = response.text
        assert "4242424242424242" not in text
        assert "5555555555554444" not in text


class TestGetPayment:
    def test_get_existing_payment(self, client):
        response = client.get("/api/v1/payments/1")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["customer"] == "Alice"

    def test_get_payment_has_card_last_four(self, client):
        response = client.get("/api/v1/payments/1")
        data = response.json()
        assert data["card_last_four"] == "4242"
        assert "card_number" not in data

    def test_get_missing_payment_returns_404(self, client):
        response = client.get("/api/v1/payments/999")
        assert response.status_code == 404
        assert response.json()["detail"] == "Payment not found"

    def test_get_payment_zero_returns_404(self, client):
        response = client.get("/api/v1/payments/0")
        assert response.status_code == 404

    def test_get_payment_negative_returns_404(self, client):
        response = client.get("/api/v1/payments/-1")
        assert response.status_code == 404


class TestFailedPayment:
    def test_failed_payment_returns_500(self, client):
        response = client.post("/api/v1/payments/failed")
        assert response.status_code == 500

    def test_failed_payment_returns_detail(self, client):
        response = client.post("/api/v1/payments/failed")
        assert "detail" in response.json()


class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"