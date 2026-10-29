from datetime import UTC, datetime

import pytest
from aiohttp import ClientConnectionError, ClientError, ClientPayloadError
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMockResponse,
)

from custom_components.seamless.pyseamless.auth import SeamlessAuth
from custom_components.seamless.pyseamless.client import SeamlessClient
from custom_components.seamless.pyseamless.exceptions import (
    ApiError,
    AuthenticationError,
    SeamlessConnectionError,
)

BASE = "https://api-gtm.grubhub.com"
UD_ID = "00000000-0000-4000-8000-000000000001"
ORDER_ID = "00000000-0000-4000-8000-0000000000a1"
AUTH_URL = f"{BASE}/auth"
LIST_URL = f"{BASE}/diners/{UD_ID}/search_listing"
STATUS_URL = f"{BASE}/diners/{UD_ID}/orders/{ORDER_ID}/order-status"
DEVICE_ID = "00000000-0000-4000-8000-0000000000d1"


@pytest.fixture
def client(session, clock, aioclient_mock, load_fixture):
    aioclient_mock.post(AUTH_URL, json=load_fixture("auth_refresh.json"))
    auth = SeamlessAuth(session, "test-client-id", DEVICE_ID, "test-refresh-1", clock=clock)
    return SeamlessClient(session, auth, UD_ID)


def api_calls(calls):
    return [c for c in calls() if c[1] != AUTH_URL]


async def test_orders_request_matches_spec_and_parses(
    client, aioclient_mock, calls, load_fixture
) -> None:
    aioclient_mock.get(LIST_URL, json=load_fixture("orders_active.json"))

    orders = await client.async_get_orders()

    ((method, url, _, headers),) = api_calls(calls)
    assert method == "GET"
    assert url == (
        f"{LIST_URL}?facet=orderType:ALL&facet=showCancelled:true&pageNum=1&pageSize=10"
    )
    assert headers["Authorization"] == "Bearer test-access-2"
    assert headers["User-Agent"].startswith("Seamless/")
    assert orders[0].order_status == "OUT_FOR_DELIVERY"


async def test_order_status_request_matches_spec_and_parses(
    client, aioclient_mock, calls, load_fixture
) -> None:
    aioclient_mock.get(STATUS_URL, json=load_fixture("status_out_for_delivery.json"))

    status = await client.async_get_order_status(ORDER_ID)

    ((_, url, _, _),) = api_calls(calls)
    assert url == (
        f"{STATUS_URL}?variation_id=use_new_order_status,courierIsArriving,"
        "courierDropoffArrived,expected_delivery_path_v2,use_self_delivery_statuses"
    )
    assert status.eta == datetime(2026, 1, 15, 18, 20, tzinfo=UTC)


async def test_401_refreshes_once_and_retries(
    client, respond_in_sequence, calls, load_fixture
) -> None:
    respond_in_sequence(
        "get", LIST_URL, (401, {}), (200, load_fixture("orders_active.json"))
    )

    orders = await client.async_get_orders()

    assert len(orders) == 2
    assert [c[0] for c in calls() if c[1] == AUTH_URL] == ["POST", "POST"]
    assert len(api_calls(calls)) == 2


async def test_401_after_refresh_raises_authentication_error(
    client, aioclient_mock, calls
) -> None:
    aioclient_mock.get(LIST_URL, status=401, json={})
    with pytest.raises(AuthenticationError):
        await client.async_get_orders()
    assert len(api_calls(calls)) == 2


async def test_server_error_raises_api_error(client, aioclient_mock) -> None:
    aioclient_mock.get(LIST_URL, status=502, json={})
    with pytest.raises(ApiError) as err:
        await client.async_get_orders()
    assert err.value.status == 502


@pytest.mark.parametrize("exc", [TimeoutError(), ClientError()])
async def test_network_failure_raises_connection_error(
    client, aioclient_mock, exc
) -> None:
    aioclient_mock.get(LIST_URL, exc=exc)
    with pytest.raises(SeamlessConnectionError):
        await client.async_get_orders()


@pytest.mark.parametrize("status", [400, 404, 410])
async def test_order_status_4xx_returns_none(client, aioclient_mock, status) -> None:
    aioclient_mock.get(STATUS_URL, status=status, json={})
    assert await client.async_get_order_status(ORDER_ID) is None


async def test_order_status_403_is_an_auth_failure(client, aioclient_mock) -> None:
    aioclient_mock.get(STATUS_URL, status=403, json={})
    with pytest.raises(AuthenticationError):
        await client.async_get_order_status(ORDER_ID)


async def test_orders_4xx_other_than_auth_raises_api_error(
    client, aioclient_mock
) -> None:
    aioclient_mock.get(LIST_URL, status=404, json={})
    with pytest.raises(ApiError):
        await client.async_get_orders()


@pytest.mark.parametrize(
    "exc", [ClientPayloadError("truncated"), ClientConnectionError("reset")]
)
@pytest.mark.parametrize("call", ["orders", "status"])
async def test_transport_failure_while_reading_body_is_a_connection_error(
    client, aioclient_mock, exc, call
) -> None:
    class BrokenBody(AiohttpClientMockResponse):
        async def json(self, *args, **kwargs):
            raise exc

    async def side_effect(method, url, data):
        return BrokenBody(method, url, status=200)

    aioclient_mock.get(LIST_URL, side_effect=side_effect)
    aioclient_mock.get(STATUS_URL, side_effect=side_effect)

    with pytest.raises(SeamlessConnectionError):
        if call == "orders":
            await client.async_get_orders()
        else:
            await client.async_get_order_status(ORDER_ID)


async def test_malformed_json_body_still_parses_as_empty(client, aioclient_mock) -> None:
    aioclient_mock.get(LIST_URL, text="not json")
    assert await client.async_get_orders() == []
