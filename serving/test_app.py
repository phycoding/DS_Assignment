"""Unit + smoke tests for the FastAPI serving layer."""
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("MLFLOW_TRACKING_URI", "http://localhost:5000")

from serving.app import app  # noqa: E402

client = TestClient(app)


def test_health_endpoint_returns_200():
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert "status" in body
    assert "model_loaded" in body


def test_predict_missing_model_returns_503_or_ok():
    resp = client.post("/predict", json={"order_count": 5, "total_spend": 120.5})
    # If no model is loaded in CI (no MLflow server / no fallback dir), we
    # expect a clean 503 rather than a crash.
    assert resp.status_code in (200, 503)
    if resp.status_code == 200:
        body = resp.json()
        assert 0.0 <= body["churn_probability"] <= 1.0
        assert body["churn_prediction"] in (0, 1)


def test_predict_validates_input_types():
    resp = client.post("/predict", json={"order_count": -5})
    assert resp.status_code == 422
