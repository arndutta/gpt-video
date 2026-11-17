"""Offline evaluator access; hidden ground truth is never exposed by Commerce HTTP."""

from pathlib import Path

from commerce.storage import connect


def read_evaluation_truth(db_path: str | Path) -> dict[str, dict[str, float]]:
    with connect(db_path) as connection:
        return {row["sku"]: {"elasticity": row["elasticity"],
                             "baseline_demand": row["baseline_demand"]}
                for row in connection.execute(
                    "SELECT sku, elasticity, baseline_demand FROM evaluation_truth ORDER BY sku")}
