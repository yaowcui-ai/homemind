"""Versioned household preferences copied into each rule task."""

from typing import Literal

from fastapi import APIRouter, Request

from homemind.auth import require_home
from homemind.persistence.models import Preference
from homemind.simulation.models import InputModel, Minutes, TargetTemperature


class PreferencesPatch(InputModel):
    require_fields = True
    comfort_temperature_c: TargetTemperature | None = None
    sleep_temperature_c: TargetTemperature | None = None
    fan_mode: Literal["low", "auto"] | None = None
    arrival_lead_minutes: Minutes | None = None


def preference_view(record):
    return {"version": record.version, **record.data}


def preferences_router():
    router = APIRouter(prefix="/preferences", tags=["preferences"])

    @router.get("")
    async def read(request: Request):
        home_id = require_home(request)
        async with request.app.state.database.sessions() as session:
            return preference_view(await session.get(Preference, home_id))

    @router.patch("")
    async def update(body: PreferencesPatch, request: Request):
        async with request.app.state.database.home(require_home(request), save=False) as (
            session,
            _,
            _e,
        ):
            record = await session.get(Preference, request.state.home_id)
            record.data = {**record.data, **body.model_dump(exclude_unset=True)}
            record.version += 1
            return preference_view(record)

    return router
