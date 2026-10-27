"""Read only HomeMind's own local settings; never print credentials."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local"
MYSQL_ENV = LOCAL / "mysql.env"
BACKEND = ROOT / "backend"
PYTHON = BACKEND / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def read_env(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key, value = stripped.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def test_environment() -> dict[str, str]:
    """A dedicated test database, supplied explicitly or by this project setup."""
    local = read_env(MYSQL_ENV)
    result = dict(os.environ)
    test_url = result.get("HOMEMIND_TEST_DATABASE_URL") or local.get("HOMEMIND_TEST_DATABASE_URL")
    instance = result.get("HOMEMIND_DATABASE_INSTANCE_ID") or local.get(
        "HOMEMIND_DATABASE_INSTANCE_ID"
    )
    if not test_url or not instance:
        raise RuntimeError("缺少 HomeMind 独立测试库配置，请先运行 scripts/setup_mysql.py。")
    # An explicit dedicated database name prevents an accidental test run on app data.
    if test_url.split("?", 1)[0].rsplit("/", 1)[-1] != "homemind_test":
        raise RuntimeError("测试仅允许 homemind_test 库，拒绝在应用库运行。")
    result.update(
        {
            "HOMEMIND_TEST_DATABASE_URL": test_url,
            "HOMEMIND_DATABASE_URL": test_url,
            "HOMEMIND_DATABASE_INSTANCE_ID": instance,
            "HOMEMIND_ENVIRONMENT": "test",
            "HOMEMIND_SIMULATION_DEBUG_ENABLED": "true",
            "HOMEMIND_MODEL_ENABLED": "false",
            "PYTHONUTF8": "1",
        }
    )
    return result
