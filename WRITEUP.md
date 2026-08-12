# Architectural Trade-offs & Production Roadmap

## Trade-offs Made (Time-Budget Constraints)

* **Single Time-Cutoff Split:** Used a fixed `2026-01-01` cutoff with an 80/20 train/validation split for speed. This risks overfitting to period-specific dynamics like seasonality. Production requires rolling-window backtesting to verify metric stability over time.
* **Basic Feature Set:** Limited inputs to five core RFM metrics (`order_count`, `total_spend`, `distinct_products`, `recency_days`, `tenure_days`) due to schema constraints. Real churn models need granular behavioral, engagement, and return data.
* **Baseline Model Complexity:** Prioritized Logistic Regression and Gradient Boosting without deep hyperparameter tuning or advanced libraries (XGBoost/LightGBM). This kept the MLflow tracking and registry architecture clear without spending time chasing leaderboard points.
* **Local Pipeline Execution:** Ran Kubeflow Pipelines (KFP) locally using `SubprocessRunner` to avoid infrastructure overhead. This skips container isolation, UI lineage tracking, and distributed scheduling native to real clusters.
* **Isolated CI Smoke Testing:** CI runs against a single local container testing the fallback path (`503` or embedded model) without an active MLflow server. Staging validation requires testing against a live MLflow registry.
* **Manual Batch Monitoring:** Implemented `monitor.py` to prove out the Population Stability Index (PSI) logic, but left it as a manual script rather than a scheduled, alerting job.
* **Direct Feature Pass-Through:** Computed features directly in SQL for training and passed raw JSON to the API for serving. This works for a small schema, but lacks the online-offline skew safeguards of a dedicated feature pipeline.

---

## Scaling Strategy for Production

1. **Rolling-Origin Evaluation:** Implement multi-cutoff backtesting and track per-window performance variance in MLflow.
2. **Feature Store Materialization:** Compute features asynchronously into materialized views or a feature store with incremental nightly refreshes rather than querying raw tables on demand.
3. **Managed Orchestration:** Deploy KFP to a managed cluster (e.g., Vertex Pipelines or Kubeflow on EKS/GKE) for container isolation, artifact tracking, retries, and scheduled execution.
4. **Cost-Aware Classification:** Handle class imbalance using class weights and adjust decision thresholds against a business cost matrix—weighing false negatives (missed at-risk customers) higher than false positives.
5. **Automated Triggering & Gates:** Automate retraining using PSI and real-time accuracy checks. Automatically run training scripts on drift detection, requiring human sign-off before promoting models from `Staging` to `Production`.
6. **Strict Schema Contracts:** Enforce shared Pydantic/JSON schemas across SQL queries, pipeline validation steps, and FastAPI endpoints to ensure breaking changes are caught at CI time.
7. **Production API Readiness:** Add load testing, request batching, autoscaling, authentication, and rate limiting to the serving layer.
