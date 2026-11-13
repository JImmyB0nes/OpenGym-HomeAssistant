"""Config flow for the openGym integration."""

from __future__ import annotations

import secrets
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers import config_validation as cv

from .const import CONF_NAME, CONF_SECRET, CONF_WEBHOOK_ID, DOMAIN


class OpenGymConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for openGym."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the signing secret and create the entry."""
        errors: dict[str, str] = {}
        if user_input is not None:
            secret = user_input.get(CONF_SECRET, "").strip()
            webhook_id = f"{DOMAIN}_{secrets.token_hex(8)}"
            if secret and not all(c in "0123456789abcdefABCDEF" for c in secret):
                errors["base"] = "invalid_secret"
            else:
                await self.async_set_unique_id(webhook_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input.get(CONF_NAME) or "openGym",
                    data={
                        CONF_WEBHOOK_ID: webhook_id,
                        CONF_SECRET: secret,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default="openGym"): cv.string,
                    vol.Optional(CONF_SECRET, default=""): cv.string,
                }
            ),
            errors=errors,
        )
