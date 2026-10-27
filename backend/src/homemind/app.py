"""M3 liveness, authenticated household APIs and explicit database boundary."""

from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from homemind import __version__
from homemind.agent.model import DeepSeekModel
from homemind.agent.routes import agent_router
from homemind.auth import AttemptLimiter, auth_router, authenticate, protect_write, require_home
from homemind.config import Settings
from homemind.persistence.database import Database
from homemind.preferences import preferences_router
from homemind.simulation.models import SimulationError
from homemind.simulation.routes import simulation_router
from homemind.tasks import tasks_router


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["homemind-api"] = "homemind-api"
    version: str = __version__
    stage: Literal["M4"] = "M4"


def error_response(error):
    return JSONResponse(
        status_code=error.status,
        content={"detail": {"code": error.code, "message": error.message}},
        headers={"Cache-Control": "no-store"},
    )


def create_app(settings: Settings | None = None, *, database: Database | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application):
        configured = application.state.database
        application.state.database_startup_ready = False
        if configured is not None:
            try:
                await configured.ready()
                application.state.database_startup_ready = True
            except SimulationError:
                # Liveness remains available; protected requests recheck and return503.
                pass
        try:
            yield
        finally:
            if configured is not None:
                await configured.close()

    app = FastAPI(title="HomeMind", version=__version__, lifespan=lifespan)
    app.state.settings = settings if settings is not None else Settings()
    config = app.state.settings
    app.state.agent_model = (
        DeepSeekModel(config)
        if config.model_enabled and config.model_api_key and config.model_api_key.get_secret_value()
        else None
    )
    app.state.database = database
    if database is None and config.database_url and config.database_instance_id:
        app.state.database = Database(
            config.database_url.get_secret_value(), instance_id=config.database_instance_id
        )
    app.state.attempts = AttemptLimiter()

    @app.middleware("http")
    async def household_boundary(request: Request, call_next):
        if request.url.path.startswith(("/auth", "/simulation", "/preferences", "/tasks")):
            try:
                if app.state.database is None:
                    raise SimulationError(503, "database_unavailable", "请先配置并迁移本项目数据库")
                await app.state.database.ready()
                await authenticate(request)
                if request.url.path.startswith(("/simulation", "/preferences", "/tasks")):
                    require_home(request)
                if request.method not in {"GET", "HEAD", "OPTIONS"}:
                    await protect_write(request)
            except SimulationError as error:
                return error_response(error)
            except SQLAlchemyError:
                return error_response(
                    SimulationError(503, "database_unavailable", "数据库暂不可用，请稍后重试")
                )
        response = await call_next(request)
        if request.url.path.startswith(("/auth", "/simulation", "/preferences", "/tasks")):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(SimulationError)
    async def simulation_error(_request: Request, error: SimulationError):
        return error_response(error)

    @app.exception_handler(SQLAlchemyError)
    async def database_error(_request: Request, _error):
        return error_response(
            SimulationError(503, "database_unavailable", "数据库暂不可用，请稍后重试")
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, _error: RequestValidationError):
        return error_response(
            SimulationError(422, "invalid_request", "请求字段、类型或参数范围不合法")
        )

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    def health():
        return HealthResponse()

    app.include_router(auth_router())
    app.include_router(preferences_router())
    app.include_router(simulation_router())
    app.include_router(agent_router())
    app.include_router(tasks_router())
    return app
