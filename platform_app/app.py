"""Local pricing platform application with explicit startup and shutdown ownership."""

from contextlib import asynccontextmanager
import time

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from platform_app.api import router
from platform_app.dashboard import router as dashboard_router
from platform_app.discovery import router as discovery_router
from platform_app.commerce_client import CommerceClient, CommerceUnavailable
from platform_app.config import Settings, tls_context
from platform_app.grounding.api import router as grounding_router
from platform_app.grounding.limits import GroundingUploadLimit
from platform_app.grounding.schemas import GroundingServiceError
from platform_app.grounding.service import GroundingService
from platform_app.runs import RunManager
from platform_app.storage import Store
from platform_app.telemetry import Telemetry
from platform_app.governance import GovernanceError
from platform_app.llm import GroundedLLMError
from platform_app.operations_api import router as operations_router
from platform_app.scenarios import router as scenarios_router
from platform_app.runtime import initialize, shutdown


def create_app(settings: Settings | None = None, commerce_transport=None, rag_factory=None,
               llm_provider_factory=None) -> FastAPI:
    config = settings or Settings.from_environment()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        tls_context(config)
        await initialize(app, config, commerce_transport, rag_factory, llm_provider_factory)
        try:
            yield
        finally:
            await shutdown(app.state)

    application = FastAPI(title="Retail Pricing Platform", version="0.1.0", lifespan=lifespan)
    application.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
                               allow_methods=["GET", "POST", "PATCH"], allow_headers=["Content-Type"])
    application.add_middleware(GroundingUploadLimit)

    @application.exception_handler(GovernanceError)
    async def governance_error(_request, error):
        return JSONResponse(status_code=error.status_code,
                            content={"detail": {"code": error.code, "message": error.detail}})

    @application.exception_handler(GroundedLLMError)
    async def model_error(_request, error):
        return JSONResponse(status_code=503, content={"detail": {"code": error.code, "message": error.detail}})

    @application.exception_handler(GroundingServiceError)
    async def grounding_error(_request, error):
        return JSONResponse(status_code=error.status_code,
                            content={"detail": {"code": error.code, "message": error.detail}})

    @application.exception_handler(CommerceUnavailable)
    async def commerce_error(_request, error):
        return JSONResponse(status_code=503, content={"detail": str(error)})

    @application.exception_handler(RequestValidationError)
    async def validation_error(_request, error):
        # Pydantic's default `input` field can echo a credential. Return location/message only.
        return JSONResponse(status_code=422, content={"detail": [
            {"loc": list(item["loc"]), "msg": item["msg"], "type": item["type"]}
            for item in error.errors()]})

    @application.middleware("http")
    async def timing(request: Request, call_next):
        start = time.perf_counter()
        if request.method in {"POST", "PATCH", "PUT", "DELETE"}:
            allowed = {f"http://{host}:{port}" for host in ("localhost", "127.0.0.1") for port in (5173, 8000)}
            origin = request.headers.get("origin")
            if (origin and origin not in allowed) or request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse(status_code=403, content={"detail": "Cross-site writes are not allowed."})
        response = await call_next(request)
        # Do not log URLs/query/body: user input and credentials must never enter telemetry.
        request.app.state.telemetry.response(request.method, response.status_code,
                                             round((time.perf_counter() - start) * 1000, 2))
        return response

    application.include_router(router)
    application.include_router(grounding_router)
    application.include_router(operations_router)
    application.include_router(scenarios_router)
    application.include_router(dashboard_router)
    application.include_router(discovery_router)
    return application


app = create_app()
