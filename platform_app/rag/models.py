"""Document and evidence contracts for local retrieval; retrieved text is untrusted data."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

COLLECTION_NAMES = ("pricing_policy", "market_intel", "product_kb", "user_uploads")
CollectionName = Literal["pricing_policy", "market_intel", "product_kb", "user_uploads"]
DEFAULT_ROLE_BREADTHS = {"router": 1, "narrator": 2, "analyst": 3, "strategist": 4}


class RagError(RuntimeError):
    """Actionable retrieval failure that never substitutes fabricated context."""


class DocumentConflict(RagError):
    """An immutable source version conflicts with supplied evidence."""


class GroundingUnavailable(RagError):
    """No usable evidence is available for the requested reasoning context."""


class CitationNotFound(RagError):
    """A citation does not resolve to published immutable evidence."""


class EmbeddingMismatch(RagError):
    """A store cannot mix embedding models or vector dimensions."""


class Document(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    title: str = Field(min_length=1, max_length=256)
    text: str = Field(min_length=1, max_length=2_000_000)
    collection: CollectionName
    source_uri: str | None = Field(default=None, max_length=2048)
    version: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("title", "text", "version")
    @classmethod
    def meaningful_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Document fields must contain non-whitespace text")
        return value


class EvidenceChunk(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    citation_id: str
    source_id: str
    title: str
    source_uri: str | None = None
    collection: CollectionName
    version: str
    chunk_index: int = Field(ge=0)
    text: str
    start_char: int = Field(ge=0)
    end_char: int = Field(gt=0)
    distance: float | None = None


class IngestResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_id: str
    collection: CollectionName
    version: str
    chunk_count: int
    corpus_version: int
    changed: bool


class RetrievalContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    query: str
    role: str
    corpus_version: int
    chunks: list[EvidenceChunk] = Field(min_length=1)
