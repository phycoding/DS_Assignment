-- ============================================================
-- Part A - Step 1: NAIVE feature/label query (deliberately slow)
--
-- Target: customer churn in the 90 days following a cutoff date.
-- cutoff := 2026-01-01, label window := (cutoff, cutoff + 90 days]
--
-- Why this is slow:
--   - 5 correlated subqueries, each executed once PER customer row
--     (50,000 executions total instead of 1 set-based scan).
--   - orders.customer_id and orders.order_date have no index.
--   - order_items has no index besides its own PK, so the join
--     inside the "distinct_products" subquery forces a seq scan
--     of ~1.5M rows for every single customer.
-- ============================================================

SELECT
    c.customer_id,
    c.signup_date,
    c.country,

    (SELECT COUNT(*)
       FROM orders o
      WHERE o.customer_id = c.customer_id
        AND o.order_date <= '2026-01-01') AS order_count,

    (SELECT MAX(o.order_date)
       FROM orders o
      WHERE o.customer_id = c.customer_id
        AND o.order_date <= '2026-01-01') AS last_order_date,

    (SELECT COALESCE(SUM(o.order_total), 0)
       FROM orders o
      WHERE o.customer_id = c.customer_id
        AND o.order_date <= '2026-01-01') AS total_spend,

    (SELECT COUNT(DISTINCT oi.product_id)
       FROM order_items oi
       JOIN orders o2 ON oi.order_id = o2.order_id
      WHERE o2.customer_id = c.customer_id
        AND o2.order_date <= '2026-01-01') AS distinct_products,

    (SELECT COUNT(*)
       FROM orders o3
      WHERE o3.customer_id = c.customer_id
        AND o3.order_date > '2026-01-01'
        AND o3.order_date <= DATE '2026-01-01' + INTERVAL '90 days'
        AND o3.status = 'completed') AS orders_next_90d

FROM customers c;
