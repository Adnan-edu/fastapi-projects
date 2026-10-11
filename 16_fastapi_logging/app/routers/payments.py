"""Payment endpoint demonstrating the handled-exception pattern.

On a gateway failure it logs the error and reports it to Sentry with
``capture_exception`` and to Logfire with ``span.record_exception`` before
returning an HTTP 402 -- a deliberate, tracked failure (as opposed to
``/boom``'s unhandled crash).
"""
import sentry_sdk  # Import Sentry SDK to capture handled exceptions
import structlog  # Import structlog for structured logging
import logfire  # Import Logfire for span-based observability and exception recording
from fastapi import APIRouter, HTTPException  # Import API routing module and HTTP exceptions handler
from pydantic import BaseModel  # Import base model schema constructor

from app.services.payment import PaymentGateway, PaymentGatewayError  # Import mocked gateway service and custom exception

router = APIRouter(prefix="/payments", tags=["payments"])  # Create router with /payments URL prefix
log = structlog.get_logger("app.payments")  # Retrieve structured logger instance for payments namespace
_gateway = PaymentGateway()  # Instantiate payment gateway service object


class PaymentRequest(BaseModel):  # Define PaymentRequest schema inheriting from BaseModel
    user_id: int  # user_id integer parameter
    amount: float  # amount float value parameter


@router.post("")  # Register POST endpoint for payments creation
def create_payment(body: PaymentRequest):  # Endpoint handler function taking payment request body
    structlog.contextvars.bind_contextvars(user_id=body.user_id, amount=body.amount)  # Bind metadata variables to logger context
    log.info("payment_started")  # Log transaction initiation
    with logfire.span(  # Open Logfire span for distributed tracing of the payment operation
        "create_payment",  # Span name identifying this operation in Logfire dashboard
        user_id=body.user_id,  # Attach user_id as span attribute for searchability
        amount=body.amount,  # Attach amount as span attribute for searchability
    ) as span:  # Capture span reference for exception recording
        try:  # Open exception capture context block
            receipt = _gateway.charge(body.user_id, body.amount)  # Attempt charging user through payment gateway service
        except PaymentGatewayError as exc:  # Catch payment failure exception
            # Handled exception: record locally AND report to Sentry/Logfire, then surface
            # a clean 402 to the client.
            log.error("payment_failed", error=str(exc), error_type=type(exc).__name__)  # Log detailed payment failure local log
            span.record_exception(exc)  # Record exception in Logfire span for trace-level visibility
            sentry_sdk.capture_exception(exc)  # Capture exception structure and upload error info to Sentry
            raise HTTPException(status_code=402, detail=str(exc)) from exc  # Raise HTTP 402 exception for client response
        log.info("payment_succeeded", transaction_id=receipt["transaction_id"])  # Log successful payment processing event
        logfire.info("payment_succeeded", transaction_id=receipt["transaction_id"])  # Emit Logfire-native success event
        return receipt  # Return receipt payload dict response

