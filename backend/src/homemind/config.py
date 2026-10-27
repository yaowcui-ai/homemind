"""Project-local, environment-overridable development settings."""

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    environment: Literal["development", "test", "production"] = "development"
    api_host: str = Field(default="127.0.0.1", min_length=1)
    api_port: int = Field(default=8100, ge=1, le=65535)
    database_url: SecretStr | None = None
    database_instance_id: str | None = None
    simulation_debug_enabled: bool = False
    model_enabled: bool = False
    model_provider: Literal["deepseek"] = "deepseek"
    model_name: str = Field(default="deepseek-flash", min_length=1, max_length=120)
    model_base_url: str = "https://api.deepseek.com"
    model_api_key: SecretStr | None = None
    allowed_origins: list[str] = [
        "http://127.0.0.1:5174",
        "http://localhost:5174",
        "http://127.0.0.1:8100",
        "http://localhost:8100",
    ]

    @field_validator("database_url")
    @classmethod
    def mysql_only(cls, value):
        if value is not None and not value.get_secret_value().startswith("mysql+asyncmy://"):
            raise ValueError("数据库必须使用 mysql+asyncmy")
        return value

    @field_validator("model_base_url")
    @classmethod
    def official_provider(cls, value):
        if value.rstrip("/") != "https://api.deepseek.com":
            raise ValueError("本阶段仅支持 DeepSeek 官方 API 地址")
        return value.rstrip("/")

    model_config = SettingsConfigDict(
        env_prefix="HOMEMIND_",
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        str_strip_whitespace=True,
    )
