"""Explicit SQLite fixtures for fast authenticated API tests only."""

from contextlib import contextmanager
from uuid import uuid4

import httpx
import pytest
import requests
from fastapi.testclient import TestClient

from homemind.app import create_app
from homemind.config import Settings
from homemind.persistence.database import Database


@pytest.fixture(autouse=True)
def no_external_http(monkeypatch):
    """Use ASGI/mock transports and gated MySQL; never use external HTTP in tests."""

    def blocked(*_args, **_kwargs):
        raise AssertionError("默认测试禁止外部HTTP；请使用内存ASGI或MockTransport")

    async def blocked_async(*_args, **_kwargs):
        blocked()

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", blocked)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", blocked_async)
    monkeypatch.setattr(requests.Session, "request", blocked)


@contextmanager
def authenticated_client(path, *, debug=True, database=None, username=None):
    database = database or Database(
        f"sqlite+aiosqlite:///{path}", instance_id="unit-installation", initialize_test=True
    )
    app = create_app(
        Settings(
            _env_file=None,
            environment="test",
            simulation_debug_enabled=debug,
            allowed_origins=["http://testserver"],
        ),
        database=database,
    )
    with TestClient(app) as client:
        anon = client.get("/auth/session")
        assert anon.status_code == 200, anon.text
        client.headers.update(
            {"Origin": "http://testserver", "X-CSRF-Token": anon.json()["csrf_token"]}
        )
        registration = client.post(
            "/auth/register",
            json={
                "username": username or "unit_" + uuid4().hex[:15],
                "password": "unit password 12345",
            },
        )
        assert registration.status_code == 200, registration.text
        client.headers["X-CSRF-Token"] = registration.json()["csrf_token"]
        yield client


@pytest.fixture
def client(tmp_path):
    with authenticated_client(tmp_path / "unit.db") as instance:
        yield instance
