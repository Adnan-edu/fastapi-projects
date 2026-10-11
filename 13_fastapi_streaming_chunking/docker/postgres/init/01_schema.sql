-- Same schema as 12_cursor_pagination so this app can run against either DB.
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

CREATE INDEX IF NOT EXISTS ix_order_events_created_at_id
    ON order_events (created_at, id);
CREATE INDEX IF NOT EXISTS ix_order_events_customer_id
    ON order_events (customer_id);
CREATE INDEX IF NOT EXISTS ix_order_events_status
    ON order_events (status);
