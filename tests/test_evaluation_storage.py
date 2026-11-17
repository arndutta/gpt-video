"""Evaluation studies read committed SQLite ground truth without JSON sidecars."""

from commerce.evaluation import read_evaluation_truth
from commerce.seed import seed_database
from commerce.storage import connect


def test_evaluation_truth_reads_database_changes_without_sidecar(tmp_path):
    path = tmp_path / "commerce.db"
    seed_database(path, sku_count=3, days=30, data_dir=tmp_path)
    (tmp_path / "evaluation_truth.json").unlink(missing_ok=True)
    initial = read_evaluation_truth(path)
    assert len(initial) == 3
    assert all(set(item) == {"elasticity", "baseline_demand"} for item in initial.values())
    with connect(path) as connection:
        connection.execute("UPDATE evaluation_truth SET elasticity=? WHERE sku=?", (-3.5, "SKU-00001"))
        connection.commit()
    assert read_evaluation_truth(path)["SKU-00001"] == {**initial["SKU-00001"], "elasticity": -3.5}
