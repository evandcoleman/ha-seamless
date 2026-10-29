"""Async client for the Seamless (Grubhub) order-tracking API. No Home Assistant imports."""

from .auth import SeamlessAuth
from .client import SeamlessClient
from .exceptions import (
    ApiError,
    AuthenticationError,
    SeamlessConnectionError,
    SeamlessError,
)
from .models import (
    AuthResult,
    Courier,
    CourierLocation,
    OrderStatus,
    OrderSummary,
    TokenSet,
    parse_orders,
)

__all__ = [
    "ApiError",
    "AuthResult",
    "AuthenticationError",
    "Courier",
    "CourierLocation",
    "OrderStatus",
    "OrderSummary",
    "SeamlessAuth",
    "SeamlessClient",
    "SeamlessConnectionError",
    "SeamlessError",
    "TokenSet",
    "parse_orders",
]
