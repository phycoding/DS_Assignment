"""
Part B - Model training with MLflow tracking + Model Registry.

Pulls the feature table produced by sql/03_feature_query_optimized.sql,
trains a baseline (LogisticRegression) and an improved model
(GradientBoostingClassifier), logs params/metrics/artifacts to MLflow,
and registers the better-performing model, transitioning it
Staging -> Production.

Usage:
    python train.py --db-url postgresql://ds_candidate:ds_candidate_pw@localhost:5432/ecommerce
"""
import argparse
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mlflow
import mlflow.sklearn
import pandas as pd
from mlflow.tracking import MlflowClient
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    RocCurveDisplay,
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sqlalchemy import create_engine, text

FEATURE_COLUMNS = ["order_count", "total_spend", "distinct_products", "recency_days", "tenure_days"]
LABEL_COLUMN = "churned"
MODEL_NAME = "customer_churn_model"

FEATURE_SQL_PATH = os.path.join(os.path.dirname(__file__), "..", "sql", "03_feature_query_optimized.sql")


def load_feature_table(db_url: str) -> pd.DataFrame:
    engine = create_engine(db_url)
    with open(FEATURE_SQL_PATH, "r", encoding="utf-8") as f:
        sql = f.read()
    with engine.connect() as conn:
        df = pd.read_sql(text(sql), conn)
    return df


def prepare_dataset(df: pd.DataFrame):
    df = df.copy()
    # Recency is undefined (NULL/9999 sentinel) for customers with no prior
    # orders; cap it so it doesn't dominate the model as an extreme outlier.
    df["recency_days"] = df["recency_days"].clip(upper=730)
    df = df.dropna(subset=FEATURE_COLUMNS + [LABEL_COLUMN])

    X = df[FEATURE_COLUMNS]
    y = df[LABEL_COLUMN]
    return train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)


def evaluate(model, X_test, y_test):
    preds = model.predict(X_test)
    proba = model.predict_proba(X_test)[:, 1]
    return {
        "accuracy": accuracy_score(y_test, preds),
        "precision": precision_score(y_test, preds, zero_division=0),
        "recall": recall_score(y_test, preds, zero_division=0),
        "f1": f1_score(y_test, preds, zero_division=0),
        "roc_auc": roc_auc_score(y_test, proba),
    }


def log_roc_curve(model, X_test, y_test, artifact_name: str):
    fig, ax = plt.subplots()
    RocCurveDisplay.from_estimator(model, X_test, y_test, ax=ax)
    path = f"{artifact_name}.png"
    fig.savefig(path)
    plt.close(fig)
    mlflow.log_artifact(path)
    os.remove(path)


def train_and_log(name, estimator, params, X_train, X_test, y_train, y_test):
    with mlflow.start_run(run_name=name) as run:
        pipeline = Pipeline([("scaler", StandardScaler()), ("clf", estimator)])
        pipeline.fit(X_train, y_train)
        metrics = evaluate(pipeline, X_test, y_test)

        mlflow.log_params(params)
        mlflow.log_param("model_type", name)
        mlflow.log_params({"n_features": len(FEATURE_COLUMNS)})
        mlflow.log_metrics(metrics)
        log_roc_curve(pipeline, X_test, y_test, f"roc_{name}")

        mlflow.sklearn.log_model(pipeline, artifact_path="model")
        print(f"[{name}] run_id={run.info.run_id} metrics={metrics}")
        return run.info.run_id, metrics


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--db-url",
        default=os.environ.get("DB_URL", "postgresql://ds_candidate:ds_candidate_pw@localhost:5432/ecommerce"),
    )
    parser.add_argument("--tracking-uri", default=os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000"))
    parser.add_argument("--experiment", default="customer_churn")
    args = parser.parse_args()

    mlflow.set_tracking_uri(args.tracking_uri)
    mlflow.set_experiment(args.experiment)

    print("Loading feature table from Postgres...")
    df = load_feature_table(args.db_url)
    print(f"Loaded {len(df):,} rows, churn rate={df[LABEL_COLUMN].mean():.3f}")

    X_train, X_test, y_train, y_test = prepare_dataset(df)

    baseline_params = {"C": 1.0, "max_iter": 1000}
    baseline_run_id, baseline_metrics = train_and_log(
        "baseline_logreg",
        LogisticRegression(C=baseline_params["C"], max_iter=baseline_params["max_iter"]),
        baseline_params,
        X_train, X_test, y_train, y_test,
    )

    improved_params = {"n_estimators": 200, "max_depth": 3, "learning_rate": 0.1}
    improved_run_id, improved_metrics = train_and_log(
        "gradient_boosting",
        GradientBoostingClassifier(
            n_estimators=improved_params["n_estimators"],
            max_depth=improved_params["max_depth"],
            learning_rate=improved_params["learning_rate"],
            random_state=42,
        ),
        improved_params,
        X_train, X_test, y_train, y_test,
    )

    # Pick the best run by ROC AUC and register it
    best_run_id, best_metrics, best_name = (
        (improved_run_id, improved_metrics, "gradient_boosting")
        if improved_metrics["roc_auc"] >= baseline_metrics["roc_auc"]
        else (baseline_run_id, baseline_metrics, "baseline_logreg")
    )
    print(f"Best model: {best_name} (roc_auc={best_metrics['roc_auc']:.4f})")

    client = MlflowClient()
    model_uri = f"runs:/{best_run_id}/model"
    mv = mlflow.register_model(model_uri, MODEL_NAME)

    client.transition_model_version_stage(
        name=MODEL_NAME, version=mv.version, stage="Staging", archive_existing_versions=False,
    )
    client.transition_model_version_stage(
        name=MODEL_NAME, version=mv.version, stage="Production", archive_existing_versions=True,
    )
    print(f"Registered {MODEL_NAME} v{mv.version} and promoted to Production")


if __name__ == "__main__":
    main()
