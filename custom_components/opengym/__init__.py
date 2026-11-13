"""The openGym integration.

Receives signed webhooks from an openGym instance (https://github.com/DuarteSantos8/openGym)
and exposes the events on the Home Assistant event bus plus sensors for the
most recent workout, personal record and weigh-in.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from homeassistant.components import webhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .const import (
    ATTR_EVENT_ID,
    ATTR_EVENT_TYPE,
    CONF_SECRET,
    CONF_WEBHOOK_ID,
    DOMAIN,
    EVENT_TYPES,
    HEADER_SIGNATURE,
)
from .coordinator import OpenGymCoordinator
from .security import verify_signature

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]

type OpenGymConfigEntry = ConfigEntry[OpenGymCoordinator]


class OpenGymRuntime:
    """Runtime data for one openGym config entry."""

    def __init__(self, hass: HomeAssistant, entry: OpenGymConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.coordinator = OpenGymCoordinator(hass)

    async def async_setup(self) -> None:
        """Register the webhook route."""
        webhook.async_register(
            self.hass,
            self.entry.data[CONF_WEBHOOK_ID],
            "openGym",
            self._handle_webhook,
            handle_args=(self,),
        )

    async def async_unload(self) -> None:
        """Unregister the webhook route."""
        webhook.async_unregister(self.hass, self.entry.data[CONF_WEBHOOK_ID])

    async def _handle_webhook(
        self, hass: HomeAssistant, request, runtime: OpenGymRuntime
    ) -> None:
        """Handle an incoming openGym webhook delivery."""
        try:
            raw = await request.text()
            payload = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            _LOGGER.warning("openGym webhook: invalid body, ignoring")
            return

        secret = self.entry.data.get(CONF_SECRET) or ""
        if secret and not verify_signature(
            secret, raw.encode(), request.headers.get(HEADER_SIGNATURE, "")
        ):
            _LOGGER.warning("openGym webhook: signature check failed, rejecting delivery")
            return

        event_type = payload.get("type")
        if event_type not in EVENT_TYPES:
            _LOGGER.debug("openGym webhook: ignoring unknown type %s", event_type)
            return

        event: dict[str, Any] = {
            ATTR_EVENT_ID: payload.get("id"),
            ATTR_EVENT_TYPE: event_type,
            "created_at": payload.get("createdAt"),
            "test": bool(payload.get("test")),
            "data": payload.get("data", {}),
            "entry_id": self.entry.entry_id,
        }
        self.hass.bus.async_fire(EVENT_TYPES[event_type], event)
        _LOGGER.debug(
            "openGym: fired %s (%s)", EVENT_TYPES[event_type], event[ATTR_EVENT_ID]
        )

        self.coordinator.update(event_type, event)
        for listener in list(self.coordinator.listeners):
            listener()


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the openGym component."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: OpenGymConfigEntry) -> bool:
    """Set up openGym from a config entry."""
    runtime = OpenGymRuntime(hass, entry)
    await runtime.async_setup()
    entry.runtime_data = runtime

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: OpenGymConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.async_unload()
    return unload_ok
