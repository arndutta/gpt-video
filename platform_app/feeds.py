"""Replaceable aggregate competitor feeds. Remote JSON access requires explicit opt-in."""

import asyncio
import json
from datetime import date
from decimal import Decimal
from typing import Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

from platform_app.commerce_client import read_competitors
from platform_app.config import tls_context


class CompetitorQuote(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    sku: str = Field(min_length=1, max_length=100)
    competitor: str = Field(min_length=1, max_length=100)
    price: str = Field(pattern=r"^\d{1,8}(?:\.\d{1,2})?$")
    observed_at: str = Field(min_length=10, max_length=40)

    @field_validator("price")
    @classmethod
    def positive(cls, value):
        if Decimal(value) <= 0:
            raise ValueError("Competitor price must be positive")
        return value

    @field_validator("observed_at")
    @classmethod
    def dated(cls, value):
        date.fromisoformat(value[:10])
        return value


class CompetitorFeed(Protocol):
    async def fetch(self) -> list[dict]: ...


class SyntheticFeed:
    def __init__(self, data_dir):
        self.data_dir = data_dir

    async def fetch(self):
        rows = await asyncio.to_thread(read_competitors, self.data_dir)
        return [CompetitorQuote.model_validate(r).model_dump() for r in rows]


class LiveJSONFeed:
    def __init__(self, settings, transport=None):
        if not settings.live_competitor_enabled or not settings.live_competitor_url:
            raise ValueError("Live competitor access is disabled. Explicitly configure and enable a JSON feed.")
        self.settings, self.transport = settings, transport

    async def fetch(self):
        try:
            async with httpx.AsyncClient(verify=tls_context(self.settings), timeout=5, transport=self.transport,
                                         follow_redirects=False) as client:
                async with client.stream("GET", self.settings.live_competitor_url) as response:
                    response.raise_for_status()
                    chunks, total = [], 0
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > 2_000_000:
                            raise ValueError("Competitor feed exceeds its limit")
                        chunks.append(chunk)
            payload = json.loads(b"".join(chunks))
            rows = payload.get("items") if isinstance(payload, dict) else payload
            if not isinstance(rows, list) or len(rows) > 10000:
                raise ValueError("Invalid quote list")
            return [CompetitorQuote.model_validate(r).model_dump() for r in rows]
        except (httpx.HTTPError, ValueError):
            raise ValueError("The optional live competitor feed is unavailable or invalid.") from None


def configured_feed(settings) -> CompetitorFeed:
    return LiveJSONFeed(settings) if settings.live_competitor_enabled else SyntheticFeed(settings.data_dir)


async def optional_quotes(settings):
    try:
        return await configured_feed(settings).fetch()
    except (ValueError, OSError):
        # Missing optional observations are explicit in numerical quality/freshness
        # factors and widen the shared engine's competitor uncertainty.
        return []
