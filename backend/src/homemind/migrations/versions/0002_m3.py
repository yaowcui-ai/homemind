"""Make opaque idempotency keys case-sensitive regardless of database defaults."""

from alembic import op
from sqlalchemy.dialects import mysql

revision = "0002_m3"
down_revision = "0001_m3"
branch_labels = None
depends_on = None


def upgrade():
    # Only this opaque caller-provided key needs explicit binary comparison.
    # Keep existing IDs, foreign keys, household rows and table defaults intact.
    op.alter_column(
        "hm_tasks",
        "idempotency_key",
        existing_type=mysql.VARCHAR(128),
        type_=mysql.VARCHAR(128, charset="utf8mb4", collation="utf8mb4_bin"),
        existing_nullable=False,
    )


def downgrade():
    raise RuntimeError("禁止回退已保存幂等键的区分大小写语义")
