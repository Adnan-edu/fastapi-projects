class TestABACOwnership:
    def test_editor_cannot_update_another_editors_document(self, client):
        response = client.put(
            "/api/v1/documents/3",
            headers={"X-User": "bob"},
            json={"title": "Tampered"},
        )
        assert response.status_code == 403
        assert "own documents" in response.json()["detail"]

    def test_admin_can_update_any_document(self, client):
        response = client.put(
            "/api/v1/documents/2",
            headers={"X-User": "alice"},
            json={"title": "Admin Override"},
        )
        assert response.status_code == 200

    def test_editor_cannot_delete_any_document(self, client):
        response = client.delete("/api/v1/documents/3", headers={"X-User": "bob"})
        assert response.status_code == 403

    def test_admin_can_delete_any_document(self, client):
        response = client.delete("/api/v1/documents/2", headers={"X-User": "alice"})
        assert response.status_code == 204


class TestAuthEdgeCases:
    def test_missing_x_user_header_returns_422(self, client):
        response = client.get("/api/v1/documents/")
        assert response.status_code == 422

    def test_unknown_user_returns_403(self, client):
        response = client.get("/api/v1/documents/", headers={"X-User": "eve"})
        assert response.status_code == 403

    def test_unknown_user_cannot_create(self, client):
        response = client.post(
            "/api/v1/documents/",
            headers={"X-User": "eve"},
            json={"title": "Hacked", "content": "Nope"},
        )
        assert response.status_code == 403

    def test_unknown_user_cannot_delete(self, client):
        response = client.delete("/api/v1/documents/1", headers={"X-User": "eve"})
        assert response.status_code == 403


class TestNotFoundErrors:
    def test_get_nonexistent_document_returns_404(self, client):
        response = client.get("/api/v1/documents/9999", headers={"X-User": "alice"})
        assert response.status_code == 404

    def test_update_nonexistent_document_returns_404(self, client):
        response = client.put(
            "/api/v1/documents/9999",
            headers={"X-User": "alice"},
            json={"title": "Ghost"},
        )
        assert response.status_code == 404

    def test_delete_nonexistent_document_returns_404(self, client):
        response = client.delete("/api/v1/documents/9999", headers={"X-User": "alice"})
        assert response.status_code == 404


class TestValidationEdgeCases:
    def test_create_document_with_empty_title_returns_422(self, client):
        response = client.post(
            "/api/v1/documents/",
            headers={"X-User": "alice"},
            json={"title": "", "content": "valid content"},
        )
        assert response.status_code == 422

    def test_create_document_with_empty_content_returns_422(self, client):
        response = client.post(
            "/api/v1/documents/",
            headers={"X-User": "alice"},
            json={"title": "valid title", "content": ""},
        )
        assert response.status_code == 422

    def test_create_document_missing_fields_returns_422(self, client):
        response = client.post(
            "/api/v1/documents/",
            headers={"X-User": "alice"},
            json={},
        )
        assert response.status_code == 422

    def test_update_with_no_fields_returns_422(self, client):
        response = client.put(
            "/api/v1/documents/1",
            headers={"X-User": "alice"},
            json={},
        )
        assert response.status_code == 422

    def test_create_document_sets_owner_correctly(self, client):
        response = client.post(
            "/api/v1/documents/",
            headers={"X-User": "bob"},
            json={"title": "Bob's Doc", "content": "Owned by bob"},
        )
        assert response.json()["owner"] == "bob"

    def test_list_documents_count_after_create(self, client):
        client.post(
            "/api/v1/documents/",
            headers={"X-User": "alice"},
            json={"title": "Extra", "content": "More"},
        )
        response = client.get("/api/v1/documents/", headers={"X-User": "carol"})
        assert len(response.json()) == 4