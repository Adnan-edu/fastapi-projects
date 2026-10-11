import pytest


@pytest.mark.asyncio
async def test_create_product(client):
    response = await client.post(
        "/api/v1/products/",
        json={"name": "Widget", "description": "A useful widget", "price": "19.99", "stock_quantity": 100},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Widget"
    assert data["description"] == "A useful widget"
    assert data["price"] == "19.99"
    assert data["stock_quantity"] == 100
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data


@pytest.mark.asyncio
async def test_create_product_defaults(client):
    response = await client.post(
        "/api/v1/products/",
        json={"name": "Gadget", "price": "5.00"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["description"] == ""
    assert data["stock_quantity"] == 0


@pytest.mark.asyncio
async def test_create_product_missing_name(client):
    response = await client.post(
        "/api/v1/products/",
        json={"price": "10.00"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_product_negative_price(client):
    response = await client.post(
        "/api/v1/products/",
        json={"name": "Bad Price", "price": "-5.00"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_product_zero_price(client):
    response = await client.post(
        "/api/v1/products/",
        json={"name": "Zero Price", "price": "0"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_product_negative_stock(client):
    response = await client.post(
        "/api/v1/products/",
        json={"name": "Bad Stock", "price": "10.00", "stock_quantity": -1},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_product_empty_name(client):
    response = await client.post(
        "/api/v1/products/",
        json={"name": "", "price": "10.00"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_products(client):
    await client.post("/api/v1/products/", json={"name": "Product A", "price": "10.00"})
    await client.post("/api/v1/products/", json={"name": "Product B", "price": "20.00"})

    response = await client.get("/api/v1/products/")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] >= 2
    assert len(data["products"]) >= 2


@pytest.mark.asyncio
async def test_list_products_empty(client):
    response = await client.get("/api/v1/products/")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["products"], list)
    assert data["count"] == len(data["products"])


@pytest.mark.asyncio
async def test_get_product(client):
    create_resp = await client.post(
        "/api/v1/products/",
        json={"name": "Find Me", "price": "15.00"},
    )
    product_id = create_resp.json()["id"]

    response = await client.get(f"/api/v1/products/{product_id}")
    assert response.status_code == 200
    assert response.json()["name"] == "Find Me"


@pytest.mark.asyncio
async def test_get_product_not_found(client):
    response = await client.get("/api/v1/products/999999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_product(client):
    create_resp = await client.post(
        "/api/v1/products/",
        json={"name": "Old Name", "description": "Old desc", "price": "10.00"},
    )
    product_id = create_resp.json()["id"]

    response = await client.patch(
        f"/api/v1/products/{product_id}",
        json={"name": "New Name", "price": "25.00"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "New Name"
    assert data["price"] == "25.00"
    assert data["description"] == "Old desc"


@pytest.mark.asyncio
async def test_update_stock_quantity(client):
    create_resp = await client.post(
        "/api/v1/products/",
        json={"name": "In Stock", "price": "5.00", "stock_quantity": 10},
    )
    product_id = create_resp.json()["id"]

    response = await client.patch(
        f"/api/v1/products/{product_id}",
        json={"stock_quantity": 50},
    )
    assert response.status_code == 200
    assert response.json()["stock_quantity"] == 50


@pytest.mark.asyncio
async def test_update_product_partial_preserves_fields(client):
    create_resp = await client.post(
        "/api/v1/products/",
        json={"name": "Preserve", "description": "Keep this", "price": "10.00", "stock_quantity": 5},
    )
    product_id = create_resp.json()["id"]

    response = await client.patch(
        f"/api/v1/products/{product_id}",
        json={"stock_quantity": 99},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["stock_quantity"] == 99
    assert data["name"] == "Preserve"
    assert data["description"] == "Keep this"
    assert data["price"] == "10.00"


@pytest.mark.asyncio
async def test_update_product_not_found(client):
    response = await client.patch(
        "/api/v1/products/999999",
        json={"name": "Ghost"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_product_empty_patch(client):
    create_resp = await client.post(
        "/api/v1/products/",
        json={"name": "No Change", "price": "10.00"},
    )
    product_id = create_resp.json()["id"]

    response = await client.patch(
        f"/api/v1/products/{product_id}",
        json={},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "No Change"


@pytest.mark.asyncio
async def test_delete_product(client):
    create_resp = await client.post(
        "/api/v1/products/",
        json={"name": "Delete Me", "price": "1.00"},
    )
    product_id = create_resp.json()["id"]

    delete_resp = await client.delete(f"/api/v1/products/{product_id}")
    assert delete_resp.status_code == 204

    get_resp = await client.get(f"/api/v1/products/{product_id}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_product_not_found(client):
    response = await client.delete("/api/v1/products/999999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_bulk_stock_update(client):
    p1 = await client.post("/api/v1/products/", json={"name": "A", "price": "1.00", "stock_quantity": 10})
    p2 = await client.post("/api/v1/products/", json={"name": "B", "price": "2.00", "stock_quantity": 20})
    id1 = p1.json()["id"]
    id2 = p2.json()["id"]

    response = await client.post(
        "/api/v1/products/bulk-stock-update",
        json={"items": [
            {"product_id": id1, "stock_quantity": 100},
            {"product_id": id2, "stock_quantity": 200},
        ]},
    )
    assert response.status_code == 204

    r1 = await client.get(f"/api/v1/products/{id1}")
    r2 = await client.get(f"/api/v1/products/{id2}")
    assert r1.json()["stock_quantity"] == 100
    assert r2.json()["stock_quantity"] == 200