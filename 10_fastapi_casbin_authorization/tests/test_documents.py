class TestDocumentCRUD:
    def test_list_documents_returns_seed_data(self, client):
        response = client.get("/api/v1/documents/", headers={"X-User": "alice"})
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3

    def test_get_document_by_id(self, client):
        response = client.get("/api/v1/documents/1", headers={"X-User": "alice"})
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["title"] == "Quarterly Report"
        assert data["owner"] == "alice"

    def test_create_document(self, client):
        response = client.post(
            "/api/v1/documents/",
            headers={"X-User": "bob"},
            json={"title": "Test Doc", "content": "Some content"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Test Doc"
        assert data["content"] == "Some content"
        assert data["owner"] == "bob"
        assert data["id"] == 4

    def test_update_document_title(self, client):
        response = client.put(
            "/api/v1/documents/2",
            headers={"X-User": "bob"},
            json={"title": "Renamed"},
        )
        assert response.status_code == 200
        assert response.json()["title"] == "Renamed"
        assert response.json()["content"] == "Decided to migrate to Casbin."

    def test_update_document_content(self, client):
        response = client.put(
            "/api/v1/documents/2",
            headers={"X-User": "bob"},
            json={"content": "Updated content"},
        )
        assert response.status_code == 200
        assert response.json()["content"] == "Updated content"

    def test_delete_document(self, client):
        response = client.delete("/api/v1/documents/3", headers={"X-User": "alice"})
        assert response.status_code == 204
        response = client.get("/api/v1/documents/3", headers={"X-User": "alice"})
        assert response.status_code == 404