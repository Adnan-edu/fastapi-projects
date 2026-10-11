-- Migration: 001_create_products_table
-- Description: Create the products table with indexes for the Product Inventory API

BEGIN;

-- Main products table
-- This table stores product information with raw SQL instead of an ORM model.
-- Compare this to a Tortoise ORM Model or SQLModel class:
--   ORM: class Product(Model): name = fields.CharFieldField(max_length=200)
--   SQL: name VARCHAR(200) NOT NULL
-- Raw SQL gives you full control over column types, constraints, and indexes.
CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    price NUMERIC(10, 2) NOT NULL,
    stock_quantity INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index on product name for fast lookups and searches
-- Without this index, WHERE name = 'Widget' scans every row (sequential scan).
-- With this index, PostgreSQL uses a B-tree to find the row in O(log n) instead.
CREATE INDEX IF NOT EXISTS idx_products_name ON products (name);

-- Index on created_at for sorting products by date
-- Common query: SELECT * FROM products ORDER BY created_at DESC LIMIT 20
-- This index lets PostgreSQL read rows in date order without a full table sort.
CREATE INDEX IF NOT EXISTS idx_products_created_at ON products (created_at);

COMMIT;