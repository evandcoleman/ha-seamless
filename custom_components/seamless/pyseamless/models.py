"""Immutable models for Seamless API responses.

Parsing fails soft: a missing or malformed field becomes ``None``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .exceptions import AuthenticationError

_EPOCH_FLOOR = datetime.min.replace(tzinfo=UTC)


def _str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


@dataclass(frozen=True)
class TokenSet:
    access_token: str
    refresh_token: str
    expires_at: float

    @classmethod
    def from_session_handle(cls, handle: Any, now: float) -> TokenSet:
        data = _dict(handle)
        access, refresh = _str(data.get("access_token")), _str(data.get("refresh_token"))
        if access is None or refresh is None:
            raise AuthenticationError("Session response is missing tokens")
        remaining = _float(data.get("token_remaining_secs")) or 0.0
        return cls(access, refresh, now + remaining)


@dataclass(frozen=True)
class AuthResult:
    """A token response; `ud_id` (the diner ID) is only guaranteed to be read by validation."""

    ud_id: str | None
    tokens: TokenSet

    @classmethod
    def from_response(cls, body: Any, now: float) -> AuthResult:
        data = _dict(body)
        return cls(
            ud_id=_str(_dict(data.get("credential")).get("ud_id")),
            tokens=TokenSet.from_session_handle(data.get("session_handle"), now),
        )


@dataclass(frozen=True)
class OrderSummary:
    id: str
    order_number: str | None
    order_status: str | None
    time_placed: datetime | None
    restaurant_name: str | None
    tracking_enabled: bool | None

    @classmethod
    def from_dict(cls, data: Any) -> OrderSummary | None:
        raw = _dict(data)
        order_id = _str(raw.get("id"))
        if order_id is None:
            return None
        restaurants = raw.get("restaurants")
        first = _dict(restaurants[0]) if isinstance(restaurants, list) and restaurants else {}
        enabled = _dict(raw.get("order_tracking")).get("enabled")
        return cls(
            id=order_id,
            order_number=_str(raw.get("order_number")),
            order_status=_str(raw.get("order_status")),
            time_placed=_datetime(raw.get("time_placed")),
            restaurant_name=_str(first.get("name")),
            tracking_enabled=enabled if isinstance(enabled, bool) else None,
        )


def parse_orders(payload: Any) -> list[OrderSummary]:
    """Parse a search_listing payload, newest order first."""
    results = _dict(payload).get("results")
    if not isinstance(results, list):
        return []
    orders = [o for o in map(OrderSummary.from_dict, results) if o is not None]
    return sorted(orders, key=lambda o: o.time_placed or _EPOCH_FLOOR, reverse=True)


@dataclass(frozen=True)
class Courier:
    name: str | None
    vehicle_type: str | None
    photo_url: str | None


@dataclass(frozen=True)
class CourierLocation:
    latitude: float
    longitude: float
    bearing: float | None
    timestamp: datetime | None


def _parse_courier(data: Any) -> Courier | None:
    if not isinstance(data, dict):
        return None
    return Courier(
        name=_str(data.get("name")),
        vehicle_type=_str(data.get("vehicle_type")),
        photo_url=_str(data.get("photo_url")),
    )


def _parse_location(data: Any) -> CourierLocation | None:
    raw = _dict(data)
    latitude, longitude = _float(raw.get("latitude")), _float(raw.get("longitude"))
    if latitude is None or longitude is None:
        return None
    return CourierLocation(
        latitude=latitude,
        longitude=longitude,
        bearing=_float(raw.get("bearing")),
        timestamp=_datetime(raw.get("timestamp")),
    )


@dataclass(frozen=True)
class OrderStatus:
    order_id: str | None
    tracking_state: str | None
    eta: datetime | None
    eta_window_start: datetime | None
    eta_window_end: datetime | None
    eta_state: str | None
    courier: Courier | None
    location: CourierLocation | None
    dropoff_pin: str | None

    @classmethod
    def from_dict(cls, data: Any) -> OrderStatus:
        raw = _dict(data)
        estimate = _dict(raw.get("display_estimate_range"))
        tracking = _dict(raw.get("delivery_tracking_info"))
        return cls(
            order_id=_str(raw.get("order_id")),
            tracking_state=_str(_dict(raw.get("order_tracking")).get("state")),
            eta=_datetime(estimate.get("single_estimate_time")),
            eta_window_start=_datetime(estimate.get("start_time")),
            eta_window_end=_datetime(estimate.get("end_time")),
            eta_state=_str(raw.get("current_eta_state")),
            courier=_parse_courier(tracking.get("courier")),
            location=_parse_location(tracking.get("current_courier_location")),
            dropoff_pin=_str(raw.get("dropoff_pin_code")),
        )
