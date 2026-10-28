"""One authoritative row per mutable household fact; immutable task snapshots."""

from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.mysql import VARCHAR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Installation(Base):
    __tablename__ = "hm_installation"
    id: Mapped[int] = mapped_column(primary_key=True)
    instance_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[int] = mapped_column(Integer)


class User(Base):
    __tablename__ = "hm_users"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str] = mapped_column(String(32), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[int] = mapped_column(Integer)


class AuthSession(Base):
    __tablename__ = "hm_sessions"
    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("hm_users.id"))
    csrf_token: Mapped[str] = mapped_column(String(128))
    expires_at: Mapped[int] = mapped_column(Integer, index=True)


class Home(Base):
    __tablename__ = "hm_homes"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("hm_users.id"), unique=True)
    world_id: Mapped[str] = mapped_column(String(64))
    revision: Mapped[int] = mapped_column(Integer)
    config_revision: Mapped[int] = mapped_column(Integer)
    simulated_minutes: Mapped[int] = mapped_column(Integer)
    event_sequence: Mapped[int] = mapped_column(Integer)


class RoomRecord(Base):
    __tablename__ = "hm_rooms"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    home_id: Mapped[str] = mapped_column(ForeignKey("hm_homes.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    initial_temperature: Mapped[Decimal] = mapped_column(Numeric(16, 3))
    temperature: Mapped[Decimal] = mapped_column(Numeric(16, 3))
    primary_temperature_entity_id: Mapped[str | None] = mapped_column(String(64))
    primary_occupancy_entity_id: Mapped[str | None] = mapped_column(String(64))
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[int] = mapped_column(Integer)


class EntityRecord(Base):
    __tablename__ = "hm_entities"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    home_id: Mapped[str] = mapped_column(ForeignKey("hm_homes.id"), index=True)
    room_id: Mapped[str] = mapped_column(ForeignKey("hm_rooms.id"))
    name: Mapped[str] = mapped_column(String(80))
    type: Mapped[str] = mapped_column(String(24))
    config: Mapped[dict[str, Any]] = mapped_column(JSON)
    state: Mapped[dict[str, Any]] = mapped_column(JSON)
    enabled: Mapped[bool] = mapped_column(Boolean)
    available: Mapped[bool] = mapped_column(Boolean)
    known: Mapped[bool] = mapped_column(Boolean)
    archived: Mapped[bool] = mapped_column(Boolean)
    version: Mapped[int] = mapped_column(Integer)
    observed_at_minutes: Mapped[int] = mapped_column(Integer)
    energy_watt_minutes: Mapped[Decimal] = mapped_column(Numeric(24, 6))
    fault_mode: Mapped[str] = mapped_column(String(24))
    delay_minutes: Mapped[int] = mapped_column(Integer)
    pending: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    archive_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    position: Mapped[int] = mapped_column(Integer)


class Preference(Base):
    __tablename__ = "hm_preferences"
    home_id: Mapped[str] = mapped_column(ForeignKey("hm_homes.id"), primary_key=True)
    version: Mapped[int] = mapped_column(Integer)
    data: Mapped[dict[str, Any]] = mapped_column(JSON)


class Task(Base):
    __tablename__ = "hm_tasks"
    __table_args__ = (UniqueConstraint("home_id", "idempotency_key"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    home_id: Mapped[str] = mapped_column(ForeignKey("hm_homes.id"), index=True)
    idempotency_key: Mapped[str] = mapped_column(
        String(128).with_variant(VARCHAR(128, charset="utf8mb4", collation="utf8mb4_bin"), "mysql")
    )
    request_hash: Mapped[str] = mapped_column(String(64))
    request: Mapped[dict[str, Any]] = mapped_column(JSON)
    scenario: Mapped[str] = mapped_column(String(24))
    mode: Mapped[str] = mapped_column(String(24), default="rule", server_default="rule")
    agent_run: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    advance_records: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32))
    world_id: Mapped[str] = mapped_column(String(64))
    initial_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    preferences_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    plan: Mapped[dict[str, Any]] = mapped_column(JSON)
    final_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    verification: Mapped[dict[str, Any]] = mapped_column(JSON)
    message: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[int] = mapped_column(Integer)


class Action(Base):
    __tablename__ = "hm_actions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    home_id: Mapped[str] = mapped_column(ForeignKey("hm_homes.id"), index=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("hm_tasks.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    entity_id: Mapped[str] = mapped_column(String(64))
    entity_name: Mapped[str] = mapped_column(String(80))
    room_name: Mapped[str] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(32))
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24))
    transport_outcome: Mapped[str | None] = mapped_column(String(24))
    message: Mapped[str] = mapped_column(String(255))
    readback: Mapped[dict[str, Any]] = mapped_column(JSON)


class Event(Base):
    __tablename__ = "hm_events"
    home_id: Mapped[str] = mapped_column(ForeignKey("hm_homes.id"), primary_key=True)
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("hm_tasks.id"))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    at_minutes: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(String(255))
    data: Mapped[dict[str, Any]] = mapped_column(JSON)
