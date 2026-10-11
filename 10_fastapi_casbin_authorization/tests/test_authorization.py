class TestAdminPermissions:
    def test_admin_can_list_documents(self, client):
        response = client.get("/api/v1/documents/", headers={"X-User": "alice"})
        assert response.status_code == 200
        assert len(response.json()) >= 1

    def test_admin_can_get_single_document(self, client):
        response = client.get("/api/v1/documents/1", headers={"X-User": "alice"})
        assert response.status_code == 200
        assert response.json()["title"] == "Quarterly Report"

    def test_admin_can_create_document(self, client):
        response = client.post(
            "/api/v1/documents/",
            headers={"X-User": "alice"},
            json={"title": "New Doc", "content": "Admin created this."},
        )
        assert response.status_code == 201
        assert response.json()["title"] == "New Doc"
        assert response.json()["owner"] == "alice"

    def test_admin_can_update_any_document(self, client):
        response = client.put(
            "/api/v1/documents/2",
            headers={"X-User": "alice"},
            json={"title": "Updated by Admin"},
        )
        assert response.status_code == 200
        assert response.json()["title"] == "Updated by Admin"

    def test_admin_can_delete_any_document(self, client):
        response = client.delete("/api/v1/documents/2", headers={"X-User": "alice"})
        assert response.status_code == 204


class TestEditorPermissions:
    def test_editor_can_list_documents(self, client):
        response = client.get("/api/v1/documents/", headers={"X-User": "bob"})
        assert response.status_code == 200

    def test_editor_can_get_single_document(self, client):
        response = client.get("/api/v1/documents/1", headers={"X-User": "bob"})
        assert response.status_code == 200

    def test_editor_can_create_document(self, client):
        response = client.post(
            "/api/v1/documents/",
            headers={"X-User": "bob"},
            json={"title": "Editor Doc", "content": "Content here."},
        )
        assert response.status_code == 201
        assert response.json()["owner"] == "bob"

    def test_editor_can_update_own_document(self, client):
        response = client.put(
            "/api/v1/documents/2",
            headers={"X-User": "bob"},
            json={"title": "Updated Meeting Notes"},
        )
        assert response.status_code == 200
        assert response.json()["title"] == "Updated Meeting Notes"

    def test_editor_cannot_delete_document(self, client):
        response = client.delete("/api/v1/documents/1", headers={"X-User": "bob"})
        assert response.status_code == 403

    def test_editor_cannot_delete_own_document(self, client):
        response = client.delete("/api/v1/documents/2", headers={"X-User": "bob"})
        assert response.status_code == 403


class TestViewerPermissions:
    def test_viewer_can_list_documents(self, client):
        response = client.get("/api/v1/documents/", headers={"X-User": "carol"})
        assert response.status_code == 200

    def test_viewer_can_get_single_document(self, client):
        response = client.get("/api/v1/documents/1", headers={"X-User": "carol"})
        assert response.status_code == 200

    def test_viewer_cannot_create_document(self, client):
        response = client.post(
            "/api/v1/documents/",
            headers={"X-User": "carol"},
            json={"title": "Viewer Doc", "content": "Should fail."},
        )
        assert response.status_code == 403

    def test_viewer_cannot_update_document(self, client):
        response = client.put(
            "/api/v1/documents/1",
            headers={"X-User": "carol"},
            json={"title": "Hacked"},
        )
        assert response.status_code == 403

    def test_viewer_cannot_delete_document(self, client):
        response = client.delete("/api/v1/documents/1", headers={"X-User": "carol"})
        assert response.status_code == 403