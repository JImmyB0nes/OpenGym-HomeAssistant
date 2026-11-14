"""Config flow for the openGym integration."""

from __future__ import annotations

import secrets
from typing import Any

import voluptuous as vol

from homeassistant.components import webhook
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    OptionsFlow,
)
from homeassistant.const import CONF_URL

# ConfigFlowResult exists only since HA 2024.4; fall back to the generic
# FlowResult on older installs so importing this module never fails
# ("Invalid handler specified").
try:  # HA >= 2024.4
    from homeassistant.config_entries import ConfigFlowResult
except ImportError:  # HA < 2024.4
    from homeassistant.data_entry_flow import FlowResult as ConfigFlowResult
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from .api import OpenGymApiClient, OpenGymError
from .const import (
    CONF_AUTO_WEBHOOK,
    CONF_NAME,
    CONF_POLL_INTERVAL,
    CONF_SECRET,
    CONF_TOKEN,
    CONF_WEBHOOK_ID,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    EVENT_TYPES,
    MAX_POLL_INTERVAL,
    MIN_POLL_INTERVAL,
)


class OpenGymConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up openGym: URL first, then pair with a code."""

    VERSION = 1

    def __init__(self) -> None:
        self._url: str = ""
        self._token: str | None = None
        # Pre-generated so the webhook URL can be shown during pairing.
        self._webhook_id = f"{DOMAIN}_{secrets.token_hex(8)}"

    def _reauth_entry(self) -> ConfigEntry:
        """Return the entry being reauthenticated.

        ``_get_reauth_entry()`` exists only since HA 2024.11; on older
        versions the entry is resolved from the flow context instead.
        """
        if hasattr(self, "_get_reauth_entry"):
            return self._get_reauth_entry()  # type: ignore[no-any-return]
        return self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> "OpenGymOptionsFlow":
        return OpenGymOptionsFlow()

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Session invalid — ask for a new pairing code."""
        self._url = entry_data[CONF_URL]
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            client = OpenGymApiClient(self.hass, self._url)
            try:
                token = await client.redeem_pairing_code(user_input["code"].strip())
            except OpenGymError:
                return self.async_show_form(
                    step_id="reauth_confirm",
                    data_schema=vol.Schema({vol.Required("code"): cv.string}),
                    errors={"base": "invalid_code"},
                )
            entry = self._reauth_entry()
            return self.async_update_reload_and_abort(
                entry,
                data={**entry.data, CONF_TOKEN: token},
            )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required("code"): cv.string}),
            description_placeholders={"url": self._url},
        )

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
                auto_webhook = bool(user_input.get(CONF_AUTO_WEBHOOK))
                if auto_webhook and not user_input.get(CONF_SECRET, "").strip():
                    # the integration creates the connection itself; the secret
                    # arrives with the first setup, not from the user
                    return self.async_create_entry(
                        title=user_input.get(CONF_NAME) or "openGym",
                        data={
                            CONF_URL: self._url,
                            CONF_TOKEN: self._token,
                            CONF_WEBHOOK_ID: self._webhook_id,
                            CONF_SECRET: "",
                            CONF_AUTO_WEBHOOK: True,
                        },
                    )
                return self.async_create_entry(
                    title=user_input.get(CONF_NAME) or "openGym",
                    data={
                        CONF_URL: self._url,
                        CONF_TOKEN: self._token,
                        CONF_WEBHOOK_ID: self._webhook_id,
                        CONF_SECRET: user_input.get(CONF_SECRET, "").strip(),
                        CONF_AUTO_WEBHOOK: False,
                    },
                )

        return self.async_show_form(
            step_id="pair",
            description_placeholders={
                "url": self._url,
                "webhook_url": webhook.async_generate_url(
                    self.hass, self._webhook_id
                ),
                "events": ", ".join(EVENT_TYPES),
                "poll_interval": str(DEFAULT_POLL_INTERVAL),
            },
            data_schema=vol.Schema(
                {
                    vol.Required("code"): cv.string,
                    vol.Optional(CONF_NAME, default="openGym"): cv.string,
                    vol.Optional(CONF_AUTO_WEBHOOK, default=True): cv.boolean,
                    vol.Optional(CONF_SECRET, default=""): cv.string,
                }
            ),
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
