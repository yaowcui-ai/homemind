"""Explicit database boundary and single-process, per-home transaction locks."""

import asyncio
import time
from contextlib import asynccontextmanager

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from homemind.persistence.codec import load_engine, save_engine
from homemind.persistence.models import Base, Home, Installation
from homemind.simulation.models import SimulationError

REVISION = "0002_m3"


class Database:
    def __init__(self, url: str, *, instance_id: str, initialize_test: bool = False):
        if initialize_test and not url.startswith("sqlite+aiosqlite:"):
            raise ValueError("测试初始化仅允许显式 SQLite 数据库")
        self.engine = create_async_engine(url, echo=False, hide_parameters=True, poolclass=NullPool)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.instance_id = instance_id
        self.initialize_test = initialize_test
        self.locks: dict[str, asyncio.Lock] = {}
        self.busy: set[str] = set()

    async def initialize(self):
        if not self.initialize_test:
            return
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            await connection.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS alembic_version "
                    "(version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
                )
            )
            version = await connection.scalar(text("SELECT version_num FROM alembic_version"))
            if version is None:
                await connection.execute(
                    text("INSERT INTO alembic_version VALUES (:revision)"), {"revision": REVISION}
                )
        async with self.sessions.begin() as session:
            marker = await session.get(Installation, 1)
            if marker is None:
                session.add(
                    Installation(id=1, instance_id=self.instance_id, created_at=int(time.time()))
                )
        self.initialize_test = False

    async def ready(self):
        try:
            await self.initialize()
            async with self.sessions() as session:
                marker = await session.get(Installation, 1)
                version = await session.scalar(text("SELECT version_num FROM alembic_version"))
                if marker is None or marker.instance_id != self.instance_id or version != REVISION:
                    raise ValueError("安装标记或迁移版本不匹配")
        except Exception as error:
            raise SimulationError(
                503, "database_unavailable", "数据库未就绪，请检查本项目数据库配置、安装标记与迁移"
            ) from error

    @asynccontextmanager
    async def home(self, home_id: str, *, save: bool = True, task_id: str | None = None):
        lock = self.locks.setdefault(home_id, asyncio.Lock())
        async with lock, self.sessions.begin() as session:
            home = await session.scalar(select(Home).where(Home.id == home_id).with_for_update())
            if home is None:
                raise SimulationError(404, "not_found", "找不到当前家庭")
            engine = await load_engine(session, home)
            yield session, home, engine
            if save:
                await save_engine(session, home, engine, task_id=task_id)

    async def close(self):
        await self.engine.dispose()
