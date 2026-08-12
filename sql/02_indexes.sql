-- ============================================================
-- Part A - Step 3: Indexes added to fix the naive query's plan.
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_orders_customer_id ON orders (customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_order_date ON orders (order_date);
CREATE INDEX IF NOT EXISTS idx_orders_customer_date ON orders (customer_id, order_date);
CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items (order_id);
CREATE INDEX IF NOT EXISTS idx_order_items_product_id ON order_items (product_id);

ANALYZE orders;
ANALYZE order_items;
ANALYZE customers;
