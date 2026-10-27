"""Create/reuse only the matching HomeMind MySQL resources, without destructive resets."""

import argparse
import json
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path
from uuid import UUID, uuid4

from local_config import BACKEND, LOCAL, MYSQL_ENV, PYTHON, ROOT, read_env

COMPOSE = ROOT / "deploy" / "compose.mysql.yaml"
CONTAINER = "homemind-mysql-1"
VOLUME = "homemind_mysql_data"
OWNER = "com.homemind.owner"
INSTANCE = "com.homemind.instance"


class SetupError(Exception):
    pass


def compose_environment(values: dict[str, str]) -> dict[str, str]:
    """Recorded project values are authoritative over unrelated shell exports."""
    return {**os.environ, **values}


def command(args: list[str], *, check=True, env=None, capture=True):
    result = subprocess.run(
        args,
        cwd=ROOT,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=capture,
    )
    if check and result.returncode:
        # Do not propagate a command's environment or possible connection diagnostics.
        raise SetupError(f"命令未完成：{Path(args[0]).name}；请检查 Docker 与本项目配置。")
    return result


def inspect(kind: str, name: str):
    result = command(["docker", kind, "inspect", name], check=False)
    if result.returncode:
        return None
    return json.loads(result.stdout)[0]


def check_owner(resource, installation: str, *, container=False):
    if resource is None:
        return
    labels = (
        resource.get("Config", {}).get("Labels", {}) if container else resource.get("Labels", {})
    )
    if labels.get(OWNER) != "homemind" or labels.get(INSTANCE) != installation:
        raise SetupError("发现同名但不属于此 HomeMind 安装的资源，拒绝复用、重建或清理。")


def write_env(path: Path, values: dict[str, str]):
    path.write_text("".join(f"{key}={value}\n" for key, value in values.items()), encoding="utf-8")
    if os.name != "nt":
        path.chmod(0o600)


