"""Locally validated Commerce wire contracts, with no implementation dependency."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class WireModel(BaseModel):
    model_config = ConfigDict(extra="allow", allow_inf_nan=False)


class CatalogItem(WireModel):
    sku: str = Field(min_length=1)
    name: str
    category: str
    family_id: str
    size: int = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    cost: Decimal = Field(ge=0)
    current_price: Decimal = Field(gt=0)
    map_price: Decimal = Field(ge=0)
    min_price: Decimal = Field(ge=0)
    max_price: Decimal = Field(gt=0)
    price_version: int = Field(gt=0)
    max_change_pct: float = Field(ge=0, le=1)
    minimum_margin_pct: float = Field(ge=0, lt=1)
    rounding_increment: Decimal = Field(gt=0)


class SalesItem(WireModel):
    sku: str = Field(min_length=1)
    date: date
    price: Decimal = Field(gt=0)
    units: int = Field(ge=0)
    promotion: bool
    seasonal_index: float = Field(gt=0)


class InventoryItem(WireModel):
    sku: str = Field(min_length=1)
    on_hand: int = Field(ge=0)
    updated_at: datetime


READ_SCHEMAS = {"/catalog": CatalogItem, "/sales": SalesItem, "/inventory": InventoryItem}
