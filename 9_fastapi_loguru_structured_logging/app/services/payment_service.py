from datetime import datetime, timezone

from loguru import logger

_PAYMENTS: list[dict] = [
    {
        "id": 1,
        "customer": "Alice",
        "amount": 99.50,
        "card_last_four": "4242",
        "status": "completed",
        "created_at": "2025-01-01T10:00:00Z",
    },
    {
        "id": 2,
        "customer": "Bob",
        "amount": 149.00,
        "card_last_four": "1234",
        "status": "pending",
        "created_at": "2025-01-02T11:30:00Z",
    },
    {
        "id": 3,
        "customer": "Carol",
        "amount": 250.75,
        "card_last_four": "5678",
        "status": "failed",
        "created_at": "2025-01-03T09:15:00Z",
    },
]

_next_id = len(_PAYMENTS) + 1


def _mask_card(card_number: str) -> str:
    if len(card_number) < 4:
        return "****"
    return f"****{card_number[-4:]}"


def create(customer: str, amount: float, card_number: str) -> dict:
    global _next_id
    logger.info(f"Creating payment for customer={customer} amount={amount}")
    logger.debug(f"Card number masked: {_mask_card(card_number)}")

    payment = {
        "id": _next_id,
        "customer": customer,
        "amount": amount,
        "card_last_four": card_number[-4:],
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _PAYMENTS.append(payment)
    _next_id += 1

    logger.info(f"Payment created id={payment['id']} customer={customer} status=pending")
    return payment


def get_by_id(payment_id: int) -> dict | None:
    for payment in _PAYMENTS:
        if payment["id"] == payment_id:
            logger.info(f"Payment retrieved id={payment_id}")
            return payment
    logger.warning(f"Payment not found id={payment_id}")
    return None


def get_all() -> list[dict]:
    logger.info(f"Listing all payments count={len(_PAYMENTS)}")
    return list(_PAYMENTS)


def simulate_failed_payment(customer: str, amount: float) -> None:
    logger.error(f"Payment processing failed customer={customer} amount={amount}")
    raise RuntimeError(f"Payment processing failed for customer={customer}")


def _reset_store() -> None:
    global _PAYMENTS, _next_id
    _PAYMENTS = [
        {
            "id": 1,
            "customer": "Alice",
            "amount": 99.50,
            "card_last_four": "4242",
            "status": "completed",
            "created_at": "2025-01-01T10:00:00Z",
        },
        {
            "id": 2,
            "customer": "Bob",
            "amount": 149.00,
            "card_last_four": "1234",
            "status": "pending",
            "created_at": "2025-01-02T11:30:00Z",
        },
        {
            "id": 3,
            "customer": "Carol",
            "amount": 250.75,
            "card_last_four": "5678",
            "status": "failed",
            "created_at": "2025-01-03T09:15:00Z",
        },
    ]
    _next_id = len(_PAYMENTS) + 1