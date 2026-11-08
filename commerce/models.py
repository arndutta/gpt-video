"""Validated Commerce write contracts; money is represented as decimal strings."""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PriceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: str = Field(min_length=1, max_length=80)
    price: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    expected_version: int = Field(ge=1, strict=True)

    @field_validator("price", mode="before")
    @classmethod
    def string_money(cls, value):
        if not isinstance(value, (str, Decimal)):
            raise ValueError("price must be a decimal string, for example '12.50'")
        return value


class PriceBatch(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    batch_key: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")
    actor: str = Field(min_length=1, max_length=100)
    approval_kind: Literal["human", "automatic"]
    items: list[PriceItem] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def unique_skus(self):
        skus = [item.sku for item in self.items]
        if len(skus) != len(set(skus)):
            raise ValueError("a batch may contain each SKU only once")
        return self
