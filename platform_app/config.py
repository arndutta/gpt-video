"""Validated configuration and memory-only gateway credentials."""

import os
import ssl
import warnings
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator, model_validator
from platform_app.constraints import RunConstraints


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    data_dir: Path = Path("data")
    startup_mode: Literal["preview", "grounded"] = "preview"
    commerce_url: str = "http://127.0.0.1:8001"
    gateway_url: str | None = None
    gateway_port: int | None = Field(default=None, ge=1, le=65535)
    api_key: SecretStr | None = Field(default=None, exclude=True, repr=False)
    allow_insecure_tls: bool = False
    verify_tls: bool = True
    model_analyst: str | None = None
    model_strategist: str | None = None
    live_competitor_enabled: bool = False
    live_competitor_url: str | None = None
    model_router: str | None = None
    model_narrator: str | None = None
    pricing_model_router: str | None = Field(default=None, max_length=200)
    pricing_model_narrator: str | None = Field(default=None, max_length=200)
    pricing_model_analyst: str | None = Field(default=None, max_length=200)
    pricing_model_strategist: str | None = Field(default=None, max_length=200)
    llm_timeout_seconds: float = Field(default=60, ge=1, le=300)
    llm_transport_retries: int = Field(default=2, ge=0, le=4)
    llm_input_cost_per_million: float = Field(default=0.10, ge=0, le=10000)
    llm_output_cost_per_million: float = Field(default=0.40, ge=0, le=10000)
    langfuse_enabled: bool = False
    langfuse_host: str | None = None
    langfuse_public_key: SecretStr | None = Field(default=None, exclude=True, repr=False)
    langfuse_secret_key: SecretStr | None = Field(default=None, exclude=True, repr=False)
    embedding_provider: Literal["local", "gateway"] = "local"
    embedding_cache_dir: Path | None = None
    gateway_embedding_model: str | None = None
    gateway_embedding_dimensions: int = Field(default=384, ge=1, le=8192)
    allow_gateway_embeddings: bool = False
    rag_chunk_size: int = Field(default=700, ge=64, le=10000)
    rag_chunk_overlap: int = Field(default=100, ge=0, le=1000)
    rag_router_top_k: int = Field(default=1, ge=1, le=10)
    rag_narrator_top_k: int = Field(default=2, ge=1, le=10)
    rag_analyst_top_k: int = Field(default=3, ge=1, le=10)
    rag_strategist_top_k: int = Field(default=4, ge=1, le=10)

    @model_validator(mode="after")
    def valid_chunk_window(self):
        if self.rag_chunk_overlap >= self.rag_chunk_size:
            raise ValueError("RAG chunk overlap must be smaller than the chunk size")
        return self

    @property
    def retrieval_breadths(self) -> dict[str, int]:
        return {role: getattr(self, f"rag_{role}_top_k")
                for role in ("router", "narrator", "analyst", "strategist")}

    @property
    def embedding_path(self) -> Path:
        return self.embedding_cache_dir or self.data_dir / "models"

    @field_validator("commerce_url", "gateway_url", "langfuse_host", "live_competitor_url")
    @classmethod
    def validate_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlsplit(value)
        try:
            valid_port = parsed.port is None or 1 <= parsed.port <= 65535
        except ValueError:
            valid_port = False
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username or parsed.password or parsed.query
                or parsed.fragment or not valid_port):
            raise ValueError("Use an HTTP(S) URL without credentials, query, or fragment")
        return value.rstrip("/")

    @classmethod
    def from_environment(cls) -> "Settings":
        mapping = {
            "DATA_DIR": "data_dir", "COMMERCE_URL": "commerce_url",
            "PRICING_STARTUP_MODE": "startup_mode",
            "GATEWAY_URL": "gateway_url", "GATEWAY_PORT": "gateway_port",
            "GATEWAY_API_KEY": "api_key", "ALLOW_INSECURE_TLS": "allow_insecure_tls",
            "LIVE_COMPETITOR_ENABLED": "live_competitor_enabled", "LIVE_COMPETITOR_URL": "live_competitor_url",
            "LLM_MODEL_ANALYST": "model_analyst", "LLM_MODEL_STRATEGIST": "model_strategist",
            "LLM_MODEL_ROUTER": "model_router", "LLM_MODEL_NARRATOR": "model_narrator",
            **{f"LLM_PRICING_MODEL_{role.upper()}": f"pricing_model_{role}"
               for role in ("router", "narrator", "analyst", "strategist")},
            "LLM_TIMEOUT_SECONDS": "llm_timeout_seconds", "LLM_TRANSPORT_RETRIES": "llm_transport_retries",
            "LLM_INPUT_COST_PER_MILLION": "llm_input_cost_per_million",
            "LLM_OUTPUT_COST_PER_MILLION": "llm_output_cost_per_million",
            "LANGFUSE_ENABLED": "langfuse_enabled", "LANGFUSE_HOST": "langfuse_host",
            "LANGFUSE_PUBLIC_KEY": "langfuse_public_key", "LANGFUSE_SECRET_KEY": "langfuse_secret_key",
            "RAG_EMBEDDING_PROVIDER": "embedding_provider", "RAG_MODEL_CACHE_DIR": "embedding_cache_dir",
            "RAG_GATEWAY_EMBEDDING_MODEL": "gateway_embedding_model",
            "RAG_GATEWAY_EMBEDDING_DIMENSIONS": "gateway_embedding_dimensions",
            "ALLOW_GATEWAY_EMBEDDINGS": "allow_gateway_embeddings",
            "RAG_CHUNK_SIZE": "rag_chunk_size", "RAG_CHUNK_OVERLAP": "rag_chunk_overlap",
            **{f"RAG_{role.upper()}_TOP_K": f"rag_{role}_top_k"
               for role in ("router", "narrator", "analyst", "strategist")},
        }
        try:
            return cls(**{field: os.environ[name] for name, field in mapping.items()
                          if os.environ.get(name)})
        except ValidationError as error:
            fields = sorted({str(item["loc"][0]) if item["loc"] else "configuration"
                             for item in error.errors()})
            raise ValueError("Invalid environment settings for: " + ", ".join(fields)
                             + ". Check URLs, ports, and booleans; secret values are omitted.") from None

    @property
    def gateway_base_url(self) -> str | None:
        if not self.gateway_url:
            return None
        parsed = urlsplit(self.gateway_url)
        host = parsed.hostname or ""
        if ":" in host:
            host = f"[{host}]"
        port = self.gateway_port or parsed.port
        return urlunsplit((parsed.scheme, host + (f":{port}" if port else ""),
                           parsed.path, "", ""))

    def public(self) -> dict:
        from platform_app.llm.safety import redact
        result = {
            "gateway_url": self.gateway_url or "", "gateway_port": self.gateway_port,
            "key_configured": self.api_key is not None,
            "verify_tls": self.verify_tls, "allow_insecure_tls": self.allow_insecure_tls,
            "models": {role: getattr(self, f"model_{role}")
                       for role in ("router", "narrator", "analyst", "strategist")},
            "pricing_models": {role: getattr(self, f"pricing_model_{role}")
                               for role in ("router", "narrator", "analyst", "strategist")},
            "cache": {"hits": 0, "misses": 0, "available": False}, "mode": "supervised",
        }
        secrets = [value.get_secret_value() for value in (self.api_key, self.langfuse_public_key, self.langfuse_secret_key) if value]
        return redact(result, secrets)


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    gateway_url: str | None = None
    gateway_port: int | None = Field(default=None, ge=1, le=65535)
    api_key: SecretStr | None = Field(default=None, repr=False)
    verify_tls: bool | None = None
    model_router: str | None = Field(default=None, max_length=200)
    model_narrator: str | None = Field(default=None, max_length=200)
    model_analyst: str | None = Field(default=None, max_length=200)
    model_strategist: str | None = Field(default=None, max_length=200)
    pricing_model_router: str | None = Field(default=None, max_length=200)
    pricing_model_narrator: str | None = Field(default=None, max_length=200)
    pricing_model_analyst: str | None = Field(default=None, max_length=200)
    pricing_model_strategist: str | None = Field(default=None, max_length=200)


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["quantitative_preview", "grounded"] = "quantitative_preview"
    category: str | None = Field(default=None, max_length=100)
    sku_ids: list[str] | None = Field(default=None, min_length=1, max_length=500)
    objective: Literal["balanced", "revenue", "margin"] = "balanced"
    iterations: int = Field(default=1000, ge=100, le=5000)
    seed: int = Field(default=42, ge=0, le=2**32 - 1)
    horizon_days: int = Field(default=14, ge=1, le=90)
    constraints: RunConstraints | None = None


class ScenarioRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sku: str = Field(min_length=1, max_length=100)
    candidate_price: str = Field(pattern=r"^\d{1,8}(?:\.\d{1,2})?$")
    iterations: int = Field(default=1000, ge=100, le=5000)
    seed: int = Field(default=42, ge=0, le=2**32 - 1)
    horizon_days: int = Field(default=14, ge=1, le=90)


def tls_context(settings: Settings) -> ssl.SSLContext:
    """One TLS policy for all backend outbound clients."""
    if not settings.verify_tls:
        if not settings.allow_insecure_tls:
            raise ValueError("Disable verification requires ALLOW_INSECURE_TLS=true")
        warnings.warn("TLS verification disabled for the configured corporate gateway", stacklevel=2)
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context
    cafile = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
    return ssl.create_default_context(cafile=cafile)
