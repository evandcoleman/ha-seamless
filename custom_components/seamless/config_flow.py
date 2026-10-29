"""Config flow: paste a session captured from a browser; no password is ever handled.

Scripted login is blocked, so setup takes the refresh token (plus the client ID
and device ID it was issued for) from a real seamless.com session.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_CLIENT_ID,
    CONF_DEVICE_ID,
    CONF_REFRESH_TOKEN,
    CONF_UD_ID,
    DOMAIN,
)
from .pyseamless import (
    ApiError,
    AuthenticationError,
    SeamlessAuth,
    SeamlessConnectionError,
    SeamlessError,
)

_LOGGER = logging.getLogger(__name__)

TOKEN_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
TEXT_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT))
REAUTH_SCHEMA = vol.Schema({vol.Required(CONF_REFRESH_TOKEN): TOKEN_SELECTOR})
USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_REFRESH_TOKEN): TOKEN_SELECTOR,
        vol.Required(CONF_CLIENT_ID): TEXT_SELECTOR,
        vol.Required(CONF_DEVICE_ID): TEXT_SELECTOR,
    }
)


def _clean(value: str) -> str:
    return value.strip().strip("\"'").strip()


def parse_device_id(value: str) -> str | int:
    """Web sessions use a numeric device ID and expect it back as a JSON number."""
    cleaned = _clean(value)
    return int(cleaned) if cleaned.isascii() and cleaned.isdigit() else cleaned


class SeamlessConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def _async_validate(
        self, client_id: str, device_id: str | int, refresh_token: str
    ) -> tuple[tuple[str, str] | None, dict[str, str]]:
        """Refresh once; return ((ud_id, rotated refresh token), errors)."""
        auth = SeamlessAuth(
            async_get_clientsession(self.hass), client_id, device_id, refresh_token
        )
        try:
            ud_id = await auth.async_validate()
        except AuthenticationError:
            return None, {"base": "invalid_auth"}
        except (SeamlessConnectionError, ApiError):
            return None, {"base": "cannot_connect"}
        except SeamlessError:
            _LOGGER.exception("Unexpected Seamless error during validation")
            return None, {"base": "unknown"}
        return (ud_id, auth.refresh_token), {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            client_id = _clean(user_input[CONF_CLIENT_ID])
            device_id = parse_device_id(user_input[CONF_DEVICE_ID])
            validated, errors = await self._async_validate(
                client_id, device_id, _clean(user_input[CONF_REFRESH_TOKEN])
            )
            if validated is not None:
                ud_id, refresh_token = validated
                await self.async_set_unique_id(ud_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="Seamless",
                    data={
                        CONF_UD_ID: ud_id,
                        CONF_CLIENT_ID: client_id,
                        CONF_DEVICE_ID: device_id,
                        CONF_REFRESH_TOKEN: refresh_token,
                    },
                )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                USER_SCHEMA,
                {
                    k: user_input[k]
                    for k in (CONF_CLIENT_ID, CONF_DEVICE_ID)
                    if user_input
                },
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            validated, errors = await self._async_validate(
                entry.data[CONF_CLIENT_ID],
                entry.data[CONF_DEVICE_ID],
                _clean(user_input[CONF_REFRESH_TOKEN]),
            )
            if validated is not None:
                ud_id, refresh_token = validated
                await self.async_set_unique_id(ud_id)
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_REFRESH_TOKEN: refresh_token}
                )
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=REAUTH_SCHEMA, errors=errors
        )
