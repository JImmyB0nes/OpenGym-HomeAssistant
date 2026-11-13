"""The openGym integration.

Receives signed webhooks from an openGym instance (https://github.com/DuarteSantos8/openGym)
and polls its state document, exposing workouts, weigh-ins, the training plan
and muscle coverage as entities, events and services.
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Any

import voluptuous as vol

from homeassistant.components import webhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

from .api import OpenGymApiClient, OpenGymError
from .const import (
    ATTR_EVENT_ID,
    ATTR_EVENT_TYPE,
    CONF_AUTO_WEBHOOK,
    CONF_POLL_INTERVAL,
    CONF_SECRET,
    CONF_TOKEN,
    CONF_URL,
    CONF_WEBHOOK_ID,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    EVENT_TYPES,
    HEADER_SIGNATURE,
    SERVICE_LOG_WEIGHIN,
    SERVICE_TRIGGER_TEST,
)
from .coordinator import OpenGymDataCoordinator
from .security import verify_signature

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.CALENDAR]

type OpenGymConfigEntry = ConfigEntry[OpenGymRuntime]


class OpenGymRuntime:
    """Runtime data for one openGym config entry."""

    def __init__(self, hass: HomeAssistant, entry: OpenGymConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.client = OpenGymApiClient(hass, entry.data[CONF_URL], entry.data.get(CONF_TOKEN))
        self.coordinator = OpenGymDataCoordinator(hass, entry, self.client)

    async def async_setup(self) -> None:
        """Register the webhook route and do an initial poll."""
        webhook.async_register(
            self.hass,
            self.entry.data[CONF_WEBHOOK_ID],
            "openGym",
            self._handle_webhook,
            handle_args=(self,),
        )
        await self.coordinator.async_config_entry_first_refresh()

    async def async_connect_webhook(self) -> str | None:
        """Create the webhook connection in openGym; returns the new secret."""
        url = webhook.async_generate_url(self.hass, self.entry.data[CONF_WEBHOOK_ID])
        answer = await self.client.connect_webhook(
            url, "Home Assistant", list(EVENT_TYPES)
        )
        return (answer.get("reveal") or {}).get("secret")

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

        self.coordinator.ingest_event(event_type, event)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the openGym component and its services."""
    hass.data.setdefault(DOMAIN, {})

    async def handle_log_weighin(call: ServiceCall) -> None:
        """Write a weigh-in into openGym's state document."""
        weight: float = call.data["weight"]
        unit: str = call.data.get("unit", "kg")
        day: str = str(call.data.get("date") or dt_util.now().date())
        entry = hass.config_entries.async_get_entry(call.data["entry_id"]) if "entry_id" in call.data else next(
            (e for e in hass.config_entries.async_entries(DOMAIN)), None
        )
        if entry is None:
            raise ValueError("no openGym config entry found")
        runtime: OpenGymRuntime = entry.runtime_data

        state, rev = await runtime.client.get_state()
        state = state or {}
        entries = list(state.get("bodyweight") or [])
        existing = next((b for b in entries if b.get("d") == day), None)
        if existing:
            existing["w"] = weight
        else:
            entries.append({"d": day, "w": weight})
        entries.sort(key=lambda b: b.get("d") or "")
        state["bodyweight"] = entries
        state["unit"] = unit
        try:
            await runtime.client.put_state(state, rev)
        except OpenGymError as err:
            raise ValueError(f"openGym write failed: {err}") from err
        await runtime.coordinator.async_refresh()

    async def handle_trigger_test(call: ServiceCall) -> None:
        """Ask openGym to deliver a test webhook now."""
        entry = next(
            (e for e in hass.config_entries.async_entries(DOMAIN)
             if e.entry_id == call.data.get("entry_id")),
            next(hass.config_entries.async_entries(DOMAIN), None),
        )
        if entry is None:
            raise ValueError("no openGym config entry found")
        runtime: OpenGymRuntime = entry.runtime_data
        connections = (await runtime.client.list_integrations()).get("connections") or []
        webhook_conns = [c for c in connections if c.get("kind") == "webhook" or c.get("provider") == "webhook"]
        if not webhook_conns:
            raise ValueError("no webhook connection found in openGym (Settings -> Integrations)")
        result = await runtime.client.test_event(
            webhook_conns[0]["id"], call.data.get("event_type", "workout.finished")
        )
        _LOGGER.info("openGym test event: %s", result)

    if DOMAIN not in hass.data.get("_opengym_services", set()):
        hass.services.async_register(
            DOMAIN,
            SERVICE_LOG_WEIGHIN,
            handle_log_weighin,
            schema=vol.Schema(
                {
                    vol.Required("weight"): vol.Coerce(float),
                    vol.Optional("unit", default="kg"): vol.In(["kg", "lb"]),
                    vol.Optional("date"): cv.date,
                    vol.Optional("entry_id"): cv.string,
                }
            ),
        )
        hass.services.async_register(
            DOMAIN,
            SERVICE_TRIGGER_TEST,
            handle_trigger_test,
            schema=vol.Schema(
                {
                    vol.Optional("event_type"): vol.In(list(EVENT_TYPES)),
                    vol.Optional("entry_id"): cv.string,
                }
            ),
        )
        hass.data.setdefault("_opengym_services", set()).add(DOMAIN)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: OpenGymConfigEntry) -> bool:
    """Set up openGym from a config entry."""
    runtime = OpenGymRuntime(hass, entry)
    await runtime.async_setup()
    entry.runtime_data = runtime

    # One-time: create the webhook connection in openGym (opt-in via config flow).
    if entry.data.get(CONF_AUTO_WEBHOOK):
        try:
            secret = await runtime.async_connect_webhook()
            if secret:
                hass.config_entries.async_update_entry(
                    entry,
                    data={**entry.data, CONF_SECRET: secret, CONF_AUTO_WEBHOOK: False},
                )
                _LOGGER.info("openGym: webhook connection created in openGym")
        except OpenGymError as err:
            _LOGGER.warning(
                "openGym: could not create the webhook connection automatically (%s); "
                "add it manually in Settings -> Integrations -> Webhooks",
                err,
            )

    # Persist a possibly renewed Bearer token (openGym rotates it at /api/me).
    if token := runtime.client.token:
        if entry.data.get(CONF_TOKEN) != token:
            hass.config_entries.async_update_entry(
                entry, data={**entry.data, CONF_TOKEN: token}
            )

    if (options := dict(entry.options)) and CONF_POLL_INTERVAL in options:
        runtime.coordinator.update_interval = timedelta(
            minutes=int(options[CONF_POLL_INTERVAL])
        )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: OpenGymConfigEntry) -> None:
    """Reload when options (poll interval) changed."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: OpenGymConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.async_unload()
    return unload_ok
