"""Order sensors, driven by entity descriptions."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from . import SeamlessConfigEntry
from .coordinator import SeamlessCoordinator, SeamlessData
from .entity import SeamlessEntity

type Value = StateType | datetime


def _lower(value: str | None) -> str | None:
    return value.lower() if value else None


@dataclass(frozen=True, kw_only=True)
class SeamlessSensorDescription(SensorEntityDescription):
    value_fn: Callable[[SeamlessData], Value]
    attributes_fn: Callable[[SeamlessData], Mapping[str, Any]] | None = None


SENSORS: tuple[SeamlessSensorDescription, ...] = (
    SeamlessSensorDescription(
        key="order_status",
        translation_key="order_status",
        device_class=SensorDeviceClass.ENUM,
        options=["confirmed", "out_for_delivery", "delivered", "cancelled", "fulfilled", "completed"],
        value_fn=lambda d: _lower(d.status.tracking_state) if d.status else None,
    ),
    SeamlessSensorDescription(
        key="eta",
        translation_key="eta",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: d.status.eta if d.status else None,
    ),
    SeamlessSensorDescription(
        key="eta_window_start",
        translation_key="eta_window_start",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: d.status.eta_window_start if d.status else None,
    ),
    SeamlessSensorDescription(
        key="eta_window_end",
        translation_key="eta_window_end",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: d.status.eta_window_end if d.status else None,
    ),
    SeamlessSensorDescription(
        key="eta_state",
        translation_key="eta_state",
        device_class=SensorDeviceClass.ENUM,
        options=["on_time"],
        value_fn=lambda d: _lower(d.status.eta_state) if d.status else None,
    ),
    SeamlessSensorDescription(
        key="restaurant",
        translation_key="restaurant",
        value_fn=lambda d: d.order.restaurant_name if d.order else None,
    ),
    SeamlessSensorDescription(
        key="courier",
        translation_key="courier",
        value_fn=lambda d: d.status.courier.name if d.status and d.status.courier else None,
        attributes_fn=lambda d: {
            "vehicle_type": d.status.courier.vehicle_type
            if d.status and d.status.courier
            else None
        },
    ),
    SeamlessSensorDescription(
        key="dropoff_pin",
        translation_key="dropoff_pin",
        value_fn=lambda d: d.status.dropoff_pin if d.status else None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SeamlessConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(SeamlessSensor(coordinator, d) for d in SENSORS)


class SeamlessSensor(SeamlessEntity, SensorEntity):
    entity_description: SeamlessSensorDescription

    def __init__(
        self, coordinator: SeamlessCoordinator, description: SeamlessSensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._known_options = list(description.options or [])
        self._sync_options()

    @property
    def native_value(self) -> Value:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        fn = self.entity_description.attributes_fn
        return fn(self.coordinator.data) if fn else None

    @callback
    def _handle_coordinator_update(self) -> None:
        self._sync_options()
        super()._handle_coordinator_update()

    def _sync_options(self) -> None:
        """ENUM states outside `options` raise, so grow them with unseen API values."""
        if self.entity_description.options is None:
            return
        value = self.native_value
        if isinstance(value, str) and value not in self._known_options:
            self._known_options = [*self._known_options, value]
        self._attr_options = self._known_options
