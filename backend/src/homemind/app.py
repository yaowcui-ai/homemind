"""API liveness only; model, database and devices belong to later stages."""

from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from homemind import __version__
from homemind.config import Settings


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["homemind-api"] = "homemind-api"
    version: str = __version__
    stage: Literal["M1"] = "M1"


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="HomeMind", version=__version__)
    app.state.settings = settings if settings is not None else Settings()

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        """Report API liveness without querying external services."""
        return HealthResponse()

    return app
