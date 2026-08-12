"""
Part F - Lightweight monitoring: compares live prediction inputs (logged by
serving/app.py to prediction_log.csv) against the training feature
distribution, using Population Stability Index (PSI) per feature.

Usage:
    python monitor.py --training-csv training_features.csv --live-csv ../serving/prediction_log.csv
"""
import argparse

import numpy as np
import pandas as pd

FEATURE_COLUMNS = ["order_count", "total_spend", "distinct_products", "recency_days", "tenure_days"]


def psi(expected: pd.Series, actual: pd.Series, buckets: int = 10) -> float:
    """Population Stability Index between two 1-D distributions.

    PSI < 0.1  -> no significant shift
    0.1 - 0.25 -> moderate shift, investigate
    > 0.25     -> significant shift, retraining candidate
    """
    expected = expected.dropna()
    actual = actual.dropna()
    quantiles = np.linspace(0, 1, buckets + 1)
    breakpoints = np.unique(np.quantile(expected, quantiles))
    if len(breakpoints) < 2:
        return 0.0

    expected_counts = np.histogram(expected, bins=breakpoints)[0] / len(expected)
    actual_counts = np.histogram(actual, bins=breakpoints)[0] / max(len(actual), 1)

    expected_counts = np.clip(expected_counts, 1e-4, None)
    actual_counts = np.clip(actual_counts, 1e-4, None)

    return float(np.sum((actual_counts - expected_counts) * np.log(actual_counts / expected_counts)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--training-csv", required=True, help="CSV with the training feature distribution")
    parser.add_argument("--live-csv", required=True, help="CSV of logged live prediction inputs (prediction_log.csv)")
    args = parser.parse_args()

    train_df = pd.read_csv(args.training_csv)
    live_df = pd.read_csv(args.live_csv)

    print(f"{'feature':<20}{'psi':>10}   verdict")
    print("-" * 50)
    for col in FEATURE_COLUMNS:
        if col not in train_df.columns or col not in live_df.columns:
            continue
        score = psi(train_df[col], live_df[col])
        verdict = "OK" if score < 0.1 else ("INVESTIGATE" if score < 0.25 else "RETRAIN")
        print(f"{col:<20}{score:>10.4f}   {verdict}")


if __name__ == "__main__":
    main()
