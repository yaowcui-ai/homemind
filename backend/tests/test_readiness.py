"""Readiness must check database ownership/revision without minting sessions."""

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from homemind.app import create_app
from homemind.config import Settings
from homemind.simulation.models import SimulationError


def settings():
    return Settings(_env_file=None, model_enabled=False)


def test_readiness_rejects_missing_database_while_liveness_stays_available():
    with TestClient(create_app(settings())) as client:
        assert client.get("/health").status_code == 200
        response = client.get("/ready")
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "database_unavailable"


def test_readiness_rechecks_database_and_never_sets_session_cookie():
    database = AsyncMock()
    with TestClient(create_app(settings(), database=database)) as client:
        database.ready.reset_mock()
        for _ in range(2):
            response = client.get("/ready")
            assert response.status_code == 200
            assert response.json() == {"status": "ready"}
            assert "set-cookie" not in response.headers
        assert database.ready.await_count == 2


def test_readiness_detects_database_loss_after_startup_without_leaking_details():
    database = AsyncMock()
    with TestClient(create_app(settings(), database=database)) as client:
        database.ready.side_effect = SimulationError(503, "database_unavailable", "数据库未就绪")
        response = client.get("/ready")
        assert response.status_code == 503
        assert "set-cookie" not in response.headers
        assert client.get("/health").status_code == 200
