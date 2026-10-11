from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class ProductCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    price: Decimal = Field(..., gt=0)
    stock_quantity: int = Field(default=0, ge=0)


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    price: Decimal | None = Field(default=None, gt=0)
    stock_quantity: int | None = Field(default=None, ge=0)


class ProductResponse(BaseModel):
    id: int
    name: str
    description: str
    price: Decimal
    stock_quantity: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProductListResponse(BaseModel):
    products: list[ProductResponse]
    count: int


class StockUpdateItem(BaseModel):
    product_id: int = Field(..., gt=0)
    stock_quantity: int = Field(..., ge=0)


class BulkStockUpdate(BaseModel):
    items: list[StockUpdateItem]