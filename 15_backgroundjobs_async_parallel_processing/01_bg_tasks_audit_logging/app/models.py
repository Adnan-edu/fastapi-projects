"""ORM mapping for the shared `order_events` table.

The DB column `metadata` is exposed as `metadata_` on the model because
SQLAlchemy's DeclarativeBase reserves the `metadata` attribute name.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, Integer, Numeric, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class OrderEvent(Base):
    __tablename__ = "order_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    order_id: Mapped[int] = mapped_column(BigInteger)
    customer_id: Mapped[int] = mapped_column(BigInteger)
    event_type: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String)
    country: Mapped[str] = mapped_column(String)
    payment_method: Mapped[str] = mapped_column(String)
    product_sku: Mapped[str] = mapped_column(String)
    quantity: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    metadata_: Mapped[str | None] = mapped_column("metadata", String, nullable=True)
