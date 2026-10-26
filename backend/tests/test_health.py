"""Public liveness contract, exercised without a model or database."""

import asyncio

import httpx

from homemind.app import create_app


def request(path: str) -> httpx.Response:
    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(app=create_app())
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get(path)

    return asyncio.run(send())


def test_health_reports_api_liveness_without_external_services() -> None:
    response = request("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "homemind-api",
        "version": "0.2.0",
        "stage": "M2",
    }


def test_devices_are_not_pretended_to_exist_in_m1() -> None:
    assert request("/devices").status_code == 404


def test_health_contract_is_documented_in_openapi() -> None:
    document = request("/openapi.json").json()
    assert "/health" in document["paths"]
