"""Finite validation evidence; never retain rejected model values or external lookups."""

from contextlib import contextmanager

from pydantic import ValidationError

from homemind.simulation.models import SimulationError

SCHEMA_CODES = frozenset(
    {
        "missing",
        "extra_forbidden",
        "literal_error",
        "int_type",
        "int_parsing",
        "less_than_equal",
        "greater_than_equal",
        "list_type",
        "dict_type",
        "string_type",
        "string_too_short",
        "string_too_long",
        "union_tag_invalid",
        "union_tag_not_found",
        "json_invalid",
        "model_type",
        "value_error",
        "too_long",
        "too_short",
        "bool_type",
    }
)


def failure_record(role, path, category):
    return {"stage": "validation_detail", "message": f"role={role} | path={path} | type={category}"}


def schema_records(error, adapter, role):
    """Only schema-owned field names, bounded indexes and static error categories."""
    fields = set()

    def collect(value):
        if isinstance(value, dict):
            fields.update(value.get("properties", {}))
            for child in value.values():
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    collect(adapter.json_schema())
    errors = (
        error.errors(include_input=False, include_context=False, include_url=False)[:3]
        if isinstance(error, ValidationError)
        else [{"type": "validation_error", "loc": ()}]
    )
    records = []
    for item in errors:
        path = "$"
        for index, segment in enumerate(item["loc"][:6]):
            if index == 0 and segment in {"goal", "selection", "plan", "clarify", "refuse"}:
                continue
            if isinstance(segment, int):
                path += f"[{segment}]" if 0 <= segment < 100 else "[*]"
            else:
                path += "." + (segment if segment in fields else "<field>")
        code = item["type"] if item["type"] in SCHEMA_CODES else "validation_error"
        records.append(failure_record(role, path, code))
    return records


@contextmanager
def validation_field(output_kind, field_path, reference_kind=None, in_current_home=None):
    try:
        yield
    except SimulationError as error:
        if not hasattr(error, "diagnostic"):
            error.diagnostic = {
                "phase": "validation",
                "output_kind": output_kind,
                "code": error.code,
                "field_path": field_path,
                "reference_kind": reference_kind,
                "reference_in_current_home": in_current_home,
            }
        raise


def reference(engine, kind, value, path, *, output_kind="plan"):
    # The engine contains only the authenticated household. Unknown and foreign IDs
    # deliberately have the same result; do not query the database to distinguish them.
    items = engine._rooms if kind == "room" else engine._entities
    item = items.get(value)
    available = item is not None and not getattr(item, "archived", False)
    with validation_field(output_kind, path, kind, available):
        return engine._room(value) if kind == "room" else engine._entity(value)
