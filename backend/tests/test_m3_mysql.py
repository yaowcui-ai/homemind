"""Gated tests against the dedicated, migrated real MySQL test installation.

No schema drops, create_all, account resets or unrelated-row cleanup occur here.
"""

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.engine import make_url

from homemind.app import create_app
from homemind.auth import digest
from homemind.config import Settings
from homemind.persistence.database import Database
from homemind.persistence.models import (
    Action,
    AuthSession,
    EntityRecord,
    Event,
    Home,
    Preference,
    RoomRecord,
    Task,
    User,
)


@pytest.fixture
def mysql_installation():
    url = os.environ.get("HOMEMIND_TEST_DATABASE_URL")
    instance_id = os.environ.get("HOMEMIND_DATABASE_INSTANCE_ID")
    if not url:
        pytest.skip("需要独立真实 MySQL HOMEMIND_TEST_DATABASE_URL；SQLite 不代替此检查")
    parsed = make_url(url)
    assert parsed.drivername == "mysql+asyncmy" and parsed.database == "homemind_test", (
        "仅允许专用测试库"
    )
    assert instance_id, "需要预配置安装标识"
    database = Database(url, instance_id=instance_id)
    asyncio.run(database.ready())  # Check marker and migration, never initialize here.
    settings = Settings(
        _env_file=None,
        environment="test",
        simulation_debug_enabled=True,
        allowed_origins=["http://testserver"],
    )
    prefix = "m3_" + uuid4().hex[:16]
    usernames = [prefix + "_a", prefix + "_b"]
    anonymous_digests = set()
    app = create_app(settings, database=database)
    try:
        yield database, settings, app, usernames, anonymous_digests
    finally:

        async def cleanup():
            async with database.sessions.begin() as session:
                user_ids = list(
                    await session.scalars(select(User.id).where(User.username.in_(usernames)))
                )
                home_ids = list(
                    await session.scalars(select(Home.id).where(Home.user_id.in_(user_ids)))
                )
                # Delete only the exact users created by this test invocation and their rows.
                for model in (Event, Action, Task, Preference, EntityRecord, RoomRecord):
                    await session.execute(delete(model).where(model.home_id.in_(home_ids)))
                await session.execute(delete(Home).where(Home.id.in_(home_ids)))
                await session.execute(delete(AuthSession).where(AuthSession.user_id.in_(user_ids)))
                if anonymous_digests:
                    await session.execute(
                        delete(AuthSession).where(AuthSession.digest.in_(anonymous_digests))
                    )
                await session.execute(delete(User).where(User.id.in_(user_ids)))
            await database.close()

        asyncio.run(cleanup())


def register(client, username):
    anon = client.get("/auth/session")
    assert anon.status_code == 200, anon.text
    client.headers.update(
        {"Origin": "http://testserver", "X-CSRF-Token": anon.json()["csrf_token"]}
    )
    result = client.post(
        "/auth/register", json={"username": username, "password": "mysql test password 123"}
    )
    assert result.status_code == 200, result.text
    client.headers["X-CSRF-Token"] = result.json()["csrf_token"]
    return result.json()


def test_mysql_product_c_advance_replay_survives_new_database_and_reset(mysql_installation):
    from test_product_c_advance import advance, sleeping, snapshot

    database, settings, app, names, _ = mysql_installation
    with TestClient(app) as first:
        register(first, names[0])
        task, body = sleeping(first)
        response = advance(first, task, body)
        assert response.status_code == 200, response.text
        committed = response.json()
        rebuilt = create_app(
            settings,
            database=Database(
                os.environ["HOMEMIND_TEST_DATABASE_URL"], instance_id=database.instance_id
            ),
        )
        with TestClient(rebuilt) as restarted:
            restarted.cookies.update(first.cookies)
            restarted.headers.update(first.headers)
            assert advance(restarted, task, body).json() == committed
            assert snapshot(restarted)["simulated_minutes"] == 10
            assert restarted.post("/simulation/reset", json={}).status_code == 200
            before = snapshot(restarted)
            assert advance(restarted, task, body).json() == committed
            assert snapshot(restarted) == before


