"""Versioned demo policy and strict human-decision contracts."""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


Mode = Literal["supervised", "assisted", "autonomous"]


class GovernanceError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int = 409):
        super().__init__(message)
        self.code, self.detail, self.status_code = code, message, status_code


class GovernancePolicy(BaseModel):
    """Initial calibration choices, not measured business guarantees.

    Variance is normalized revenue standard deviation / mean, so thresholds do
    not change solely because a product is sold in a different currency.
    The market-gap limit is a configured trial norm, not an empirical historical
    distribution; the evaluated gap and threshold remain visible in band evidence.
    """
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    confidence_threshold: float = Field(default=0.8, ge=0, le=1, strict=True)
    bulk_confidence_threshold: float = Field(default=0.8, ge=0, le=1, strict=True)
    auto_delta_pct: float = Field(default=5.0, ge=0, le=100, strict=True)
    volatility_limit: float = Field(default=0.35, gt=0, le=5, strict=True)
    margin_proximity_buffer: float = Field(default=0.03, ge=0, le=1, strict=True)
    market_gap_limit_pct: float = Field(default=30., ge=0, le=1000, strict=True)
    minimum_sample: int = Field(default=60, ge=30, le=10000, strict=True)
    oscillation_window: int = Field(default=8, ge=2, le=100, strict=True)
    reversals_threshold: int = Field(default=2, ge=1, le=20, strict=True)
    damping_fraction: float = Field(default=0.35, gt=0, le=1, strict=True)
    minimum_change_seconds: int = Field(default=0, ge=0, le=604800, strict=True)
    anomaly_z_threshold: float = Field(default=4.0, ge=1, le=20, strict=True)
    hold_seconds: int = Field(default=60, ge=0, le=86400, strict=True)
    maximum_change_pct: float | None = Field(default=None, ge=0, le=1, strict=True)
    minimum_margin_pct: float | None = Field(default=None, ge=0, lt=1, strict=True)
    rounding_increment: str | None = Field(default=None, pattern=r"^\d+(?:\.\d{1,2})?$")

    @field_validator("rounding_increment")
    @classmethod
    def positive_tick(cls, value):
        if value is not None and Decimal(value) <= 0:
            raise ValueError("Rounding increment must be positive")
        return value


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    action: Literal["approve", "reject", "override"]
    expected_revision: int = Field(ge=1, strict=True)
    reason: str | None = Field(default=None, max_length=2000)
    price: str | None = Field(default=None, pattern=r"^\d{1,8}(?:\.\d{1,2})?$")

    @model_validator(mode="after")
    def override_needs_reason(self):
        if self.action == "override" and (not self.reason or self.price is None):
            raise ValueError("A price override requires a price and written reason")
        if self.action != "override" and self.price is not None:
            raise ValueError("Only an override may change the price")
        if self.price is not None and Decimal(self.price) <= 0:
            raise ValueError("Price must be positive")
        return self


class ModeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Mode
    hold_seconds: int | None = Field(default=None, ge=0, le=86400, strict=True)
