# =====================================================================
# app/models/base.py - Convenience re-export of the SQLAlchemy Base
# =====================================================================
# Some files prefer `from app.models.base import Base` for readability.
# The real declaration lives in app/database.py — we just re-export it
# here so model files can stay grouped under app/models/ without
# reaching across the package boundary.
# =====================================================================

from app.database import Base  # noqa: F401 - re-export Base for all models
