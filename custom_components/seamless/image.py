"""Courier photo."""

from __future__ import annotations

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import SeamlessConfigEntry
from .coordinator import SeamlessCoordinator
from .entity import SeamlessEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SeamlessConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([SeamlessCourierPhoto(hass, entry.runtime_data)])


class SeamlessCourierPhoto(SeamlessEntity, ImageEntity):
    def __init__(self, hass: HomeAssistant, coordinator: SeamlessCoordinator) -> None:
        SeamlessEntity.__init__(self, coordinator, "courier_photo")
        ImageEntity.__init__(self, hass)
        self._seen_url: str | None = None
        self._attr_image_url = None  # a URL source, never the executor `image()` hook
        self._sync_url()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._sync_url()
        super()._handle_coordinator_update()

    def _photo_url(self) -> str | None:
        status = self.coordinator.data.status
        return status.courier.photo_url if status and status.courier else None

    def _sync_url(self) -> None:
        """Bump `image_last_updated` and drop the cached bytes only when the URL changes."""
        url = self._photo_url()
        if url == self._seen_url:
            return
        self._seen_url = url
        self._attr_image_url = url
        self._attr_image_last_updated = dt_util.utcnow() if url else None
        self._cached_image = None
