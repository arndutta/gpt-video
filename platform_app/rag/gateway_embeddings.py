"""Explicitly selected gateway embeddings; local failures never enable external egress."""

import httpx

from platform_app.config import Settings, tls_context
from platform_app.rag.embedding_common import EmbeddingUnavailable, validate_texts, validate_vectors


class GatewayEmbedder:
    def __init__(self, settings: Settings, *, model: str, dimensions: int,
                 allow_external: bool = False, transport=None):
        if not allow_external:
            raise EmbeddingUnavailable("Gateway embeddings are disabled. Explicit external-embedding opt-in is required.")
        if not isinstance(model, str) or not model.strip() or type(dimensions) is not int or not 1 <= dimensions <= 8192:
            raise ValueError("Gateway embeddings require a nonblank model alias and dimensions between 1 and 8192.")
        if not settings.gateway_base_url or not settings.api_key or not settings.api_key.get_secret_value():
            raise EmbeddingUnavailable("Gateway embeddings require a configured backend gateway URL and in-memory API key.")
        self.settings, self.model, self.dimensions = settings, model.strip(), dimensions
        self.transport = transport
        self.model_id = f"gateway:{settings.gateway_base_url}:{self.model}:{dimensions}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        validate_texts(texts)
        try:
            with httpx.Client(verify=tls_context(self.settings), timeout=30,
                              transport=self.transport) as client:
                response = client.post(self.settings.gateway_base_url + "/embeddings",
                                       headers={"Authorization": f"Bearer {self.settings.api_key.get_secret_value()}"},
                                       json={"model": self.model, "input": texts})
                response.raise_for_status()
                payload = response.json()
            rows = payload.get("data")
            if not isinstance(rows, list) or len(rows) != len(texts):
                raise ValueError
            indexed = {}
            for row in rows:
                if not isinstance(row, dict) or type(row.get("index")) is not int:
                    raise ValueError
                if row["index"] in indexed:
                    raise ValueError
                indexed[row["index"]] = row["embedding"]
            if set(indexed) != set(range(len(texts))):
                raise ValueError
            return validate_vectors([indexed[index] for index in range(len(texts))], len(texts), self.dimensions)
        except EmbeddingUnavailable:
            raise
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError, OSError):
            raise EmbeddingUnavailable("Gateway embedding request failed or returned an invalid contract. Check the configured alias, dimensions, TLS, and access; no local fallback was attempted.") from None

    def check(self) -> dict:
        try:
            self.embed(["Embedding readiness check."])
            available, detail = True, "Gateway embedding response and dimensions verified."
        except EmbeddingUnavailable as error:
            available, detail = False, str(error)
        return {"available": available, "provider": "gateway", "model_id": self.model_id,
                "dimensions": self.dimensions, "detail": detail}

    def prepare(self) -> dict:
        return self.check()
