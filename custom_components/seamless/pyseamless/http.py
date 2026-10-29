"""Shared request plumbing: headers, timeouts and error mapping."""

from __future__ import annotations

import asyncio
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout, ContentTypeError

from .const import BASE_URL, REQUEST_TIMEOUT_SECONDS, USER_AGENT
from .exceptions import SeamlessConnectionError


def build_headers(access_token: str | None = None, *, has_body: bool = False) -> dict[str, str]:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if has_body:
        headers["Content-Type"] = "application/json"
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    return headers


async def async_request(
    session: ClientSession,
    method: str,
    path: str,
    *,
    access_token: str | None = None,
    json: Any = None,
    params: Any = None,
) -> tuple[int, Any]:
    """Send one request and return (status, parsed JSON or None)."""
    try:
        async with session.request(
            method,
            f"{BASE_URL}{path}",
            headers=build_headers(access_token, has_body=json is not None),
            json=json,
            params=params,
            timeout=ClientTimeout(total=REQUEST_TIMEOUT_SECONDS),
        ) as response:
            try:
                body = await response.json(content_type=None)
            except (ValueError, ContentTypeError):
                # Undecodable body only; transport errors must reach the handler below.
                body = None
            return response.status, body
    except (ClientError, asyncio.TimeoutError) as err:
        raise SeamlessConnectionError(f"Request to {path} failed: {err}") from err
