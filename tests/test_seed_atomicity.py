"""Invalid generated market data must not commit a Commerce reset."""

import pytest

from commerce import seed
from commerce.storage import connect, product_rows
from platform_app.commerce_client import read_competitors


def test_invalid_market_quotes_preserve_existing_commerce_and_market_data(tmp_path, monkeypatch):
    path = tmp_path / "commerce.db"
    seed.seed_database(path, sku_count=2, days=2, data_dir=tmp_path)
    with connect(path) as db:
        catalog = product_rows(db)
        sales = [dict(row) for row in db.execute("SELECT * FROM sales ORDER BY id")]
    quotes = read_competitors(tmp_path)
    invalid = seed.generate(3, 2, seed=43)
    invalid["competitors"][0]["price"] = "-1.00"
    monkeypatch.setattr(seed, "generate", lambda *_args, **_kwargs: invalid)

    with pytest.raises(ValueError, match="Invalid competitor quote"):
        seed.seed_database(path, sku_count=3, days=2, data_dir=tmp_path, reset=True)

    with connect(path) as db:
        assert product_rows(db) == catalog
        assert [dict(row) for row in db.execute("SELECT * FROM sales ORDER BY id")] == sales
    assert read_competitors(tmp_path) == quotes
