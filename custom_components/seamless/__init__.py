"""Seamless order tracking."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_CLIENT_ID, CONF_DEVICE_ID, CONF_REFRESH_TOKEN, CONF_UD_ID
from .coordinator import SeamlessCoordinator
from .pyseamless import SeamlessAuth, SeamlessClient

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.DEVICE_TRACKER,
    Platform.IMAGE,
    Platform.SENSOR,
]

type SeamlessConfigEntry = ConfigEntry[SeamlessCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: SeamlessConfigEntry) -> bool:
    session = async_get_clientsession(hass)

    def save_refresh_token(token: str) -> None:
        # No update listener is registered, so this never triggers a reload.
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_REFRESH_TOKEN: token}
        )

    auth = SeamlessAuth(
        session,
        entry.data[CONF_CLIENT_ID],
        entry.data[CONF_DEVICE_ID],
        entry.data[CONF_REFRESH_TOKEN],
        on_refresh_token=save_refresh_token,
    )
    client = SeamlessClient(session, auth, entry.data[CONF_UD_ID])
    coordinator = SeamlessCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SeamlessConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
