"""M3 initial relational schema; frozen 2026-10-27."""

import sqlalchemy as sa
from alembic import op

revision = "0001_m3"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "hm_installation",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("instance_id", sa.String(length=64), primary_key=False, nullable=False),
        sa.Column("created_at", sa.Integer(), primary_key=False, nullable=False),
    )
    op.create_table(
        "hm_users",
        sa.Column("id", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column("username", sa.String(length=32), primary_key=False, nullable=False),
        sa.Column("password_hash", sa.String(length=255), primary_key=False, nullable=False),
        sa.Column("created_at", sa.Integer(), primary_key=False, nullable=False),
        sa.UniqueConstraint("username"),
    )
    op.create_table(
        "hm_homes",
        sa.Column("id", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            sa.String(length=64),
            sa.ForeignKey("hm_users.id"),
            primary_key=False,
            nullable=False,
        ),
        sa.Column("world_id", sa.String(length=64), primary_key=False, nullable=False),
        sa.Column("revision", sa.Integer(), primary_key=False, nullable=False),
        sa.Column("config_revision", sa.Integer(), primary_key=False, nullable=False),
        sa.Column("simulated_minutes", sa.Integer(), primary_key=False, nullable=False),
        sa.Column("event_sequence", sa.Integer(), primary_key=False, nullable=False),
        sa.UniqueConstraint("user_id"),
    )
    op.create_table(
        "hm_sessions",
        sa.Column("digest", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            sa.String(length=64),
            sa.ForeignKey("hm_users.id"),
            primary_key=False,
            nullable=True,
        ),
        sa.Column("csrf_token", sa.String(length=128), primary_key=False, nullable=False),
        sa.Column("expires_at", sa.Integer(), primary_key=False, nullable=False),
    )
    op.create_index("ix_hm_sessions_expires_at", "hm_sessions", ["expires_at"], unique=False)
    op.create_table(
        "hm_preferences",
        sa.Column(
            "home_id",
            sa.String(length=64),
            sa.ForeignKey("hm_homes.id"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), primary_key=False, nullable=False),
        sa.Column("data", sa.JSON(), primary_key=False, nullable=False),
    )
    op.create_table(
        "hm_rooms",
        sa.Column("id", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column(
            "home_id",
            sa.String(length=64),
            sa.ForeignKey("hm_homes.id"),
            primary_key=False,
            nullable=False,
        ),
        sa.Column("name", sa.String(length=80), primary_key=False, nullable=False),
        sa.Column(
            "initial_temperature",
            sa.Numeric(precision=16, scale=3),
            primary_key=False,
            nullable=False,
        ),
        sa.Column(
            "temperature", sa.Numeric(precision=16, scale=3), primary_key=False, nullable=False
        ),
        sa.Column(
            "primary_temperature_entity_id", sa.String(length=64), primary_key=False, nullable=True
        ),
        sa.Column(
            "primary_occupancy_entity_id", sa.String(length=64), primary_key=False, nullable=True
        ),
        sa.Column("archived", sa.Boolean(), primary_key=False, nullable=False),
        sa.Column("position", sa.Integer(), primary_key=False, nullable=False),
    )
    op.create_index("ix_hm_rooms_home_id", "hm_rooms", ["home_id"], unique=False)
    op.create_table(
        "hm_tasks",
        sa.Column("id", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column(
            "home_id",
            sa.String(length=64),
            sa.ForeignKey("hm_homes.id"),
            primary_key=False,
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(length=128), primary_key=False, nullable=False),
        sa.Column("request_hash", sa.String(length=64), primary_key=False, nullable=False),
        sa.Column("request", sa.JSON(), primary_key=False, nullable=False),
        sa.Column("scenario", sa.String(length=24), primary_key=False, nullable=False),
        sa.Column("status", sa.String(length=32), primary_key=False, nullable=False),
        sa.Column("world_id", sa.String(length=64), primary_key=False, nullable=False),
        sa.Column("initial_snapshot", sa.JSON(), primary_key=False, nullable=False),
        sa.Column("preferences_snapshot", sa.JSON(), primary_key=False, nullable=False),
        sa.Column("plan", sa.JSON(), primary_key=False, nullable=False),
        sa.Column("final_snapshot", sa.JSON(), primary_key=False, nullable=False),
        sa.Column("verification", sa.JSON(), primary_key=False, nullable=False),
        sa.Column("message", sa.String(length=255), primary_key=False, nullable=False),
        sa.Column("created_at", sa.Integer(), primary_key=False, nullable=False),
        sa.Column("updated_at", sa.Integer(), primary_key=False, nullable=False),
        sa.UniqueConstraint("home_id", "idempotency_key"),
    )
    op.create_index("ix_hm_tasks_home_id", "hm_tasks", ["home_id"], unique=False)
    op.create_table(
        "hm_actions",
        sa.Column("id", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column(
            "home_id",
            sa.String(length=64),
            sa.ForeignKey("hm_homes.id"),
            primary_key=False,
            nullable=False,
        ),
        sa.Column(
            "task_id",
            sa.String(length=64),
            sa.ForeignKey("hm_tasks.id"),
            primary_key=False,
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), primary_key=False, nullable=False),
        sa.Column("entity_id", sa.String(length=64), primary_key=False, nullable=False),
        sa.Column("entity_name", sa.String(length=80), primary_key=False, nullable=False),
        sa.Column("room_name", sa.String(length=80), primary_key=False, nullable=False),
        sa.Column("action", sa.String(length=32), primary_key=False, nullable=False),
        sa.Column("parameters", sa.JSON(), primary_key=False, nullable=False),
        sa.Column("status", sa.String(length=24), primary_key=False, nullable=False),
        sa.Column("transport_outcome", sa.String(length=24), primary_key=False, nullable=True),
        sa.Column("message", sa.String(length=255), primary_key=False, nullable=False),
        sa.Column("readback", sa.JSON(), primary_key=False, nullable=False),
    )
    op.create_index("ix_hm_actions_task_id", "hm_actions", ["task_id"], unique=False)
    op.create_index("ix_hm_actions_home_id", "hm_actions", ["home_id"], unique=False)
    op.create_table(
        "hm_entities",
        sa.Column("id", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column(
            "home_id",
            sa.String(length=64),
            sa.ForeignKey("hm_homes.id"),
            primary_key=False,
            nullable=False,
        ),
        sa.Column(
            "room_id",
            sa.String(length=64),
            sa.ForeignKey("hm_rooms.id"),
            primary_key=False,
            nullable=False,
        ),
        sa.Column("name", sa.String(length=80), primary_key=False, nullable=False),
        sa.Column("type", sa.String(length=24), primary_key=False, nullable=False),
        sa.Column("config", sa.JSON(), primary_key=False, nullable=False),
        sa.Column("state", sa.JSON(), primary_key=False, nullable=False),
        sa.Column("enabled", sa.Boolean(), primary_key=False, nullable=False),
        sa.Column("available", sa.Boolean(), primary_key=False, nullable=False),
        sa.Column("known", sa.Boolean(), primary_key=False, nullable=False),
        sa.Column("archived", sa.Boolean(), primary_key=False, nullable=False),
        sa.Column("version", sa.Integer(), primary_key=False, nullable=False),
        sa.Column("observed_at_minutes", sa.Integer(), primary_key=False, nullable=False),
        sa.Column(
            "energy_watt_minutes",
            sa.Numeric(precision=24, scale=6),
            primary_key=False,
            nullable=False,
        ),
        sa.Column("fault_mode", sa.String(length=24), primary_key=False, nullable=False),
        sa.Column("delay_minutes", sa.Integer(), primary_key=False, nullable=False),
        sa.Column("pending", sa.JSON(), primary_key=False, nullable=True),
        sa.Column("archive_snapshot", sa.JSON(), primary_key=False, nullable=True),
        sa.Column("position", sa.Integer(), primary_key=False, nullable=False),
    )
    op.create_index("ix_hm_entities_home_id", "hm_entities", ["home_id"], unique=False)
    op.create_table(
        "hm_events",
        sa.Column(
            "home_id",
            sa.String(length=64),
            sa.ForeignKey("hm_homes.id"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "task_id",
            sa.String(length=64),
            sa.ForeignKey("hm_tasks.id"),
            primary_key=False,
            nullable=True,
        ),
        sa.Column("entity_id", sa.String(length=64), primary_key=False, nullable=True),
        sa.Column("at_minutes", sa.Integer(), primary_key=False, nullable=False),
        sa.Column("kind", sa.String(length=64), primary_key=False, nullable=False),
        sa.Column("message", sa.String(length=255), primary_key=False, nullable=False),
        sa.Column("data", sa.JSON(), primary_key=False, nullable=False),
    )


def downgrade():
    raise RuntimeError("禁止自动降级删除家庭数据；请使用独立备份恢复流程")