def test_mysql_isolation_persistence_history_and_cookie_revocation(mysql_installation):
    database, settings, app, names, anonymous = mysql_installation
    with TestClient(app) as first, TestClient(app) as second:
        account_a = register(first, names[0])
        register(second, names[1])
        before = first.get("/simulation").json()
        room = before["rooms"][0]
        light = next(e for e in before["entities"] if e["type"] == "light")
        assert second.delete(f"/simulation/entities/{light['id']}").status_code == 404
        assert (
            second.patch(f"/simulation/rooms/{room['id']}", json={"name": "stolen"}).status_code
            == 404
        )
        first.patch("/preferences", json={"comfort_temperature_c": 24})
        first.patch(f"/simulation/rooms/{room['id']}", json={"name": "MySQL persisted room"})
        first.delete(f"/simulation/entities/{light['id']}")
        request = {"scenario": "homecoming", "room_ids": [room["id"]]}
        task_response = first.post(
            "/tasks", json=request, headers={"Idempotency-Key": "mysql-task-123"}
        )
        assert task_response.status_code == 200, task_response.text
        task = task_response.json()
        assert (
            first.post("/tasks", json=request, headers={"Idempotency-Key": "mysql-task-123"}).json()
            == task
        )
        assert second.get(f"/tasks/{task['id']}").status_code == 404
        assert second.post(f"/tasks/{task['id']}/verify", json={}).status_code == 404
        foreign = second.get("/simulation").json()["rooms"][0]["id"]
        assert (
            first.post(
                "/tasks",
                json={**request, "protected_room_ids": [foreign]},
                headers={"Idempotency-Key": "foreign-rule-123"},
            ).status_code
            == 404
        )
        other_request = {"scenario": "away", "room_ids": [foreign]}
        assert (
            second.post(
                "/tasks", json=other_request, headers={"Idempotency-Key": "mysql-task-123"}
            ).status_code
            == 200
        )
        first.post("/simulation/advance", json={"minutes": 4})
        persisted = first.get("/simulation").json()
        cookie = first.cookies.get("homemind_session")
        old_csrf = first.headers["X-CSRF-Token"]
        logged_out = first.post("/auth/logout", json={})
        anonymous.add(digest(first.cookies.get("homemind_session")))
        assert logged_out.json()["csrf_token"] != old_csrf
        assert first.post("/simulation/reset", json={}).status_code == 401
        first.cookies.set("homemind_session", cookie)
        assert first.get("/simulation").status_code == 401
    # Independent app/engine/connection. Real process restart is a separate root check.
    reopened = Database(
        str(database.engine.url.render_as_string(hide_password=False)),
        instance_id=database.instance_id,
    )
    with TestClient(create_app(settings, database=reopened)) as client:
        anon = client.get("/auth/session").json()
        client.headers.update({"Origin": "http://testserver", "X-CSRF-Token": anon["csrf_token"]})
        result = client.post(
            "/auth/login", json={"username": names[0], "password": "mysql test password 123"}
        )
        assert result.status_code == 200, result.text
        assert result.json()["user"] == account_a["user"]
        assert client.get("/simulation").json() == persisted
        assert client.get("/preferences").json()["comfort_temperature_c"] == 24
        assert client.get(f"/tasks/{task['id']}").json() == task
    asyncio.run(reopened.close())


def test_mysql_concurrent_tasks_claim_one_home_without_interleaving(mysql_installation):
    database, settings, app, names, _ = mysql_installation
    with TestClient(app) as client:
        register(client, names[0])
        home = client.get("/simulation").json()
        request = {"scenario": "away", "room_ids": [home["rooms"][0]["id"]]}
        gate = Barrier(8)

        def submit(index):
            gate.wait(timeout=10)
            response = client.post(
                "/tasks", json=request, headers={"Idempotency-Key": f"mysql-concurrent-{index}"}
            )
            return response.status_code, response.json()

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(submit, range(8)))
        assert any(status == 200 for status, _ in results), results
        assert any(
            status == 409 and value["detail"]["code"] == "home_busy" for status, value in results
        ), results
        assert all(status in {200, 409} for status, _ in results), results
        tasks = client.get("/tasks").json()
        assert len(tasks) == sum(status == 200 for status, _ in results)
        assert all(task["status"] == "succeeded" for task in tasks)

        async def history():
            async with database.sessions() as session:
                records = list(
                    await session.scalars(
                        select(Event)
                        .where(Event.home_id == home["home_id"])
                        .order_by(Event.sequence)
                    )
                )
                assert len(records) == len(tasks) * 3
                assert [e.sequence for e in records] == list(range(1, len(records) + 1))
                # Each task's local simulation transaction forms one contiguous event block.
                for start in range(0, len(records), 3):
                    assert len({e.task_id for e in records[start : start + 3]}) == 1

        asyncio.run(history())


