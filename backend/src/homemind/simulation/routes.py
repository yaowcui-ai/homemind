"""Every operation loads and commits only the authenticated household."""

from fastapi import APIRouter, Request

from homemind.auth import require_home
from homemind.simulation.models import (
    AdvanceRequest,
    ControlRequest,
    EntityCreate,
    EntityPatch,
    EventRequest,
    FaultRequest,
    ResetRequest,
    RoomCreate,
    RoomPatch,
    SimulationError,
)


async def operate(request, method, *args, debug=False):
    home_id = require_home(request)
    if debug and not request.app.state.settings.simulation_debug_enabled:
        raise SimulationError(403, "debug_disabled", "仿真调试功能未启用")
    async with request.app.state.database.home(home_id, save=method != "snapshot") as (
        _,
        _,
        engine,
    ):
        return getattr(engine, method)(*args)


def simulation_router() -> APIRouter:
    router = APIRouter(prefix="/simulation", tags=["simulation"])

    @router.get("")
    async def get_snapshot(request: Request):
        return await operate(request, "snapshot")

    @router.post("/rooms")
    async def create_room(body: RoomCreate, request: Request):
        return await operate(request, "create_room", body)

    @router.patch("/rooms/{room_id}")
    async def patch_room(room_id: str, body: RoomPatch, request: Request):
        return await operate(request, "patch_room", room_id, body)

    @router.delete("/rooms/{room_id}")
    async def delete_room(room_id: str, request: Request):
        return await operate(request, "delete_room", room_id)

    @router.post("/entities")
    async def create_entity(body: EntityCreate, request: Request):
        return await operate(request, "create_entity", body)

    @router.patch("/entities/{entity_id}")
    async def patch_entity(entity_id: str, body: EntityPatch, request: Request):
        return await operate(request, "patch_entity", entity_id, body)

    @router.delete("/entities/{entity_id}")
    async def delete_entity(entity_id: str, request: Request):
        return await operate(request, "delete_entity", entity_id)

    @router.post("/controls/{entity_id}")
    async def control(entity_id: str, body: ControlRequest, request: Request):
        return await operate(request, "control", entity_id, body)

    @router.post("/events")
    async def event(body: EventRequest, request: Request):
        return await operate(request, "event", body, debug=True)

    @router.post("/faults/{entity_id}")
    async def fault(entity_id: str, body: FaultRequest, request: Request):
        return await operate(request, "set_fault", entity_id, body, debug=True)

    @router.post("/advance")
    async def advance(body: AdvanceRequest, request: Request):
        return await operate(request, "advance", body.minutes, debug=True)

    @router.post("/reset")
    async def reset(body: ResetRequest, request: Request):
        return await operate(request, "reset", debug=True)

    return router
