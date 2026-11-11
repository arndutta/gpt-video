"""Locally validated Commerce wire contracts, with no implementation dependency."""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator


class WireModel(BaseModel):
    model_config = ConfigDict(extra="allow", allow_inf_nan=False)

    @field_validator("cost", "current_price", "map_price", "min_price", "max_price", "rounding_increment",
                     "price", "prior_price", "new_price", mode="before", check_fields=False)
    @classmethod
    def money_is_wire_string(cls, value):
        if not isinstance(value, str):
            raise ValueError("Commerce money must be a decimal string")
        return value


class CatalogItem(WireModel):
    sku: str = Field(min_length=1)
    name: str
    category: str
    family_id: str
    size: int = Field(gt=0, strict=True)
    currency: str = Field(min_length=3, max_length=3)
    cost: Decimal = Field(ge=0)
    current_price: Decimal = Field(gt=0)
    map_price: Decimal = Field(ge=0)
    min_price: Decimal = Field(ge=0)
    max_price: Decimal = Field(gt=0)
    price_version: int = Field(gt=0, strict=True)
    max_change_pct: float = Field(ge=0, le=1)
    minimum_margin_pct: float = Field(ge=0, lt=1)
    rounding_increment: Decimal = Field(gt=0)


class SalesItem(WireModel):
    sku: str = Field(min_length=1)
    date: date
    price: Decimal = Field(gt=0)
    units: int = Field(ge=0, strict=True)
    promotion: bool = Field(strict=True)
    seasonal_index: float = Field(gt=0)


class InventoryItem(WireModel):
    sku: str = Field(min_length=1)
    on_hand: int = Field(ge=0, strict=True)
    updated_at: AwareDatetime


class PriceItem(WireModel):
    sku: str = Field(min_length=1)
    current_price: Decimal = Field(gt=0)
    price_version: int = Field(gt=0, strict=True)
    updated_at: AwareDatetime
    currency: str = Field(min_length=3, max_length=3)


class PriceHistoryItem(WireModel):
    id: int = Field(gt=0, strict=True)
    sku: str = Field(min_length=1)
    batch_key: str | None
    prior_price: Decimal = Field(gt=0)
    new_price: Decimal = Field(gt=0)
    prior_version: int = Field(gt=0, strict=True)
    new_version: int = Field(gt=0, strict=True)
    actor: str = Field(min_length=1, max_length=100)
    approval_kind: Literal["human", "automatic"]
    applied_at: AwareDatetime

    @model_validator(mode="after")
    def coherent_change(self):
        if self.new_price == self.prior_price or self.new_version != self.prior_version + 1:
            raise ValueError("Commerce price history must describe an actual versioned change")
        return self


class CommerceHealth(WireModel):
    service: Literal["commerce"]
    status: Literal["ok", "unavailable"]
    catalog_count: int = Field(ge=0, strict=True)
    seeded: bool = Field(strict=True)
    as_of: AwareDatetime | None

    @model_validator(mode="after")
    def coherent_seed_state(self):
        if self.seeded != (self.catalog_count > 0) or self.seeded and self.as_of is None:
            raise ValueError("Commerce seed state is inconsistent")
        return self


READ_SCHEMAS = {"/catalog": CatalogItem, "/sales": SalesItem, "/inventory": InventoryItem,
                "/prices": PriceItem, "/price-history": PriceHistoryItem}
