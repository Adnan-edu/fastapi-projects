import uuid
import time

from starlette.requests import Request
from starlette.responses import Response

from loguru import logger


REQUEST_ID_HEADER = "X-Request-ID"


async def request_id_middleware(request: Request, call_next) -> Response:
    request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
    request.state.request_id = request_id

    with logger.contextualize(request_id=request_id):
        logger.info(f"Request started {request.method} {request.url.path}")
        start_time = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception as exc:
            logger.exception(f"Unhandled exception: {exc}")
            raise

        process_time = time.perf_counter() - start_time
        logger.info(
            f"Request completed {request.method} {request.url.path} "
            f"status={response.status_code} duration={process_time:.4f}s"
        )

    response.headers[REQUEST_ID_HEADER] = request_id
    response.headers["X-Process-Time"] = str(process_time)
    return response