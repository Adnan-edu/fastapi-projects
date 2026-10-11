# =====================================================================
# app/schemas/__init__.py - Re-exports of every Pydantic schema
# =====================================================================
# Convenience aggregation so route modules can write:
#     from app.schemas import JobCreate, PaymentRead
# Schemas describe the SHAPE of API requests/responses and are
# separate from the ORM models (which describe persistent storage).
# =====================================================================

from app.schemas.user import UserCreate, UserRead  # noqa: F401
from app.schemas.job import JobCreate, JobRead, JobStatusResponse  # noqa: F401
from app.schemas.report import ReportCreate, ReportRead  # noqa: F401
from app.schemas.payment import PaymentCreate, PaymentRead, RefundRequest  # noqa: F401
from app.schemas.webhook import WebhookRegister, WebhookPayload  # noqa: F401
