"""Validated configuration and memory-only gateway credentials."""

import os
import ssl
import warnings
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    data_dir: Path = Path("data")
    commerce_url: str = "http://127.0.0.1:8001"
    gateway_url: str | None = None
    gateway_port: int | None = Field(default=None, ge=1, le=65535)
    api_key: SecretStr | None = Field(default=None, exclude=True, repr=False)
    allow_insecure_tls: bool = False
    verify_tls: bool = True
    model_analyst: str | None = None
    model_strategist: str | None = None

    @field_validator("commerce_url", "gateway_url")
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
            "GATEWAY_URL": "gateway_url", "GATEWAY_PORT": "gateway_port",
            "GATEWAY_API_KEY": "api_key", "ALLOW_INSECURE_TLS": "allow_insecure_tls",
            "LLM_MODEL_ANALYST": "model_analyst", "LLM_MODEL_STRATEGIST": "model_strategist",
        }
        try:
            return cls(**{field: os.environ[name] for name, field in mapping.items()
                          if os.environ.get(name)})
        except ValidationError as error:
            fields = sorted({str(item["loc"][0]) for item in error.errors()})
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
        return {
            "gateway_url": self.gateway_url or "", "gateway_port": self.gateway_port,
            "key_configured": self.api_key is not None,
            "verify_tls": self.verify_tls, "allow_insecure_tls": self.allow_insecure_tls,
            "models": {"analyst": self.model_analyst, "strategist": self.model_strategist},
            "cache": {"hits": 0, "misses": 0, "available": False}, "mode": "supervised",
        }


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    gateway_url: str | None = None
    gateway_port: int | None = Field(default=None, ge=1, le=65535)
    api_key: SecretStr | None = Field(default=None, repr=False)
    verify_tls: bool | None = None


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: str | None = Field(default=None, max_length=100)
    sku_ids: list[str] | None = Field(default=None, max_length=500)
    objective: Literal["balanced", "revenue", "margin"] = "balanced"
    iterations: int = Field(default=1000, ge=100, le=5000)
    seed: int = Field(default=42, ge=0, le=2**32 - 1)
    horizon_days: int = Field(default=14, ge=1, le=90)


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
