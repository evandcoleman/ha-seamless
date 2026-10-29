from datetime import timedelta

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.seamless.const import (
    CONF_CLIENT_ID,
    CONF_DEVICE_ID,
    CONF_REFRESH_TOKEN,
    CONF_UD_ID,
    DOMAIN,
)

from .conftest import DEVICE_ID, NOW, UD_ID

SECOND = timedelta(seconds=1)


async def setup_entry(hass: HomeAssistant, freezer) -> MockConfigEntry:
    freezer.move_to(NOW)
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=UD_ID,
        data={
            CONF_UD_ID: UD_ID,
            CONF_CLIENT_ID: "beta_seamless_test",
            CONF_DEVICE_ID: DEVICE_ID,
            CONF_REFRESH_TOKEN: "test-refresh-1",
        },
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    if entry.state is ConfigEntryState.LOADED:
        # Coordinators only schedule polls while something listens; entities do.
        entry.runtime_data.async_add_listener(lambda: None)
    return entry


async def tick(hass: HomeAssistant, freezer, delta: timedelta) -> None:
    """Advance the frozen clock by `delta` and fire timers due within it.

    The coordinator adds up to 1 s of random jitter to each refresh, so a full
    interval needs `delta + SECOND` to be certain to fire.
    """
    freezer.tick(delta)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
