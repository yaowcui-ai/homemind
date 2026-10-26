"""Configuration boundaries and safe defaults."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from homemind.config import ENV_FILE, Settings


def test_default_settings_need_no_model_or_database_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("HOMEMIND_ENVIRONMENT", "HOMEMIND_API_HOST", "HOMEMIND_API_PORT"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(_env_file=None)
    assert settings.environment == "development"
    assert settings.api_host == "127.0.0.1"
    assert settings.api_port == 8100


@pytest.mark.parametrize("port", [0, -1, 65536])
def test_invalid_port_is_rejected(port: int) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, api_port=port)


def test_invalid_environment_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, environment="unexpected")


def test_empty_bind_host_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, api_host=" ")


def test_environment_overrides_project_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / "config.env"
    env_file.write_text("HOMEMIND_API_PORT=8101\n", encoding="utf-8")
    monkeypatch.setenv("HOMEMIND_API_PORT", "8102")
    assert Settings(_env_file=env_file).api_port == 8102


def test_default_config_path_does_not_follow_terminal_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = Path(__file__).resolve().parents[1] / ".env"
    monkeypatch.chdir(tmp_path)
    assert ENV_FILE == expected
