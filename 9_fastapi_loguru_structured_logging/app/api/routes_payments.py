from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from loguru import logger

from app.services import payment_service

router = APIRouter(prefix="/api/v1/payments", tags=["payments"])


class PaymentCreate(BaseModel):
    customer: str = Field(min_length=1)
    amount: float = Field(gt=0)
    card_number: str = Field(min_length=4)


class PaymentResponse(BaseModel):
    id: int
    customer: str
    amount: float
    card_last_four: str
    status: str
    created_at: str


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=PaymentResponse)
def create_payment(payment: PaymentCreate):
    created = payment_service.create(
        customer=payment.customer,
        amount=payment.amount,
        card_number=payment.card_number,
    )
    return created


@router.get("/", status_code=status.HTTP_200_OK)
def list_payments():
    return {"payments": payment_service.get_all()}


@router.get("/{payment_id}", status_code=status.HTTP_200_OK, response_model=PaymentResponse)
def get_payment(payment_id: int):
    payment = payment_service.get_by_id(payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    return payment


@router.post("/failed", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
def failed_payment():
    try:
        payment_service.simulate_failed_payment(customer="TestUser", amount=999.00)
    except RuntimeError as exc:
        logger.exception(f"Simulated payment failure: {exc}")
        raise HTTPException(status_code=500, detail="Payment processing failed")