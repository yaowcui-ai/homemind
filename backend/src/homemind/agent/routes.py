"""Authenticated single-agent endpoints; mounted before dynamic task routes."""

from fastapi import APIRouter, Header, Request

from homemind.agent.schemas import AgentRequest, ConfirmRequest, ReplyRequest
from homemind.agent.service import confirm_agent, create_agent, public_config, reply_agent
from homemind.auth import require_home


def agent_router():
    router = APIRouter(prefix="/tasks", tags=["agent"])

    @router.get("/agent/config")
    async def config(request: Request):
        require_home(request)
        return public_config(request.app)

    @router.post("/agent")
    async def create(
        body: AgentRequest,
        request: Request,
        idempotency_key: str = Header(pattern=r"^[A-Za-z0-9._:-]{8,128}$"),
    ):
        require_home(request)
        return await create_agent(request, body, idempotency_key)

    @router.post("/{task_id}/reply")
    async def reply(
        task_id: str,
        body: ReplyRequest,
        request: Request,
        idempotency_key: str = Header(pattern=r"^[A-Za-z0-9._:-]{8,128}$"),
    ):
        require_home(request)
        return await reply_agent(request, task_id, body, idempotency_key)

    @router.post("/{task_id}/confirm")
    async def confirm(
        task_id: str,
        body: ConfirmRequest,
        request: Request,
        idempotency_key: str = Header(pattern=r"^[A-Za-z0-9._:-]{8,128}$"),
    ):
        require_home(request)
        return await confirm_agent(request, task_id, body, idempotency_key)

    return router
