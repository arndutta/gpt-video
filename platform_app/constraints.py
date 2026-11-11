"""Per-run SKU pricing bounds, independent of mode and model output."""

from decimal import Decimal
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


MONEY = re.compile(r"^\d{1,8}(?:\.\d{1,2})?$")


class RunConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, frozen=True)
    max_change_pct: float | None = Field(default=None, ge=0, le=1, strict=True)
    category_floors: dict[str, str] = Field(default_factory=dict, max_length=50)
    category_ceilings: dict[str, str] = Field(default_factory=dict, max_length=50)

    @field_validator("category_floors", "category_ceilings", mode="before")
    @classmethod
    def positive_category_money(cls, values):
        if not isinstance(values, dict):
            raise ValueError("Category bounds must map category names to decimal money strings")
        if len(values) > 50:
            raise ValueError("At most 50 category bounds are supported")
        result = {}
        for category, price in values.items():
            if not isinstance(category, str) or not 1 <= len(category.strip()) <= 100:
                raise ValueError("Category names must contain 1–100 characters")
            category = category.strip()
            if category in result:
                raise ValueError("Category names must remain unique after trimming")
            if not isinstance(price, str) or not MONEY.fullmatch(price) or Decimal(price) <= 0:
                raise ValueError("Category bounds must be positive decimal money strings with at most two decimals")
            result[category] = format(Decimal(price), ".2f")
        return result

    @model_validator(mode="after")
    def coherent_bounds(self):
        for category in self.category_floors.keys() & self.category_ceilings.keys():
            if Decimal(self.category_floors[category]) > Decimal(self.category_ceilings[category]):
                raise ValueError("A category floor cannot exceed its ceiling")
        return self


def constraints_model(value=None):
    return value if isinstance(value, RunConstraints) else RunConstraints.model_validate(value or {})


def apply_run_constraints(catalog: list[dict], constraints=None) -> list[dict]:
    """Tighten candidate bounds before optimization without mutating Commerce input."""
    limits = constraints_model(constraints)
    result = []
    for product in catalog:
        row = dict(product)
        if limits.max_change_pct is not None:
            row["max_change_pct"] = min(float(row["max_change_pct"]), limits.max_change_pct)
        floor = limits.category_floors.get(row["category"])
        ceiling = limits.category_ceilings.get(row["category"])
        if floor is not None:
            row["min_price"] = format(max(Decimal(str(row["min_price"])), Decimal(floor)), ".2f")
        if ceiling is not None:
            row["max_price"] = format(min(Decimal(str(row["max_price"])), Decimal(ceiling)), ".2f")
        result.append(row)
    return result


def constraint_rules(product: dict, price: Decimal, constraints=None) -> list[dict]:
    """Extra absolute vetoes reused for register, human edits, dispatch, and revert."""
    limits = constraints_model(constraints)
    rules = []
    if limits.max_change_pct is not None:
        delta = abs(price - Decimal(str(product["current_price"]))) / Decimal(str(product["current_price"]))
        rules.append({"rule": "run_max_change", "passed": delta <= Decimal(str(limits.max_change_pct)),
                      "actual": float(delta), "threshold": limits.max_change_pct,
                      "message": "The candidate must respect this run's maximum price-change fraction."})
    for mapping, rule, is_floor in ((limits.category_floors, "run_category_floor", True),
                                     (limits.category_ceilings, "run_category_ceiling", False)):
        value = mapping.get(product["category"])
        if value is not None:
            passed = price >= Decimal(value) if is_floor else price <= Decimal(value)
            rules.append({"rule": rule, "passed": passed, "actual": str(price), "threshold": value,
                          "message": "The candidate must respect this run's category price bound."})
    return rules
