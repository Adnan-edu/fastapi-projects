from datetime import datetime

import pytest
from fastapi import HTTPException

from app.cursor import Cursor


def test_roundtrip():
    c = Cursor(created_at=datetime(2024, 8, 16, 14, 12, 31), id=42)
    token = c.encode()
    assert isinstance(token, str)
    assert Cursor.decode(token) == c


def test_decode_garbage_raises_400():
    with pytest.raises(HTTPException) as exc:
        Cursor.decode("not-a-real-cursor!!!")
    assert exc.value.status_code == 400


def test_url_safe():
    c = Cursor(created_at=datetime(2024, 1, 1), id=1)
    token = c.encode()
    assert "/" not in token and "+" not in token and "=" not in token
