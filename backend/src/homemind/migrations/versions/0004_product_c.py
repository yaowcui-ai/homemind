"""Persist protected task clock submissions without rewriting existing tasks."""

import sqlalchemy as sa
from alembic import op

revision = "0004_product_c"
down_revision = "0003_m4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("hm_tasks", sa.Column("advance_records", sa.JSON(), nullable=True))


def downgrade():
    raise RuntimeError("禁止删除已保存的推进幂等记录")
