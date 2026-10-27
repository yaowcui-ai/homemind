"""Local resource/config guards, using synthetic values and no Docker operations."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import local_config
import setup_mysql


def test_owned_compose_values_override_conflicting_shell_variables(monkeypatch):
    own = {
        "HOMEMIND_MYSQL_APP_PASSWORD": "synthetic_owned_app",
        "HOMEMIND_MYSQL_ROOT_PASSWORD": "synthetic_owned_root",
        "HOMEMIND_DATABASE_INSTANCE_ID": "owned-installation",
        "HOMEMIND_MYSQL_IMAGE": "mysql@sha256:synthetic_owned_digest",
    }
    for key in own:
        monkeypatch.setenv(key, "synthetic_foreign_value")
    monkeypatch.setenv("PATH", "keep-parent-path")
    env = setup_mysql.compose_environment(own)
    assert all(env[key] == value for key, value in own.items())
    assert env["PATH"] == "keep-parent-path"


def test_existing_foreign_volume_and_container_cannot_be_adopted():
    with pytest.raises(setup_mysql.SetupError):
        setup_mysql.check_owner({"Labels": {"com.homemind.owner": "another-project"}}, "ours")
    with pytest.raises(setup_mysql.SetupError):
        setup_mysql.check_owner(
            {
                "Config": {
                    "Labels": {"com.homemind.owner": "homemind", "com.homemind.instance": "theirs"}
                }
            },
            "ours",
            container=True,
        )


def test_test_database_never_falls_back_to_application_database(tmp_path, monkeypatch):
    monkeypatch.setattr(local_config, "MYSQL_ENV", tmp_path / "absent.env")
    monkeypatch.delenv("HOMEMIND_TEST_DATABASE_URL", raising=False)
    monkeypatch.setenv("HOMEMIND_DATABASE_URL", "mysql+asyncmy://synthetic@127.0.0.1/homemind_app")
    with pytest.raises(RuntimeError):
        local_config.test_environment()
    monkeypatch.setenv(
        "HOMEMIND_TEST_DATABASE_URL", "mysql+asyncmy://synthetic@127.0.0.1/homemind_app"
    )
    monkeypatch.setenv("HOMEMIND_DATABASE_INSTANCE_ID", "synthetic-installation")
    with pytest.raises(RuntimeError):
        local_config.test_environment()
