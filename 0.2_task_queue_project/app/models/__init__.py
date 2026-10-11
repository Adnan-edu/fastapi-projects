# =====================================================================
# app/models/__init__.py - Re-exports of every ORM model
# =====================================================================
# Centralised import surface so callers can do:
#     from app.models import User, Payment, Report, JobLog
# instead of importing each module individually. The `# noqa: F401`
# comments tell linters not to complain about "imported but unused" —
# these imports are intentional re-exports, not dead code.
#
# Importing every model here ALSO triggers their class definitions,
# which registers each table on `Base.metadata`. That is essential
# for `Base.metadata.create_all(...)` to know about every table.
# =====================================================================

from app.models.user import User  # noqa: F401
from app.models.job_log import JobLog, JobStatus  # noqa: F401
from app.models.report import Report, ReportType, ReportStatus  # noqa: F401
from app.models.payment import Payment, PaymentStatus  # noqa: F401
