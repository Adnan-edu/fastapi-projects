class TestCreateOrder:
    def test_create_order_returns_201(self, client):
        response = client.post(
            "/api/v1/orders/",
            json={"customer": "Dave", "item": "Sprocket", "quantity": 2},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["customer"] == "Dave"
        assert data["item"] == "Sprocket"
        assert data["quantity"] == 2
        assert data["status"] == "pending"
        assert "id" in data
        assert "created_at" in data

    def test_create_order_auto_increments_id(self, client):
        r1 = client.post(
            "/api/v1/orders/",
            json={"customer": "Eve", "item": "Bolt", "quantity": 1},
        )
        r2 = client.post(
            "/api/v1/orders/",
            json={"customer": "Frank", "item": "Nut", "quantity": 10},
        )
        assert r1.json()["id"] < r2.json()["id"]

    def test_create_order_empty_customer_returns_422(self, client):
        response = client.post(
            "/api/v1/orders/",
            json={"customer": "", "item": "Bolt", "quantity": 1},
        )
        assert response.status_code == 422

    def test_create_order_zero_quantity_returns_422(self, client):
        response = client.post(
            "/api/v1/orders/",
            json={"customer": "Eve", "item": "Bolt", "quantity": 0},
        )
        assert response.status_code == 422

    def test_create_order_negative_quantity_returns_422(self, client):
        response = client.post(
            "/api/v1/orders/",
            json={"customer": "Eve", "item": "Bolt", "quantity": -1},
        )
        assert response.status_code == 422

    def test_create_order_missing_fields_returns_422(self, client):
        response = client.post(
            "/api/v1/orders/",
            json={},
        )
        assert response.status_code == 422


class TestListOrders:
    def test_list_orders_returns_all(self, client):
        response = client.get("/api/v1/orders/")
        assert response.status_code == 200
        data = response.json()
        assert "orders" in data
        assert len(data["orders"]) == 3

    def test_list_orders_has_expected_fields(self, client):
        response = client.get("/api/v1/orders/")
        order = response.json()["orders"][0]
        for field in ("id", "customer", "item", "quantity", "status", "created_at"):
            assert field in order

    def test_list_orders_includes_newly_created(self, client):
        client.post(
            "/api/v1/orders/",
            json={"customer": "Dave", "item": "Sprocket", "quantity": 2},
        )
        response = client.get("/api/v1/orders/")
        assert len(response.json()["orders"]) == 4


class TestGetOrder:
    def test_get_existing_order(self, client):
        response = client.get("/api/v1/orders/1")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["customer"] == "Alice"

    def test_get_missing_order_returns_404(self, client):
        response = client.get("/api/v1/orders/999")
        assert response.status_code == 404
        assert response.json()["detail"] == "Order not found"

    def test_get_order_zero_returns_404(self, client):
        response = client.get("/api/v1/orders/0")
        assert response.status_code == 404

    def test_get_order_negative_returns_404(self, client):
        response = client.get("/api/v1/orders/-1")
        assert response.status_code == 404


class TestSlowEndpoint:
    def test_slow_endpoint_returns_200(self, client):
        response = client.get("/api/v1/orders/slow")
        assert response.status_code == 200
        data = response.json()
        assert "delay_seconds" in data

    def test_slow_endpoint_returns_delay_message(self, client):
        response = client.get("/api/v1/orders/slow")
        data = response.json()
        assert data["delay_seconds"] == 0.5


class TestErrorEndpoint:
    def test_error_endpoint_returns_500(self, client):
        response = client.get("/api/v1/orders/error")
        assert response.status_code == 500

    def test_error_endpoint_returns_detail(self, client):
        response = client.get("/api/v1/orders/error")
        assert "detail" in response.json()


class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
