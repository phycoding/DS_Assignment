"""
FastAPI serving layer for the churn model registered in MLflow Model Registry.

Loads the "Production" stage of the `customer_churn_model` from the MLflow
Model Registry (falls back to a local model file for offline/dev use) and
exposes /predict and /health endpoints.
"""
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import mlflow
import mlflow.pyfunc
import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("serving")

MLFLOW_TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000")
MODEL_NAME = os.environ.get("MODEL_NAME", "customer_churn_model")
MODEL_STAGE = os.environ.get("MODEL_STAGE", "Production")
FALLBACK_MODEL_PATH = os.environ.get("FALLBACK_MODEL_PATH", "/app/model")

FEATURE_DEFAULTS = {
    "order_count": 0,
    "total_spend": 0.0,
    "distinct_products": 0,
    "recency_days": 9999,
    "tenure_days": 0,
}

app = FastAPI(title="Customer Churn Prediction API", version="1.0.0")

_model = None
_model_source = None


class ChurnFeatures(BaseModel):
    order_count: Optional[int] = Field(None, ge=0, description="Orders placed before cutoff")
    total_spend: Optional[float] = Field(None, ge=0, description="Total historical spend")
    distinct_products: Optional[int] = Field(None, ge=0, description="Distinct products purchased")
    recency_days: Optional[int] = Field(None, ge=0, description="Days since last order")
    tenure_days: Optional[int] = Field(None, ge=0, description="Days since signup")


class PredictionResponse(BaseModel):
    churn_probability: float
    churn_prediction: int
    model_source: str
    used_defaults_for: list[str]


def _load_model():
    global _model, _model_source
    try:
        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        uri = f"models:/{MODEL_NAME}/{MODEL_STAGE}"
        _model = mlflow.pyfunc.load_model(uri)
        _model_source = uri
        logger.info("Loaded model from MLflow registry: %s", uri)
    except Exception as exc:  # noqa: BLE001 - fall back gracefully
        logger.warning("Could not load model from MLflow registry (%s); trying local fallback", exc)
        if os.path.isdir(FALLBACK_MODEL_PATH):
            _model = mlflow.pyfunc.load_model(FALLBACK_MODEL_PATH)
            _model_source = f"local:{FALLBACK_MODEL_PATH}"
            logger.info("Loaded fallback model from %s", FALLBACK_MODEL_PATH)
        else:
            _model = None
            _model_source = None
            logger.error("No model available - /predict will return 503 until one is loaded")


@app.on_event("startup")
def startup_event():
    _load_model()


@app.get("/health")
def health():
    return {
        "status": "ok" if _model is not None else "degraded",
        "model_loaded": _model is not None,
        "model_source": _model_source,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/predict", response_model=PredictionResponse)
def predict(features: ChurnFeatures):
    if _model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    payload = features.model_dump()
    used_defaults = [k for k, v in payload.items() if v is None]
    for key, default in FEATURE_DEFAULTS.items():
        if payload.get(key) is None:
            payload[key] = default

    df = pd.DataFrame([payload])[list(FEATURE_DEFAULTS.keys())]

    try:
        proba = _model.predict(df)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Prediction failed")
        raise HTTPException(status_code=500, detail=f"Prediction failed: {exc}") from exc

    score = float(proba[0]) if hasattr(proba, "__getitem__") else float(proba)
    # some models output a probability, some output a 0/1 label directly
    if score > 1 or score < 0:
        score = max(0.0, min(1.0, score))

    _log_prediction(payload, score)

    return PredictionResponse(
        churn_probability=round(score, 4),
        churn_prediction=int(score >= 0.5),
        model_source=_model_source or "unknown",
        used_defaults_for=used_defaults,
    )


def _log_prediction(payload: dict, score: float) -> None:
    """Append input/output to a local log for the monitoring/drift job (Part F)."""
    log_path = os.environ.get("PREDICTION_LOG_PATH", "prediction_log.csv")
    row = {**payload, "churn_probability": score, "logged_at": datetime.now(timezone.utc).isoformat()}
    df = pd.DataFrame([row])
    write_header = not os.path.exists(log_path)
    df.to_csv(log_path, mode="a", header=write_header, index=False)
