# =====================================================================
# app/services/image_service.py - Image processing stub
# =====================================================================
# Production would call Pillow / ImageMagick / a managed service.
# Here we just fabricate plausible file paths so tasks have something
# to return and assert against.
# =====================================================================

import logging
import uuid  # Used to make each fake output path unique.

logger = logging.getLogger(__name__)


class ImageService:
    """Service for image processing. Used by both sync API and async ARQ tasks."""

    # Creates a thumbnail; returns the fake path that would be uploaded.
    async def create_thumbnail(self, image_url: str, size: str) -> dict:
        logger.info("Creating thumbnail for %s at size %s", image_url, size)
        # uuid4().hex[:8] keeps the path short and unique-per-call.
        thumbnail_path = f"/thumbnails/{uuid.uuid4().hex[:8]}_{size}.png"
        return {"thumbnail_path": thumbnail_path, "original_url": image_url, "size": size}

    # Resizes an image to the given dimensions.
    async def resize(self, image_url: str, dimensions: str) -> dict:
        logger.info("Resizing image %s to %s", image_url, dimensions)
        resized_path = f"/resized/{uuid.uuid4().hex[:8]}_{dimensions}.png"
        return {"resized_path": resized_path, "original_url": image_url, "dimensions": dimensions}
