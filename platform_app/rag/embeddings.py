"""Public embedding-provider interface for T14 ingestion and retrieval."""

from platform_app.rag.embedding_common import EmbeddingUnavailable
from platform_app.rag.gateway_embeddings import GatewayEmbedder
from platform_app.rag.local_embeddings import LocalMiniLM

__all__ = ["EmbeddingUnavailable", "GatewayEmbedder", "LocalMiniLM"]
