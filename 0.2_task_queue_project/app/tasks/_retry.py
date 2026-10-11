# =====================================================================
# app/tasks/_retry.py - Shared retry/backoff helper for ARQ tasks
# =====================================================================
# Several task modules (image, payment, etl, webhook) share the same
# linear-backoff retry pattern. Centralising it here keeps the per-task
# files focused on their domain logic and ensures the backoff formula
# stays consistent across modules.
# =====================================================================

from arq import Retry


def retry_with_backoff(ctx: dict, *, factor: int) -> None:
    """Raise an ARQ Retry with linear backoff based on the current attempt.

    Delay grows linearly with ctx['job_try']: try1=factor, try2=2*factor, ...
    Until the worker's max_tries cap is hit, at which point the job fails.
    """
    raise Retry(defer=ctx["job_try"] * factor)
