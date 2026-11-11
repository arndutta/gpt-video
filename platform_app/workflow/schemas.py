"""Only prose and citations are model-authored; numeric artifacts are separate."""

from typing import TypedDict
from pydantic import BaseModel, ConfigDict, Field


class CitedNarrative(BaseModel):
    model_config = ConfigDict(extra="forbid")
    interpretation: str = Field(min_length=1, max_length=6000)
    assumptions: list[str] = Field(default_factory=list, max_length=20)
    anomalies: list[str] = Field(default_factory=list, max_length=20)
    citations: list[str] = Field(min_length=1, max_length=50)


class SKUReason(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sku: str = Field(min_length=1, max_length=100)
    rationale: str = Field(min_length=1, max_length=4000)
    citations: list[str] = Field(min_length=1, max_length=30)


class StrategyNarrative(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recommendations: list[SKUReason] = Field(min_length=1, max_length=25)
    citations: list[str] = Field(min_length=1, max_length=50)


class WorkflowState(TypedDict, total=False):
    run_id: str
    request: dict
    context: dict
    competitors: list
    history: list
    family_catalog: list
    quality: dict
    data_narrative: dict
    report: dict
    quantitative_narrative: dict
    validation_narrative: dict
    item_ids: list[str]
    review_ids: list[str]
    numeric_hash: str
    execution_ready: bool
