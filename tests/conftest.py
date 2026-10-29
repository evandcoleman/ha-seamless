import json
from pathlib import Path

import pytest

import custom_components

# phcc ships its own `custom_components` package; make ours importable too.
_REPO_COMPONENTS = str(Path(__file__).resolve().parent.parent / "custom_components")
if _REPO_COMPONENTS not in custom_components.__path__:
    custom_components.__path__.append(_REPO_COMPONENTS)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def load_fixture():
    def _load(name: str) -> dict:
        return json.loads((FIXTURES / name).read_text())

    return _load


BASE_URL = "https://api-gtm.grubhub.com"
UD_ID = "00000000-0000-4000-8000-000000000001"
DEVICE_ID = "00000000-0000-4000-8000-0000000000d1"
NOW = "2026-01-15T18:00:00+00:00"


class FakeApi:
    """Mutable fake of the Seamless API; tests flip its fixtures between polls."""

    def __init__(self, aioclient_mock, load_fixture) -> None:
        from pytest_homeassistant_custom_component.test_util.aiohttp import (
            AiohttpClientMockResponse,
        )

        self._mock = aioclient_mock
        self._load = load_fixture
        self._response = AiohttpClientMockResponse
        self.orders = "orders_empty.json"
        self.status = "status_out_for_delivery.json"
        self.orders_http = 200
        self.status_http = 200
        self.refresh_http = 200
        self.error: Exception | None = None

        import re

        aioclient_mock.post(f"{BASE_URL}/auth", side_effect=self._auth)
        aioclient_mock.get(f"{BASE_URL}/diners/{UD_ID}/search_listing", side_effect=self._orders)
        aioclient_mock.get(
            re.compile(rf"{BASE_URL}/diners/{UD_ID}/orders/[^/]+/order-status"),
            side_effect=self._status,
        )

    def _reply(self, method, url, status: int, fixture: str | None):
        if self.error is not None:
            raise self.error
        body = self._load(fixture) if status < 400 and fixture else {}
        return self._response(method, url, status=status, json=body)

    async def _auth(self, method, url, data):
        return self._reply(method, url, self.refresh_http, "auth_refresh.json")

    async def _orders(self, method, url, data):
        return self._reply(method, url, self.orders_http, self.orders)

    async def _status(self, method, url, data):
        return self._reply(method, url, self.status_http, self.status)

    def count(self, kind: str) -> int:
        marker = {
            "auth": "/auth",
            "list": "/search_listing",
            "status": "/order-status",
        }[kind]
        return sum(1 for call in self._mock.mock_calls if marker in str(call[1]))


@pytest.fixture
def api(aioclient_mock, load_fixture) -> FakeApi:
    return FakeApi(aioclient_mock, load_fixture)
