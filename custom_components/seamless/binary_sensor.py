"""Binary sensor: is an order currently being tracked."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SeamlessConfigEntry
from .coordinator import SeamlessCoordinator
from .entity import SeamlessEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SeamlessConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([SeamlessOrderActive(entry.runtime_data)])


class SeamlessOrderActive(SeamlessEntity, BinarySensorEntity):
    def __init__(self, coordinator: SeamlessCoordinator) -> None:
        super().__init__(coordinator, "order_active")

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.is_active

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        order = self.coordinator.data.order
        if order is None:
            return None
        return {"order_id": order.id, "order_number": order.order_number}
