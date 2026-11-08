"""HTTP boundary for the local Commerce system of record."""

from contextlib import asynccontextmanager
from datetime import date, timedelta
import os
from pathlib import Path

from fastapi import FastAPI, Query

from commerce.batches import apply_batch, receipt
from commerce.models import PriceBatch
from commerce.storage import connect, initialize, page, scope_filters, source_timestamp


def create_app(db_path: str | Path | None = None) -> FastAPI:
    path = Path(db_path or os.environ.get("COMMERCE_DB_PATH", "data/commerce.db"))

    @asynccontextmanager
    async def lifespan(application):
        initialize(path)
        yield

    application = FastAPI(title="Retail Commerce Service", version="0.1.0", lifespan=lifespan)
    application.state.db_path = path

    @application.get("/health")
    def health():
        with connect(path) as connection:
            count = connection.execute("SELECT COUNT(*) FROM products").fetchone()[0]
            return {"status": "ok", "service": "commerce", "catalog_count": count,
                    "seeded": count > 0, "as_of": source_timestamp(connection)}

    @application.get("/catalog")
    def catalog(sku: str | None = None, category: str | None = None,
                limit: int = Query(100, ge=1, le=5000), offset: int = Query(0, ge=0)):
        clauses, values = scope_filters(sku, category)
        with connect(path) as connection:
            return page(connection, "p.*, q.current_price, q.price_version",
                        "products p JOIN prices q USING (sku)", clauses, values,
                        "p.sku", limit, offset)

    @application.get("/sales")
    def sales(sku: str | None = None, category: str | None = None,
              days: int | None = Query(None, ge=1, le=3650), since: date | None = None,
              limit: int = Query(1000, ge=1, le=100000), offset: int = Query(0, ge=0)):
        clauses, values = scope_filters(sku, category)
        with connect(path) as connection:
            if days is not None:
                as_of = source_timestamp(connection)
                end = date.fromisoformat(as_of[:10]) if as_of else date.today()
                boundary = end - timedelta(days=days - 1)
                since = max(since, boundary) if since else boundary
            if since:
                clauses.append("s.date >= ?")
                values.append(since.isoformat())
            result = page(connection,
                          "s.sku, s.date, s.price, s.units, s.promotion, s.seasonal_index",
                          "sales s JOIN products p USING (sku)", clauses, values,
                          "s.sku, s.date", limit, offset)
            for item in result["items"]:
                item["promotion"] = bool(item["promotion"])
            return result

    @application.get("/inventory")
    def inventory(sku: str | None = None, category: str | None = None,
                  limit: int = Query(100, ge=1, le=5000), offset: int = Query(0, ge=0)):
        clauses, values = scope_filters(sku, category)
        with connect(path) as connection:
            return page(connection, "i.sku, i.on_hand, i.updated_at",
                        "inventory i JOIN products p USING (sku)", clauses, values,
                        "i.sku", limit, offset)

    @application.get("/prices")
    def prices(sku: str | None = None, category: str | None = None,
               limit: int = Query(100, ge=1, le=5000), offset: int = Query(0, ge=0)):
        clauses, values = scope_filters(sku, category)
        with connect(path) as connection:
            return page(connection, "q.sku, q.current_price, q.price_version, q.updated_at, p.currency",
                        "prices q JOIN products p USING (sku)", clauses, values,
                        "q.sku", limit, offset)

    @application.get("/price-history")
    def history(sku: str | None = None, category: str | None = None,
                limit: int = Query(100, ge=1, le=5000), offset: int = Query(0, ge=0)):
        clauses, values = scope_filters(sku, category)
        with connect(path) as connection:
            return page(connection, "h.*", "price_history h JOIN products p USING (sku)",
                        clauses, values, "h.id DESC", limit, offset)

    @application.post("/prices/batches")
    def push_prices(batch: PriceBatch):
        return apply_batch(path, batch)

    @application.get("/prices/batches/{batch_key}")
    def batch_receipt(batch_key: str):
        return receipt(path, batch_key)

    return application


app = create_app()
