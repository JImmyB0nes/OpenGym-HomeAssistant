"""The openGym integration.

Receives signed webhooks from an openGym instance (https://github.com/DuarteSantos8/openGym)
and polls its state document, exposing workouts, weigh-ins, the training plan
and muscle coverage as entities, events and services.
"""

from __future__ import annotations

import copy
import json
import logging
import time
from collections.abc import Callable
from datetime import timedelta
from typing import TYPE_CHECKING, Any

import voluptuous as vol

from homeassistant.components import webhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_START, Platform
from homeassistant.core import CoreState, HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.network import NoURLAvailableError
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

from . import logic
from .api import OpenGymApiClient, OpenGymConflictError, OpenGymError, OpenGymFeatureOffError
from .const import (
    ATTR_EVENT_ID,
    ATTR_EVENT_TYPE,
    CONF_AUTO_WEBHOOK,
    CONF_POLL_INTERVAL,
    CONF_REV_INTERVAL,
    DEFAULT_REV_INTERVAL,
    SERVICE_ADD_DAY_NOTE,
    SERVICE_CANCEL_REST_TIMER,
    SERVICE_COACH_REVIEW,
    SERVICE_MOVE_DAY,
    SERVICE_SET_REST_DAY,
    SERVICE_START_REST_TIMER,
    CONF_SECRET,
    CONF_TOKEN,
    CONF_URL,
    CONF_WEBHOOK_ID,
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
from .websocket_api import async_setup_ws

_LOGGER = logging.getLogger(__name__)


def _entry_for_call(hass: HomeAssistant, call: ServiceCall):
    """Resolve the (loaded) config entry a service call targets."""
    entry_id = call.data.get("entry_id")
    if entry_id:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unknown_entry",
                translation_placeholders={"entry_id": str(entry_id)},
            )
    else:
        entries = [
            e for e in hass.config_entries.async_entries(DOMAIN)
            if getattr(e, "runtime_data", None) is not None
        ]
        if not entries:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="no_entry"
            )
        entry = entries[0]
    if getattr(entry, "runtime_data", None) is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="entry_not_loaded"
        )
    return entry


def _write_failed(err: Exception) -> HomeAssistantError:
    return HomeAssistantError(
        translation_domain=DOMAIN,
        translation_key="write_failed",
        translation_placeholders={"error": str(err)[:200]},
    )


CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.CALENDAR,
    Platform.UPDATE,
    Platform.BUTTON,
]

# PUT /api/data conflict retries before giving up (409 hands back the fresh doc)
MAX_WRITE_ATTEMPTS = 4

# ``ConfigEntry[...]`` as a subscripted generic requires HA >= 2024.6
# (ConfigEntry became Generic there). Keep the parameterized alias for
# type checkers only, so importing this module never fails on older cores.
OpenGymConfigEntry = ConfigEntry
if TYPE_CHECKING:
    OpenGymConfigEntry = ConfigEntry["OpenGymRuntime"]  # type: ignore[misc]