def ensure_configuration(installation: str):
    values = read_env(MYSQL_ENV)
    if values:
        required = {
            "HOMEMIND_MYSQL_ROOT_PASSWORD",
            "HOMEMIND_MYSQL_APP_PASSWORD",
            "HOMEMIND_MYSQL_TEST_PASSWORD",
            "HOMEMIND_TEST_DATABASE_URL",
            "HOMEMIND_DATABASE_INSTANCE_ID",
        }
        if not required.issubset(values) or values["HOMEMIND_DATABASE_INSTANCE_ID"] != installation:
            raise SetupError("本项目数据库配置缺项或安装标识不匹配；拒绝覆盖现有凭据。")
    else:
        values = {
            "HOMEMIND_DATABASE_INSTANCE_ID": installation,
            "HOMEMIND_MYSQL_ROOT_PASSWORD": secrets.token_urlsafe(36),
            "HOMEMIND_MYSQL_APP_PASSWORD": secrets.token_urlsafe(36),
            "HOMEMIND_MYSQL_TEST_PASSWORD": secrets.token_urlsafe(36),
            "HOMEMIND_MYSQL_IMAGE": "mysql:8.4",
        }
        values["HOMEMIND_TEST_DATABASE_URL"] = (
            "mysql+asyncmy://homemind_test:"
            + values["HOMEMIND_MYSQL_TEST_PASSWORD"]
            + "@127.0.0.1:13306/homemind_test?charset=utf8mb4"
        )
        write_env(MYSQL_ENV, values)
    app_url = (
        "mysql+asyncmy://homemind_app:"
        + values["HOMEMIND_MYSQL_APP_PASSWORD"]
        + "@127.0.0.1:13306/homemind_app?charset=utf8mb4"
    )
    backend_env_path = BACKEND / ".env"
    backend_values = read_env(backend_env_path)
    for key, expected in (
        ("HOMEMIND_DATABASE_URL", app_url),
        ("HOMEMIND_DATABASE_INSTANCE_ID", installation),
    ):
        if key in backend_values and backend_values[key] != expected:
            raise SetupError("backend/.env 已有不同数据库目标，拒绝自动覆盖。")
    backend_values.update(
        {
            "HOMEMIND_DATABASE_URL": app_url,
            "HOMEMIND_DATABASE_INSTANCE_ID": installation,
        }
    )
    backend_values.setdefault("HOMEMIND_ENVIRONMENT", "development")
    backend_values.setdefault("HOMEMIND_API_HOST", "127.0.0.1")
    backend_values.setdefault("HOMEMIND_API_PORT", "8100")
    backend_values.setdefault("HOMEMIND_SIMULATION_DEBUG_ENABLED", "true")
    write_env(backend_env_path, backend_values)
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provision-only", action="store_true", help="仅准备容器，暂不迁移应用表")
    args = parser.parse_args()
    command(["docker", "version", "--format", "{{.Server.Version}}"])
    LOCAL.mkdir(exist_ok=True)
    instance_file = LOCAL / "instance.json"
    if instance_file.exists():
        installation = str(
            UUID(json.loads(instance_file.read_text(encoding="utf-8"))["instance_id"])
        )
    else:
        # Existing named resources are never adopted merely by creating a new config.
        if inspect("container", CONTAINER) or inspect("volume", VOLUME):
            raise SetupError("存在同名资源但没有本项目安装记录，拒绝自动接管。")
        installation = str(uuid4())
        instance_file.write_text(
            json.dumps({"instance_id": installation}, indent=2), encoding="utf-8"
        )
    container = inspect("container", CONTAINER)
    check_owner(container, installation, container=True)
    check_owner(inspect("volume", VOLUME), installation)
    if container is None:
        try:
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 13306))
        except OSError:
            raise SetupError("127.0.0.1:13306 被占用；不会停止其他服务。") from None
    values = ensure_configuration(installation)
    compose = [
        "docker",
        "compose",
        "--project-name",
        "homemind",
        "--env-file",
        str(MYSQL_ENV),
        "--file",
        str(COMPOSE),
    ]
    compose_env = compose_environment(values)
    command([*compose, "config", "--quiet"], env=compose_env)
    image_ref = values.get("HOMEMIND_MYSQL_IMAGE", "mysql:8.4")
    if not command(["docker", "image", "inspect", image_ref], check=False).returncode == 0:
        print("准备 HomeMind 的 MySQL 8.4 镜像…", flush=True)
        command([*compose, "pull", "mysql"], capture=False, env=compose_env)
    image_data = json.loads(command(["docker", "image", "inspect", image_ref]).stdout)[0]
    digests = image_data.get("RepoDigests", [])
    if not digests:
        raise SetupError("镜像缺少可追溯摘要，拒绝将未标识镜像作为交付基线。")
    pinned_image = digests[0]
    values["HOMEMIND_MYSQL_IMAGE"] = pinned_image
    write_env(MYSQL_ENV, values)
    compose_env = compose_environment(values)
    print("启动匹配安装标识的 HomeMind MySQL（保留已有数据）…", flush=True)
    command([*compose, "up", "--detach", "--no-recreate", "mysql"], capture=False, env=compose_env)
    for _ in range(90):
        container = inspect("container", CONTAINER)
        check_owner(container, installation, container=True)
        state = container.get("State", {}) if container else {}
        if state.get("Health", {}).get("Status") == "healthy":
            break
        if state.get("Status") in {"exited", "dead"}:
            raise SetupError("HomeMind MySQL 启动退出；请检查本项目容器日志，勿重建数据卷。")
        time.sleep(2)
    else:
        raise SetupError("HomeMind MySQL 未在等待时间内就绪；保留容器和数据供检查。")
    metadata = {
        "instance_id": installation,
        "image": pinned_image,
        "container_id": container["Id"],
        "volume": VOLUME,
        "port": 13306,
    }
    (LOCAL / "mysql-resource.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print("HomeMind MySQL 已健康，镜像摘要和资源身份已保存。", flush=True)
    if not args.provision_only:
        if not PYTHON.is_file():
            raise SetupError(
                "缺少本项目 Python 环境，请先在 backend 运行 python -m uv sync --frozen。"
            )
        env = dict(os.environ)
        env["PYTHONUTF8"] = "1"
        # Set exact owned URLs; shell variables from other projects cannot redirect migration.
        backend_values = read_env(BACKEND / ".env")
        env.update(
            {
                "HOMEMIND_DATABASE_URL": backend_values["HOMEMIND_DATABASE_URL"],
                "HOMEMIND_DATABASE_INSTANCE_ID": installation,
            }
        )
        command(
            [str(PYTHON), "-m", "homemind.migrate", "--initialize-empty"], env=env, capture=False
        )
        env["HOMEMIND_DATABASE_URL"] = values["HOMEMIND_TEST_DATABASE_URL"]
        command(
            [str(PYTHON), "-m", "homemind.migrate", "--initialize-empty"], env=env, capture=False
        )
        print("应用库与独立测试库迁移完成。", flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    try:
        main()
    except SetupError as error:
        print(f"HomeMind 初始化未完成：{error}", file=sys.stderr)
        sys.exit(1)
    except (OSError, ValueError, KeyError):
        # Avoid dumping local configuration or a child's sensitive environment.
        print(
            "HomeMind 初始化未完成。请核对 Docker、资源归属和本项目本地配置；已有数据未清理。",
            file=sys.stderr,
        )
        sys.exit(1)
