"""Bound multipart request bytes before parsing, including requests without Content-Length."""

from starlette.formparsers import MultiPartException
from starlette.responses import JSONResponse

MAX_FILE_BYTES = 2_000_000
MAX_REQUEST_BYTES = MAX_FILE_BYTES + 64_000


class UploadBodyTooLarge(MultiPartException):
    """Also triggers Starlette's multipart temporary-file cleanup."""


class GroundingUploadLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if not (scope["type"] == "http" and scope.get("method") == "POST"
                and scope.get("path", "").rstrip("/") == "/api/grounding/uploads"):
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        try:
            length = int(headers.get(b"content-length", b"0"))
            if length < 0:
                raise ValueError
        except ValueError:
            return await JSONResponse({"detail": "Invalid upload request length."}, status_code=400)(scope, receive, send)
        if length > MAX_REQUEST_BYTES:
            return await self._reject(scope, receive, send)
        size, started = 0, False

        async def bounded_receive():
            nonlocal size
            message = await receive()
            if message["type"] == "http.request":
                size += len(message.get("body", b""))
                if size > MAX_REQUEST_BYTES:
                    scope.setdefault("state", {})["grounding_upload_too_large"] = True
                    raise UploadBodyTooLarge("Upload exceeds the allowed request size.")
            return message

        async def tracked_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, bounded_receive, tracked_send)
        except UploadBodyTooLarge:
            if started:
                raise
            await self._reject(scope, receive, send)

    @staticmethod
    async def _reject(scope, receive, send):
        response = JSONResponse({"detail": "Upload is too large. Choose a file no larger than 2MB."}, status_code=413)
        await response(scope, receive, send)
