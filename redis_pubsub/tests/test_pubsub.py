import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app


def test_publish_fans_out_and_cleans_up_disconnected_subscribers():
    channel = f"test:{uuid4().hex}"

    with TestClient(app) as client:
        with (
            client.websocket_connect(f"/ws/{channel}") as first,
            client.websocket_connect(f"/ws/{channel}") as second,
        ):
            assert first.receive_json() == {
                "type": "subscribed",
                "channel": channel,
            }
            assert second.receive_json() == {
                "type": "subscribed",
                "channel": channel,
            }

            response = client.post(
                f"/channels/{channel}/messages",
                json={"message": "Hello from Redis!"},
            )

            assert response.status_code == 200
            assert response.json() == {
                "channel": channel,
                "subscriber_count": 2,
            }
            expected = {
                "type": "message",
                "channel": channel,
                "message": "Hello from Redis!",
            }
            assert first.receive_json() == expected
            assert second.receive_json() == expected

        deadline = time.monotonic() + 2
        while True:
            response = client.post(
                f"/channels/{channel}/messages",
                json={"message": "cleanup probe"},
            )
            assert response.status_code == 200
            if response.json()["subscriber_count"] == 0:
                break
            if time.monotonic() >= deadline:
                pytest.fail("Redis subscribers remained after WebSocket disconnect")
            time.sleep(0.05)
