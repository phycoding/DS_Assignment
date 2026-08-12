# Customer Churn — End-to-End ML System

Predicts whether a customer will place **zero completed orders in the 90
days following a fixed cutoff date**, 

**Dataset Used:** synthetic e-commerce
Postgres database (50k customers / 500k orders / 1.53M order_items).

## Architecture

```mermaid
flowchart LR
    subgraph DB["Postgres (Docker)"]
        C[(customers)] --- O[(orders)] --- OI[(order_items)]
    end

    subgraph SQL["Part A — sql/"]
        Q1[01_feature_query_naive.sql]
        Q2[02_indexes.sql]
        Q3[03_feature_query_optimized.sql]
    end

    subgraph KFP["Part C — pipeline/ (KFP)"]
        E[extract] --> T[transform] --> V[validate]
    end

    subgraph Train["Part B — training/"]
        TR[train.py] --> MLF[(MLflow Tracking + Model Registry)]
    end

    subgraph Serve["Part D — serving/"]
        API[FastAPI /predict /health] 
    end

    subgraph Mon["Part F — monitoring/"]
        M[monitor.py: PSI drift]
    end

    DB --> Q1 & Q3
    Q3 --> E
    V --> TR
    MLF -- Production stage --> API
    API -- prediction_log.csv --> M
    M -. triggers .-> TR
```

## Prerequisites

- Docker Desktop
- Python 3.11
- `pip install -r requirements.txt`

## Setup

1. Start Postgres (already configured in `docker-compose.yml`):
   ```
   docker-compose up -d
   ```
2. Load schema + data (see [SETUP INSTRUCTIONS.txt](SETUP%20INSTRUCTIONS.txt) for the exact `COPY` commands). Data is already generated in `data/`.

## Part A — SQL & Query Optimization

- [sql/01_feature_query_naive.sql](sql/01_feature_query_naive.sql) — 5 correlated subqueries per customer row (deliberately slow).
- [sql/02_indexes.sql](sql/02_indexes.sql) — indexes on `orders(customer_id, order_date)`, `order_items(order_id, product_id)`.
- [sql/03_feature_query_optimized.sql](sql/03_feature_query_optimized.sql) — CTE + `GROUP BY` rewrite, one pass per table.
- Results: [sql/EXPLAIN_ANALYZE_RESULTS.md](sql/EXPLAIN_ANALYZE_RESULTS.md) — **51.3s (500 rows, no index) → 0.57s (5k rows, indexed) → 2.1s (all 50k rows, rewritten query)**.

Run it yourself:
```powershell
Get-Content sql\explain_naive_sample.sql -Raw | docker exec -i ds_interview_postgres psql -U ds_candidate -d ecommerce
Get-Content sql\02_indexes.sql -Raw | docker exec -i ds_interview_postgres psql -U ds_candidate -d ecommerce
Get-Content sql\explain_optimized_full.sql -Raw | docker exec -i ds_interview_postgres psql -U ds_candidate -d ecommerce
```

## Part B — Model Development (MLflow)

Start a local MLflow tracking server, then train:
```powershell
mlflow server --backend-store-uri sqlite:///mlflow.db --default-artifact-root ./mlruns --host 0.0.0.0 --port 5000
python training/train.py --db-url postgresql://ds_candidate:ds_candidate_pw@localhost:5432/ecommerce --tracking-uri http://localhost:5000
```
This logs a baseline (`LogisticRegression`) and an improved model
(`GradientBoostingClassifier`) run to MLflow, registers the better one as
`customer_churn_model`, and promotes it `Staging -> Production`. Open
http://localhost:5000 to see runs/metrics/artifacts and the registry.
See [training/model_card.md](training/model_card.md) for features, validation
strategy, and known limitations.

## Part C — Data Preparation Pipeline (KFP)

```powershell
python pipeline/pipeline.py --run-local --cutoff-date 2026-01-01
python -m pytest pipeline/test_transform.py -v
```
3 components: `extract` (runs Part A's optimized SQL) -> `transform`
(cleaning/feature engineering) -> `validate` (schema + data-quality
assertions). Parameterized by `cutoff_date`; produces a versioned CSV
`Dataset` artifact consumed by training.

## Part D — Model Deployment

```powershell
docker build -t churn-api ./serving
docker run -p 8000:8000 -e MLFLOW_TRACKING_URI=http://host.docker.internal:5000 churn-api
curl http://localhost:8000/health
curl -X POST http://localhost:8000/predict -H "Content-Type: application/json" -d "{\"order_count\":5,\"total_spend\":250.0,\"distinct_products\":3,\"recency_days\":40,\"tenure_days\":300}"
```
`/health` reports model-load status; `/predict` validates input via Pydantic
(negative values rejected with 422) and falls back to defaults for any
missing feature (see `used_defaults_for` in the response). If the MLflow
registry is unreachable, the app falls back to a local model dir (`serving/model/`).

## Part E — CI/CD

See [.github/workflows/ci.yml](.github/workflows/ci.yml): on push/PR it lints
(`ruff`), runs unit tests for `pipeline/` and `serving/`, builds the Docker
image, and runs a smoke test (`/health` + `/predict`) against the running
container.

## Part F — Monitoring

```powershell
python monitoring/monitor.py --training-csv training_features.csv --live-csv serving/prediction_log.csv
```
Computes Population Stability Index (PSI) per feature between the training
distribution and live prediction inputs logged by the API
(`serving/prediction_log.csv`). PSI > 0.25 on a feature is treated as a
retraining trigger.

**Retraining trigger (discussion):** in production this PSI job would run on
a schedule (e.g. daily via a cron/Airflow job or a scheduled KFP run) against
a rolling window of `prediction_log.csv`; if PSI crosses 0.25 for a key
feature, or if a labeled-outcome batch job shows realized accuracy/AUC
dropping below a threshold, it opens a ticket / triggers `train.py` to run
and register a new candidate in `Staging` for manual review before promoting
to `Production`.

## Write-up

See [WRITEUP.md](WRITEUP.md) for trade-offs made under the time constraint
and what would change at real production scale.
