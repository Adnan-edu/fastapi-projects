from uuid import uuid4

import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

from app.main import app


def test_message_length_validation():
    channel = f"test:{uuid4().hex}"

    with TestClient(app) as client:
        empty_response = client.post(
            f"/channels/{channel}/messages",
            json={"message": ""},
        )
        oversized_response = client.post(
            f"/channels/{channel}/messages",
            json={"message": "x" * 10_001},
        )

    assert empty_response.status_code == 422
    assert oversized_response.status_code == 422


def test_publish_rejects_invalid_channel():
    with TestClient(app) as client:
        response = client.post(
            "/channels/-invalid/messages",
            json={"message": "valid message"},
        )

    assert response.status_code == 422


def test_websocket_rejects_invalid_channel():
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/ws/-invalid"):
                pass

    assert exc_info.value.code == 1008


def test_valid_boundaries_are_accepted():
    channel = f"test:{uuid4().hex}".ljust(128, "a")

    with TestClient(app) as client:
        response = client.post(
            f"/channels/{channel}/messages",
            json={"message": "x" * 10_000},
        )

    assert response.status_code == 200
    assert response.json() == {
        "channel": channel,
        "subscriber_count": 0,
    }
