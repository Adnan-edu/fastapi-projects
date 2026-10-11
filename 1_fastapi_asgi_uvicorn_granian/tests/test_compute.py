import pytest


@pytest.mark.asyncio
async def test_light_compute_default_n(client):
    response = await client.get("/api/v1/compute/light")
    assert response.status_code == 200
    data = response.json()
    assert data["input"] == 10000
    assert "result" in data
    assert "elapsed_seconds" in data


@pytest.mark.asyncio
async def test_light_compute_small_n(client):
    response = await client.get("/api/v1/compute/light", params={"n": 30})
    assert response.status_code == 200
    data = response.json()
    assert data["input"] == 30
    assert data["result"] == 832040


@pytest.mark.asyncio
async def test_light_compute_n_zero(client):
    response = await client.get("/api/v1/compute/light", params={"n": 0})
    assert response.status_code == 200
    assert response.json()["result"] == 0


@pytest.mark.asyncio
async def test_light_compute_n_one(client):
    response = await client.get("/api/v1/compute/light", params={"n": 1})
    assert response.status_code == 200
    assert response.json()["result"] == 1


@pytest.mark.asyncio
async def test_light_compute_negative_n(client):
    response = await client.get("/api/v1/compute/light", params={"n": -5})
    assert response.status_code == 200
    assert response.json()["result"] == 0


@pytest.mark.asyncio
async def test_light_compute_non_integer_n(client):
    response = await client.get("/api/v1/compute/light", params={"n": "abc"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_light_compute_returns_elapsed(client):
    response = await client.get("/api/v1/compute/light", params={"n": 100})
    data = response.json()
    assert isinstance(data["elapsed_seconds"], (int, float))
    assert data["elapsed_seconds"] >= 0


@pytest.mark.asyncio
async def test_io_simulated_default_delay(client):
    response = await client.get("/api/v1/compute/io-simulated")
    assert response.status_code == 200
    data = response.json()
    assert data["simulated_delay"] == 0.5


@pytest.mark.asyncio
async def test_io_simulated_small_delay(client):
    response = await client.get("/api/v1/compute/io-simulated", params={"delay": 0.01})
    assert response.status_code == 200
    data = response.json()
    assert data["simulated_delay"] == 0.01
    assert data["actual_elapsed_seconds"] >= 0.01


@pytest.mark.asyncio
async def test_io_simulated_zero_delay(client):
    response = await client.get("/api/v1/compute/io-simulated", params={"delay": 0})
    assert response.status_code == 200
    data = response.json()
    assert data["simulated_delay"] == 0
    assert data["actual_elapsed_seconds"] >= 0


@pytest.mark.asyncio
async def test_io_simulated_negative_delay(client):
    response = await client.get("/api/v1/compute/io-simulated", params={"delay": -1})
    assert response.status_code == 200
    data = response.json()
    assert data["simulated_delay"] == -1


@pytest.mark.asyncio
async def test_io_simulated_elapsed_greater_than_delay(client):
    response = await client.get("/api/v1/compute/io-simulated", params={"delay": 0.1})
    data = response.json()
    assert data["actual_elapsed_seconds"] >= data["simulated_delay"]