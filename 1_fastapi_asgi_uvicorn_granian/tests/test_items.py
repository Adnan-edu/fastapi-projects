import pytest


@pytest.mark.asyncio
async def test_list_items_empty(client):
    response = await client.get("/api/v1/items")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_create_item_with_description(client):
    resp = await client.post(
        "/api/v1/items",
        json={"name": "Widget", "description": "A useful widget"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Widget"
    assert data["description"] == "A useful widget"
    assert data["id"] == 1


@pytest.mark.asyncio
async def test_create_item_without_description(client):
    resp = await client.post(
        "/api/v1/items",
        json={"name": "Gadget"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Gadget"
    assert data["description"] is None
    assert data["id"] == 1


@pytest.mark.asyncio
async def test_create_item_with_null_description(client):
    resp = await client.post(
        "/api/v1/items",
        json={"name": "Thing", "description": None},
    )
    assert resp.status_code == 201
    assert resp.json()["description"] is None


@pytest.mark.asyncio
async def test_create_item_ids_increment(client):
    r1 = await client.post("/api/v1/items", json={"name": "A"})
    r2 = await client.post("/api/v1/items", json={"name": "B"})
    assert r1.json()["id"] == 1
    assert r2.json()["id"] == 2


@pytest.mark.asyncio
async def test_create_item_empty_name_rejected(client):
    resp = await client.post(
        "/api/v1/items",
        json={"name": ""},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_item_missing_name_rejected(client):
    resp = await client.post(
        "/api/v1/items",
        json={"description": "no name"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_item_extra_fields_rejected(client):
    resp = await client.post(
        "/api/v1/items",
        json={"name": "X", "extra": "should fail"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_item_empty_body_rejected(client):
    resp = await client.post("/api/v1/items", json={})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_item_wrong_content_type(client):
    resp = await client.post(
        "/api/v1/items",
        content="not json",
        headers={"Content-Type": "text/plain"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_item_by_id(client):
    create_resp = await client.post(
        "/api/v1/items",
        json={"name": "Widget", "description": "desc"},
    )
    item_id = create_resp.json()["id"]
    get_resp = await client.get(f"/api/v1/items/{item_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "Widget"


@pytest.mark.asyncio
async def test_get_item_not_found(client):
    response = await client.get("/api/v1/items/9999")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_item_zero_id(client):
    response = await client.get("/api/v1/items/0")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_item_negative_id(client):
    response = await client.get("/api/v1/items/-1")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_item_non_integer_id(client):
    response = await client.get("/api/v1/items/abc")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_items_after_multiple_creates(client):
    await client.post("/api/v1/items", json={"name": "A"})
    await client.post("/api/v1/items", json={"name": "B"})
    response = await client.get("/api/v1/items")
    assert response.status_code == 200
    assert len(response.json()) == 2


@pytest.mark.asyncio
async def test_items_post_is_not_get(client):
    response = await client.post("/api/v1/items")
    assert response.status_code == 422