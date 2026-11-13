"""Config flow for the openGym integration."""

from __future__ import annotations

import secrets
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import CONF_URL
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from .api import OpenGymApiClient, OpenGymError
from .const import (
    CONF_NAME,
    CONF_POLL_INTERVAL,
    CONF_SECRET,
    CONF_TOKEN,
    CONF_WEBHOOK_ID,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    MAX_POLL_INTERVAL,
    MIN_POLL_INTERVAL,
)


class OpenGymConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up openGym: URL first, then pair with a code."""

    VERSION = 1

    def __init__(self) -> None:
        self._url: str = ""
        self._token: str | None = None

    @staticmethod
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> "OpenGymOptionsFlow":
        return OpenGymOptionsFlow()

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Session expired — pair a new code."""
        self._url = entry_data[CONF_URL]
        return await self.async_step_pair()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Ask for the server URL and check it is reachable."""
        errors: dict[str, str] = {}
        if user_input is not None:
            url = user_input[CONF_URL].strip().rstrip("/")
            client = OpenGymApiClient(self.hass, url)
            try:
                await client.check_connection()
            except OpenGymError:
                errors["base"] = "cannot_connect"
            else:
                self._url = url
                return await self.async_step_pair()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_URL): cv.string}),
            errors=errors,
        )

    async def async_step_pair(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Exchange the pairing code for a Bearer token."""
        errors: dict[str, str] = {}
        if user_input is not None:
            client = OpenGymApiClient(self.hass, self._url)
            try:
                self._token = await client.redeem_pairing_code(
                    user_input["code"].strip()
                )
            except OpenGymError:
                errors["base"] = "invalid_code"
            else:
                await self.async_set_unique_id(secrets.token_hex(8))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input.get(CONF_NAME) or "openGym",
                    data={
                        CONF_URL: self._url,
                        CONF_TOKEN: self._token,
                        CONF_WEBHOOK_ID: f"{DOMAIN}_{secrets.token_hex(8)}",
                        CONF_SECRET: user_input.get(CONF_SECRET, "").strip(),
                    },
                )

        description = (
            "In openGym: Einstellungen → Integrationen → „Die App koppeln“, Code "
            "erstellen und hier eintragen. Der Code ist 5 Minuten gültig."
        )
        return self.async_show_form(
            step_id="pair",
            description_placeholders={"url": self._url},
            data_schema=vol.Schema(
                {
                    vol.Required("code"): cv.string,
                    vol.Optional(CONF_NAME, default="openGym"): cv.string,
                    vol.Optional(CONF_SECRET, default=""): cv.string,
                }
            ),
            description=description,
            errors=errors,
        )

class OpenGymOptionsFlow(OptionsFlow):
    """Adjust the polling interval."""

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_POLL_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL
                        ),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=MIN_POLL_INTERVAL,
                            max=MAX_POLL_INTERVAL,
                            step=1,
                            mode=NumberSelectorMode.SLIDER,
                        )
                    ),
                }
            ),
        )
