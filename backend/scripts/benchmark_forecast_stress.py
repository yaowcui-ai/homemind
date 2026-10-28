"""Upper-bound active/archived fixtures and two-worker contention; no model or DB."""

import asyncio
import json
import time
from pathlib import Path

from benchmark_forecast import process_memory

from homemind.agent.forecast import run_forecast
from homemind.simulation.models import ControlRequest, EntityCreate, EventRequest, RoomCreate
from homemind.simulation.service import SimulationService


def fixture(archived=False):
    engine = SimulationService()
    initial = engine.snapshot()
    target = initial["rooms"][0]["id"]
    devices = {e["type"]: e for e in initial["entities"] if e["room_id"] == target}
    while len(engine._rooms) < 16:
        engine.create_room(RoomCreate(name="Synthetic stress room"))
    other_rooms = [rid for rid in engine._rooms if rid != target]
    while len(engine._entities) < 256:
        n = len(engine._entities)
        kind = ("climate", "climate", "light", "window", "occupancy", "temperature")[n % 6]
        snapshot = engine.create_entity(
            EntityCreate(
                room_id=other_rooms[n % len(other_rooms)],
                name="Synthetic active load",
                type=kind,
            )
        )
        entity_id = snapshot["entities"][-1]["id"]
        if kind == "climate":
            engine.control(
                entity_id,
                ControlRequest(
                    action="set_climate",
                    parameters={
                        "mode": "cool",
                        "target_temperature_c": 16,
                        "fan_mode": "auto",
                    },
                ),
            )
        elif kind == "light":
            engine.control(
                entity_id,
                ControlRequest(
                    action="set_light",
                    parameters={
                        "power": True,
                        "brightness_pct": 100,
                    },
                ),
            )
        elif kind in {"window", "occupancy"}:
            engine.event(
                EventRequest(
                    entity_id=entity_id,
                    **{
                        "window_open" if kind == "window" else "occupied": True,
                    },
                )
            )
        if archived:
            engine.delete_entity(entity_id)
    goal = dict(
        kind="goal",
        room_id=target,
        climate_entity_id=devices["climate"]["id"],
        cover_entity_id=devices["cover"]["id"],
        target_temperature_c=26,
        ready_in_minutes=1440,
        priority="energy_first",
        allowed_fan_modes=["low", "auto"],
        cover_constraint="allow_open_close",
        keep_entity_ids=[],
        protected_room_ids=[],
    )
    return engine, goal


async def batch(name, count, archived=False):
    fixtures = [fixture(archived) for _ in range(count)]
    baselines = [engine.snapshot() for engine, _ in fixtures]
    lag_ms = []
    stop = asyncio.Event()

    async def ticker():
        while not stop.is_set():
            started = time.perf_counter()
            await asyncio.sleep(0.01)
            lag_ms.append(max(0, (time.perf_counter() - started - 0.01) * 1000))

    async def measured(engine, goal):
        started = time.perf_counter()
        try:
            result = await run_forecast(engine, goal, time.monotonic() + 60)
            outcome = {"outcome": "completed", "candidates": len(result["candidates"])}
        except TimeoutError:
            outcome = {"outcome": "round_timeout"}
        except Exception as error:
            outcome = {"outcome": getattr(error, "code", type(error).__name__)}
        return outcome | {"elapsed_ms": round((time.perf_counter() - started) * 1000)}

    memory_before = process_memory()
    ticker_task = asyncio.create_task(ticker())
    try:
        results = await asyncio.gather(*(measured(*f) for f in fixtures))
    finally:
        stop.set()
        await ticker_task
    return dict(
        name=name,
        concurrent_workers=count,
        rooms_per_worker=16,
        entity_records_per_worker=256,
        archived_per_worker=len(fixtures[0][0]._archives),
        steps_per_completed_worker=5760,
        results=results,
        max_event_loop_lag_ms=round(max(lag_ms), 3),
        process_memory_before=memory_before,
        process_memory_after=process_memory(),
        all_sources_unchanged=all(e.snapshot() == b for (e, _), b in zip(fixtures, baselines)),
    )


async def main():
    runs = [
        await batch("active-mixed-single", 1),
        await batch("active-mixed-two-workers", 2),
        await batch("archived-records-single", 1, archived=True),
    ]
    evidence = dict(
        real_model_requests=0,
        runs=runs,
        note=(
            "Synthetic boundary loads, not a proof of universal worst-case latency; "
            "no concurrent test suites requested."
        ),
    )
    path = Path(__file__).resolve().parents[2] / "output/product-d2-forecast-stress.json"
    path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
