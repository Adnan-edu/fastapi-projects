-- Initial schema for order_events. Mirrors what the ingestion script will create
-- if the table is missing. Kept here so a fresh `docker compose up` produces a
-- ready-to-query database even before ingestion runs.

CREATE TABLE IF NOT EXISTS order_events (
    id              BIGINT PRIMARY KEY,
    order_id        BIGINT       NOT NULL,
    customer_id     BIGINT       NOT NULL,
    event_type      TEXT         NOT NULL,
    status          TEXT         NOT NULL,
    amount          NUMERIC(12,2) NOT NULL,
    currency        TEXT         NOT NULL,
    country         TEXT         NOT NULL,
    payment_method  TEXT         NOT NULL,
    product_sku     TEXT         NOT NULL,
    quantity        INTEGER      NOT NULL,
    created_at      TIMESTAMP    NOT NULL,
    metadata        TEXT
);

-- Composite index that powers the (created_at, id) cursor seek.
CREATE INDEX IF NOT EXISTS ix_order_events_created_at_id
    ON order_events (created_at, id);

-- Secondary indexes used by filtered queries.
CREATE INDEX IF NOT EXISTS ix_order_events_customer_id
    ON order_events (customer_id);

CREATE INDEX IF NOT EXISTS ix_order_events_status
    ON order_events (status);
