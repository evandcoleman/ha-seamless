import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.seamless.const import (
    CONF_CLIENT_ID,
    CONF_DEVICE_ID,
    CONF_REFRESH_TOKEN,
    CONF_UD_ID,
    DOMAIN,
)

AUTH_URL = "https://api-gtm.grubhub.com/auth"
UD_ID = "00000000-0000-4000-8000-000000000001"
DEVICE_ID = "00000000-0000-4000-8000-0000000000d1"
CLIENT_ID = "beta_seamless_test"
PASTED = {
    CONF_REFRESH_TOKEN: "test-pasted-refresh",
    CONF_CLIENT_ID: CLIENT_ID,
    CONF_DEVICE_ID: DEVICE_ID,
}


@pytest.fixture(autouse=True)
def mock_setup_entry():
    from unittest.mock import patch

    with patch("custom_components.seamless.async_setup_entry", return_value=True) as m:
        yield m


@pytest.fixture
def mock_refresh(aioclient_mock, load_fixture):
    aioclient_mock.post(AUTH_URL, json=load_fixture("auth_refresh.json"))
    return aioclient_mock


def existing_entry(unique_id: str = UD_ID) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=unique_id,
        title="Seamless",
        data={
            CONF_UD_ID: unique_id,
            CONF_CLIENT_ID: CLIENT_ID,
            CONF_DEVICE_ID: DEVICE_ID,
            CONF_REFRESH_TOKEN: "test-old-refresh",
        },
    )


async def start_user_flow(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert set(result["data_schema"].schema) == {
        CONF_REFRESH_TOKEN,
        CONF_CLIENT_ID,
        CONF_DEVICE_ID,
    }
    return result


async def test_user_flow_validates_with_one_refresh_and_stores_rotated_token(
    hass: HomeAssistant, mock_refresh
) -> None:
    result = await start_user_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], PASTED)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Seamless"
    assert result["data"] == {
        CONF_UD_ID: UD_ID,
        CONF_CLIENT_ID: CLIENT_ID,
        CONF_DEVICE_ID: DEVICE_ID,
        CONF_REFRESH_TOKEN: "test-refresh-2",
    }
    assert result["result"].unique_id == UD_ID
    assert mock_refresh.call_count == 1
    assert mock_refresh.mock_calls[0][2] == {
        "brand": "SEAMLESS",
        "client_id": CLIENT_ID,
        "refresh_token": "test-pasted-refresh",
        "device_id": DEVICE_ID,
    }


async def test_numeric_device_id_is_sent_and_stored_as_a_number(
    hass: HomeAssistant, mock_refresh
) -> None:
    result = await start_user_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**PASTED, CONF_DEVICE_ID: " 1234567 "}
    )

    assert result["data"][CONF_DEVICE_ID] == 1234567
    assert mock_refresh.mock_calls[0][2]["device_id"] == 1234567


@pytest.mark.parametrize(
    ("refresh_kwargs", "error"),
    [
        ({"status": 401, "json": {}}, "invalid_auth"),
        ({"status": 403, "json": {}}, "invalid_auth"),
        ({"status": 503, "json": {}}, "cannot_connect"),
        ({"exc": TimeoutError()}, "cannot_connect"),
    ],
)
async def test_user_flow_errors_then_recovers(
    hass: HomeAssistant, aioclient_mock, load_fixture, refresh_kwargs, error
) -> None:
    aioclient_mock.post(AUTH_URL, **refresh_kwargs)

    result = await start_user_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], PASTED)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    aioclient_mock.clear_requests()
    aioclient_mock.post(AUTH_URL, json=load_fixture("auth_refresh.json"))
    result = await hass.config_entries.flow.async_configure(result["flow_id"], PASTED)
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_aborts_when_account_already_configured(
    hass: HomeAssistant, mock_refresh
) -> None:
    existing_entry().add_to_hass(hass)
    result = await start_user_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], PASTED)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_asks_only_for_a_refresh_token_and_reuses_entry_ids(
    hass: HomeAssistant, mock_refresh
) -> None:
    entry = existing_entry()
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    assert set(result["data_schema"].schema) == {CONF_REFRESH_TOKEN}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_REFRESH_TOKEN: "test-new-pasted"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert dict(entry.data) == {
        CONF_UD_ID: UD_ID,
        CONF_CLIENT_ID: CLIENT_ID,
        CONF_DEVICE_ID: DEVICE_ID,
        CONF_REFRESH_TOKEN: "test-refresh-2",
    }
    assert mock_refresh.mock_calls[0][2]["client_id"] == CLIENT_ID
    assert mock_refresh.mock_calls[0][2]["device_id"] == DEVICE_ID
    assert mock_refresh.mock_calls[0][2]["refresh_token"] == "test-new-pasted"


async def test_reauth_with_rejected_token_shows_error(
    hass: HomeAssistant, aioclient_mock
) -> None:
    aioclient_mock.post(AUTH_URL, status=401, json={})
    entry = existing_entry()
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_REFRESH_TOKEN: "test-bad"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_reauth_with_different_account_aborts(
    hass: HomeAssistant, mock_refresh
) -> None:
    entry = existing_entry(unique_id="00000000-0000-4000-8000-000000000002")
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_REFRESH_TOKEN: "test-other-account"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "unique_id_mismatch"
    assert entry.data[CONF_REFRESH_TOKEN] == "test-old-refresh"
