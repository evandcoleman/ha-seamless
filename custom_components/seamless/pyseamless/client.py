"""Read-only Seamless API client for order tracking."""

from __future__ import annotations

from typing import Any

from aiohttp import ClientSession

from .auth import SeamlessAuth
from .const import ORDER_LIST_PAGE_SIZE, ORDER_STATUS_VARIATIONS
from .exceptions import ApiError, AuthenticationError
from .http import async_request
from .models import OrderStatus, OrderSummary, parse_orders


class SeamlessClient:
    def __init__(self, session: ClientSession, auth: SeamlessAuth, ud_id: str) -> None:
        self._session = session
        self._auth = auth
        self._ud_id = ud_id

    async def async_get_orders(self) -> list[OrderSummary]:
        """Return recent orders, newest first."""
        status, body = await self._get(
            f"/diners/{self._ud_id}/search_listing",
            [
                ("facet", "orderType:ALL"),
                ("facet", "showCancelled:true"),
                ("pageNum", "1"),
                ("pageSize", str(ORDER_LIST_PAGE_SIZE)),
            ],
        )
        if status >= 400:
            raise ApiError(status)
        return parse_orders(body)

    async def async_get_order_status(self, order_id: str) -> OrderStatus | None:
        """Return live tracking for an order, or None if the API refuses it (4xx)."""
        status, body = await self._get(
            f"/diners/{self._ud_id}/orders/{order_id}/order-status",
            [("variation_id", ORDER_STATUS_VARIATIONS)],
        )
        if 400 <= status < 500:
            return None
        if status >= 500:
            raise ApiError(status)
        return OrderStatus.from_dict(body)

    async def _get(self, path: str, params: list[tuple[str, str]]) -> tuple[int, Any]:
        """GET with one refresh-and-retry on 401; 403 is an immediate auth failure."""
        token = await self._auth.async_get_access_token()
        status, body = await async_request(
            self._session, "GET", path, access_token=token, params=params
        )
        if status == 401:
            token = await self._auth.async_force_refresh(stale_access_token=token)
            status, body = await async_request(
                self._session, "GET", path, access_token=token, params=params
            )
        if status in (401, 403):
            raise AuthenticationError(f"{path} rejected with HTTP {status}")
        return status, body
