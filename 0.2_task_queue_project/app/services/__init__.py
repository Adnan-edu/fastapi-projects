# =====================================================================
# app/services/__init__.py - Service-layer re-exports
# =====================================================================
# Bundles all service classes so they can be imported from one place:
#     from app.services import PaymentService, EmailService
#
# Services contain BUSINESS LOGIC and are deliberately decoupled from
# both FastAPI (no Request/Response types) and ARQ (no ctx dict). That
# lets both API routes (sync mode) and tasks (async mode) reuse them.
# =====================================================================

from app.services.email_service import EmailService  # noqa: F401
from app.services.image_service import ImageService  # noqa: F401
from app.services.report_service import ReportService  # noqa: F401
from app.services.payment_service import PaymentService  # noqa: F401
from app.services.etl_service import ETLService  # noqa: F401
from app.services.webhook_service import WebhookService  # noqa: F401
from app.services.notification_service import NotificationService  # noqa: F401
