"""Local pricing platform application with explicit startup and shutdown ownership."""

from contextlib import asynccontextmanager
import time

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from platform_app.api import router
from platform_app.commerce_client import CommerceClient, CommerceUnavailable
from platform_app.config import Settings, tls_context
from platform_app.runs import RunManager
from platform_app.storage import Store
from platform_app.telemetry import Telemetry


def create_app(settings: Settings | None = None, commerce_transport=None) -> FastAPI:
    config = settings or Settings.from_environment()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        tls_context(config)
        app.state.settings = config
        app.state.store = Store(config.data_dir)
        app.state.commerce = CommerceClient(config.commerce_url, commerce_transport)
        app.state.runs = RunManager(config, app.state.store, app.state.commerce)
        app.state.telemetry = Telemetry(config.data_dir)
        try:
            yield
        finally:
            await app.state.runs.stop()
            app.state.telemetry.close()

    application = FastAPI(title="Retail Pricing Platform", version="0.1.0", lifespan=lifespan)
    application.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
                               allow_methods=["GET", "POST", "PATCH"], allow_headers=["Content-Type"])

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
        response = await call_next(request)
        # Do not log URLs/query/body: user input and credentials must never enter telemetry.
        request.app.state.telemetry.response(request.method, response.status_code,
                                             round((time.perf_counter() - start) * 1000, 2))
        return response

    application.include_router(router)
    return application


app = create_app()
