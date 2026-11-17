"""Serve the production UI against disposable SQLite data for Chromium acceptance.

Confidence/stability inputs deliberately exercise every review band. They are UI
fixtures, not evidence of model accuracy or business effectiveness. All decisions
use real governance, Commerce HTTP adapters, and temporary databases.
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import tempfile

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import httpx
import uvicorn

from commerce.app import create_app as commerce_app
from commerce.seed import money, seed_database
from platform_app.app import create_app
from platform_app.commerce_client import read_competitors
from platform_app.config import Settings
from platform_app.rag.models import Document
from platform_app.tools import simulate_sku
from scripts.benchmark import ModelFixture


ROOT = Path(__file__).resolve().parents[1]


async def populate(state):
    job = state.grounding.submit(Document(source_id="browser-policy", title="Browser acceptance policy",
        text="Synthetic pricing must preserve margin, MAP, maximum change and family order. Human review remains authoritative.",
        collection="pricing_policy", version="v1"), "browser-policy.md")
    for _ in range(300):
        current = state.grounding.get_upload(job["id"])
        if current["status"] == "ready":
            break
        if current["status"] in {"failed", "interrupted"}:
            raise RuntimeError("Browser fixture evidence failed to index")
        await asyncio.sleep(.05)
    else:
        raise RuntimeError("Browser fixture evidence was not ready within 15 seconds")
    context = await state.commerce.context()
    quotes = read_competitors(state.settings.data_dir)
    citation = (await state.grounding.retrieve("margin policy", role="analyst")).chunks[0].citation_id
    recommendations = []
    for index, product in enumerate(context["catalog"]):
        group = index // 3
        factor = ("1.02", "1.08", "1.02", "1.50", "1.02")[group]
        price = money(Decimal(product["current_price"]) * Decimal(factor))
        item = await asyncio.to_thread(simulate_sku, product, context["sales"], context["inventory"], quotes,
                                      price, 1000, 42, 14)
        item.update(confidence=.95, rationale="Declared synthetic browser fixture; numerical forecasts use the shared engine.",
                    citations=[citation])
        if group == 2:
            item["initial_stability"] = {"oscillation": True}
        recommendations.append(item)
    # First four families cover all bands under ordinary Supervised review.
    await state.governance.register("browser-review-fixture", recommendations[:12])
    # A separate family supplies genuine automatic receipts in disposable Commerce.
    await state.governance.set_mode("assisted")
    automatic = await state.governance.register("browser-automatic-fixture", recommendations[12:])
    await state.governance.dispatch_due([item["id"] for item in automatic])
    await state.governance.set_mode("supervised")
    state.browser_fixture_ready = True


def application(directory):
    seed_database(directory / "commerce.db", sku_count=15, days=120,
                  as_of=datetime.now(timezone.utc).date(), data_dir=directory)
    upstream = commerce_app(directory / "commerce.db")
    settings = Settings(data_dir=directory, commerce_url="http://browser-commerce",
        embedding_cache_dir=ROOT / "data/models", gateway_url="https://browser-fixture.invalid/v1",
        api_key="browser-fixture-only", model_router="fixture", model_narrator="fixture",
        model_analyst="fixture", model_strategist="fixture")
    app = create_app(settings, commerce_transport=httpx.ASGITransport(app=upstream),
                     llm_provider_factory=lambda *_: ModelFixture())
    original = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(current):
        async with original(current):
            await populate(current.state)
            yield

    app.router.lifespan_context = lifespan

    @app.get("/__qa/ready")
    def ready():
        return {"ready": getattr(app.state, "browser_fixture_ready", False),
                "scope": "Disposable synthetic UI acceptance; no live data or gateway"}

    app.mount("/assets", StaticFiles(directory=ROOT / "web/dist/assets"), name="assets")

    @app.get("/{page:path}", include_in_schema=False)
    def frontend(page: str):
        return FileResponse(ROOT / "web/dist/index.html")

    return app


def main():
    if not (ROOT / "web/dist/index.html").exists():
        raise SystemExit("Build the UI before starting browser acceptance")
    with tempfile.TemporaryDirectory(prefix="pricing-browser-", ignore_cleanup_errors=True) as temporary:
        uvicorn.run(application(Path(temporary)), host="127.0.0.1", port=5173, log_level="warning", access_log=False)


if __name__ == "__main__":
    main()
