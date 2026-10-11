# =====================================================================
# app/tasks/__init__.py - Re-export every ARQ task function
# =====================================================================
# Importing this package triggers the import of every task module,
# which causes each `async def` to be defined and made available by
# name. The worker can then find tasks by their string name when it
# pulls a job off the queue.
# =====================================================================

from app.tasks.email_tasks import send_welcome_email, send_report_email, send_batch_email  # noqa: F401
from app.tasks.image_tasks import generate_thumbnail, resize_image  # noqa: F401
from app.tasks.report_tasks import generate_pdf_report, generate_csv_export  # noqa: F401
from app.tasks.payment_tasks import process_payment, process_refund  # noqa: F401
from app.tasks.etl_tasks import run_data_pipeline, sync_external_data  # noqa: F401
from app.tasks.webhook_tasks import dispatch_webhook, retry_webhook  # noqa: F401
from app.tasks.notification_tasks import send_push_notification, batch_notify  # noqa: F401
from app.tasks.cleanup_tasks import cleanup_expired_sessions, cleanup_old_job_results  # noqa: F401
