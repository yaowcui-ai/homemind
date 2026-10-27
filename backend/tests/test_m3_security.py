"""Security boundaries observed through cookies and persisted sessions."""

import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from homemind.auth import HASHER, digest
from homemind.persistence.models import AuthSession, User


def test_cookie_flags_and_password_hash_are_private(client):
    cookie = client.cookies.get("homemind_session")

    async def inspect_records():
        async with client.app.state.database.sessions() as session:
            auth = await session.get(AuthSession, digest(cookie))
            user = await session.get(User, auth.user_id)
            assert auth.digest != cookie
            assert user.password_hash.startswith("$argon2id$v=19$m=65536,t=3,p=2$")
            assert HASHER.verify(user.password_hash, "unit password 12345")

    asyncio.run(inspect_records())
    # Logout rotates both secrets and returns an anonymous HttpOnly cookie.
    old_csrf = client.headers["X-CSRF-Token"]
    response = client.post("/auth/logout", json={})
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=lax" in response.headers["set-cookie"]
    assert response.json()["csrf_token"] != old_csrf
    assert cookie != client.cookies.get("homemind_session")
    assert "password_hash" not in response.text
    with TestClient(client.app) as stolen:
        stolen.cookies.set("homemind_session", cookie)
        assert stolen.get("/simulation").status_code == 401


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": "https://foreign.example"},
        {"Origin": "null"},
        {"Origin": "http://testserver", "X-CSRF-Token": "wrong"},
    ],
)
def test_write_requires_exact_origin_and_csrf(client, headers):
    response = client.post("/simulation/reset", json={}, headers=headers)
    assert response.status_code == 403


def test_missing_origin_and_non_json_are_rejected(client):
    origin = client.headers.pop("Origin")
    assert client.post("/simulation/reset", json={}).status_code == 403
    client.headers["Origin"] = origin
    assert (
        client.post(
            "/simulation/reset", content="{}", headers={"Content-Type": "text/plain"}
        ).status_code
        == 415
    )


def test_expired_session_cannot_read_or_write(client):
    cookie = client.cookies.get("homemind_session")

    async def expire():
        async with client.app.state.database.sessions.begin() as session:
            auth = await session.get(AuthSession, digest(cookie))
            auth.expires_at = int(time.time()) - 1

    asyncio.run(expire())
    assert client.get("/simulation").status_code == 401
    assert client.post("/simulation/reset", json={}).status_code == 401


def test_login_has_uniform_bad_credentials_and_rate_limit(client):
    user = client.get("/auth/session").json()["user"]["username"]
    client.post("/auth/logout", json={})
    anonymous = client.get("/auth/session").json()
    client.headers["X-CSRF-Token"] = anonymous["csrf_token"]
    first = client.post("/auth/login", json={"username": user, "password": "wrong password 123"})
    second = client.post(
        "/auth/login", json={"username": "nonexistent", "password": "wrong password 123"}
    )
    assert first.status_code == second.status_code == 401
    assert first.json() == second.json()
    # Exhaust the actual bounded attempt window without doing another expensive hash.
    limiter = client.app.state.attempts
    key = next(k for k in limiter.entries if k[1] == "login")
    limiter.entries[key].extend([time.monotonic()] * 28)
    assert (
        client.post(
            "/auth/login", json={"username": user, "password": "wrong password 123"}
        ).status_code
        == 429
    )


def test_cross_account_room_task_keep_and_protection_are_scoped(client, tmp_path):
    from conftest import authenticated_client

    with authenticated_client(tmp_path / "foreign.db") as other:
        foreign = other.get("/simulation").json()
        own = client.get("/simulation").json()
        request = {"scenario": "away", "room_ids": [own["rooms"][0]["id"]]}
        task = client.post(
            "/tasks", json=request, headers={"Idempotency-Key": "cross-task-123"}
        ).json()
        assert other.get(f"/tasks/{task['id']}").status_code == 404
        assert other.post(f"/tasks/{task['id']}/verify", json={}).status_code == 404
        assert (
            client.patch(
                f"/simulation/rooms/{foreign['rooms'][0]['id']}", json={"name": "foreign"}
            ).status_code
            == 404
        )
        for extra in [
            {"keep_entity_ids": [foreign["entities"][0]["id"]]},
            {"protected_room_ids": [foreign["rooms"][0]["id"]]},
        ]:
            response = client.post(
                "/tasks", json={**request, **extra}, headers={"Idempotency-Key": "cross-ref-123"}
            )
            assert response.status_code == 404


def test_database_installation_mismatch_is_503(client):
    client.app.state.database.instance_id = "foreign-installation"
    assert client.get("/simulation").status_code == 503
    assert client.get("/health").status_code == 200


def test_non_ascii_csrf_header_is_rejected_without_server_error(client):
    response = client.post("/simulation/reset", json={}, headers={b"X-CSRF-Token": b"\xff"})
    assert response.status_code == 403


def test_session_and_household_responses_disable_shared_caching(client):
    assert client.get("/auth/session").headers.get("Cache-Control") == "no-store"
    assert client.get("/simulation").headers.get("Cache-Control") == "no-store"
