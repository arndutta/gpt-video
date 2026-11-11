"""Best-effort local JSONL operational metadata. Never records request content."""

from pathlib import Path
import queue
import threading
import time

import structlog


class Telemetry:
    def __init__(self, data_dir: Path):
        self._stream = None
        self._lock = threading.Lock()
        self.available = True
        self._queue = queue.Queue(maxsize=2048)
        self.dropped = 0
        try:
            self._stream = (data_dir / "telemetry.jsonl").open("a", encoding="utf-8", buffering=1)
        except OSError:
            self.available = False
        self._worker = threading.Thread(target=self._consume, daemon=True, name="local-telemetry")
        self._worker.start()

    def response(self, method: str, status: int, latency_ms: float):
        # A fixed metadata allowlist makes URL/body/secret leakage impossible at this callsite.
        self.event("http_response", method=method, status=status, latency_ms=latency_ms)

    def event(self, event: str, **metadata):
        allowed = {"method", "status", "latency_ms", "run_id", "agent", "model", "cache",
                   "tokens_in", "tokens_out", "cost_usd", "operation", "attempt", "error_code",
                   "pricing_source", "pricing_model"}
        item = {"event": event[:80], "timestamp": time.time(),
                **{key: value for key, value in metadata.items() if key in allowed
                   and isinstance(value, (str, int, float, bool, type(None)))}}
        try:
            self._queue.put_nowait(item)
        except queue.Full:
            self.dropped += 1

    def _consume(self):
        while True:
            event = self._queue.get()
            if event is None:
                return
            self._write(event)

    def _write(self, event):
        try:
            encoded = structlog.processors.JSONRenderer()(None, "info", event)
            with self._lock:
                if self._stream and not self._stream.closed:
                    self._stream.write(encoded + "\n")
        except Exception:
            self.available = False

    def close(self):
        if self._worker.is_alive():
            try:
                self._queue.put(None, timeout=.2)
                self._worker.join(timeout=2)
            except queue.Full:
                self.available = False
            if self._worker.is_alive():
                self.available = False
                return
        try:
            with self._lock:
                if self._stream:
                    self._stream.close()
        except OSError:
            self.available = False
