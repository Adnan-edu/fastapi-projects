# =====================================================================
# app/models/user.py - SQLAlchemy ORM model for the `users` table
# =====================================================================
# PURPOSE
# -------
# Represents the application's user account. Users are referenced by
# Payment.user_id and Report.user_id via foreign keys, so this is the
# "parent" entity in the relational model.
# =====================================================================

# stdlib imports we use for ID generation and timestamps.
import enum
import uuid
from datetime import datetime, timezone

# SQLAlchemy column types and constraints we need on this model.
from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text
# `Mapped` + `mapped_column` are the SQLAlchemy 2.0 typed mapping API.
# `relationship` defines ORM-level associations (joins) between tables.
from sqlalchemy.orm import Mapped, mapped_column, relationship

# Inherit from the same Base used by every other model so they share
# metadata and create_all() can find every table.
from app.database import Base


class User(Base):
    # Physical table name in the database.
    __tablename__ = "users"

    # Surrogate primary key. autoincrement=True lets the DB assign ids.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Email. `unique=True` guarantees no duplicates; `index=True` adds
    # a B-tree index to speed up `WHERE email = ...` lookups.
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    # Username. Also unique + indexed for fast login lookups.
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    # Display name.
    full_name: Mapped[str] = mapped_column(String(255))
    # Soft-delete / disable flag. New users default to active.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Creation timestamp. The lambda is evaluated at INSERT time so each
    # row gets the moment-of-creation rather than the moment-of-import.
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    # --- ORM RELATIONSHIPS (NOT real columns) -------------------------
    # `relationship(...)` creates a Python-side attribute that, when
    # accessed, runs a SELECT to fetch related rows. `back_populates`
    # ties it to the reverse side defined on Payment/Report.
    payments: Mapped[list["Payment"]] = relationship(back_populates="user")
    reports: Mapped[list["Report"]] = relationship(back_populates="user")
