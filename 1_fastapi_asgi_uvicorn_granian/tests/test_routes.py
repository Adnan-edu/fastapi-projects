import pytest


@pytest.mark.asyncio
async def test_unknown_route_returns_404(client):
    response = await client.get("/nonexistent")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_unknown_api_route_returns_404(client):
    response = await client.get("/api/v1/unknown")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_items_put_not_allowed(client):
    response = await client.put("/api/v1/items/1", json={"name": "X"})
    assert response.status_code == 405


@pytest.mark.asyncio
async def test_items_delete_not_allowed(client):
    response = await client.delete("/api/v1/items/1")
    assert response.status_code == 405


@pytest.mark.asyncio
async def test_compute_post_not_allowed(client):
    response = await client.post("/api/v1/compute/light")
    assert response.status_code == 405


@pytest.mark.asyncio
async def test_openapi_schema_accessible(client):
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    data = response.json()
    assert "paths" in data
    assert "/health" in data["paths"]
    assert "/api/v1/items" in data["paths"]