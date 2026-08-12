-- EXPLAIN ANALYZE wrapper for the naive query, but on the FULL customer set,
-- run against the optimized schema (i.e. with indexes already applied) so we
-- can isolate the effect of the query rewrite from the effect of indexing.
-- WARNING: even with indexes, the correlated-subquery shape means this is
-- still O(customers) planner-time round-trips; only run this if you have a
-- few minutes to spare.
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    c.customer_id,
    (SELECT COUNT(*) FROM orders o WHERE o.customer_id = c.customer_id AND o.order_date <= '2026-01-01') AS order_count,
    (SELECT COUNT(DISTINCT oi.product_id)
       FROM order_items oi JOIN orders o2 ON oi.order_id = o2.order_id
      WHERE o2.customer_id = c.customer_id AND o2.order_date <= '2026-01-01') AS distinct_products
FROM customers c
WHERE c.customer_id <= 5000;
