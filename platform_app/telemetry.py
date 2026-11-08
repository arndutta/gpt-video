"""Best-effort local JSONL operational metadata. Never records request content."""

from pathlib import Path
import threading
import time

import structlog


class Telemetry:
    def __init__(self, data_dir: Path):
        self._stream = None
        self._lock = threading.Lock()
        self.available = True
        try:
            self._stream = (data_dir / "telemetry.jsonl").open("a", encoding="utf-8", buffering=1)
        except OSError:
            self.available = False

    def response(self, method: str, status: int, latency_ms: float):
        # A fixed metadata allowlist makes URL/body/secret leakage impossible at this callsite.
        event = {"event": "http_response", "timestamp": time.time(), "method": method,
                 "status": status, "latency_ms": latency_ms}
        try:
            encoded = structlog.processors.JSONRenderer()(None, "info", event)
            with self._lock:
                if self._stream and not self._stream.closed:
                    self._stream.write(encoded + "\n")
        except (OSError, ValueError):
            self.available = False

    def close(self):
        try:
            with self._lock:
                if self._stream:
                    self._stream.close()
        except OSError:
            self.available = False
