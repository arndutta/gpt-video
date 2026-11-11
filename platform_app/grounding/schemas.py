"""Safe, public failures for runtime grounding APIs."""


class GroundingServiceError(RuntimeError):
    """A fixed message and status, never a raw SDK exception or document excerpt."""

    def __init__(self, code: str, detail: str, status_code: int = 503):
        super().__init__(detail)
        self.code, self.detail, self.status_code = code, detail, status_code


LOCAL_PREPARE_COMMAND = ".venv/bin/python -m scripts.rag prepare"
LOCAL_UNAVAILABLE = (
    "Local embedding model is unavailable or corrupt. "
    "Run python -m scripts.rag prepare using the project's virtual environment."
)
