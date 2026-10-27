"""Migrations run only through the guarded homemind.migrate entry point."""

from alembic import context

connection = context.config.attributes.get("connection")
if connection is None:
    raise RuntimeError("请使用 python -m homemind.migrate")
context.configure(connection=connection, compare_type=True)
with context.begin_transaction():
    context.run_migrations()
