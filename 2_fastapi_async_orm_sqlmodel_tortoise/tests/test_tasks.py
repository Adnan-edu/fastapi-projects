import pytest


@pytest.mark.asyncio
async def test_create_task(client):
    response = await client.post(
        "/api/v1/tasks/",
        json={"title": "Buy groceries", "description": "Milk, eggs, bread"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Buy groceries"
    assert data["description"] == "Milk, eggs, bread"
    assert data["status"] == "pending"
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data


@pytest.mark.asyncio
async def test_create_task_with_status(client):
    response = await client.post(
        "/api/v1/tasks/",
        json={"title": "Study FastAPI", "status": "in_progress"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "in_progress"


@pytest.mark.asyncio
async def test_create_task_missing_title(client):
    response = await client.post(
        "/api/v1/tasks/",
        json={"description": "No title provided"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_task_empty_title(client):
    response = await client.post(
        "/api/v1/tasks/",
        json={"title": ""},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_task_invalid_status(client):
    response = await client.post(
        "/api/v1/tasks/",
        json={"title": "Bad status", "status": "unknown"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_tasks(client):
    await client.post("/api/v1/tasks/", json={"title": "Task A"})
    await client.post("/api/v1/tasks/", json={"title": "Task B"})

    response = await client.get("/api/v1/tasks/")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] >= 2
    assert len(data["tasks"]) >= 2


@pytest.mark.asyncio
async def test_list_tasks_empty(client):
    response = await client.get("/api/v1/tasks/")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["tasks"], list)
    assert data["count"] == len(data["tasks"])


@pytest.mark.asyncio
async def test_get_task(client):
    create_resp = await client.post(
        "/api/v1/tasks/",
        json={"title": "Get me"},
    )
    task_id = create_resp.json()["id"]

    response = await client.get(f"/api/v1/tasks/{task_id}")
    assert response.status_code == 200
    assert response.json()["title"] == "Get me"


@pytest.mark.asyncio
async def test_get_task_not_found(client):
    response = await client.get("/api/v1/tasks/999999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_task_status(client):
    create_resp = await client.post(
        "/api/v1/tasks/",
        json={"title": "Update me"},
    )
    task_id = create_resp.json()["id"]

    response = await client.patch(
        f"/api/v1/tasks/{task_id}",
        json={"status": "completed"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_update_task_title_and_description(client):
    create_resp = await client.post(
        "/api/v1/tasks/",
        json={"title": "Old title", "description": "Old desc"},
    )
    task_id = create_resp.json()["id"]

    response = await client.patch(
        f"/api/v1/tasks/{task_id}",
        json={"title": "New title", "description": "New desc"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "New title"
    assert data["description"] == "New desc"


@pytest.mark.asyncio
async def test_update_task_not_found(client):
    response = await client.patch(
        "/api/v1/tasks/999999",
        json={"status": "completed"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_task(client):
    create_resp = await client.post(
        "/api/v1/tasks/",
        json={"title": "Delete me"},
    )
    task_id = create_resp.json()["id"]

    delete_resp = await client.delete(f"/api/v1/tasks/{task_id}")
    assert delete_resp.status_code == 204

    get_resp = await client.get(f"/api/v1/tasks/{task_id}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_task_not_found(client):
    response = await client.delete("/api/v1/tasks/999999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_partial_only_status(client):
    create_resp = await client.post(
        "/api/v1/tasks/",
        json={"title": "Partial update", "description": "Keep this"},
    )
    task_id = create_resp.json()["id"]

    response = await client.patch(
        f"/api/v1/tasks/{task_id}",
        json={"status": "in_progress"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "in_progress"
    assert data["title"] == "Partial update"
    assert data["description"] == "Keep this"