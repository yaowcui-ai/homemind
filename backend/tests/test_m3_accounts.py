"""Authenticated API contracts; SQLite here is explicit, not a MySQL substitute."""

from fastapi.testclient import TestClient

from homemind.app import create_app
from homemind.config import Settings


def test_missing_database_is_unavailable_without_memory_fallback():
    with TestClient(
        create_app(Settings(_env_file=None, database_url=None, database_instance_id=None))
    ) as client:
        assert client.get("/health").json()["stage"] == "M3"
        response = client.get("/auth/session")
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "database_unavailable"
        assert client.get("/simulation").status_code == 503


def test_cookie_csrf_isolation_persistence_and_logout(tmp_path):
    from homemind.persistence.database import Database

    database = Database(
        f"sqlite+aiosqlite:///{tmp_path / 'unit.db'}",
        instance_id="unit-installation",
        initialize_test=True,
    )
    settings = Settings(
        _env_file=None,
        environment="test",
        simulation_debug_enabled=True,
        allowed_origins=["http://testserver"],
    )
    app = create_app(settings, database=database)
    with TestClient(app) as first, TestClient(app) as second:
        assert first.get("/simulation").status_code == 401
        anon = first.get("/auth/session").json()
        old_cookie = first.cookies.get("homemind_session")
        assert anon["user"] is None
        assert first.post("/auth/register", json={}).status_code == 403
        first.headers.update({"Origin": "http://testserver", "X-CSRF-Token": anon["csrf_token"]})
        registered = first.post(
            "/auth/register", json={"username": "Alice", "password": " space pass word "}
        )
        assert registered.status_code == 200, registered.text
        first.headers["X-CSRF-Token"] = registered.json()["csrf_token"]
        assert registered.json()["user"]["username"] == "alice"
        assert old_cookie != first.cookies.get("homemind_session")
        other_anon = second.get("/auth/session").json()
        second.headers.update(
            {"Origin": "http://testserver", "X-CSRF-Token": other_anon["csrf_token"]}
        )
        other = second.post(
            "/auth/register", json={"username": "bob", "password": "other password 123"}
        )
        assert other.status_code == 200, other.text
        second.headers["X-CSRF-Token"] = other.json()["csrf_token"]
        before = first.get("/simulation").json()
        separate = second.get("/simulation").json()
        assert before["home_id"] == registered.json()["user"]["home_id"]
        assert before["home_id"] != separate["home_id"]
        light = next(e for e in before["entities"] if e["type"] == "light")
        assert second.delete(f"/simulation/entities/{light['id']}").status_code == 404
        assert first.delete(f"/simulation/entities/{light['id']}").status_code == 200
        pref = first.patch("/preferences", json={"comfort_temperature_c": 24}).json()
        assert pref["version"] == 2 and pref["comfort_temperature_c"] == 24
        assert second.get("/preferences").json()["comfort_temperature_c"] == 26
        logged_out = first.post("/auth/logout", json={})
        assert logged_out.status_code == 200 and logged_out.json()["user"] is None
        assert first.get("/simulation").status_code == 401
        first.headers["X-CSRF-Token"] = logged_out.json()["csrf_token"]
        login = first.post(
            "/auth/login", json={"username": "ALICE", "password": " space pass word "}
        )
        assert login.status_code == 200, login.text
        after = first.get("/simulation").json()
        assert after["world_id"] == before["world_id"]
        assert after["archived_count"] == 1 and len(after["entities"]) == 11
    # A new app and a new connection to the same explicitly injected test database.
    reopened = Database(
        f"sqlite+aiosqlite:///{tmp_path / 'unit.db'}", instance_id="unit-installation"
    )
    with TestClient(create_app(settings, database=reopened)) as client:
        session = client.get("/auth/session").json()
        client.headers.update(
            {"Origin": "http://testserver", "X-CSRF-Token": session["csrf_token"]}
        )
        assert (
            client.post(
                "/auth/login", json={"username": "alice", "password": " space pass word "}
            ).status_code
            == 200
        )
        assert client.get("/simulation").json()["archived_count"] == 1
        assert client.get("/preferences").json()["comfort_temperature_c"] == 24


def test_application_startup_validates_database_before_business_request(tmp_path):
    import asyncio

    from homemind.persistence.database import Database
    from homemind.persistence.models import Installation

    database = Database(
        f"sqlite+aiosqlite:///{tmp_path / 'startup.db'}",
        instance_id="startup-installation",
        initialize_test=True,
    )
    app = create_app(Settings(_env_file=None), database=database)
    with TestClient(app):

        async def marker():
            async with database.sessions() as session:
                return await session.get(Installation, 1)

        assert asyncio.run(marker()).instance_id == "startup-installation"
