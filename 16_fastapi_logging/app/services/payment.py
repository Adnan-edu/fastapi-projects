"""A tiny in-memory payment gateway used to demonstrate error handling.

It exists so the ``/payments`` endpoint can show the article's handled-exception
pattern: catch :class:`PaymentGatewayError`, log it with Loguru/structlog, report
it to Sentry with ``capture_exception``, then re-raise.
"""
import uuid  # Import uuid for mock transaction token generation

# Reject implausibly large charges so a failure path is easy to trigger.
_MAX_AMOUNT = 100_000  # Define maximum allowable transaction threshold limit


class PaymentGatewayError(Exception):  # Define custom exception class for payment gateway failures
    """Raised when the (simulated) payment gateway rejects a charge."""


class PaymentGateway:  # Define mock PaymentGateway driver class
    """Simulated payment gateway."""

    def charge(self, user_id: int, amount: float) -> dict:  # Charge simulation function taking parameters
        """Charge ``amount`` to ``user_id`` and return a receipt.

        Raises :class:`PaymentGatewayError` for non-positive or over-limit amounts.
        """
        if amount <= 0:  # Check if charge amount parameter is non-positive
            raise PaymentGatewayError(f"amount must be positive, got {amount}")  # Raise GatewayError for non-positive amount
        if amount > _MAX_AMOUNT:  # Check if requested charge exceeds transaction limit
            raise PaymentGatewayError(f"amount {amount} exceeds limit {_MAX_AMOUNT}")  # Raise GatewayError for amount limit breach
        return {  # Return transaction receipt details dictionary mapping parameters
            "transaction_id": uuid.uuid4().hex,  # Generate dynamic transaction UUID token string
            "user_id": user_id,  # Map target user ID parameter
            "amount": amount,  # Map charge value parameter
            "status": "succeeded",  # Tag successfully completed status label
        }