class OpenGymRuntime:
    """Runtime data for one openGym config entry."""

    def __init__(self, hass: HomeAssistant, entry: OpenGymConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.client = OpenGymApiClient(hass, entry.data[CONF_URL], entry.data.get(CONF_TOKEN))
        self.coordinator = OpenGymDataCoordinator(hass, entry, self.client)

    async def async_setup(self) -> None:
        """Do an initial poll, then register the webhook route.

        The first refresh may raise ConfigEntryNotReady; registering the
        webhook only afterwards keeps a setup retry from failing with
        "Handler is already defined!".
        """
        await self.coordinator.async_config_entry_first_refresh()
        webhook.async_register(
            self.hass,
            DOMAIN,
            "openGym",
            self.entry.data[CONF_WEBHOOK_ID],
            self._handle_webhook,
        )

    async def async_connect_webhook(self) -> str | None:
        """Create the webhook connection in openGym; returns the new secret."""
        url = webhook.async_generate_url(self.hass, self.entry.data[CONF_WEBHOOK_ID])
        answer = await self.client.connect_webhook(
            url, "Home Assistant", list(EVENT_TYPES)
        )
        return (answer.get("reveal") or {}).get("secret")

    async def async_unload(self) -> None:
        """Unregister the webhook route and stop the fast tick."""
        self.coordinator.async_stop_fast_tick()
        webhook.async_unregister(self.hass, self.entry.data[CONF_WEBHOOK_ID])

    async def async_mutate_state(
        self, mutate: Callable[[dict[str, Any]], dict[str, Any]]
    ) -> dict[str, Any]:
        """Read-modify-write the state document with a conditional PUT.

        `mutate` gets a private copy of the document and returns the edited
        one. A 409 hands back the server's current document and revision
        (openapi putData), so the same edit is re-applied on top of it — up
        to MAX_WRITE_ATTEMPTS times. Without `stamped` the server stamps the
        changed sections itself.
        """
        state, rev = await self.client.get_state()
        for attempt in range(1, MAX_WRITE_ATTEMPTS + 1):
            edited = mutate(copy.deepcopy(state or {}))
            try:
                result = await self.client.put_state(edited, rev)
            except OpenGymConflictError as err:
                if attempt == MAX_WRITE_ATTEMPTS:
                    raise HomeAssistantError(
                        translation_domain=DOMAIN, translation_key="write_conflict"
                    ) from err
                _LOGGER.debug("openGym: write conflict (rev %s), retrying", err.rev)
                state, rev = err.state, err.rev
                if state is None:
                    state, rev = await self.client.get_state()
                continue
            await self.coordinator.async_refresh()
            return result
        raise HomeAssistantError(  # pragma: no cover - loop always returns/raises
            translation_domain=DOMAIN, translation_key="write_conflict"
        )

    async def _handle_webhook(
        self, hass: HomeAssistant, webhook_id: str, request
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
        runtime: OpenGymRuntime = _entry_for_call(hass, call).runtime_data
        try:
            await runtime.async_mutate_state(
                lambda state: logic.set_weighin(state, day, weight, unit)
            )
        except OpenGymError as err:
            raise _write_failed(err) from err

    async def _plan_edit(call: ServiceCall, edit: Callable[[dict[str, Any]], Any]) -> None:
        runtime: OpenGymRuntime = _entry_for_call(hass, call).runtime_data
        try:
            await runtime.async_mutate_state(edit)
        except logic.PlanEditError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key=f"plan_{err.key}",
                translation_placeholders=err.placeholders,
            ) from err
        except OpenGymError as err:
            raise _write_failed(err) from err

    async def handle_set_rest_day(call: ServiceCall) -> None:
        """Mark a day as rest (or, with `clear`, drop the day's override)."""
        day = call.data.get("date") or dt_util.now().date()
        if call.data.get("clear"):
            await _plan_edit(call, lambda s: logic.clear_day_override(s, day))
        else:
            await _plan_edit(call, lambda s: logic.set_rest_day(s, day))

    async def handle_move_day(call: ServiceCall) -> None:
        """Move the session planned on one day to another."""
        src, dst = call.data["from_date"], call.data["to_date"]
        await _plan_edit(call, lambda s: logic.move_day(s, src, dst))

    async def handle_add_day_note(call: ServiceCall) -> None:
        """Day note (sick, travel, rest, injured + text); excuses the day from nudges."""
        today = dt_util.now().date()
        day = call.data.get("date") or today
        await _plan_edit(
            call,
            lambda s: logic.add_day_note(
                s, day, today, int(time.time() * 1000),
                call.data.get("tag"), call.data.get("text"),
            ),
        )

    async def handle_start_rest_timer(call: ServiceCall) -> None:
        """Have openGym push a rest-timer notification to your devices."""
        runtime: OpenGymRuntime = _entry_for_call(hass, call).runtime_data
        state = runtime.coordinator.data
        seconds = logic.clamp_rest_seconds(
            call.data.get("seconds"), state.rest_seconds() if state else None
        )
        try:
            await runtime.client.start_rest_timer(seconds, call.data.get("device_id"))
        except OpenGymError as err:
            raise _write_failed(err) from err
        runtime.coordinator.set_rest_timer(seconds)

    async def handle_cancel_rest_timer(call: ServiceCall) -> None:
        runtime: OpenGymRuntime = _entry_for_call(hass, call).runtime_data
        try:
            await runtime.client.cancel_rest_timer(call.data.get("device_id"))
        except OpenGymError as err:
            raise _write_failed(err) from err
        runtime.coordinator.set_rest_timer(None)

    async def handle_coach_review(call: ServiceCall) -> dict[str, Any]:
        """Ask the openGym Coach to review the plan (answer arrives as a proposal)."""
        runtime: OpenGymRuntime = _entry_for_call(hass, call).runtime_data
        try:
            result = await runtime.client.coach_review(
                call.data.get("note"), call.data.get("lang")
            )
        except OpenGymFeatureOffError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="coach_off"
            ) from err
        except OpenGymError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="coach_failed",
                translation_placeholders={"error": str(err)[:200]},
            ) from err
        await runtime.coordinator.async_request_refresh()
        return {"job": (result or {}).get("job") or result}

    async def handle_trigger_test(call: ServiceCall) -> None:
        """Ask openGym to deliver a test webhook now."""
        entry = _entry_for_call(hass, call)
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
        entry_field = {vol.Optional("entry_id"): cv.string}
        device_field = {
            vol.Optional("device_id"): vol.All(cv.string, vol.Match(r"^[A-Za-z0-9_-]{8,64}$"))
        }
        hass.services.async_register(
            DOMAIN,
            SERVICE_START_REST_TIMER,
            handle_start_rest_timer,
            schema=vol.Schema({
                vol.Optional("seconds"): vol.All(vol.Coerce(int), vol.Range(min=1, max=3600)),
                **device_field,
                **entry_field,
            }),
        )
        hass.services.async_register(
            DOMAIN,
            SERVICE_CANCEL_REST_TIMER,
            handle_cancel_rest_timer,
            schema=vol.Schema({**device_field, **entry_field}),
        )
        hass.services.async_register(
            DOMAIN,
            SERVICE_COACH_REVIEW,
            handle_coach_review,
            schema=vol.Schema({
                vol.Optional("note"): vol.All(cv.string, vol.Length(max=2000)),
                vol.Optional("lang"): vol.In(["de", "en"]),
                **entry_field,
            }),
            supports_response=SupportsResponse.OPTIONAL,
        )
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_REST_DAY,
            handle_set_rest_day,
            schema=vol.Schema({
                vol.Optional("date"): cv.date,
                vol.Optional("clear", default=False): cv.boolean,
                **entry_field,
            }),
        )
        hass.services.async_register(
            DOMAIN,
            SERVICE_MOVE_DAY,
            handle_move_day,
            schema=vol.Schema({
                vol.Required("from_date"): cv.date,
                vol.Required("to_date"): cv.date,
                **entry_field,
            }),
        )
        hass.services.async_register(
            DOMAIN,
            SERVICE_ADD_DAY_NOTE,
            handle_add_day_note,
            schema=vol.Schema({
                vol.Optional("date"): cv.date,
                vol.Optional("tag"): vol.In(list(logic.DAY_NOTE_TAGS)),
                vol.Optional("text"): vol.All(cv.string, vol.Length(max=logic.NOTE_MAX)),
                **entry_field,
            }),
        )
        hass.data.setdefault("_opengym_services", set()).add(DOMAIN)

    # WebSocket commands for the bundled card (detail panels, version check).
    async_setup_ws(hass)

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
        except (OpenGymError, NoURLAvailableError) as err:
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
    # (1) fast tick: revision check + live presence / watch / Coach job
    runtime.coordinator.async_start_fast_tick(
        int(entry.options.get(CONF_REV_INTERVAL, DEFAULT_REV_INTERVAL))
    )
    return True


async def _async_update_listener(hass: HomeAssistant, entry: OpenGymConfigEntry) -> None:
    """Reload when options (poll interval) changed."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: OpenGymConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.async_unload()
    return unload_ok
