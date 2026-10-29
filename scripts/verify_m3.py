"""Real MySQL integration and owned API process restart checks; no mock persistence claim."""

import argparse
import http.cookiejar
import json
import os
import secrets
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from uuid import uuid4

from local_config import BACKEND, LOCAL, PYTHON, ROOT, test_environment

PORT = 18100
ORIGIN = f"http://127.0.0.1:{PORT}"


def api_client():
    cookies = http.cookiejar.CookieJar()
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(cookies)
    )


def call(client, path, method="GET", body=None, csrf=None, headers=None):
    request_headers = {"Accept": "application/json", **(headers or {})}
    if method != "GET":
        request_headers.update({"Origin": ORIGIN, "X-CSRF-Token": csrf or ""})
    data = None
    if body is not None:
        request_headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        ORIGIN + path, data=data, method=method, headers=request_headers
    )
    try:
        with client.open(request, timeout=10) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"HTTP {error.code}: {method} {path}") from None


def stop_owned(process, pid_file, nonce):
    if pid_file.is_file():
        record = json.loads(pid_file.read_text(encoding="utf-8"))
        if record.get("nonce") != nonce:
            raise RuntimeError("API process ownership marker mismatch; refusing to stop it.")
        actual_pid = int(record["pid"])
        if os.name == "nt":
            # Windows venv Python can be a redirector process. Verify the actual
            # runtime's unique nonce rather than killing a port or a process name.
            query = (
                "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new(); "
                f'Get-CimInstance Win32_Process -Filter "ProcessId={actual_pid}" '
                "| Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"
            )
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", query],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
            )
            if result.stdout.strip():
                identity = json.loads(result.stdout)
                if nonce not in identity.get(
                    "CommandLine", ""
                ) or "serve_owned_api.py" not in identity.get("CommandLine", ""):
                    raise RuntimeError("API PID no longer identifies this verification process.")
                os.kill(actual_pid, signal.SIGTERM)
        elif process.poll() is None:
            process.terminate()
    elif process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        # Terminate only the original Popen process handle, never unrelated services.
        process.terminate()
        process.wait(timeout=5)


@contextmanager
def server(env, phase):
    (ROOT / "output").mkdir(parents=True, exist_ok=True)
    nonce = uuid4().hex
    pid_file = LOCAL / f"m3-api-{nonce}.json"
    log_path = ROOT / "output" / f"m3-restart-api-{phase}.log"
    with log_path.open("w", encoding="utf-8") as log:
        kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
        process = subprocess.Popen(
            [
                str(PYTHON),
                str(ROOT / "scripts" / "serve_owned_api.py"),
                "--pid-file",
                str(pid_file),
                "--nonce",
                nonce,
            ],
            cwd=BACKEND,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            **kwargs,
        )
        try:
            probe = api_client()
            for _ in range(200):
                if process.poll() is not None:
                    raise RuntimeError(
                        "Owned API exited before readiness; inspect its project output log."
                    )
                try:
                    if call(probe, "/health").get("stage") in {"M3", "M4"}:
                        break
                except (OSError, RuntimeError):
                    time.sleep(0.2)
            else:
                raise RuntimeError("Owned API readiness timeout.")
            yield process
        finally:
            stop_owned(process, pid_file, nonce)


