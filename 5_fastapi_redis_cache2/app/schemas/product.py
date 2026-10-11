"""Product schemas — small catalogue domain for Redis learning."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    sku: str = Field(min_length=1, max_length=40)
    price: float = Field(ge=0)
    stock: int = Field(ge=0, default=0)
    category: str = Field(default="general", max_length=60)
    tags: list[str] = Field(default_factory=list)


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    price: float | None = Field(default=None, ge=0)
    stock: int | None = Field(default=None, ge=0)
    category: str | None = Field(default=None, max_length=60)
    tags: list[str] | None = None


class ProductOut(BaseModel):
    id: int
    name: str
    sku: str
    price: float
    stock: int
    category: str
    tags: list[str]
    created_at: datetime
    updated_at: datetime


class CartItemIn(BaseModel):
    product_id: int
    qty: int = Field(ge=1, le=99)


class CartOut(BaseModel):
    user_id: str
    items: dict[int, int]
    ttl_seconds: int
