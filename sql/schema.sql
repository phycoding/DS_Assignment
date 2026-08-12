-- ============================================================
-- Synthetic E-commerce Schema
-- Deliberately realistic: some missing indexes, some nullable
-- columns that shouldn't be null, a couple of dirty edge cases.
-- Candidates are expected to find and fix the performance issues
-- themselves as part of Part A of the assignment.
-- ============================================================

DROP TABLE IF EXISTS order_items CASCADE;
DROP TABLE IF EXISTS orders CASCADE;
DROP TABLE IF EXISTS products CASCADE;
DROP TABLE IF EXISTS customers CASCADE;

CREATE TABLE customers (
    customer_id     BIGINT PRIMARY KEY,
    first_name      TEXT,
    last_name       TEXT,
    email           TEXT,                 -- NOTE: not unique on purpose (some dupes exist)
    signup_date     DATE,
    country         TEXT,
    marketing_opt_in BOOLEAN
);

CREATE TABLE products (
    product_id      BIGINT PRIMARY KEY,
    product_name    TEXT,
    category        TEXT,                 -- some NULL categories on purpose
    unit_price      NUMERIC(10,2),
    active          BOOLEAN DEFAULT TRUE
);

CREATE TABLE orders (
    order_id        BIGINT PRIMARY KEY,
    customer_id     BIGINT REFERENCES customers(customer_id),
    order_date      TIMESTAMP,            -- small % NULL on purpose (data quality issue)
    status          TEXT,                 -- 'completed','cancelled','returned','pending'
    order_total     NUMERIC(12,2)
);

CREATE TABLE order_items (
    order_item_id   BIGINT PRIMARY KEY,
    order_id        BIGINT REFERENCES orders(order_id),
    product_id      BIGINT REFERENCES products(product_id),
    quantity        INT,
    unit_price      NUMERIC(10,2)
);

-- ------------------------------------------------------------
-- Intentional index gaps (this is the point of the exercise):
--   - No index on orders.customer_id
--   - No index on order_items.order_id
--   - No index on orders.order_date
-- A candidate doing the feature-engineering join/aggregation
-- query in Part A should discover these via EXPLAIN ANALYZE.
--
-- We DO index primary keys (Postgres does this automatically)
-- and leave one "trap" composite scenario: order_items has no
-- index at all beyond its own PK, forcing a sequential scan on
-- any join back to orders or products.
-- ------------------------------------------------------------

-- Helpful for the loader / sanity checks only, not the exercise itself:
CREATE INDEX idx_customers_country ON customers(country);
