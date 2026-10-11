"""ORM model for the `order_events` table.

Schema is intentionally identical to `13_fastapi_streaming`'s OrderEvent so
both apps can point at the same database — no separate ingest, no
migration. If you change a column here, change it there too (or factor the
model into a shared library).

Why SQLAlchemy 2.0 DeclarativeBase + Mapped[]?
----------------------------------------------
SQLAlchemy 2.0 introduced typed declarative mapping using PEP 484 types.
`Mapped[int]` tells both Python's type checker and SQLAlchemy's metadata
that the attribute is a non-null int column. The result:
- IDE autocomplete on `OrderEvent.amount` knows it's a Decimal.
- A typo like `OrderEvent.contry` is caught by mypy/pyright at edit time.
- The same source declares the runtime ORM mapping AND the static type — no
  drift possible between them.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Index, Integer, Numeric, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Shared declarative base. All ORM models in this app inherit from it
    so they share one MetaData / table registry.
    """

    pass


class OrderEvent(Base):
    """A single event in an order's lifecycle.

    The table has multiple rows per order (placed → paid → packed →
    shipped), each with its own `event_type`/`status`. The pipeline doesn't
    care about that structure — it just streams rows in id order — but the
    `status` filter in the demo endpoint is a faithful real-world use case
    ("export everything in the `paid` state").
    """

    __tablename__ = "order_events"

    # BigInteger because the dataset is ~1M rows in dev and could be much
    # larger in prod. id is the keyset cursor; it's monotonic and indexed
    # as the primary key, which is exactly what `WHERE id > :last_id` needs.
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    order_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    customer_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    # Numeric(12, 2) preserves exact decimal arithmetic — critical for money
    # amounts. `Mapped[Decimal]` ensures Python sees Decimal objects on the
    # way out, not floats.
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(Text, nullable=False)
    country: Mapped[str] = mapped_column(Text, nullable=False)
    payment_method: Mapped[str] = mapped_column(Text, nullable=False)
    product_sku: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    # The column is named `metadata` in the DB, but `metadata` is a
    # reserved attribute on DeclarativeBase (it's the schema metadata
    # object). We use a Python-side underscore suffix and the explicit
    # column name override `"metadata"` so the DB schema stays intact.
    metadata_: Mapped[str | None] = mapped_column("metadata", Text, nullable=True)

    # Indexes mirror what the seed script created. We don't actually
    # *create* indexes here (the DB already has them); declaring them in
    # __table_args__ keeps the model in sync with the live schema, so
    # `Base.metadata.create_all(...)` from a fresh DB would produce the
    # same indexes.
    __table_args__ = (
        # Composite index on (created_at, id) — supports range queries by
        # time with id as a stable tiebreaker.
        Index("ix_order_events_created_at_id", "created_at", "id"),
        # Single-column indexes for the most common filters.
        Index("ix_order_events_customer_id", "customer_id"),
        Index("ix_order_events_status", "status"),
    )
