"""Finite validation evidence; never retain rejected model values or external lookups."""

from contextlib import contextmanager

from homemind.simulation.models import SimulationError


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
