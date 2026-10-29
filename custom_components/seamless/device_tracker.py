"""GPS device tracker for the courier."""

from __future__ import annotations

from typing import Any

from homeassistant.components.device_tracker import SourceType, TrackerEntity
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
    async_add_entities([SeamlessCourierTracker(entry.runtime_data)])


class SeamlessCourierTracker(SeamlessEntity, TrackerEntity):
    _attr_source_type = SourceType.GPS

    def __init__(self, coordinator: SeamlessCoordinator) -> None:
        super().__init__(coordinator, "courier")

    @property
    def _location(self):
        status = self.coordinator.data.status
        return status.location if status else None

    @property
    def latitude(self) -> float | None:
        return self._location.latitude if self._location else None

    @property
    def longitude(self) -> float | None:
        return self._location.longitude if self._location else None

    @property
    def in_zones(self) -> list[str] | None:
        # An empty list (not None) makes the tracker report not_home without coordinates.
        return None if self._location else []

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        location = self._location
        if location is None:
            return None
        return {
            "bearing": location.bearing,
            "timestamp": location.timestamp.isoformat() if location.timestamp else None,
        }
