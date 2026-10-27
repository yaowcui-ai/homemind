"""Persist explicit task modes and public single-agent round records."""

import sqlalchemy as sa
from alembic import op

revision = "0003_m4"
down_revision = "0002_m3"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "hm_tasks", sa.Column("mode", sa.String(24), nullable=False, server_default="rule")
    )
    op.add_column("hm_tasks", sa.Column("agent_run", sa.JSON(), nullable=True))


def downgrade():
    raise RuntimeError("禁止删除已保存的 Agent 运行记录")
