-- EXPLAIN ANALYZE wrapper for the naive query, restricted to a sample of
-- 5,000 customers (out of 50,000) so the demo finishes in a reasonable time.
-- The full unrestricted run is proportionally slower (see EXPLAIN_ANALYZE_RESULTS.md).
EXPLAIN (ANALYZE, BUFFERS)
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

FROM customers c
WHERE c.customer_id <= 500;
