"""Token lifecycle: refresh with rotation and expiry handling.

There is no login: scripted login is blocked, so a session starts from a
refresh token captured from a real browser session. That token only works with
the same `client_id` and `device_id` the session was created with.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

from aiohttp import ClientSession

from .const import BRAND, TOKEN_REFRESH_MARGIN_SECONDS
from .exceptions import ApiError, AuthenticationError
from .http import async_request
from .models import AuthResult, TokenSet

_REJECTED = (401, 403)


class SeamlessAuth:
    """Owns the access/refresh tokens for one diner session.

    The refresh token rotates on every refresh; ``on_refresh_token`` is called
    synchronously with the new one before the refreshed access token is used.
    ``device_id`` is sent with the JSON type it was given (web sessions use an int).
    """

    def __init__(
        self,
        session: ClientSession,
        client_id: str,
        device_id: str | int,
        refresh_token: str,
        *,
        on_refresh_token: Callable[[str], None] | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._session = session
        self._client_id = client_id
        self._device_id = device_id
        self._refresh_token = refresh_token
        self._on_refresh_token = on_refresh_token
        self._clock = clock
        self._tokens: TokenSet | None = None
        self._lock = asyncio.Lock()

    @property
    def refresh_token(self) -> str:
        return self._refresh_token

    async def async_validate(self) -> str:
        """Refresh once and return the diner ID (`ud_id`) the token belongs to."""
        async with self._lock:
            result = await self._refresh()
        if result.ud_id is None:
            raise AuthenticationError("Refresh response is missing the diner ID")
        return result.ud_id

    async def async_get_access_token(self) -> str:
        async with self._lock:
            if self._tokens is None or self._is_expiring(self._tokens):
                await self._refresh()
            assert self._tokens is not None
            return self._tokens.access_token

    async def async_force_refresh(self, stale_access_token: str | None = None) -> str:
        """Refresh now, unless the rejected token has already been replaced."""
        async with self._lock:
            replaced = (
                stale_access_token is not None
                and self._tokens is not None
                and self._tokens.access_token != stale_access_token
            )
            if not replaced:
                await self._refresh()
            assert self._tokens is not None
            return self._tokens.access_token

    def _is_expiring(self, tokens: TokenSet) -> bool:
        return tokens.expires_at - self._clock() <= TOKEN_REFRESH_MARGIN_SECONDS

    async def _refresh(self) -> AuthResult:
        if not self._refresh_token:
            raise AuthenticationError("No refresh token available")
        status, body = await async_request(
            self._session,
            "POST",
            "/auth",
            json={
                "brand": BRAND,
                "client_id": self._client_id,
                "refresh_token": self._refresh_token,
                "device_id": self._device_id,
            },
        )
        if status in _REJECTED:
            raise AuthenticationError(f"Refresh rejected with HTTP {status}")
        if status >= 400:
            raise ApiError(status)
        if not isinstance(body, dict):
            raise ApiError(status, "Refresh returned an unreadable body")
        result = AuthResult.from_response(body, self._clock())
        rotated = result.tokens.refresh_token != self._refresh_token
        self._tokens = result.tokens
        self._refresh_token = result.tokens.refresh_token
        if rotated and self._on_refresh_token is not None:
            self._on_refresh_token(result.tokens.refresh_token)
        return result
