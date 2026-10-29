import asyncio

import pytest
from aiohttp import ClientError

from custom_components.seamless.pyseamless.auth import SeamlessAuth
from custom_components.seamless.pyseamless.exceptions import (
    ApiError,
    AuthenticationError,
    SeamlessConnectionError,
)

BASE = "https://api-gtm.grubhub.com"
AUTH_URL = f"{BASE}/auth"
DEVICE_ID = "00000000-0000-4000-8000-0000000000d1"
CLIENT_ID = "test-client-id"
UA = "Seamless/2026.42 (iPhone; iOS 27.0.1; Scale/3.00)"


def make_auth(
    session,
    clock,
    refresh_token="test-refresh-1",
    callback=None,
    device_id=DEVICE_ID,
):
    return SeamlessAuth(
        session,
        CLIENT_ID,
        device_id,
        refresh_token,
        on_refresh_token=callback,
        clock=clock,
    )


async def test_refresh_sends_exact_body_and_rotates_token(
    aioclient_mock, session, clock, calls, load_fixture
) -> None:
    aioclient_mock.post(AUTH_URL, json=load_fixture("auth_refresh.json"))
    rotated: list[str] = []
    auth = make_auth(session, clock, callback=rotated.append)

    token = await auth.async_get_access_token()

    assert token == "test-access-2"
    ((method, url, body, headers),) = calls()
    assert (method, url) == ("POST", AUTH_URL)
    assert body == {
        "brand": "SEAMLESS",
        "client_id": CLIENT_ID,
        "refresh_token": "test-refresh-1",
        "device_id": DEVICE_ID,
    }
    assert headers == {
        "User-Agent": UA,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    assert auth.refresh_token == "test-refresh-2"
    assert rotated == ["test-refresh-2"]


async def test_callback_runs_before_token_is_returned(
    aioclient_mock, session, clock, load_fixture
) -> None:
    aioclient_mock.post(AUTH_URL, json=load_fixture("auth_refresh.json"))
    seen: list[str] = []
    auth = make_auth(session, clock, callback=seen.append)
    await auth.async_force_refresh()
    assert seen == ["test-refresh-2"]


async def test_token_with_more_than_five_minutes_left_is_reused(
    aioclient_mock, session, clock, load_fixture
) -> None:
    aioclient_mock.post(AUTH_URL, json=load_fixture("auth_refresh.json"))
    auth = make_auth(session, clock)
    await auth.async_get_access_token()
    clock.advance(3600 - 301)
    await auth.async_get_access_token()
    assert aioclient_mock.call_count == 1


async def test_token_with_five_minutes_or_less_left_is_refreshed(
    aioclient_mock, session, clock, load_fixture
) -> None:
    aioclient_mock.post(AUTH_URL, json=load_fixture("auth_refresh.json"))
    auth = make_auth(session, clock)
    await auth.async_get_access_token()
    clock.advance(3600 - 300)
    await auth.async_get_access_token()
    assert aioclient_mock.call_count == 2


@pytest.mark.parametrize("status", [401, 403])
async def test_refresh_rejection_raises_authentication_error(
    aioclient_mock, session, clock, status
) -> None:
    aioclient_mock.post(AUTH_URL, status=status, json={})
    auth = make_auth(session, clock)
    with pytest.raises(AuthenticationError):
        await auth.async_get_access_token()


async def test_refresh_server_error_raises_api_error(
    aioclient_mock, session, clock
) -> None:
    aioclient_mock.post(AUTH_URL, status=503, json={})
    auth = make_auth(session, clock)
    with pytest.raises(ApiError) as err:
        await auth.async_get_access_token()
    assert err.value.status == 503


@pytest.mark.parametrize("exc", [ClientError(), TimeoutError()])
async def test_refresh_network_failure_raises_connection_error(
    aioclient_mock, session, clock, exc
) -> None:
    aioclient_mock.post(AUTH_URL, exc=exc)
    auth = make_auth(session, clock)
    with pytest.raises(SeamlessConnectionError):
        await auth.async_get_access_token()


async def test_empty_refresh_token_raises_authentication_error(session, clock) -> None:
    auth = make_auth(session, clock, refresh_token="")
    with pytest.raises(AuthenticationError):
        await auth.async_get_access_token()


async def test_concurrent_callers_cause_exactly_one_refresh(
    aioclient_mock, session, clock, load_fixture
) -> None:
    aioclient_mock.post(AUTH_URL, json=load_fixture("auth_refresh.json"))
    auth = make_auth(session, clock)
    tokens = await asyncio.gather(*(auth.async_get_access_token() for _ in range(5)))
    assert tokens == ["test-access-2"] * 5
    assert aioclient_mock.call_count == 1


async def test_force_refresh_skips_when_rejected_token_is_no_longer_current(
    aioclient_mock, session, clock, load_fixture
) -> None:
    aioclient_mock.post(AUTH_URL, json=load_fixture("auth_refresh.json"))
    auth = make_auth(session, clock)
    await auth.async_get_access_token()
    await asyncio.gather(
        auth.async_force_refresh(stale_access_token="older-token"),
        auth.async_force_refresh(stale_access_token="older-token"),
    )
    assert aioclient_mock.call_count == 1


async def test_numeric_device_id_is_sent_as_a_number(
    aioclient_mock, session, clock, calls, load_fixture
) -> None:
    aioclient_mock.post(AUTH_URL, json=load_fixture("auth_refresh.json"))
    auth = make_auth(session, clock, device_id=1234567)
    await auth.async_get_access_token()
    assert calls()[0][2]["device_id"] == 1234567
    assert isinstance(calls()[0][2]["device_id"], int)


async def test_validate_refreshes_and_returns_ud_id(
    aioclient_mock, session, clock, load_fixture
) -> None:
    aioclient_mock.post(AUTH_URL, json=load_fixture("auth_refresh.json"))
    rotated: list[str] = []
    auth = make_auth(session, clock, callback=rotated.append)

    assert await auth.async_validate() == "00000000-0000-4000-8000-000000000001"
    assert auth.refresh_token == "test-refresh-2"
    assert rotated == ["test-refresh-2"]


async def test_validate_without_ud_id_raises_authentication_error(
    aioclient_mock, session, clock, load_fixture
) -> None:
    body = load_fixture("auth_refresh.json")
    del body["credential"]
    aioclient_mock.post(AUTH_URL, json=body)
    auth = make_auth(session, clock)
    with pytest.raises(AuthenticationError):
        await auth.async_validate()


@pytest.mark.parametrize("status", [401, 403])
async def test_validate_rejection_raises_authentication_error(
    aioclient_mock, session, clock, status
) -> None:
    aioclient_mock.post(AUTH_URL, status=status, json={})
    auth = make_auth(session, clock)
    with pytest.raises(AuthenticationError):
        await auth.async_validate()
