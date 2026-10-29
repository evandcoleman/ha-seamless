"""Polling coordinator: slow list polling while idle, fast status polling while active."""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    ACTIVE_INTERVAL,
    ACTIVE_WINDOW,
    DOMAIN,
    IDLE_INTERVAL,
    TERMINAL_STATUSES,
)
from .pyseamless import (
    AuthenticationError,
    OrderStatus,
    OrderSummary,
    SeamlessClient,
    SeamlessError,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class SeamlessData:
    order: OrderSummary | None
    status: OrderStatus | None
    is_active: bool


NO_ORDER = SeamlessData(order=None, status=None, is_active=False)


def is_terminal(state: str | None) -> bool:
    return state is not None and state.upper() in TERMINAL_STATUSES


def in_window(order: OrderSummary, now: datetime) -> bool:
    return order.time_placed is not None and now - order.time_placed < ACTIVE_WINDOW


def select_order(orders: list[OrderSummary], now: datetime) -> OrderSummary | None:
    """The newest order, if it was placed inside the active window."""
    if not orders:
        return None
    newest = orders[0]
    return newest if in_window(newest, now) else None


def is_active(order: OrderSummary | None, recorded_terminal_id: str | None) -> bool:
    """Active = not terminal per the list, and not already seen finishing."""
    return (
        order is not None
        and order.id != recorded_terminal_id
        and not is_terminal(order.order_status)
    )


class SeamlessCoordinator(DataUpdateCoordinator[SeamlessData]):
    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: SeamlessClient
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=IDLE_INTERVAL,
        )
        self._client = client
        self._finished_order_id: str | None = None

    async def _async_update_data(self) -> SeamlessData:
        now = dt_util.utcnow()
        try:
            if self.data is not None and self.data.is_active:
                data = await self._poll_active(self.data, now)
            else:
                data = await self._poll_idle(now)
        except AuthenticationError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except SeamlessError as err:
            raise UpdateFailed(str(err)) from err
        self.update_interval = ACTIVE_INTERVAL if data.is_active else IDLE_INTERVAL
        return data

    async def _poll_idle(self, now: datetime) -> SeamlessData:
        order = select_order(await self._client.async_get_orders(), now)
        if is_active(order, self._finished_order_id):
            return await self._track(order)
        if (
            order is not None
            and order.id == self._finished_order_id
            and self.data is not None
        ):
            return replace(self.data, is_active=False)
        return NO_ORDER

    async def _poll_active(self, current: SeamlessData, now: datetime) -> SeamlessData:
        if not in_window(current.order, now):
            return NO_ORDER
        return await self._track(current.order)

    async def _track(self, order: OrderSummary) -> SeamlessData:
        """Fetch status for an active order and record it if it just finished."""
        status = await self._client.async_get_order_status(order.id)
        if status is not None and is_terminal(status.tracking_state):
            self._finished_order_id = order.id
            return SeamlessData(order, status, is_active=False)
        return SeamlessData(order, status, is_active=True)
