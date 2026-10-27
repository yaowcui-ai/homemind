"""Lossless private engine codec; public snapshots never serve as physical state."""

from collections import deque
from copy import deepcopy
from dataclasses import asdict
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from homemind.persistence.models import EntityRecord, Event, Home, RoomRecord
from homemind.simulation.models import Entity, EntityType, FaultMode, PendingControl, Room
from homemind.simulation.service import SimulationService


async def load_engine(session: AsyncSession, home: Home) -> SimulationService:
    engine = SimulationService(home.id, seed=False)
    engine._world_id = home.world_id
    engine._revision = home.revision
    engine._config_revision = home.config_revision
    engine._minutes = home.simulated_minutes
    engine._event_sequence = home.event_sequence
    rooms = await session.scalars(
        select(RoomRecord)
        .where(RoomRecord.home_id == home.id, RoomRecord.archived.is_(False))
        .order_by(RoomRecord.position)
    )
    for record in rooms:
        engine._rooms[record.id] = Room(
            **{
                key: getattr(record, key)
                for key in (
                    "id",
                    "name",
                    "initial_temperature",
                    "temperature",
                    "primary_temperature_entity_id",
                    "primary_occupancy_entity_id",
                )
            }
        )
    entities = await session.scalars(
        select(EntityRecord).where(EntityRecord.home_id == home.id).order_by(EntityRecord.position)
    )
    for record in entities:
        fields = {
            key: deepcopy(getattr(record, key))
            for key in (
                "id",
                "room_id",
                "name",
                "config",
                "state",
                "enabled",
                "available",
                "known",
                "archived",
                "version",
                "observed_at_minutes",
                "energy_watt_minutes",
                "delay_minutes",
            )
        }
        engine._entities[record.id] = Entity(
            **fields,
            type=EntityType(record.type),
            fault_mode=FaultMode(record.fault_mode),
            pending=PendingControl(**record.pending) if record.pending else None,
        )
    events = list(
        await session.scalars(
            select(Event).where(Event.home_id == home.id).order_by(Event.sequence.desc()).limit(50)
        )
    )
    engine._events = deque(
        (
            {
                "sequence": e.sequence,
                "at_minutes": e.at_minutes,
                "kind": e.kind,
                "message": e.message,
                "entity_id": e.entity_id,
            }
            for e in reversed(events)
        ),
        maxlen=50,
    )
    return engine


def archive_data(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: archive_data(item) for key, item in value.items()}
    if isinstance(value, list):
        return [archive_data(item) for item in value]
    return value


async def save_engine(
    session: AsyncSession, home: Home, engine: SimulationService, *, task_id: str | None = None
) -> None:
    home.world_id = engine._world_id
    home.revision = engine._revision
    home.config_revision = engine._config_revision
    home.simulated_minutes = engine._minutes
    home.event_sequence = engine._event_sequence
    rooms = {
        r.id: r
        for r in await session.scalars(select(RoomRecord).where(RoomRecord.home_id == home.id))
    }
    for room_id, record in rooms.items():
        record.archived = room_id not in engine._rooms
    for position, room in enumerate(engine._rooms.values()):
        record = rooms.get(room.id)
        if record is None:
            record = RoomRecord(id=room.id, home_id=home.id)
            session.add(record)
        for key, value in asdict(room).items():
            setattr(record, key, value)
        record.archived = False
        record.position = position
    await session.flush()  # Rooms exist before entity foreign keys are written.
    entities = {
        e.id: e
        for e in await session.scalars(select(EntityRecord).where(EntityRecord.home_id == home.id))
    }
    archives = {
        a["entity"].id: archive_data(
            {
                "world_id": a["world_id"],
                "at_minutes": a["at_minutes"],
                "entity": asdict(a["entity"]),
            }
        )
        for a in engine._archives
    }
    for position, entity in enumerate(engine._entities.values()):
        record = entities.get(entity.id)
        if record is None:
            record = EntityRecord(id=entity.id, home_id=home.id)
            session.add(record)
        for key, value in asdict(entity).items():
            setattr(record, key, deepcopy(value))
        record.position = position
        if entity.id in archives:
            record.archive_snapshot = archives[entity.id]
    for event in engine._new_events:
        session.add(Event(home_id=home.id, task_id=task_id, data={}, **event))
    engine._new_events.clear()
    await session.flush()
