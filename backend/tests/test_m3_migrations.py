"""Migration identity checks never accept a foreign or mismatched database."""

import pytest


def test_database_name_and_installation_preflight():
    from homemind.migrate import check_identity

    check_identity("homemind_app", [], None, "own-install", initialize_empty=True)
    check_identity(
        "homemind_test",
        ["hm_installation", "hm_users", "alembic_version"],
        "own-install",
        "own-install",
        initialize_empty=False,
    )
    for name, tables, marker, initialize in [
        ("other_app", [], None, True),
        ("homemind_app", [], None, False),
        ("homemind_app", ["customers"], None, True),
        ("homemind_app", ["hm_users"], None, True),
        ("homemind_app", ["hm_installation"], "foreign-install", True),
        ("homemind_app", ["hm_installation", "foreign_table"], "own-install", False),
    ]:
        with pytest.raises(ValueError):
            check_identity(name, tables, marker, "own-install", initialize_empty=initialize)


def test_mysql_idempotency_ddl_requires_explicit_binary_column_collation():
    from sqlalchemy.dialects import mysql
    from sqlalchemy.schema import CreateTable

    from homemind.persistence.models import Task

    ddl = str(CreateTable(Task.__table__).compile(dialect=mysql.dialect()))
    key_line = next(line for line in ddl.splitlines() if "idempotency_key VARCHAR" in line)
    assert "CHARACTER SET utf8mb4 COLLATE utf8mb4_bin" in key_line


def test_latest_alembic_head_is_binary_key_upgrade_of_existing_installations():
    from pathlib import Path

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    import homemind
    from homemind.persistence.database import REVISION

    config = Config()
    config.set_main_option("script_location", str(Path(homemind.__file__).with_name("migrations")))
    script = ScriptDirectory.from_config(config)
    assert script.get_current_head() == REVISION == "0002_m3"
    assert script.get_revision("0002_m3").down_revision == "0001_m3"


def test_upgrade_changes_only_existing_idempotency_column_to_binary_mysql():
    import importlib
    from io import StringIO

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy.dialects import mysql

    output = StringIO()
    context = MigrationContext.configure(
        dialect=mysql.dialect(), opts={"as_sql": True, "output_buffer": output}
    )
    migration = importlib.import_module("homemind.migrations.versions.0002_m3")
    with Operations.context(context):
        migration.upgrade()
    ddl = output.getvalue().strip()
    assert ddl.startswith("ALTER TABLE hm_tasks MODIFY idempotency_key VARCHAR(128)")
    assert "CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL" in ddl
    assert ddl.count("ALTER TABLE") == 1
    assert "FOREIGN KEY" not in ddl and "DROP" not in ddl
