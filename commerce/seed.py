"""Seed reproducible synthetic data without exposing evaluator ground truth over HTTP."""

import argparse
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import json
import math
from pathlib import Path
import random

from commerce.market import quote_values, replace_quotes
from commerce.storage import connect, initialize, seed_statements


def money(value: float | Decimal) -> str:
    return str(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def generate(sku_count=500, days=180, seed=42, as_of=date(2026, 11, 8),
             categories=("Beverages", "Snacks", "Household")) -> dict:
    if sku_count < 1 or days < 1 or not categories:
        raise ValueError("sku_count, days, and the category list must be positive/nonempty")
    rng = random.Random(seed)
    stamp = datetime.combine(as_of, time(), timezone.utc).isoformat()
    products, prices, inventory, sales, truth, competitors = [], [], [], [], [], []
    family_base = {}
    for index in range(sku_count):
        family = index // 3
        category = categories[family % len(categories)]
        base = family_base.setdefault(family, round(rng.uniform(2.5, 18.0), 2))
        size = (250, 500, 750)[index % 3]
        sku, family_id = f"SKU-{index + 1:05}", f"FAMILY-{family + 1:04}"
        price = float(money(base * (1.0, 1.65, 2.2)[index % 3]))
        cost = money(price * rng.uniform(0.43, 0.60))
        products.append((sku, f"{category} item {family + 1:03} · {size}", category,
                         family_id, size, "USD", cost, money(price * .75),
                         money(price * .70), money(price * 1.8), .20, .15, "0.01"))
        prices.append((sku, money(price), 1, stamp))
        elasticity = rng.uniform(-2.5, -.8)
        daily_demand = rng.uniform(30, 160) / (1 + index % 3 * .2)
        inventory.append((sku, int(daily_demand * rng.uniform(5, 90)), stamp))
        truth.append((sku, elasticity, daily_demand))
        for day_index in range(days):
            observed = as_of - timedelta(days=days - day_index - 1)
            seasonal = 1 + .18 * math.sin(2 * math.pi * observed.timetuple().tm_yday / 365)
            seasonal *= 1.08 if observed.weekday() in (5, 6) else 1.0
            promotion = rng.random() < .12
            observed_price = float(money(price * rng.uniform(.88, 1.12) * (.90 if promotion else 1)))
            expected = daily_demand * (observed_price / price) ** elasticity * seasonal
            expected *= 1.18 if promotion else 1
            units = max(0, round(expected * rng.lognormvariate(-.005, .10)))
            sales.append((sku, observed.isoformat(), money(observed_price), units,
                          int(promotion), round(seasonal, 8)))
        for competitor in ("Northstar Retail", "Market Square"):
            competitors.append({"sku": sku, "competitor": competitor,
                                "price": money(price * rng.uniform(.88, 1.12)),
                                "observed_at": stamp})
    return {"products": products, "prices": prices, "inventory": inventory,
            "sales": sales, "truth": truth, "competitors": competitors, "as_of": stamp}


def seed_database(db_path: str | Path, *, sku_count=500, days=180, seed=42,
                  as_of=date(2026, 11, 8), data_dir: str | Path | None = None,
                  reset=False, categories=("Beverages", "Snacks", "Household")) -> dict:
    """Validate before changing data, then commit atomically within each database.

    Commerce and market use separate transactions; an I/O failure between their
    commits can require retrying the explicit seed/reset operation.
    """
    path = Path(db_path)
    initialize(path)
    output = Path(data_dir) if data_dir else path.parent
    output.mkdir(parents=True, exist_ok=True)
    dataset = generate(sku_count, days, seed, as_of, categories)
    quote_values(dataset["competitors"])
    statements = seed_statements()
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        if connection.execute("SELECT COUNT(*) FROM products").fetchone()[0] and not reset:
            raise ValueError("Commerce already contains products. Use --reset only to replace demo data.")
        if reset:
            for table in ("batches", "price_history", "sales", "inventory", "prices",
                          "evaluation_truth", "products", "metadata"):
                connection.execute(f"DELETE FROM {table}")
        for table in ("products", "prices", "inventory", "sales", "truth"):
            connection.executemany(statements[table], dataset[table])
        connection.executemany(statements["metadata"], [
            ("as_of", dataset["as_of"]), ("seed", str(seed)), ("history_days", str(days))
        ])
        connection.commit()
    replace_quotes(output, dataset["competitors"])
    return {"sku_count": sku_count, "sales_rows": len(dataset["sales"]),
            "competitor_quotes": len(dataset["competitors"]),
            "as_of": dataset["as_of"], "db_path": str(path), "market_db_path": str(output / "market.db")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sku-count", type=int, default=500)
    parser.add_argument("--days", type=int, default=180)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--as-of", type=date.fromisoformat, default=datetime.now(timezone.utc).date())
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--db-path", type=Path)
    parser.add_argument("--category", help="Generate one category, useful for the 500-SKU benchmark.")
    parser.add_argument("--reset", action="store_true", help="Explicitly replace existing synthetic Commerce data.")
    args = parser.parse_args()
    try:
        result = seed_database(args.db_path or args.data_dir / "commerce.db", sku_count=args.sku_count,
                               days=args.days, seed=args.seed, as_of=args.as_of, data_dir=args.data_dir,
                               reset=args.reset, categories=(args.category,) if args.category else
                               ("Beverages", "Snacks", "Household"))
    except (ValueError, OSError) as error:
        parser.exit(1, f"Seed failed: {error}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
