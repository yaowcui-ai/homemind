"""Offline D2 upper-bound timing; synthetic records, no settings, secrets or HTTP."""

import asyncio
import ctypes
import json
import os
import time
from pathlib import Path

from homemind.agent.forecast import run_forecast
from homemind.simulation.models import EntityCreate, RoomCreate
from homemind.simulation.service import SimulationService


def process_memory():
    """Windows process resident/peak memory, including Python and loaded libraries."""
    if os.name != "nt":
        return None
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
            (name, ctypes.c_size_t)
            for name in (
                "PeakWorkingSetSize",
                "WorkingSetSize",
                "QuotaPeakPagedPoolUsage",
                "QuotaPagedPoolUsage",
                "QuotaPeakNonPagedPoolUsage",
                "QuotaNonPagedPoolUsage",
                "PagefileUsage",
                "PeakPagefileUsage",
            )
        ]

    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    success = ctypes.windll.psapi.GetProcessMemoryInfo(
        wintypes.HANDLE(-1), ctypes.byref(counters), counters.cb
    )
    if not success:
        raise ctypes.WinError()
    return dict(
        working_set_bytes=counters.WorkingSetSize,
        peak_working_set_bytes=counters.PeakWorkingSetSize,
    )


async def main():
    engine = SimulationService()
    snapshot = engine.snapshot()
    room_id = snapshot["rooms"][0]["id"]
    by_type = {e["type"]: e for e in snapshot["entities"] if e["room_id"] == room_id}
    while len(engine._rooms) < 16:
        engine.create_room(RoomCreate(name="Synthetic benchmark room"))
    room_ids = list(engine._rooms)
    while len(engine._entities) < 256:
        index = len(engine._entities)
        engine.create_entity(
            EntityCreate(room_id=room_ids[index % 16], name="Synthetic load", type="light")
        )
    goal = dict(
        kind="goal",
        room_id=room_id,
        climate_entity_id=by_type["climate"]["id"],
        cover_entity_id=by_type["cover"]["id"],
        target_temperature_c=26,
        ready_in_minutes=1440,
        priority="energy_first",
        allowed_fan_modes=["low", "auto"],
        cover_constraint="allow_open_close",
        keep_entity_ids=[],
        protected_room_ids=[],
    )
    before = engine.snapshot()
    lag_ms = []
    stop = asyncio.Event()

    async def ticker():
        while not stop.is_set():
            start = time.perf_counter()
            await asyncio.sleep(0.01)
            lag_ms.append(max(0, (time.perf_counter() - start - 0.01) * 1000))

    ticker_task = asyncio.create_task(ticker())
    started = time.perf_counter()
    memory_before = process_memory()
    try:
        result = await run_forecast(engine, goal, time.monotonic() + 60)
    finally:
        stop.set()
        await ticker_task
    evidence = dict(
        rooms=16,
        entities=256,
        candidates=len(result["candidates"]),
        simulated_steps=5760,
        elapsed_ms=round((time.perf_counter() - started) * 1000),
        max_event_loop_lag_ms=round(max(lag_ms), 3),
        ticker_samples=len(lag_ms),
        source_unchanged=engine.snapshot() == before,
        process_memory_before=memory_before,
        process_memory_after=process_memory(),
        real_model_requests=0,
        note="Single offline synthetic run; process-local two-worker bound.",
    )
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    path = Path(__file__).resolve().parents[2] / "output" / "product-d2-forecast-benchmark.json"
    path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
