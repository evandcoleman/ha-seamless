"""Diagnostics with every personal field redacted."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import SeamlessConfigEntry

TO_REDACT = {
    "email",
    "phone",
    "address",
    "refresh_token",
    "access_token",
    "dropoff_pin",
    "latitude",
    "longitude",
    "ud_id",
    "client_id",
    "device_id",
    "photo_url",
    "name",
    "id",
    "order_id",
    "order_number",
    "restaurant_name",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: SeamlessConfigEntry
) -> dict[str, Any]:
    data = entry.runtime_data.data
    return {
        "entry": {"data": async_redact_data(dict(entry.data), TO_REDACT)},
        "coordinator": async_redact_data(
            {
                "is_active": data.is_active,
                "order": asdict(data.order) if data.order else None,
                "status": asdict(data.status) if data.status else None,
            },
            TO_REDACT,
        ),
    }
