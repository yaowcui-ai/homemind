"""Thin synchronous routes; each service operation owns its complete lock scope."""

from fastapi import APIRouter

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
)
from homemind.simulation.service import SimulationService


def simulation_router(service: SimulationService) -> APIRouter:
    router = APIRouter(prefix="/simulation", tags=["simulation"])

    @router.get("")
    def get_snapshot():
        return service.snapshot()

    @router.post("/rooms")
    def create_room(body: RoomCreate):
        return service.create_room(body)

    @router.patch("/rooms/{room_id}")
    def patch_room(room_id: str, body: RoomPatch):
        return service.patch_room(room_id, body)

    @router.delete("/rooms/{room_id}")
    def delete_room(room_id: str):
        return service.delete_room(room_id)

    @router.post("/entities")
    def create_entity(body: EntityCreate):
        return service.create_entity(body)

    @router.patch("/entities/{entity_id}")
    def patch_entity(entity_id: str, body: EntityPatch):
        return service.patch_entity(entity_id, body)

    @router.delete("/entities/{entity_id}")
    def delete_entity(entity_id: str):
        return service.delete_entity(entity_id)

    @router.post("/controls/{entity_id}")
    def control(entity_id: str, body: ControlRequest):
        return service.control(entity_id, body)

    @router.post("/events")
    def event(body: EventRequest):
        return service.event(body)

    @router.post("/faults/{entity_id}")
    def fault(entity_id: str, body: FaultRequest):
        return service.set_fault(entity_id, body)

    @router.post("/advance")
    def advance(body: AdvanceRequest):
        return service.advance(body.minutes)

    @router.post("/reset")
    def reset(body: ResetRequest):
        return service.reset()

    return router
