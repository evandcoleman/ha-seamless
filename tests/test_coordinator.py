from datetime import timedelta

from aiohttp import ClientError
from homeassistant.config_entries import ConfigEntryState

from custom_components.seamless.const import (
    ACTIVE_INTERVAL,
    CONF_CLIENT_ID,
    CONF_DEVICE_ID,
    CONF_REFRESH_TOKEN,
    CONF_UD_ID,
    DOMAIN,
    IDLE_INTERVAL,
)

from .helpers import SECOND, setup_entry, tick


async def test_idle_polls_the_list_every_five_minutes(hass, freezer, api) -> None:
    entry = await setup_entry(hass, freezer)
    coordinator = entry.runtime_data
    assert coordinator.update_interval == IDLE_INTERVAL
    assert api.count("list") == 1

    await tick(hass, freezer, IDLE_INTERVAL - 10 * SECOND)
    assert api.count("list") == 1
    await tick(hass, freezer, IDLE_INTERVAL + SECOND)
    assert api.count("list") == 2
    assert api.count("status") == 0
    assert coordinator.data.order is None
    assert coordinator.data.is_active is False


async def test_active_order_polls_status_only_every_thirty_seconds(
    hass, freezer, api
) -> None:
    api.orders = "orders_active.json"
    entry = await setup_entry(hass, freezer)
    coordinator = entry.runtime_data

    assert (api.count("list"), api.count("status")) == (1, 1)
    assert coordinator.data.is_active is True
    assert coordinator.data.order.order_number == "TEST-0001"
    assert coordinator.data.status.tracking_state == "OUT_FOR_DELIVERY"
    assert coordinator.update_interval == ACTIVE_INTERVAL

    await tick(hass, freezer, ACTIVE_INTERVAL + SECOND)
    await tick(hass, freezer, ACTIVE_INTERVAL + SECOND)
    assert (api.count("list"), api.count("status")) == (1, 3)


async def test_results_state_completed_does_not_make_an_order_terminal(
    hass, freezer, api
) -> None:
    api.orders = "orders_active.json"  # every result carries state: COMPLETED
    entry = await setup_entry(hass, freezer)
    assert entry.runtime_data.data.is_active is True


async def test_delivered_drops_to_idle_polling_and_status_stays_visible(
    hass, freezer, api
) -> None:
    api.orders = "orders_active.json"
    entry = await setup_entry(hass, freezer)
    coordinator = entry.runtime_data

    api.status = "status_delivered.json"
    await tick(hass, freezer, ACTIVE_INTERVAL + SECOND)

    assert coordinator.data.is_active is False
    assert coordinator.data.status.tracking_state == "DELIVERED"
    assert coordinator.data.order.order_number == "TEST-0001"
    assert coordinator.update_interval == IDLE_INTERVAL

    status_calls = api.count("status")
    await tick(hass, freezer, ACTIVE_INTERVAL + SECOND)
    assert api.count("status") == status_calls
    await tick(hass, freezer, IDLE_INTERVAL + SECOND)
    assert api.count("list") == 2
    assert coordinator.data.status.tracking_state == "DELIVERED"


async def test_lagging_list_does_not_reactivate_a_finished_order(
    hass, freezer, api
) -> None:
    api.orders = "orders_active.json"
    entry = await setup_entry(hass, freezer)
    api.status = "status_delivered.json"
    await tick(hass, freezer, ACTIVE_INTERVAL + SECOND)
    status_calls = api.count("status")

    # The list still claims OUT_FOR_DELIVERY for several idle polls.
    for _ in range(3):
        await tick(hass, freezer, IDLE_INTERVAL + SECOND)

    assert api.count("status") == status_calls
    assert entry.runtime_data.data.is_active is False
    assert entry.runtime_data.data.status.tracking_state == "DELIVERED"


async def test_finished_order_clears_when_the_four_hour_window_ends(
    hass, freezer, api
) -> None:
    api.orders = "orders_active.json"  # placed 17:30Z, window ends 21:30Z
    entry = await setup_entry(hass, freezer)
    api.status = "status_delivered.json"
    await tick(hass, freezer, ACTIVE_INTERVAL + SECOND)
    assert entry.runtime_data.data.order is not None

    await tick(hass, freezer, timedelta(hours=3, minutes=40))

    assert entry.runtime_data.data.order is None
    assert entry.runtime_data.data.status is None
    assert entry.runtime_data.data.is_active is False


async def test_active_order_left_open_is_retired_by_the_window(
    hass, freezer, api
) -> None:
    api.orders = "orders_active.json"
    entry = await setup_entry(hass, freezer)

    await tick(hass, freezer, timedelta(hours=4))

    assert entry.runtime_data.data.order is None
    assert entry.runtime_data.data.is_active is False
    assert entry.runtime_data.update_interval == IDLE_INTERVAL


async def test_stale_confirmed_order_is_not_active(hass, freezer, api) -> None:
    api.orders = "orders_stale.json"
    entry = await setup_entry(hass, freezer)
    assert entry.runtime_data.data.order is None
    assert entry.runtime_data.data.is_active is False
    assert api.count("status") == 0


async def test_fulfilled_newest_order_is_not_active(hass, freezer, api) -> None:
    api.orders = "orders_idle.json"
    entry = await setup_entry(hass, freezer)
    assert entry.runtime_data.data.is_active is False
    assert api.count("status") == 0


async def test_order_already_terminal_on_first_status_is_recorded(
    hass, freezer, api
) -> None:
    api.orders = "orders_active.json"
    api.status = "status_delivered.json"
    entry = await setup_entry(hass, freezer)

    assert entry.runtime_data.data.is_active is False
    assert entry.runtime_data.data.status.tracking_state == "DELIVERED"
    await tick(hass, freezer, IDLE_INTERVAL + SECOND)
    assert api.count("status") == 1


async def test_status_4xx_fails_soft_and_polling_continues(hass, freezer, api) -> None:
    api.orders = "orders_active.json"
    api.status_http = 404
    entry = await setup_entry(hass, freezer)

    assert entry.runtime_data.last_update_success is True
    assert entry.runtime_data.data.is_active is True
    assert entry.runtime_data.data.status is None
    await tick(hass, freezer, ACTIVE_INTERVAL + SECOND)
    assert api.count("status") == 2


async def test_rotated_refresh_token_is_saved_to_the_entry(hass, freezer, api) -> None:
    entry = await setup_entry(hass, freezer)
    assert entry.data[CONF_REFRESH_TOKEN] == "test-refresh-2"
    assert set(entry.data) == {
        CONF_UD_ID,
        CONF_CLIENT_ID,
        CONF_DEVICE_ID,
        CONF_REFRESH_TOKEN,
    }


async def test_refresh_rejection_starts_reauth(hass, freezer, api) -> None:
    api.refresh_http = 401
    entry = await setup_entry(hass, freezer)

    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [f["context"]["source"] for f in flows] == ["reauth"]


async def test_server_error_marks_update_failed(hass, freezer, api) -> None:
    entry = await setup_entry(hass, freezer)
    api.orders_http = 500

    await tick(hass, freezer, IDLE_INTERVAL + SECOND)

    assert entry.runtime_data.last_update_success is False


async def test_network_error_during_setup_retries(hass, freezer, api) -> None:
    api.error = ClientError()
    entry = await setup_entry(hass, freezer)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_unload(hass, freezer, api) -> None:
    entry = await setup_entry(hass, freezer)
    assert entry.state is ConfigEntryState.LOADED
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
