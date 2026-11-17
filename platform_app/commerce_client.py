"""HTTP-only Commerce adapter; the platform never opens commerce.db."""

import asyncio
from contextlib import closing
from pathlib import Path
import sqlite3

import httpx

from platform_app.wire import CommerceHealth, READ_SCHEMAS


class CommerceUnavailable(RuntimeError):
    pass


class CommerceClient:
    def __init__(self, base_url: str, transport=None):
        self.base_url = base_url
        self.transport = transport

    async def get(self, route: str, **params) -> dict:
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=30,
                                        transport=self.transport) as client:
                response = await client.get(route, params={k: v for k, v in params.items() if v is not None})
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict):
                    raise ValueError("Expected an object")
                if route == "/health":
                    CommerceHealth.model_validate(data)
                else:
                    if (not isinstance(data.get("items"), list)
                            or not all(isinstance(item, dict) for item in data["items"])
                            or type(data.get("total")) is not int or data["total"] < 0
                            or not isinstance(data.get("as_of"), (str, type(None)))):
                        raise ValueError("Invalid read envelope")
                    if route in READ_SCHEMAS:
                        for item in data["items"]:
                            READ_SCHEMAS[route].model_validate(item)
                return data
        except (httpx.HTTPError, ValueError) as exc:
            raise CommerceUnavailable("Commerce is unavailable or returned invalid data. "
                                      "Start it on port 8001 and verify its health endpoint.") from exc

    async def all(self, route: str, **params) -> dict:
        limit = 5000
        items = []
        offset = 0
        while True:
            page = await self.get(route, limit=limit, offset=offset, **params)
            batch = page.get("items", [])
            if not isinstance(batch, list):
                raise CommerceUnavailable("Commerce returned an invalid item list.")
            items.extend(batch)
            offset += len(batch)
            if offset >= page.get("total", len(items)):
                return {"items": items, "total": len(items), "as_of": page.get("as_of")}
            if not batch:
                raise CommerceUnavailable("Commerce pagination ended before the reported total.")

    async def context(self, *, category=None, sku_ids=None) -> dict:
        params = {"category": category, "sku": ",".join(sku_ids) if sku_ids else None}
        catalog, sales, inventory = await asyncio.gather(
            self.all("/catalog", **params), self.all("/sales", **params), self.all("/inventory", **params))
        return {"catalog": catalog["items"], "sales": sales["items"],
                "inventory": inventory["items"], "as_of": catalog.get("as_of")}


def read_competitors(data_dir: Path) -> list[dict]:
    """Read current external observations from market.db, independently of Commerce."""
    path = Path(data_dir) / "market.db"
    if not path.exists():
        return []
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=10)) as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute(
                "SELECT sku,competitor,price,observed_at FROM competitor_quotes ORDER BY rowid")]
    except sqlite3.Error:
        raise ValueError("The SQLite competitor feed is unavailable or invalid") from None
