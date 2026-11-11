"""Explicit provider selection: local failure never sends documents to a gateway."""

from platform_app.config import Settings


def create_embedder(settings: Settings):
    from platform_app.rag.embeddings import EmbeddingUnavailable, GatewayEmbedder, LocalMiniLM

    if settings.embedding_provider == "local":
        return LocalMiniLM(settings.embedding_path, settings=settings)
    if not settings.allow_gateway_embeddings:
        raise EmbeddingUnavailable(
            "Gateway embeddings require ALLOW_GATEWAY_EMBEDDINGS=true. "
            "This opt-in permits document text to leave the local machine for the configured gateway.")
    if not settings.gateway_embedding_model or not settings.gateway_embedding_model.strip():
        raise EmbeddingUnavailable("Set RAG_GATEWAY_EMBEDDING_MODEL to a nonblank configured gateway alias.")
    return GatewayEmbedder(settings, model=settings.gateway_embedding_model,
                           dimensions=settings.gateway_embedding_dimensions, allow_external=True)


def create_store(settings: Settings):
    from platform_app.rag.store import RagStore

    return RagStore(settings.data_dir / "chroma", create_embedder(settings),
                    chunk_size=settings.rag_chunk_size, chunk_overlap=settings.rag_chunk_overlap,
                    role_breadths=settings.retrieval_breadths)
