"""T14 command-line ingestion/retrieval; browser uploads are a separate T15 feature."""

import argparse
import json
from pathlib import Path
import sys

from pydantic import ValidationError

from platform_app.config import Settings
from platform_app.rag.factory import create_embedder, create_store


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--data-dir", type=Path, help="Override DATA_DIR for an isolated knowledge store")
    sub = result.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="Check local availability offline; explicitly selected gateway uses a probe")
    sub.add_parser("prepare", help="Download and verify the local embedding model once")
    sub.add_parser("migrate", help="Move legacy Chroma evidence into SQLite without reembedding; stop the app first")
    ingest = sub.add_parser("ingest", help="Ingest a UTF-8 .txt or .md document")
    ingest.add_argument("file", type=Path)
    ingest.add_argument("--source-id", required=True, help="Stable identifier used across document versions")
    ingest.add_argument("--title")
    ingest.add_argument("--version")
    ingest.add_argument("--collection", choices=["pricing_policy", "market_intel", "product_kb", "user_uploads"],
                        default="user_uploads")
    query = sub.add_parser("query", help="Retrieve citable evidence from every knowledge collection")
    query.add_argument("query")
    query.add_argument("--role", choices=["router", "narrator", "analyst", "strategist"], default="analyst")
    citation = sub.add_parser("citation", help="Resolve an immutable citation, including an older version")
    citation.add_argument("citation_id")
    sub.add_parser("collections", help="Inspect persisted collection counts")
    return result


def main(argv=None) -> int:
    options = parser()
    args = options.parse_args(argv)
    store = None
    try:
        settings = Settings.from_environment()
        if args.data_dir:
            settings = settings.model_copy(update={"data_dir": args.data_dir})
        if args.command == "migrate":
            from platform_app.rag.migration import migrate_chroma

            print(json.dumps(migrate_chroma(settings.data_dir), indent=2))
            return 0
        embedder = create_embedder(settings)
        if args.command == "check":
            report = embedder.check()
            print(json.dumps(report, indent=2))
            return 0 if report.get("available") else 1
        if args.command == "prepare":
            if settings.embedding_provider != "local":
                options.error("prepare only downloads the local provider; use check for an opted-in gateway")
            print(json.dumps(embedder.prepare(), indent=2))
            return 0
        from platform_app.rag.models import Document

        store = create_store(settings)
        if args.command == "ingest":
            if args.file.suffix.lower() not in {".txt", ".md"}:
                options.error("T14 accepts UTF-8 .txt and .md files")
            if args.file.stat().st_size > 2_000_000:
                options.error("Document exceeds the initial 2MB ingestion limit")
            document = Document(source_id=args.source_id, title=args.title or args.file.stem,
                                collection=args.collection, text=args.file.read_text(encoding="utf-8"),
                                version=args.version, source_uri=args.file.name)
            report = store.ingest(document).model_dump(mode="json")
        elif args.command == "query":
            report = store.retrieve(args.query, role=args.role).model_dump(mode="json")
        elif args.command == "citation":
            report = store.resolve_citation(args.citation_id).model_dump(mode="json")
        else:
            report = {"collections": store.collections()}
        print(json.dumps(report, indent=2))
        return 0
    except ValidationError as error:
        # Validation errors can include document content by default; never echo their inputs.
        fields = sorted({".".join(map(str, item["loc"])) or "document" for item in error.errors()})
        print("RAG input validation failed for: " + ", ".join(fields), file=sys.stderr)
        return 1
    except Exception as error:
        from platform_app.rag.embeddings import EmbeddingUnavailable
        from platform_app.rag.models import RagError

        if isinstance(error, (EmbeddingUnavailable, RagError)):
            message = str(error)
        elif isinstance(error, (OSError, UnicodeError)):
            message = "Cannot read the document or write local RAG storage. Check UTF-8 encoding and permissions."
        else:
            message = "RAG operation failed. Check dependencies, embedding readiness, and storage permissions."
        print(message, file=sys.stderr)
        return 1
    finally:
        if store is not None:
            store.close()


if __name__ == "__main__":
    raise SystemExit(main())
