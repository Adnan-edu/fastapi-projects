import pytest


@pytest.mark.asyncio
async def test_health_returns_ok(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "app" in data


@pytest.mark.asyncio
async def test_health_response_schema(client):
    response = await client.get("/health")
    data = response.json()
    assert isinstance(data["status"], str)
    assert isinstance(data["app"], str)
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_health_is_get_only(client):
    response = await client.post("/health")
    assert response.status_code == 405