def test_mysql_idempotency_keys_preserve_case_for_same_and_different_content(mysql_installation):
    from sqlalchemy import text

    database, _, app, names, _ = mysql_installation

    async def inspect_column():
        async with database.sessions() as session:
            column = (
                await session.execute(
                    text(
                        "SELECT COLLATION_NAME, CHARACTER_SET_NAME FROM information_schema.COLUMNS "
                        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'hm_tasks' "
                        "AND COLUMN_NAME = 'idempotency_key'"
                    )
                )
            ).one()
            assert column.COLLATION_NAME == "utf8mb4_bin"
            assert column.CHARACTER_SET_NAME == "utf8mb4"

    asyncio.run(inspect_column())

    with TestClient(app) as client:
        register(client, names[0])
        home = client.get("/simulation").json()
        request = {"scenario": "away", "room_ids": [home["rooms"][0]["id"]]}
        different = {"scenario": "away", "room_ids": [home["rooms"][1]["id"]]}
        keys_and_requests = [
            ("Task-Key-Same-123", request),
            ("task-key-same-123", request),
            ("Task-Key-Different-123", request),
            ("task-key-different-123", different),
        ]
        ids = []
        for key, content in keys_and_requests:
            response = client.post("/tasks", json=content, headers={"Idempotency-Key": key})
            assert response.status_code == 200, response.text
            task = response.json()
            ids.append(task["id"])
            replayed = client.post("/tasks", json=content, headers={"Idempotency-Key": key})
            assert replayed.status_code == 200 and replayed.json() == task
        assert len(set(ids)) == 4
        conflict = client.post(
            "/tasks", json=different, headers={"Idempotency-Key": "Task-Key-Different-123"}
        )
        assert conflict.status_code == 409
        assert len(client.get("/tasks").json()) == 4


def test_mysql_agent_clarification_reopens_and_executes_once(mysql_installation):
    from test_m4_agent import ScriptedModel, plan

    database, settings, app, names, _ = mysql_installation
    with TestClient(app) as first:
        register(first, names[0])
        snapshot = first.get("/simulation").json()
        request = {"text": "请选择后打开指定灯", "expected_world_id": snapshot["world_id"]}
        app.state.agent_model = ScriptedModel(
            {
                "kind": "clarify",
                "question": "哪个房间",
                "options": [
                    {"id": r["id"], "label": r["name"], "kind": "room"} for r in snapshot["rooms"]
                ],
            }
        )
        task_response = first.post(
            "/tasks/agent", json=request, headers={"Idempotency-Key": "mysql-agent-create-123"}
        )
        assert task_response.status_code == 200, task_response.text
        waiting = task_response.json()
        assert waiting["status"] == "waiting_input" and waiting["mode"] == "single_agent"
        cookie = first.cookies.get("homemind_session")
        csrf = first.headers["X-CSRF-Token"]
    reopened = Database(
        str(database.engine.url.render_as_string(hide_password=False)),
        instance_id=database.instance_id,
    )
    second_app = create_app(settings, database=reopened)
    model = ScriptedModel(plan(snapshot))
    second_app.state.agent_model = model
    with TestClient(second_app) as second:
        second.cookies.set("homemind_session", cookie)
        second.headers.update({"Origin": "http://testserver", "X-CSRF-Token": csrf})
        url = f"/tasks/{waiting['id']}"
        assert second.get(url).json() == waiting
        reply = {"text": "第一个房间", "expected_turn": 0}
        headers = {"Idempotency-Key": "mysql-agent-reply-123"}
        response = second.post(url + "/reply", json=reply, headers=headers)
        assert response.status_code == 200, response.text
        done = response.json()
        assert done["id"] == waiting["id"] and done["status"] == "succeeded"
        assert done["agent_run"]["model_calls"] == 2 and done["agent_run"]["usage"] is None
        assert (
            done["agent_run"]["turn"] == 1
            and "mysql-agent-reply-123" in done["agent_run"]["operations"]
        )
        assert len(done["actions"]) == 1 and done["actions"][0]["status"] == "verified"
        assert second.post(url + "/reply", json=reply, headers=headers).json() == done
        assert (
            second.post(
                "/tasks/agent", json=request, headers={"Idempotency-Key": "mysql-agent-create-123"}
            ).json()
            == done
        )
        assert len(model.calls) == 1
        assert second.get(url).json() == done

        async def inspect():
            async with reopened.sessions() as session:
                stored = await session.get(Task, done["id"])
                actions = list(
                    await session.scalars(select(Action).where(Action.task_id == done["id"]))
                )
                assert stored.mode == "single_agent" and stored.agent_run == done["agent_run"]
                assert len(actions) == 1

        asyncio.run(inspect())
    asyncio.run(reopened.close())
