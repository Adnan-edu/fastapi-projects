from fastapi.testclient import TestClient

from app.main import app


def test_browser_demo_is_served():
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")

    for marker in (
        'for="channel-input"',
        'for="message-input"',
        'id="connect-button"',
        'id="send-button"',
        'id="message-list"',
    ):
        assert marker in response.text
