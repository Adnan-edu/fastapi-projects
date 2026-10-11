# =====================================================================
# app/tasks/image_tasks.py - ARQ tasks for image processing
# =====================================================================
# Demonstrates ARQ's Retry mechanism for handling flaky downstreams.
# Raising `Retry(defer=N)` tells the worker: don't fail, requeue this
# job to run again N seconds from now. The `ctx["job_try"]` counter
# increments each time, letting us implement exponential backoff.
# =====================================================================

import logging
from datetime import datetime, timezone

from app.services.image_service import ImageService
from app.tasks._retry import retry_with_backoff

logger = logging.getLogger(__name__)


async def generate_thumbnail(ctx: dict, image_url: str, size: str = "200x200") -> dict:
    """Generate a thumbnail from an image URL.

    ARQ Feature: Retry with exponential backoff using raise Retry(defer=...).
    If the image service is temporarily unavailable, the task will be
    retried with increasing delay (5s, 10s, 15s, etc.) up to max_tries.
    """
    logger.info("Generating thumbnail for %s at size %s", image_url, size)
    image_service = ctx.get("image_service", ImageService())
    try:
        result = await image_service.create_thumbnail(image_url, size)
        logger.info("Thumbnail generated for %s", image_url)
        return {"image_url": image_url, "size": size, "thumbnail_path": result["thumbnail_path"], "timestamp": datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        # Any failure becomes a Retry. defer scales linearly with job_try
        # so the backoff is: try1=5s, try2=10s, try3=15s, ...
        logger.warning("Thumbnail generation failed for %s: %s (try %s)", image_url, e, ctx["job_try"])
        retry_with_backoff(ctx, factor=5)


async def resize_image(ctx: dict, image_url: str, dimensions: str) -> dict:
    """Resize an image to the specified dimensions.

    ARQ Feature: func() wrapper with keep_result and max_tries.
    Configured in WorkerSettings as:
      func(resize_image, keep_result=86400, max_tries=3)
    Results are kept for 24 hours.
    """
    logger.info("Resizing image %s to %s", image_url, dimensions)
    image_service = ctx.get("image_service", ImageService())
    # Note: no try/except here — failures bubble up and ARQ will use
    # the worker's default retry behaviour (max_tries from the func() wrap).
    result = await image_service.resize(image_url, dimensions)
    logger.info("Image resized: %s -> %s", image_url, dimensions)
    return {"image_url": image_url, "dimensions": dimensions, "resized_path": result["resized_path"], "timestamp": datetime.now(timezone.utc).isoformat()}
