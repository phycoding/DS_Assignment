"""
generate_data.py
----------------
Generates a synthetic e-commerce dataset (customers, products, orders,
order_items) as CSVs, sized so that query optimization actually matters
(order_items lands around 1.5-2M rows by default).

Deliberate "realistic messiness" baked in, matching sql/schema.sql:
  - ~1% duplicate customer emails
  - ~5% NULL product categories
  - ~2% NULL order_date
  - skewed order value distribution (long tail of big spenders)
  - ~0.5% duplicate order_items (same order+product inserted twice,
    simulating a double-add bug upstream)
  - status distribution skewed toward 'completed'

Usage:
    python3 generate_data.py --out-dir ../data \
        --n-customers 50000 --n-products 2000 --n-orders 500000

Runtime: ~1-2 minutes for the default sizes on a laptop.
"""

import argparse
import os
import numpy as np
import pandas as pd
from faker import Faker
from datetime import datetime, timedelta

fake = Faker()
Faker.seed(42)
np.random.seed(42)

CATEGORIES = [
    "Electronics", "Home & Kitchen", "Apparel", "Sports & Outdoors",
    "Beauty", "Toys", "Books", "Grocery", "Automotive", "Office Supplies",
]

COUNTRIES = ["US", "US", "US", "CA", "GB", "DE", "FR", "IN", "BR", "AU"]  # skewed toward US

STATUSES = ["completed", "completed", "completed", "completed",
            "cancelled", "returned", "pending"]  # skewed toward completed


def gen_customers(n):
    print(f"Generating {n:,} customers...")
    customer_ids = np.arange(1, n + 1)

    first_names = [fake.first_name() for _ in range(n)]
    last_names = [fake.last_name() for _ in range(n)]
    emails = [f"{fn.lower()}.{ln.lower()}{np.random.randint(1,999)}@example.com"
              for fn, ln in zip(first_names, last_names)]

    # Inject ~1% duplicate emails (simulate a real-world data quality issue)
    dupe_count = int(n * 0.01)
    dupe_idx = np.random.choice(n, dupe_count, replace=False)
    source_idx = np.random.choice(n, dupe_count, replace=False)
    for d, s in zip(dupe_idx, source_idx):
        emails[d] = emails[s]

    signup_start = datetime(2021, 1, 1)
    signup_days_range = (datetime(2026, 1, 1) - signup_start).days
    signup_dates = [signup_start + timedelta(days=int(x))
                     for x in np.random.randint(0, signup_days_range, n)]

    countries = np.random.choice(COUNTRIES, n)
    marketing_opt_in = np.random.choice([True, False, None], n, p=[0.55, 0.35, 0.10])

    df = pd.DataFrame({
        "customer_id": customer_ids,
        "first_name": first_names,
        "last_name": last_names,
        "email": emails,
        "signup_date": signup_dates,
        "country": countries,
        "marketing_opt_in": marketing_opt_in,
    })
    return df


def gen_products(n):
    print(f"Generating {n:,} products...")
    product_ids = np.arange(1, n + 1)
    product_names = [f"{fake.word().capitalize()} {fake.word().capitalize()}" for _ in range(n)]

    categories = np.random.choice(CATEGORIES, n)
    # ~5% NULL categories (data quality gap)
    null_mask = np.random.rand(n) < 0.05
    categories = categories.astype(object)
    categories[null_mask] = None

    # Log-normal price distribution (mostly cheap items, some expensive outliers)
    unit_price = np.round(np.random.lognormal(mean=3.0, sigma=1.0, size=n), 2)
    unit_price = np.clip(unit_price, 1.99, 2999.99)

    active = np.random.choice([True, False], n, p=[0.92, 0.08])

    df = pd.DataFrame({
        "product_id": product_ids,
        "product_name": product_names,
        "category": categories,
        "unit_price": unit_price,
        "active": active,
    })
    return df


