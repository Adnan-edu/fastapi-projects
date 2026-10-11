import asyncio

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.core.monitoring import increment_orders_created
from app.services import order_service

router = APIRouter(prefix="/api/v1/orders", tags=["orders"])


class OrderCreate(BaseModel):
    customer: str = Field(min_length=1)
    item: str = Field(min_length=1)
    quantity: int = Field(gt=0)


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_order(order: OrderCreate):
    created = order_service.create(
        customer=order.customer,
        item=order.item,
        quantity=order.quantity,
    )
    increment_orders_created(order.item)
    return created


@router.get("/", status_code=status.HTTP_200_OK)
def list_orders():
    return {"orders": order_service.get_all()}


@router.get("/slow", status_code=status.HTTP_200_OK)
async def slow_endpoint():
    await asyncio.sleep(0.5)
    return {"message": "This was a slow response", "delay_seconds": 0.5}


@router.get("/error", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
def error_endpoint():
    raise HTTPException(
        status_code=500,
        detail="Simulated internal server error",
    )


@router.get("/{order_id}", status_code=status.HTTP_200_OK)
def get_order(order_id: int):
    order = order_service.get_by_id(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order
