"""
Part C - Kubeflow Pipeline (KFP SDK v2), runnable locally without a cluster.

Three components:
  1. extract      - runs the Part A optimized SQL against Postgres
  2. transform     - feature engineering / cleaning on the extracted data
  3. validate      - schema + data-quality checks (Great-Expectations-style
                     assertions) before the dataset is handed to training

Pipeline is parameterized by `cutoff_date` and produces a versioned CSV
dataset artifact consumed by training/train.py.

Run locally (no cluster required) with the KFP local runner (Linux/CI/WSL):
    python pipeline.py --run-local

On native Windows, KFP's subprocess runner requires a POSIX shell and mangles
Windows paths, so use the direct in-process fallback instead:
    python pipeline.py --run-local-direct

Or compile to a YAML spec for a real KFP/Vertex/minikube backend:
    python pipeline.py --compile pipeline.yaml
"""
import argparse
import os

from kfp import dsl, local
from kfp.dsl import Dataset, Input, Output


def transform_logic(df):
    """Pure feature-engineering logic, kept outside the KFP component so it
    can be unit tested (see test_transform.py) without a KFP runtime."""
    df = df.copy()
    # Cap recency sentinel / fill missing values (mirrors training/train.py)
    df["recency_days"] = df["recency_days"].fillna(9999).clip(upper=730)
    df["total_spend"] = df["total_spend"].fillna(0)
    df["distinct_products"] = df["distinct_products"].fillna(0).astype(int)
    df["order_count"] = df["order_count"].fillna(0).astype(int)
    df["tenure_days"] = df["tenure_days"].fillna(0).astype(int)
    df["churned"] = df["churned"].fillna(0).astype(int)
    return df


def validate_logic(df):
    """Pure schema/data-quality assertions, unit tested separately from KFP."""
    required_columns = {
        "customer_id", "order_count", "total_spend", "distinct_products",
        "recency_days", "tenure_days", "churned",
    }
    missing = required_columns - set(df.columns)
    assert not missing, f"Missing required columns: {missing}"

    assert df["customer_id"].is_unique, "customer_id must be unique per row"
    assert df["order_count"].ge(0).all(), "order_count must be >= 0"
    assert df["total_spend"].ge(0).all(), "total_spend must be >= 0"
    assert df["churned"].isin([0, 1]).all(), "churned must be binary"
    assert len(df) > 0, "dataset must not be empty"

    null_fraction = df[list(required_columns)].isna().mean().max()
    assert null_fraction < 0.01, f"Unexpectedly high null fraction: {null_fraction:.3f}"

    print(f"Validation passed: {len(df):,} rows, churn_rate={df['churned'].mean():.3f}")


@dsl.component(base_image="python:3.11-slim", packages_to_install=["pandas", "sqlalchemy", "psycopg2-binary"])
def extract(db_url: str, cutoff_date: str, feature_sql: str, raw_data: Output[Dataset]):
    import pandas as pd
    from sqlalchemy import create_engine, text

    sql = feature_sql.replace("2026-01-01", cutoff_date)
    engine = create_engine(db_url)
    with engine.connect() as conn:
        df = pd.read_sql(text(sql), conn)
    df.to_csv(raw_data.path, index=False)
    print(f"Extracted {len(df):,} rows for cutoff={cutoff_date}")


@dsl.component(base_image="python:3.11-slim", packages_to_install=["pandas"])
def transform(raw_data: Input[Dataset], features: Output[Dataset]):
    import pandas as pd

    df = pd.read_csv(raw_data.path)
    df = transform_logic(df)
    df.to_csv(features.path, index=False)
    print(f"Transformed {len(df):,} rows")


@dsl.component(base_image="python:3.11-slim", packages_to_install=["pandas"])
def validate(features: Input[Dataset], validated: Output[Dataset]):
    import pandas as pd

    df = pd.read_csv(features.path)
    validate_logic(df)
    df.to_csv(validated.path, index=False)

    df.to_csv(validated.path, index=False)


@dsl.pipeline(name="churn-feature-pipeline", description="Extract -> transform -> validate churn features")
def churn_feature_pipeline(
    db_url: str = "postgresql://ds_candidate:ds_candidate_pw@localhost:5432/ecommerce",
    cutoff_date: str = "2026-01-01",
    feature_sql: str = "",
):
    extract_task = extract(db_url=db_url, cutoff_date=cutoff_date, feature_sql=feature_sql)
    transform_task = transform(raw_data=extract_task.outputs["raw_data"])
    validate(features=transform_task.outputs["features"])


def _read_feature_sql() -> str:
    sql_path = os.path.join(os.path.dirname(__file__), "..", "sql", "03_feature_query_optimized.sql")
    with open(sql_path, "r", encoding="utf-8") as f:
        return f.read()


def _run_local_direct(db_url: str, cutoff_date: str, output_dir: str = "pipeline_output") -> str:
    """Runs extract -> transform -> validate in-process (no KFP subprocess/shell).

    KFP's SubprocessRunner shells out via "sh -c" and serializes Windows paths
    into JSON without escaping backslashes, which breaks on native Windows
    Python (no /bin/sh, backslash path mangling, invalid JSON escapes). This
    calls the same pure functions the KFP components wrap, so the produced
    artifact is identical; use --run-local (real KFP) on Linux/CI/WSL instead.
    """
    import pandas as pd
    from sqlalchemy import create_engine, text

    sql = _read_feature_sql().replace("2026-01-01", cutoff_date)
    engine = create_engine(db_url)
    with engine.connect() as conn:
        df = pd.read_sql(text(sql), conn)
    print(f"Extracted {len(df):,} rows for cutoff={cutoff_date}")

    df = transform_logic(df)
    print(f"Transformed {len(df):,} rows")

    validate_logic(df)

    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, f"features_{cutoff_date}.csv")
    df.to_csv(out_path, index=False)
    print(f"Validated dataset written to {out_path}")
    return out_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--compile", dest="compile_path", help="Compile the pipeline to this YAML file")
    parser.add_argument("--run-local", action="store_true", help="Run the pipeline locally via kfp.local (Linux/CI/WSL)")
    parser.add_argument("--run-local-direct", action="store_true", help="Run extract/transform/validate in-process (Windows-safe fallback)")
    parser.add_argument("--db-url", default=os.environ.get("DB_URL", "postgresql://ds_candidate:ds_candidate_pw@localhost:5432/ecommerce"))
    parser.add_argument("--cutoff-date", default="2026-01-01")
    args = parser.parse_args()

    if args.compile_path:
        from kfp import compiler
        compiler.Compiler().compile(churn_feature_pipeline, args.compile_path)
        print(f"Compiled pipeline to {args.compile_path}")

    if args.run_local_direct:
        _run_local_direct(args.db_url, args.cutoff_date)
    elif args.run_local:
        local.init(runner=local.SubprocessRunner(use_venv=False))
        churn_feature_pipeline(
            db_url=args.db_url,
            cutoff_date=args.cutoff_date,
            feature_sql=_read_feature_sql(),
        )


if __name__ == "__main__":
    main()
