-- EXPLAIN ANALYZE wrapper for the optimized query (full 50,000 customers).
EXPLAIN (ANALYZE, BUFFERS)
WITH cutoff AS (
    SELECT DATE '2026-01-01' AS d
),
past_orders AS (
    SELECT o.customer_id,
           o.order_id,
           o.order_date,
           o.order_total
      FROM orders o, cutoff
     WHERE o.order_date <= cutoff.d
),
past_agg AS (
    SELECT customer_id,
           COUNT(*)                    AS order_count,
           MAX(order_date)             AS last_order_date,
           COALESCE(SUM(order_total),0) AS total_spend
      FROM past_orders
     GROUP BY customer_id
),
past_products AS (
    SELECT po.customer_id, COUNT(DISTINCT oi.product_id) AS distinct_products
      FROM past_orders po
      JOIN order_items oi ON oi.order_id = po.order_id
     GROUP BY po.customer_id
),
future_orders AS (
    SELECT o.customer_id, COUNT(*) AS orders_next_90d
      FROM orders o, cutoff
     WHERE o.order_date > cutoff.d
       AND o.order_date <= cutoff.d + INTERVAL '90 days'
       AND o.status = 'completed'
     GROUP BY o.customer_id
)
SELECT
    c.customer_id,
    c.signup_date,
    c.country,
    COALESCE(pa.order_count, 0)        AS order_count,
    pa.last_order_date,
    COALESCE(pa.total_spend, 0)        AS total_spend,
    COALESCE(pp.distinct_products, 0)  AS distinct_products,
    COALESCE(fo.orders_next_90d, 0)    AS orders_next_90d
FROM customers c
LEFT JOIN past_agg pa ON pa.customer_id = c.customer_id
LEFT JOIN past_products pp ON pp.customer_id = c.customer_id
LEFT JOIN future_orders fo ON fo.customer_id = c.customer_id;
