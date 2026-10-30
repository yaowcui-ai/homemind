"""Compose dotenv parsing must preserve the same key value as local settings."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(shutil.which("docker") is None, reason="Requires Compose CLI, not its engine")
def test_quoted_model_key_is_unquoted_in_both_container_environments(tmp_path):
    (tmp_path / "backend").mkdir()
    (tmp_path / "deploy").mkdir()
    shutil.copyfile(ROOT / "compose.yaml", tmp_path / "compose.yaml")
    shutil.copyfile(ROOT / "deploy/compose.mysql.yaml", tmp_path / "deploy/compose.mysql.yaml")
    (tmp_path / "backend/.env").write_text(
        'HOMEMIND_MODEL_API_KEY="synthetic_quoted_model_key"\n', encoding="utf-8"
    )
    (tmp_path / "runtime.env").write_text(
        "HOMEMIND_DATABASE_INSTANCE_ID=synthetic-installation\n"
        "HOMEMIND_MYSQL_APP_PASSWORD=synthetic_app\n"
        "HOMEMIND_MYSQL_ROOT_PASSWORD=synthetic_root\n"
        "HOMEMIND_MYSQL_TEST_PASSWORD=synthetic_test\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            "runtime.env",
            "config",
            "--format",
            "json",
        ],
        cwd=tmp_path,
        env={k: v for k, v in os.environ.items() if not k.startswith(("HOMEMIND_", "COMPOSE_"))},
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    services = json.loads(result.stdout)["services"]
    for name in ("api", "migrate"):
        assert (
            services[name]["environment"]["HOMEMIND_MODEL_API_KEY"] == "synthetic_quoted_model_key"
        )
