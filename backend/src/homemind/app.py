"""API liveness and the development-only, process-local M2 simulation."""

from typing import Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from homemind import __version__
from homemind.config import Settings
from homemind.simulation.models import SimulationError
from homemind.simulation.routes import simulation_router
from homemind.simulation.service import SimulationService


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["homemind-api"] = "homemind-api"
    version: str = __version__
    stage: Literal["M2"] = "M2"


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="HomeMind", version=__version__)
    app.state.settings = settings if settings is not None else Settings()

    @app.exception_handler(SimulationError)
    async def simulation_error(_request: Request, error: SimulationError) -> JSONResponse:
        return JSONResponse(
            status_code=error.status,
            content={"detail": {"code": error.code, "message": error.message}},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, _error: RequestValidationError) -> JSONResponse:
        # Do not echo raw inputs (including non-finite JSON numbers) or stack traces.
        return JSONResponse(
            status_code=422,
            content={
                "detail": {"code": "invalid_request", "message": "请求字段、类型或参数范围不合法"}
            },
        )

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        """Report API liveness without querying external services."""
        return HealthResponse()

    if app.state.settings.environment != "production":
        app.state.simulation = SimulationService()
        app.include_router(simulation_router(app.state.simulation))

    return app
