"""Local all-MiniLM-L6-v2 vectors; inference never implicitly downloads a model."""

from functools import cached_property
from importlib.util import find_spec
from collections import OrderedDict
import hashlib
import os
from pathlib import Path
import threading

from platform_app.config import Settings
from platform_app.rag.embedding_common import EmbeddingUnavailable, validate_texts, validate_vectors
from platform_app.rag.embedding_download import ARCHIVE_SHA256, MODEL_FILES, cache_ready, prepare_cache


class LocalMiniLM:
    dimensions = 384
    max_tokens = 256
    model_id = "local:all-MiniLM-L6-v2:onnx:" + ARCHIVE_SHA256

    def __init__(self, cache_dir: Path, *, settings: Settings | None = None):
        self.cache_dir = Path(cache_dir)
        self.root = self.cache_dir / ARCHIVE_SHA256
        self.settings = settings or Settings()
        self._verified_snapshot = None
        self._vectors = OrderedDict()
        self._vector_lock = threading.Lock()

    def _file_snapshot(self):
        # Hash the 90MB model once per unchanged filesystem snapshot, rather than on
        # every query. ctime/inode catch replacement or edits even if mtime is restored.
        paths = [self.root / "manifest.json", *(self.root / "onnx" / name for name in MODEL_FILES)]
        return tuple((stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
                     for path in paths for stat in [path.stat()])

    def check(self) -> dict:
        dependencies = all(find_spec(name) is not None for name in ("numpy", "onnxruntime", "tokenizers"))
        ready = False
        if dependencies:
            try:
                snapshot = self._file_snapshot()
                ready = snapshot == self._verified_snapshot or cache_ready(self.root)
                self._verified_snapshot = snapshot if ready else None
            except OSError:
                self._verified_snapshot = None
        return {"available": ready, "provider": "local", "model_id": self.model_id,
                "dimensions": self.dimensions, "cache_dir": str(self.cache_dir),
                "detail": "Verified local model is ready." if ready else
                "Prepare the local embedding model and install RAG dependencies before ingestion/retrieval."}

    def prepare(self) -> dict:
        if not all(find_spec(name) is not None for name in ("numpy", "onnxruntime", "tokenizers")):
            raise EmbeddingUnavailable("RAG dependencies are missing. Install the project's locked dependencies first.")
        prepare_cache(self.cache_dir, self.settings)
        # Validate the actual runtime, not only successful file download.
        self.embed(["Embedding readiness check."])
        return self.check()

    def _require_ready(self):
        if not self.check()["available"]:
            raise EmbeddingUnavailable("Local embedding model is unavailable or corrupt. Run the explicit model preparation command first.")

    @cached_property
    def _tokenizer(self):
        self._require_ready()
        from tokenizers import Tokenizer
        tokenizer = Tokenizer.from_file(str(self.root / "onnx" / "tokenizer.json"))
        tokenizer.no_truncation()
        tokenizer.no_padding()
        return tokenizer

    def token_count(self, text: str) -> int:
        if not isinstance(text, str):
            raise ValueError("Tokenizer input must be text.")
        return len(self._tokenizer.encode(text).ids)

    @cached_property
    def _engine(self):
        # ORT's POSIX telemetry initializes at import, before its Python opt-out API.
        # This documented opt-out prevents uploader/device-ID initialization entirely.
        os.environ["ORT_DISABLE_TELEMETRY"] = "1"
        import onnxruntime
        onnxruntime.disable_telemetry_events()
        import numpy as np

        self._require_ready()
        options = onnxruntime.SessionOptions()
        options.log_severity_level = 3
        options.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
        session = onnxruntime.InferenceSession(str(self.root / "onnx" / "model.onnx"),
                                             providers=["CPUExecutionProvider"], sess_options=options)

        def encode(texts):
            result = []
            for offset in range(0, len(texts), 32):
                encodings = self._tokenizer.encode_batch(texts[offset:offset + 32])
                if any(len(item.ids) > self.max_tokens for item in encodings):
                    raise EmbeddingUnavailable("Text exceeds the local model's 256-token limit; text was not truncated.")
                # Keep the existing model's padding and pooling so migrated vectors
                # remain in the same embedding space and revision.
                ids = np.array([item.ids + [0] * (self.max_tokens - len(item.ids)) for item in encodings], dtype=np.int64)
                mask = np.array([item.attention_mask + [0] * (self.max_tokens - len(item.ids))
                                 for item in encodings], dtype=np.int64)
                hidden = session.run(None, {"input_ids": ids, "attention_mask": mask,
                                            "token_type_ids": np.zeros_like(ids)})[0]
                expanded = np.broadcast_to(mask[..., None], hidden.shape)
                pooled = (hidden * expanded).sum(axis=1) / np.maximum(expanded.sum(axis=1), 1e-9)
                norms = np.linalg.norm(pooled, axis=1, keepdims=True)
                result.extend((pooled / np.maximum(norms, 1e-12)).astype(np.float32).tolist())
            return result

        return encode

    def embed(self, texts: list[str]) -> list[list[float]]:
        validate_texts(texts)
        self._require_ready()
        try:
            if any(self.token_count(text) > self.max_tokens for text in texts):
                raise EmbeddingUnavailable("Text exceeds the local model's 256-token limit. Use smaller chunks or a shorter query; text was not truncated.")
            keys = [hashlib.sha256(text.encode()).digest() for text in texts]
            with self._vector_lock:
                found = {key: self._vectors[key] for key in keys if key in self._vectors}
            missing = list(dict.fromkeys(key for key in keys if key not in found))
            if missing:
                inputs = [texts[keys.index(key)] for key in missing]
                vectors = validate_vectors(self._engine(inputs), len(inputs), self.dimensions)
                found.update(zip(missing, vectors))
            with self._vector_lock:
                for key in keys:
                    self._vectors[key] = found[key]
                    self._vectors.move_to_end(key)
                while len(self._vectors) > 256:
                    self._vectors.popitem(last=False)
            return [list(found[key]) for key in keys]
        except EmbeddingUnavailable:
            raise
        except Exception:
            raise EmbeddingUnavailable("Local embedding inference failed. Check the verified model cache and ONNX runtime.") from None
