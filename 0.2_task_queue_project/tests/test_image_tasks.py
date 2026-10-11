# =====================================================================
# tests/test_image_tasks.py - Image-task tests
# =====================================================================
# Exercises the thumbnail Retry path and the simpler resize_image task.
# =====================================================================

import pytest

from app.tasks.image_tasks import generate_thumbnail, resize_image
from app.services.image_service import ImageService


@pytest.mark.asyncio
async def test_generate_thumbnail():
    # Happy path: real ImageService stub returns a thumbnail_path.
    ctx = {"image_service": ImageService(), "job_try": 1}
    result = await generate_thumbnail(ctx, image_url="https://example.com/photo.jpg", size="200x200")
    assert result["image_url"] == "https://example.com/photo.jpg"
    assert result["size"] == "200x200"
    assert "thumbnail_path" in result


@pytest.mark.asyncio
async def test_generate_thumbnail_retry():
    """Test that generate_thumbnail raises Retry on failure."""
    from arq import Retry
    from unittest.mock import AsyncMock

    # Inject a failing service so the task hits its except branch.
    mock_service = AsyncMock()
    mock_service.create_thumbnail = AsyncMock(side_effect=Exception("Image service unavailable"))

    # job_try=2 → defer = job_try * 5 = 10s → 10000 ms.
    ctx = {"image_service": mock_service, "job_try": 2}
    with pytest.raises(Retry) as exc_info:
        await generate_thumbnail(ctx, image_url="https://example.com/bad.jpg", size="200x200")
    assert exc_info.value.defer_score == 10000  # job_try * 5 * 1000 = 2 * 5 * 1000 ms


@pytest.mark.asyncio
async def test_resize_image():
    # resize_image has no Retry branch — purely a happy-path test.
    ctx = {"image_service": ImageService()}
    result = await resize_image(ctx, image_url="https://example.com/photo.jpg", dimensions="800x600")
    assert result["image_url"] == "https://example.com/photo.jpg"
    assert result["dimensions"] == "800x600"
    assert "resized_path" in result
