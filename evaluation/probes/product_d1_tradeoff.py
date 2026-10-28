"""Replay existing physics only: no settings, database, provider, or forecast tool."""

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from homemind.simulation.models import ControlRequest  # noqa: E402
from homemind.simulation.physics import MODEL_VERSION  # noqa: E402
from homemind.simulation.service import SimulationService  # noqa: E402


def replay(horizon: int, fan: str) -> dict:
    engine = SimulationService()
    initial = engine.snapshot()
    room = next(room for room in initial["rooms"] if room["name"] == "客厅")
    devices = {e["type"]: e for e in initial["entities"] if e["room_id"] == room["id"]}
    engine.control(
        devices["climate"]["id"],
        ControlRequest(
            action="set_climate",
            parameters={"mode": "cool", "target_temperature_c": 26, "fan_mode": fan},
        ),
    )
    engine.control(
        devices["cover"]["id"],
        ControlRequest(action="set_cover", parameters={"position_pct": 0}),
    )
    first = 0 if room["temperature_c"] <= 26 else None
    for minute in range(1, horizon + 1):
        final = engine.advance(1)
        reading = next(r["temperature_c"] for r in final["rooms"] if r["id"] == room["id"])
        if first is None and reading <= 26:
            first = minute
    # Only target AC and moving cover consume energy in this fixture.
    return {
        "horizon_minutes": horizon,
        "fan_mode": fan,
        "final_temperature_c": reading,
        "first_observed_goal_minute": first,
        "energy_wh": final["energy_wh"] - initial["energy_wh"],
        "deadline_met": reading <= 26,
    }


if __name__ == "__main__":
    payload = {
        "date": "2026-10-28 Asia/Shanghai",
        "source": "existing_simulation_engine_only",
        "real_model_requests": 0,
        "new_forecast_tool_implemented": False,
        "initial_facts": {
            "living_temperature_c": 28.0,
            "bedroom_temperature_c": 27.0,
            "windows": "known_closed",
            "occupancy": False,
            "lights": "off",
            "all_climate_initial_modes": "off",
            "cover_target_pct": 0,
            "target_temperature_c": 26,
        },
        "model_version": MODEL_VERSION,
        "physics_source_sha256": hashlib.sha256(
            (ROOT / "backend/src/homemind/simulation/physics.py").read_bytes()
        ).hexdigest(),
        "observations": [replay(h, fan) for h in (20, 60) for fan in ("low", "auto")],
    }
    # Date identifies the frozen fixture, not a claim about a later execution date.
    sys.stdout.buffer.write((json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode())
