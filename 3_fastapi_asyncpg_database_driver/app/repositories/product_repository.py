from decimal import Decimal

import asyncpg

from app.core.db import get_pool


def _record_to_dict(record: asyncpg.Record) -> dict:
    return dict(record)


async def create_product(
    name: str,
    description: str,
    price: Decimal,
    stock_quantity: int,
) -> dict:
    pool = get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO products (name, description, price, stock_quantity)
        VALUES ($1, $2, $3, $4)
        RETURNING id, name, description, price, stock_quantity, created_at, updated_at
        """,
        name,
        description,
        price,
        stock_quantity,
    )
    return _record_to_dict(row)


async def get_product_by_id(product_id: int) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        """
        SELECT id, name, description, price, stock_quantity, created_at, updated_at
        FROM products
        WHERE id = $1
        """,
        product_id,
    )
    if row is None:
        return None
    return _record_to_dict(row)


async def list_products() -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        """
        SELECT id, name, description, price, stock_quantity, created_at, updated_at
        FROM products
        ORDER BY id
        """,
    )
    return [_record_to_dict(row) for row in rows]


async def update_product(
    product_id: int,
    name: str | None,
    description: str | None,
    price: Decimal | None,
    stock_quantity: int | None,
) -> dict | None:
    pool = get_pool()
    existing = await get_product_by_id(product_id)
    if existing is None:
        return None

    updated_name = name if name is not None else existing["name"]
    updated_description = description if description is not None else existing["description"]
    updated_price = price if price is not None else existing["price"]
    updated_stock = stock_quantity if stock_quantity is not None else existing["stock_quantity"]

    row = await pool.fetchrow(
        """
        UPDATE products
        SET name = $1, description = $2, price = $3, stock_quantity = $4, updated_at = NOW()
        WHERE id = $5
        RETURNING id, name, description, price, stock_quantity, created_at, updated_at
        """,
        updated_name,
        updated_description,
        updated_price,
        updated_stock,
        product_id,
    )
    if row is None:
        return None
    return _record_to_dict(row)


async def delete_product(product_id: int) -> int | None:
    pool = get_pool()
    row = await pool.fetchrow(
        """
        DELETE FROM products
        WHERE id = $1
        RETURNING id
        """,
        product_id,
    )
    if row is None:
        return None
    return row["id"]


async def bulk_update_stock(updates: list[tuple[int, int]]) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            for product_id, new_stock in updates:
                await conn.execute(
                    """
                    UPDATE products
                    SET stock_quantity = $1, updated_at = NOW()
                    WHERE id = $2
                    """,
                    new_stock,
                    product_id,
                )