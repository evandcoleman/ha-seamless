"""Base entity shared by every Seamless platform."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SeamlessCoordinator


class SeamlessEntity(CoordinatorEntity[SeamlessCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: SeamlessCoordinator, key: str) -> None:
        super().__init__(coordinator)
        unique_id = coordinator.config_entry.unique_id
        self._attr_unique_id = f"{unique_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, unique_id)},
            name="Seamless",
            manufacturer="Seamless",
            entry_type=DeviceEntryType.SERVICE,
        )
