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
from homeassistant.const import CoreState, EVENT_HOMEASSISTANT_START, Platform
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
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
    SERVICE_GET_ROUTINES,
    SERVICE_GET_WORKOUT_HISTORY,
    SERVICE_LOG_WEIGHIN,
    SERVICE_TRIGGER_TEST,
)
from .coordinator import OpenGymDataCoordinator
from .frontend import async_schedule_frontend
from .security import verify_signature

_LOGGER = logging.getLogger(__name__)


def _entry_for_call(hass: HomeAssistant, call: ServiceCall):
    """Resolve the config entry a service call targets."""
    entry_id = call.data.get("entry_id")
    if entry_id:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None:
            raise ValueError(f"unknown openGym entry: {entry_id}")
        return entry
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        raise ValueError("no openGym config entry found")
    return entries[0]


PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.CALENDAR,
    Platform.UPDATE,
]

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

    async def handle_get_workout_history(call: ServiceCall) -> dict[str, Any]:
        """Return enriched workout history for the last N days."""
        entry = _entry_for_call(hass, call)
        runtime: OpenGymRuntime = entry.runtime_data
        await runtime.coordinator.async_refresh()
        state = runtime.coordinator.data
        if state is None:
            return {"summary": {}, "workouts": []}
        from datetime import timedelta
        days = int(call.data.get("days", 30))
        start = dt_util.now().date() - timedelta(days=days)
        workouts = state.workouts_between(start, dt_util.now().date())
        durations = [
            (w["end"] - w["start"]) / 60000
            for w in workouts
            if isinstance(w.get("start"), (int, float))
            and isinstance(w.get("end"), (int, float))
        ]
        return {
            "summary": {
                "total_workouts": len(workouts),
                "total_volume": round(sum(w.get("vol") or 0 for w in workouts), 1),
                "workout_days": len({w.get("d") for w in workouts}),
                "avg_duration_min": round(sum(durations) / len(durations), 1)
                if durations
                else None,
                "unit": state.unit,
            },
            "workouts": [
                {
                    "date": w.get("d"),
                    "name": w.get("name"),
                    "volume": w.get("vol"),
                    "exercises": [
                        {
                            "id": e.get("id"),
                            "sets": [
                                {"weight": s.get("w"), "reps": s.get("r")}
                                for s in e.get("sets") or []
                            ],
                        }
                        for e in w.get("entries") or []
                    ],
                }
                for w in workouts
            ],
        }

    async def handle_get_routines(call: ServiceCall) -> dict[str, Any]:
        """Return the saved routines with their exercises."""
        entry = _entry_for_call(hass, call)
        runtime: OpenGymRuntime = entry.runtime_data
        await runtime.coordinator.async_refresh()
        state = runtime.coordinator.data
        if state is None:
            return {"count": 0, "routines": []}
        return {
            "count": len(state.routines),
            "routines": [
                {
                    "id": r.get("id"),
                    "name": r.get("name"),
                    "emoji": r.get("emoji"),
                    "exercises": r.get("ex") or [],
                }
                for r in state.routines.values()
            ],
        }

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
        hass.services.async_register(
            DOMAIN,
            SERVICE_GET_WORKOUT_HISTORY,
            handle_get_workout_history,
            schema=vol.Schema(
                {
                    vol.Optional("days", default=30): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=365)
                    ),
                    vol.Optional("entry_id"): cv.string,
                }
            ),
            supports_response=SupportsResponse.ONLY,
        )
        hass.services.async_register(
            DOMAIN,
            SERVICE_GET_ROUTINES,
            handle_get_routines,
            schema=vol.Schema({vol.Optional("entry_id"): cv.string}),
            supports_response=SupportsResponse.ONLY,
        )
        hass.data.setdefault("_opengym_services", set()).add(DOMAIN)

    # Serve and register the bundled muscle card (once per HA start).
    if hass.state == CoreState.running:
        async_schedule_frontend(hass)
    else:
        async def _register_on_start(_event) -> None:
            async_schedule_frontend(hass)

        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_START, _register_on_start)

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
