"""Guarded migration CLI: never infer ownership from a familiar database name."""

import argparse
import asyncio
import sys
import time
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from homemind.config import Settings
from homemind.persistence.models import Base, Installation


def check_identity(name, tables, marker, expected, *, initialize_empty):
    if name not in {"homemind_app", "homemind_test"} or not expected:
        raise ValueError("数据库名称或安装标识不合法")
    if not tables:
        if not initialize_empty:
            raise ValueError("空数据库首次迁移须明确指定 --initialize-empty")
        return
    known = set(Base.metadata.tables) | {"alembic_version"}
    if not set(tables) <= known or marker != expected:
        raise ValueError("拒绝迁移非本项目数据库或安装标识不匹配的数据库")


async def migrate(settings, *, initialize_empty=False):
    if not settings.database_url or not settings.database_instance_id:
        raise ValueError("请先配置本项目数据库及安装标识")
    url = settings.database_url.get_secret_value()
    parsed = make_url(url)
    if parsed.drivername != "mysql+asyncmy":
        raise ValueError("迁移仅支持本项目 MySQL 数据库")
    engine = create_async_engine(url, hide_parameters=True)
    try:
        async with engine.begin() as connection:
            tables = await connection.run_sync(lambda c: inspect(c).get_table_names())
            marker = None
            if "hm_installation" in tables:
                marker = await connection.scalar(
                    select(Installation.instance_id).where(Installation.id == 1)
                )
            check_identity(
                parsed.database,
                tables,
                marker,
                settings.database_instance_id,
                initialize_empty=initialize_empty,
            )
            config = Config()
            config.set_main_option("script_location", str(Path(__file__).with_name("migrations")))

            def upgrade(sync_connection):
                config.attributes["connection"] = sync_connection
                command.upgrade(config, "head")

            await connection.run_sync(upgrade)
            if not tables:
                await connection.execute(
                    Installation.__table__.insert().values(
                        id=1, instance_id=settings.database_instance_id, created_at=int(time.time())
                    )
                )
    finally:
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="安全迁移本项目独立数据库")
    parser.add_argument("--initialize-empty", action="store_true")
    arguments = parser.parse_args()
    try:
        asyncio.run(migrate(Settings(), initialize_empty=arguments.initialize_empty))
    except Exception:
        print(
            "数据库迁移失败：请检查本项目配置、库名、安装标识及空库初始化条件；未输出连接凭据。",
            file=sys.stderr,
        )
        return 1
    print("本项目数据库迁移完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
