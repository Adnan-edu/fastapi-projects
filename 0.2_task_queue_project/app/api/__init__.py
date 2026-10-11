# =====================================================================
# app/api/__init__.py - API package marker
# =====================================================================
# Re-exports the aggregated APIRouter so callers can do:
#     from app.api import router
# without knowing about the internal `router.py` file.
# =====================================================================

from app.api.router import router  # noqa: F401
