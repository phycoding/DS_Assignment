"""Unit tests for the feature-engineering / validation logic (Part C, Part E)."""
import os
import sys

import pandas as pd
import pytest

from pipeline import transform_logic, validate_logic  


def test_transform_fills_missing_values():
    df = pd.DataFrame({
        "customer_id": [1, 2, 3],
        "order_count": [2, None, 0],
        "total_spend": [100.0, None, 0.0],
        "distinct_products": [3, None, 0],
        "recency_days": [10, None, 9999],
        "tenure_days": [365, 100, None],
        "churned": [0, 1, None],
    })

    out = transform_logic(df)

    assert out.isna().sum().sum() == 0
    assert out["recency_days"].max() <= 730
    assert set(out["churned"].unique()).issubset({0, 1})


def test_transform_preserves_row_count():
    df = pd.DataFrame({
        "customer_id": range(1, 21),
        "order_count": [1] * 20,
        "total_spend": [50.0] * 20,
        "distinct_products": [2] * 20,
        "recency_days": [30] * 20,
        "tenure_days": [400] * 20,
        "churned": [0] * 20,
    })

    out = transform_logic(df)
    assert len(out) == 20


def test_validate_logic_passes_on_clean_data():
    df = transform_logic(pd.DataFrame({
        "customer_id": [1, 2],
        "order_count": [1, 2],
        "total_spend": [10.0, 20.0],
        "distinct_products": [1, 2],
        "recency_days": [5, 15],
        "tenure_days": [100, 200],
        "churned": [0, 1],
    }))
    validate_logic(df)  # should not raise


def test_validate_logic_rejects_duplicate_customer_id():
    df = pd.DataFrame({
        "customer_id": [1, 1],
        "order_count": [1, 2],
        "total_spend": [10.0, 20.0],
        "distinct_products": [1, 2],
        "recency_days": [5, 15],
        "tenure_days": [100, 200],
        "churned": [0, 1],
    })
    with pytest.raises(AssertionError):
        validate_logic(df)


def test_validate_logic_rejects_negative_spend():
    df = pd.DataFrame({
        "customer_id": [1, 2],
        "order_count": [1, 2],
        "total_spend": [-10.0, 20.0],
        "distinct_products": [1, 2],
        "recency_days": [5, 15],
        "tenure_days": [100, 200],
        "churned": [0, 1],
    })
    with pytest.raises(AssertionError):
        validate_logic(df)
