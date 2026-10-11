VALID_USER = {
    "username": "johndoe",
    "email": "john@example.com",
    "password": "Str0ng!Pass",
    "confirm_password": "Str0ng!Pass",
    "first_name": "John",
    "last_name": "Doe",
}


def test_register_user_valid(client):
    response = client.post("/api/v1/users/", json=VALID_USER)
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "johndoe"
    assert data["email"] == "john@example.com"
    assert data["first_name"] == "John"
    assert data["last_name"] == "Doe"
    assert "password" not in data
    assert "password_hash" not in data
    assert "id" in data


def test_register_user_invalid_email(client):
    payload = {**VALID_USER, "email": "not-an-email"}
    response = client.post("/api/v1/users/", json=payload)
    assert response.status_code == 422


def test_register_user_weak_password_no_uppercase(client):
    payload = {**VALID_USER, "password": "weak1!pass", "confirm_password": "weak1!pass"}
    response = client.post("/api/v1/users/", json=payload)
    assert response.status_code == 422


def test_register_user_weak_password_no_digit(client):
    payload = {**VALID_USER, "password": "Weak!!pass", "confirm_password": "Weak!!pass"}
    response = client.post("/api/v1/users/", json=payload)
    assert response.status_code == 422


def test_register_user_weak_password_no_special(client):
    payload = {**VALID_USER, "password": "Weak123Pass", "confirm_password": "Weak123Pass"}
    response = client.post("/api/v1/users/", json=payload)
    assert response.status_code == 422


def test_register_user_password_mismatch(client):
    payload = {**VALID_USER, "confirm_password": "Different1!"}
    response = client.post("/api/v1/users/", json=payload)
    assert response.status_code == 422


def test_register_user_missing_required_fields(client):
    response = client.post("/api/v1/users/", json={})
    assert response.status_code == 422


def test_register_user_invalid_username_pattern(client):
    payload = {**VALID_USER, "username": "has spaces"}
    response = client.post("/api/v1/users/", json=payload)
    assert response.status_code == 422


def test_register_user_short_username(client):
    payload = {**VALID_USER, "username": "ab"}
    response = client.post("/api/v1/users/", json=payload)
    assert response.status_code == 422


def test_register_user_with_address(client):
    payload = {
        **VALID_USER,
        "address": {
            "street": "123 Main St",
            "city": "Springfield",
            "state": "IL",
            "zip_code": "62701",
        },
    }
    response = client.post("/api/v1/users/", json=payload)
    assert response.status_code == 201


def test_register_user_invalid_zip_code(client):
    payload = {
        **VALID_USER,
        "address": {
            "street": "123 Main St",
            "city": "Springfield",
            "state": "IL",
            "zip_code": "invalid",
        },
    }
    response = client.post("/api/v1/users/", json=payload)
    assert response.status_code == 422


def test_register_user_duplicate_username(client):
    client.post("/api/v1/users/", json=VALID_USER)
    payload = {**VALID_USER, "email": "other@example.com"}
    response = client.post("/api/v1/users/", json=payload)
    assert response.status_code == 409


def test_get_user_profile(client):
    create_resp = client.post("/api/v1/users/", json=VALID_USER)
    user_id = create_resp.json()["id"]

    response = client.get(f"/api/v1/users/{user_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "johndoe"
    assert data["full_name"] == "John Doe"


def test_get_user_profile_with_alias(client):
    response = client.post("/api/v1/users/", json=VALID_USER)
    user_id = response.json()["id"]

    profile = client.get(f"/api/v1/users/{user_id}")
    data = profile.json()
    assert "full_name" in data
    assert data["full_name"] == "John Doe"


def test_get_user_not_found(client):
    response = client.get("/api/v1/users/999999")
    assert response.status_code == 404


def test_update_user_profile(client):
    create_resp = client.post("/api/v1/users/", json=VALID_USER)
    user_id = create_resp.json()["id"]

    response = client.patch(
        f"/api/v1/users/{user_id}",
        json={"first_name": "Jane", "last_name": "Smith"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["full_name"] == "Jane Smith"


def test_update_user_phone(client):
    create_resp = client.post("/api/v1/users/", json=VALID_USER)
    user_id = create_resp.json()["id"]

    response = client.patch(
        f"/api/v1/users/{user_id}",
        json={"phone": "+14155551234"},
    )
    assert response.status_code == 200


def test_update_user_not_found(client):
    response = client.patch("/api/v1/users/999999", json={"first_name": "Ghost"})
    assert response.status_code == 404


def test_list_users(client):
    client.post("/api/v1/users/", json=VALID_USER)
    second_user = {
        **VALID_USER,
        "username": "janedoe",
        "email": "jane@example.com",
    }
    client.post("/api/v1/users/", json=second_user)

    response = client.get("/api/v1/users/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2


def test_response_excludes_password(client):
    create_resp = client.post("/api/v1/users/", json=VALID_USER)
    assert "password" not in create_resp.json()
    assert "password_hash" not in create_resp.json()
    assert "confirm_password" not in create_resp.json()


def test_validate_notification_email(client):
    response = client.post(
        "/api/v1/users/validate-notification",
        json={"type": "email", "email_address": "test@example.com"},
    )
    assert response.status_code == 200
    assert response.json()["type"] == "email"


def test_validate_notification_sms(client):
    response = client.post(
        "/api/v1/users/validate-notification",
        json={"type": "sms", "phone_number": "+14155551234"},
    )
    assert response.status_code == 200
    assert response.json()["type"] == "sms"


def test_validate_notification_invalid_type(client):
    response = client.post(
        "/api/v1/users/validate-notification",
        json={"type": "push", "device_token": "abc123"},
    )
    assert response.status_code == 422