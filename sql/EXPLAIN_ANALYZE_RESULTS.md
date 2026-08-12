# Part A — SQL & Query Optimization

## 1. Naive query (correlated subqueries), no indexes 
(`01_feature_query_naive.sql`)
**Bottleneck Identification:** 
Filepath: explain_before_naive_500.txt

**Bottleneck Analysis:**The query forces Postgres into an $O(N \times M)$ access loop. For every customer row scanned, Postgres executes 4 separate SubPlan operations. Each subquery triggers a full Seq Scan on orders (500,000 rows) and a Hash Join against order_items (1,530,225 rows) with zero index support. Processing just 500 customers results in 2,000 full table scans and over 43 million buffer hits, taking over 51 seconds. And running with 5000 customers took 225.4s.
Extrapolated to the full 50,000-customer table,
the naive query would take on the order of **1.5–2 hours**.

## 2. Naive query, same shape, with indexes added (`02_indexes.sql`)

**~392x faster** than the same query without indexes (225.4 s → 0.575 s).

## 3. Optimized query — CTE/window rewrite + indexes. (`03_feature_query_optimized.sql`)

50,000 customers **2,099 ms** (~2.1 s) | [explain_optimized_full_result.txt](explain_optimized_full_result.txt) |

The rewritten query (`03_feature_query_optimized.sql`) scans `orders` and
`order_items` **once each** (via the `past_orders` CTE and a single
`Hash Join` / `GroupAggregate`), instead of once per customer. It computes
the feature table for **all 50,000 customers** in ~2.1 seconds — faster than
even the reduced 2-subquery naive query on just 5,000 customers.

## Comparision Table


| Run Configuration | Customer Sample | Execution Time | Speedup |
|---|---|---|---|
| Naive Query (No Indexes) | 500 | 51,305 ms (~51.3 s) | Baseline |
| Naive Query (No Indexes) | 5,000 | 225,353 ms (~225.4 s) | 1x |
| Naive Query (+ Indexes) | 5,000 | 575 ms | ~392x |
| Optimized Query (Rewrite + Indexes) | 50,000 (100% data) | 2,099 ms (~2.1 s) | >2,500x (extrapolated) |


## Why the fix worked (2–3 sentences)
The naive query re-executed 2 to 4 correlated subqueries per `customer`, forcing repeated sequential scans over `500,000` order records and an `O(N×M)` total execution footprint. Adding indexes converted these expensive full scans into fast microsecond B-tree lookups, yielding an immediate **~392x improvement**. Rewriting the logic into CTEs with explicit joins transformed the operation into a single-pass O(N+M) pipeline, allowing Postgres to scan each table exactly once and compute features for all 50,000 customers in 2.1 seconds.
