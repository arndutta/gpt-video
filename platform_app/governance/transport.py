"""Bounded HTTP dispatch and strict, payload-bound Commerce receipt validation."""

from decimal import Decimal
import asyncio
from datetime import datetime
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class ItemReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sku: str
    status: Literal["applied", "rejected"]
    prior_price: str | None
    new_price: str
    prior_version: int | None = Field(ge=1, strict=True)
    new_version: int | None = Field(ge=1, strict=True)
    applied_at: str | None
    rejection_code: str | None
    rejection_reason: str | None


class BatchReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    batch_key: str
    status: Literal["applied", "partial", "rejected"]
    items: list[ItemReceipt] = Field(min_length=1, max_length=1000)


def validate_receipt(data, payload):
    receipt = BatchReceipt.model_validate(data).model_dump()
    expected = {item["sku"]: item for item in payload["items"]}
    rows = receipt["items"]
    if (receipt["batch_key"] != payload["batch_key"] or len(rows) != len(expected)
            or {row["sku"] for row in rows} != set(expected)):
        raise ValueError("Receipt does not match the dispatch")
    for row in rows:
        wanted = expected[row["sku"]]
        if Decimal(row["new_price"]) != Decimal(wanted["price"]):
            raise ValueError("Receipt contains a different price")
        if row["status"] == "applied":
            prior = Decimal(row["prior_price"])
            applied = datetime.fromisoformat(str(row["applied_at"]).replace("Z", "+00:00"))
            expected_new_version = wanted["expected_version"] + int(prior != Decimal(wanted["price"]))
            if (not prior.is_finite() or prior <= 0 or applied.tzinfo is None
                    or row["prior_version"] != wanted["expected_version"]
                    or row["new_version"] != expected_new_version
                    or row["rejection_code"] or row["rejection_reason"]):
                raise ValueError("Applied receipt is inconsistent")
        elif (row["applied_at"] is not None or not row["rejection_code"] or not row["rejection_reason"]
              or row["new_version"] != row["prior_version"]):
            raise ValueError("Rejected receipt is inconsistent")
    applied = sum(row["status"] == "applied" for row in rows)
    status = "applied" if applied == len(rows) else "partial" if applied else "rejected"
    if receipt["status"] != status:
        raise ValueError("Batch outcome is inconsistent")
    return receipt


class CommerceWriter:
    def __init__(self, commerce):
        self.commerce = commerce

    async def lookup(self, payload):
        try:
            async with httpx.AsyncClient(base_url=self.commerce.base_url, timeout=5,
                                          transport=self.commerce.transport) as client:
                response = await client.get(f'/prices/batches/{payload["batch_key"]}')
                if response.status_code == 404:
                    return None
                response.raise_for_status()
                return validate_receipt(response.json(), payload)
        except (httpx.HTTPError, ValidationError, ValueError, ArithmeticError, TypeError):
            return None

    async def send(self, payload, on_attempt=None):
        for attempt in range(3):
            retryable = True
            try:
                if on_attempt:
                    on_attempt(attempt + 1)
                async with httpx.AsyncClient(base_url=self.commerce.base_url, timeout=5,
                                              transport=self.commerce.transport) as client:
                    response = await client.post("/prices/batches", json=payload)
                    retryable = response.status_code in {429, 500, 502, 503, 504}
                    response.raise_for_status()
                    return validate_receipt(response.json(), payload)
            except (httpx.HTTPError, ValidationError, ValueError, ArithmeticError, TypeError):
                # A timeout or malformed response does not prove no commit occurred.
                receipt = await self.lookup(payload)
                if receipt:
                    return receipt
                if not retryable or attempt == 2:
                    return None
                # Replay only this immutable key and payload while the original
                # dispatch admission is still fenced against kill/mode changes.
                await asyncio.sleep(.1 * 2 ** attempt)
        return None
