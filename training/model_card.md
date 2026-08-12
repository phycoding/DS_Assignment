# Model Card — Customer Churn Prediction

## Overview
Predicts whether a customer will place **zero completed orders in the 90 days
following a fixed cutoff date** (`2026-01-01`), using only information known
as of the cutoff. This approximates a "will this customer churn next
quarter" business question.

## Training Data
- Source: `sql/03_feature_query_optimized.sql` against the `ecommerce`
  Postgres database (50,000 customers, 500,000 orders, ~1.53M order_items).
- One row per customer; label `churned` = 1 if the customer has 0 completed
  orders in `(cutoff, cutoff + 90 days]`, else 0.
- Split: 80/20 train/test, stratified by label, `random_state=42`.

## Features
| Feature | Description |
|---|---|
| `order_count` | Number of orders placed on/before cutoff |
| `total_spend` | Sum of `order_total` on/before cutoff |
| `distinct_products` | Distinct products purchased on/before cutoff |
| `recency_days` | Days between cutoff and the customer's last order (capped at 730; 730 used as sentinel for customers with no prior orders) |
| `tenure_days` | Days between cutoff and signup date |

## Models
- **Baseline:** `LogisticRegression` (scaled features), `C=1.0`.
- **Improved:** `GradientBoostingClassifier`, `n_estimators=200`,
  `max_depth=3`, `learning_rate=0.1`.
- Both tracked in MLflow (experiment `customer_churn`); the run with the
  higher ROC AUC is registered as `customer_churn_model` and promoted
  `Staging -> Production`.

## Validation Strategy
Single stratified hold-out split (80/20). Metrics: accuracy, precision,
recall, F1, ROC AUC — logged as MLflow metrics, plus an ROC curve artifact
per run.

## Known Limitations
- Single time-based cutoff, not rolling/backtested across multiple periods —
  real deployment should validate across several historical cutoffs to
  avoid overfitting to one calendar window.
- No customer-level features beyond order history (no marketing
  engagement, no return/refund rate, no browsing/session data).
- Class imbalance is not explicitly rebalanced (e.g. no class weights or
  SMOTE) — acceptable for a take-home baseline, worth revisiting in
  production.
- `recency_days` sentinel (730) for customers with no historical orders is a
  simplification; a missing-indicator feature would be more principled.
- Churn label for customers with 0 pre-cutoff orders is trivially 1 (no
  future orders is guaranteed); in production these "not-yet-active"
  customers might be filtered out of the training set or modeled
  separately.