def gen_orders(n, n_customers):
    print(f"Generating {n:,} orders...")
    order_ids = np.arange(1, n + 1)

    # Skew orders toward a subset of "power" customers (Zipf-like)
    customer_weights = np.random.zipf(a=1.5, size=n_customers)
    customer_weights = customer_weights / customer_weights.sum()
    customer_id = np.random.choice(np.arange(1, n_customers + 1), size=n, p=customer_weights)

    start_date = datetime(2024, 1, 1)
    date_range_days = (datetime(2026, 7, 1) - start_date).days
    order_dates = [start_date + timedelta(
        days=int(d), seconds=int(np.random.randint(0, 86400)))
        for d in np.random.randint(0, date_range_days, n)]

    # ~2% NULL order_date (data quality gap candidates should notice)
    order_dates = np.array(order_dates, dtype=object)
    null_mask = np.random.rand(n) < 0.02
    order_dates[null_mask] = None

    status = np.random.choice(STATUSES, n)

    # order_total filled in later once order_items are known (placeholder here)
    df = pd.DataFrame({
        "order_id": order_ids,
        "customer_id": customer_id,
        "order_date": order_dates,
        "status": status,
        "order_total": 0.0,  # patched after order_items generation
    })
    return df


def gen_order_items(orders_df, products_df, avg_items_per_order=3):
    n_orders = len(orders_df)
    print(f"Generating order_items for {n_orders:,} orders (~{avg_items_per_order} items/order)...")

    n_products = len(products_df)
    product_prices = products_df.set_index("product_id")["unit_price"]

    # number of items per order: Poisson-ish, min 1, max 8
    items_per_order = np.clip(np.random.poisson(avg_items_per_order, n_orders), 1, 8)
    total_items = int(items_per_order.sum())

    order_id_col = np.repeat(orders_df["order_id"].values, items_per_order)
    product_id_col = np.random.randint(1, n_products + 1, total_items)
    quantity_col = np.random.randint(1, 5, total_items)
    unit_price_col = product_prices.loc[product_id_col].values

    order_item_id_col = np.arange(1, total_items + 1)

    df = pd.DataFrame({
        "order_item_id": order_item_id_col,
        "order_id": order_id_col,
        "product_id": product_id_col,
        "quantity": quantity_col,
        "unit_price": unit_price_col,
    })

    # Inject ~0.5% duplicate rows (same order+product added twice — a
    # realistic "double click / retry bug" data quality issue)
    dupe_count = int(len(df) * 0.005)
    dupes = df.sample(n=dupe_count, random_state=1).copy()
    dupes["order_item_id"] = np.arange(total_items + 1, total_items + 1 + dupe_count)
    df = pd.concat([df, dupes], ignore_index=True)

    return df


def patch_order_totals(orders_df, order_items_df):
    print("Patching order_total from order_items...")
    line_totals = (order_items_df["quantity"] * order_items_df["unit_price"])
    totals = order_items_df.assign(line_total=line_totals).groupby("order_id")["line_total"].sum()
    orders_df["order_total"] = orders_df["order_id"].map(totals).fillna(0).round(2)
    return orders_df


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default="../data")
    parser.add_argument("--n-customers", type=int, default=50_000)
    parser.add_argument("--n-products", type=int, default=2_000)
    parser.add_argument("--n-orders", type=int, default=500_000)
    parser.add_argument("--avg-items-per-order", type=float, default=3.0)
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    customers = gen_customers(args.n_customers)
    products = gen_products(args.n_products)
    orders = gen_orders(args.n_orders, args.n_customers)
    order_items = gen_order_items(orders, products, args.avg_items_per_order)
    orders = patch_order_totals(orders, order_items)

    print("Writing CSVs...")
    customers.to_csv(os.path.join(args.out_dir, "customers.csv"), index=False)
    products.to_csv(os.path.join(args.out_dir, "products.csv"), index=False)
    orders.to_csv(os.path.join(args.out_dir, "orders.csv"), index=False)
    order_items.to_csv(os.path.join(args.out_dir, "order_items.csv"), index=False)

    print("\nDone. Row counts:")
    print(f"  customers:   {len(customers):,}")
    print(f"  products:    {len(products):,}")
    print(f"  orders:      {len(orders):,}")
    print(f"  order_items: {len(order_items):,}")


if __name__ == "__main__":
    main()