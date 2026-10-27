"""Opaque cookie sessions, exact-Origin CSRF checks and Argon2id credentials."""

import hashlib
import secrets
import time
from collections import OrderedDict, deque
from uuid import uuid4

from argon2 import PasswordHasher, Type
from argon2.exceptions import VerificationError
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool

from homemind.persistence.codec import save_engine
from homemind.persistence.models import AuthSession, Home, Preference, User
from homemind.simulation.models import SimulationError
from homemind.simulation.service import SimulationService

COOKIE = "homemind_session"
HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2, type=Type.ID)
DUMMY_HASH = HASHER.hash(secrets.token_urlsafe(32))
DEFAULT_PREFERENCES = {
    "comfort_temperature_c": 26,
    "sleep_temperature_c": 27,
    "fan_mode": "low",
    "arrival_lead_minutes": 20,
}


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def require_home(request: Request) -> str:
    if request.state.home_id is None:
        raise SimulationError(401, "authentication_required", "请先登录")
    return request.state.home_id


async def authenticate(request: Request):
    request.state.identity = None
    request.state.home_id = None
    request.state.auth_session = None
    token = request.cookies.get(COOKIE)
    if token is None or len(token) > 256:
        return
    async with request.app.state.database.sessions() as session:
        record = await session.get(AuthSession, digest(token))
        if record is None or record.expires_at <= int(time.time()):
            return
        request.state.auth_session = record
        if record.user_id:
            user = await session.get(User, record.user_id)
            home = await session.scalar(select(Home).where(Home.user_id == record.user_id))
            if user and home:
                request.state.identity = {
                    "id": user.id,
                    "username": user.username,
                    "home_id": home.id,
                }
                request.state.home_id = home.id


async def protect_write(request: Request):
    if request.headers.get("origin") not in request.app.state.settings.allowed_origins:
        raise SimulationError(403, "csrf_rejected", "请求来源或防护令牌不合法，请刷新页面")
    session = request.state.auth_session
    supplied = request.headers.get("x-csrf-token", "")
    if session is None or not secrets.compare_digest(
        supplied.encode("utf-8"), session.csrf_token.encode("utf-8")
    ):
        raise SimulationError(403, "csrf_rejected", "请求来源或防护令牌不合法，请刷新页面")
    if await request.body():
        content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
        if content_type != "application/json":
            raise SimulationError(415, "json_required", "请求体须使用 JSON 格式")


def session_view(request, record, identity=None):
    return {
        "user": identity,
        "csrf_token": record.csrf_token,
        "simulation_debug_enabled": request.app.state.settings.simulation_debug_enabled,
    }


def set_cookie(request, response, token):
    response.set_cookie(
        COOKIE,
        token,
        max_age=43200,
        httponly=True,
        secure=request.app.state.settings.environment == "production",
        samesite="lax",
        path="/",
    )


async def rotate(session, old, user_id=None):
    if old:
        await session.execute(delete(AuthSession).where(AuthSession.digest == old.digest))
    token = secrets.token_urlsafe(48)
    record = AuthSession(
        digest=digest(token),
        user_id=user_id,
        csrf_token=secrets.token_urlsafe(32),
        expires_at=int(time.time()) + 43200,
    )
    session.add(record)
    return token, record


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(strict=True, min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_]+$")
    password: str = Field(strict=True, min_length=12, max_length=128)


class EmptyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AttemptLimiter:
    """Bounded single-process protection, deliberately not a distributed rate limiter."""

    def __init__(self):
        self.entries = OrderedDict()

    def check(self, request, operation):
        key = (request.client.host if request.client else "unknown", operation)
        now = time.monotonic()
        attempts = self.entries.setdefault(key, deque())
        self.entries.move_to_end(key)
        while attempts and attempts[0] < now - 60:
            attempts.popleft()
        if len(attempts) >= 30:
            raise SimulationError(429, "rate_limited", "尝试次数过多，请稍后重试")
        attempts.append(now)
        while len(self.entries) > 1024:
            self.entries.popitem(last=False)


def auth_router():
    router = APIRouter(prefix="/auth", tags=["accounts"])

    @router.get("/session")
    async def current(request: Request, response: Response):
        record = request.state.auth_session
        if record is None:
            async with request.app.state.database.sessions.begin() as session:
                token, record = await rotate(session, None)
            set_cookie(request, response, token)
        return session_view(request, record, request.state.identity)

    @router.post("/register")
    async def register(body: Credentials, request: Request, response: Response):
        request.app.state.attempts.check(request, "register")
        hashed = await run_in_threadpool(HASHER.hash, body.password)
        user = User(
            id=uuid4().hex,
            username=body.username.lower(),
            password_hash=hashed,
            created_at=int(time.time()),
        )
        home_id = uuid4().hex
        engine = SimulationService(home_id)
        home = Home(
            id=home_id,
            user_id=user.id,
            world_id=engine._world_id,
            revision=0,
            config_revision=0,
            simulated_minutes=0,
            event_sequence=0,
        )
        try:
            async with request.app.state.database.sessions.begin() as session:
                session.add(user)
                await session.flush()
                session.add(home)
                await session.flush()
                session.add(Preference(home_id=home.id, version=1, data=dict(DEFAULT_PREFERENCES)))
                await save_engine(session, home, engine)
                token, record = await rotate(session, request.state.auth_session, user.id)
        except IntegrityError as error:
            raise SimulationError(409, "username_unavailable", "用户名不可用") from error
        set_cookie(request, response, token)
        return session_view(
            request, record, {"id": user.id, "username": user.username, "home_id": home.id}
        )

    @router.post("/login")
    async def login(body: Credentials, request: Request, response: Response):
        request.app.state.attempts.check(request, "login")
        async with request.app.state.database.sessions.begin() as session:
            user = await session.scalar(select(User).where(User.username == body.username.lower()))
            try:
                await run_in_threadpool(
                    HASHER.verify, user.password_hash if user else DUMMY_HASH, body.password
                )
            except VerificationError:
                user = None
            if user is None:
                raise SimulationError(401, "invalid_credentials", "用户名或密码不正确")
            home = await session.scalar(select(Home).where(Home.user_id == user.id))
            token, record = await rotate(session, request.state.auth_session, user.id)
        set_cookie(request, response, token)
        return session_view(
            request, record, {"id": user.id, "username": user.username, "home_id": home.id}
        )

    @router.post("/logout")
    async def logout(body: EmptyBody, request: Request, response: Response):
        async with request.app.state.database.sessions.begin() as session:
            token, record = await rotate(session, request.state.auth_session)
        set_cookie(request, response, token)
        return session_view(request, record)

    return router