def restart_check(env):
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", PORT))
        except OSError:
            raise RuntimeError(
                f"Port {PORT} is occupied; refusing to stop another service."
            ) from None
    env = dict(env)
    env.update(
        {
            "HOMEMIND_API_HOST": "127.0.0.1",
            "HOMEMIND_API_PORT": str(PORT),
            "HOMEMIND_ALLOWED_ORIGINS": json.dumps([ORIGIN]),
        }
    )
    LOCAL.mkdir(exist_ok=True)
    client = api_client()
    name = "restart_" + uuid4().hex[:20]
    print("Checking saved state across two actual owned API processes…", flush=True)
    with server(env, "before"):
        bootstrap = call(client, "/auth/session")
        account = call(
            client,
            "/auth/register",
            "POST",
            {"username": name, "password": secrets.token_urlsafe(24)},
            bootstrap["csrf_token"],
        )
        csrf = account["csrf_token"]
        initial = call(client, "/simulation")
        room = initial["rooms"][0]
        lamp = next(
            e for e in initial["entities"] if e["room_id"] == room["id"] and e["type"] == "light"
        )
        call(client, f"/simulation/rooms/{room['id']}", "PATCH", {"name": "重启验证室"}, csrf)
        call(
            client,
            f"/simulation/controls/{lamp['id']}",
            "POST",
            {
                "action": "set_light",
                "parameters": {"power": True, "brightness_pct": 65},
                "expected_world_id": initial["world_id"],
            },
            csrf,
        )
        extra = call(
            client,
            "/simulation/entities",
            "POST",
            {"room_id": room["id"], "name": "已归档验证灯", "type": "light"},
            csrf,
        )
        archived = next(e for e in extra["entities"] if e["name"] == "已归档验证灯")
        call(client, f"/simulation/entities/{archived['id']}", "DELETE", csrf=csrf)
        preferences = call(client, "/preferences", "PATCH", {"comfort_temperature_c": 25}, csrf)
        body = {
            "scenario": "away",
            "room_ids": [room["id"]],
            "keep_entity_ids": [lamp["id"]],
            "expected_world_id": initial["world_id"],
        }
        key = uuid4().hex
        task = call(client, "/tasks", "POST", body, csrf, {"Idempotency-Key": key})
        if task["status"] != "succeeded":
            raise RuntimeError("Deterministic away scenario did not verify before restart.")
        call(client, "/simulation/advance", "POST", {"minutes": 7}, csrf)
        before = call(client, "/simulation")
        if before["archived_count"] != 1:
            raise RuntimeError("Archived entity was not retained before restart.")
    with server(env, "after"):
        account_after = call(client, "/auth/session")
        after = call(client, "/simulation")
        preferences_after = call(client, "/preferences")
        task_after = call(client, f"/tasks/{task['id']}")
        if account_after["user"] != account["user"]:
            raise RuntimeError("Session/owner was not restored after process restart.")
        if after != before or preferences_after != preferences or task_after != task:
            raise RuntimeError(
                "Saved configuration, environment, preferences or frozen task changed on restart."
            )
        replay = call(
            client, "/tasks", "POST", body, account_after["csrf_token"], {"Idempotency-Key": key}
        )
        if replay != task or call(client, "/simulation") != after:
            raise RuntimeError("Task replay produced another side effect after process restart.")
        proof = {
            "mysql_integration": True,
            "api_process_restart": True,
            "session_restored": True,
            "configuration_and_world_equal": True,
            "archived_not_reseeded": True,
            "preferences_equal": True,
            "task_and_actions_equal": True,
            "idempotent_replay_equal": True,
            "home_id": after["home_id"],
            "world_id": after["world_id"],
            "task_id": task["id"],
            "entity_count": len(after["entities"]),
            "archived_count": after["archived_count"],
            "simulated_minutes": after["simulated_minutes"],
            "api_port": PORT,
        }
        (ROOT / "output" / "m3-restart-proof.json").write_text(
            json.dumps(proof, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(
        "Actual restart check passed: session, configuration, world, archive, "
        "preferences, task/actions and replay.",
        flush=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--tests-only", action="store_true")
    mode.add_argument("--restart-only", action="store_true")
    args = parser.parse_args()
    env = test_environment()
    if not args.restart_only:
        result = subprocess.run(
            [str(PYTHON), "-m", "pytest", "tests/test_m3_mysql.py", "-q"], cwd=BACKEND, env=env
        )
        if result.returncode:
            return result.returncode
    if not args.tests_only:
        restart_check(env)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, ValueError, KeyError) as error:
        print(f"HomeMind verification failed: {error}", file=sys.stderr)
        raise SystemExit(1) from None
