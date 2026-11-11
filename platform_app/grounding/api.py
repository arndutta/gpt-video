"""Runtime upload/status/statistics endpoints backed by the T14 knowledge store."""

import asyncio
import hashlib
from pathlib import PurePosixPath
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.formparsers import MultiPartException

from platform_app.grounding.limits import MAX_FILE_BYTES, UploadBodyTooLarge
from platform_app.grounding.multipart import upload_form
from platform_app.rag.models import Document

router = APIRouter(prefix="/api/grounding", tags=["Knowledge grounding"])
UPLOAD_FIELDS = {"file", "collection", "source_id", "title", "version"}
UPLOAD_ORIGINS = {"http://127.0.0.1:5173", "http://localhost:5173",
                  "http://127.0.0.1:8000", "http://localhost:8000"}


class RetrievalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=4000)
    role: Literal["router", "narrator", "analyst", "strategist"] = "analyst"


@router.get("/collections")
async def collections(request: Request):
    return await request.app.state.grounding.collections()


def _filename(name: str | None) -> str:
    if not name:
        raise HTTPException(422, "Choose a named text or Markdown file.")
    leaf = name.replace("\\", "/").split("/")[-1]
    if leaf in {"", ".", ".."} or len(leaf) > 255 or any(ord(char) < 32 for char in leaf):
        raise HTTPException(422, "The document filename is invalid.")
    if PurePosixPath(leaf).suffix.lower() not in {".txt", ".md"}:
        raise HTTPException(415, "Supported document formats are UTF-8 .txt and .md files.")
    return leaf


def _document(form, name: str, text: str) -> Document:
    for key in UPLOAD_FIELDS - {"file"}:
        if key in form and not isinstance(form[key], str):
            raise HTTPException(422, "Upload metadata must contain text fields only.")
    source_id = form.get("source_id") or "upload-" + hashlib.sha256(name.encode()).hexdigest()[:24]
    try:
        return Document(source_id=source_id, title=form.get("title") or PurePosixPath(name).stem,
                        text=text, collection=form.get("collection") or "user_uploads",
                        version=form.get("version") or None, source_uri=name)
    except ValidationError as error:
        fields = ", ".join(sorted({str(item["loc"][0]) for item in error.errors()}))
        raise HTTPException(422, f"Invalid document fields: {fields}. Check their length and format.") from None


@router.post("/uploads", status_code=202)
async def upload(request: Request):
    # CORS controls response access, not whether a simple cross-site form can submit.
    # CLI clients omit Origin; browser writes must come from this local application.
    if request.headers.get("origin") is not None and request.headers["origin"] not in UPLOAD_ORIGINS:
        raise HTTPException(403, "Document uploads must originate from the local pricing application.")
    media_type = request.headers.get("content-type", "").partition(";")[0].strip().lower()
    if media_type != "multipart/form-data":
        raise HTTPException(415, "Upload the document as multipart/form-data.")
    try:
        async with upload_form(request) as form:
            if set(form) - UPLOAD_FIELDS or any(len(form.getlist(key)) != 1 for key in form):
                raise HTTPException(422, "Use one file and only the supported document metadata fields.")
            file = form.get("file")
            if not isinstance(file, UploadFile):
                raise HTTPException(422, "A document file is required.")
            name = _filename(file.filename)
            content = await file.read(MAX_FILE_BYTES + 1)
            if len(content) > MAX_FILE_BYTES:
                raise HTTPException(413, "Upload is too large. Choose a file no larger than 2MB.")
            try:
                text = content.decode("utf-8-sig")
            except UnicodeError:
                raise HTTPException(422, "The document must use UTF-8 text encoding.") from None
            if not text.strip() or "\x00" in text:
                raise HTTPException(422, "The document must contain nonempty, readable text.")
            document = _document(form, name, text)
        return await asyncio.to_thread(request.app.state.grounding.submit, document, name)
    except (MultiPartException, StarletteHTTPException) as error:
        if isinstance(error, UploadBodyTooLarge) or getattr(request.state, "grounding_upload_too_large", False):
            raise HTTPException(413, "Upload is too large. Choose a file no larger than 2MB.") from None
        if isinstance(error, HTTPException):
            raise
        raise HTTPException(422, "Invalid multipart upload. Choose one document and supported metadata fields.") from None


@router.get("/uploads")
async def uploads(request: Request, limit: int = Query(25, ge=1, le=100)):
    return {"items": await asyncio.to_thread(request.app.state.grounding.list_uploads, limit)}


@router.get("/uploads/{upload_id}")
async def upload_status(upload_id: str, request: Request):
    result = await asyncio.to_thread(request.app.state.grounding.get_upload, upload_id)
    if result is None:
        raise HTTPException(404, "Document upload not found.")
    return result


@router.post("/retrieve")
async def retrieve(payload: RetrievalRequest, request: Request):
    if not payload.query.strip():
        raise HTTPException(422, "Enter a nonempty retrieval query.")
    result = await request.app.state.grounding.retrieve(payload.query, payload.role)
    return result.model_dump(mode="json")


@router.get("/citations/{citation_id}")
async def citation(citation_id: str, request: Request):
    result = await request.app.state.grounding.citation(citation_id)
    return result.model_dump(mode="json")
