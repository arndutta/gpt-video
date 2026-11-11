"""Real HTTP Commerce fixtures shared by governance acceptance tests."""

from decimal import Decimal

import httpx

from commerce.app import create_app
from commerce.seed import money, seed_database
from platform_app.commerce_client import CommerceClient
from platform_app.governance import Governance
from platform_app.storage import Store


def setup_governance(tmp_path, transport=None):
    path = tmp_path / "commerce.db"
    seed_database(path, sku_count=9, days=60, data_dir=tmp_path)
    client = CommerceClient("http://commerce", transport or httpx.ASGITransport(app=create_app(path)))

    async def forecast(item, price, product):
        return {"forecast": {"revenue": {"mean": 100, "variance": 4},
                             "gross_profit": {"mean": 40, "variance": 1}},
                "current_forecast": {"revenue": {"mean": 98, "variance": 4}},
                "confidence": item["confidence"], "impact": {"revenue": {"mean": 2}}}

    return Governance(Store(tmp_path), client, forecast), client, path


def recommendation(product, *, factor="1.02", confidence=.95, variance=4, samples=180):
    price = money(Decimal(product["current_price"]) * Decimal(factor))
    return {"sku": product["sku"], "name": product["name"], "category": product["category"],
            "family_id": product["family_id"], "currency": product["currency"],
            "current_price": product["current_price"], "proposed_price": price,
            "price_version": product["price_version"],
            "delta_pct": 100 * (float(price) / float(product["current_price"]) - 1),
            "confidence": confidence, "elasticity": {"sample_size": samples},
            "forecast": {"revenue": {"mean": 100, "variance": variance}},
            "rationale": "Typed, cited fixture narrative.", "citations": ["fixture-policy-v1"]}
