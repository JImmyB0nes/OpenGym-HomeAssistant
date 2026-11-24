"""Event entities: workout finished, personal record, weigh-in, Coach.

Each openGym event becomes the newest state of an event entity: selectable
in the automation editor ("Entity → State → event type"), visible in the
history, with the payload's useful fields as attributes. The entities listen
to the integration's own bus events, so webhooks and Coach results reach
them the same way they reach automations.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import logic
from .const import EVENT_COACH_ANSWER, EVENT_COACH_DEBRIEF, EVENT_TYPES
from .coordinator import OpenGymDataCoordinator
from .device_info import open_gym_device_info, prune_entities, suggested_entity_id

# translation key -> (bus event, event type, openGym type)
WEBHOOK_EVENTS = (
    ("workout_finished", EVENT_TYPES["workout.finished"], "workout_finished", "workout.finished", "mdi:weight-lifter"),
    ("personal_record", EVENT_TYPES["workout.pr"], "personal_record", "workout.pr", "mdi:trophy"),
    ("weigh_in", EVENT_TYPES["weighin.logged"], "weigh_in", "weighin.logged", "mdi:scale-bathroom"),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: OpenGymDataCoordinator = entry.runtime_data.coordinator
    entities: list[EventEntity] = [
        OpenGymWebhookEvent(coordinator, entry, key, bus, etype, og_type, icon)
        for key, bus, etype, og_type, icon in WEBHOOK_EVENTS
    ]
    if coordinator.coach_enabled:
        entities.append(OpenGymCoachEvent(coordinator, entry))
    elif coordinator.coach_enabled is False:
        prune_entities(hass, entry, "event", ("coach_event",))
    async_add_entities(entities)


class _OpenGymEvent(EventEntity):
    """Listens to one or more openGym bus events of this config entry."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator, entry, key: str) -> None:
        self.coordinator = coordinator
        self._entry_id = entry.entry_id
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = open_gym_device_info(entry)
        self.entity_id = suggested_entity_id(entry, "event", key)

    def _listen(self, bus_event: str) -> None:
        @callback
        def _handle(event: Event) -> None:
            if event.data.get("entry_id") != self._entry_id:
                return
            self._on_event(bus_event, dict(event.data))

        self.async_on_remove(self.hass.bus.async_listen(bus_event, _handle))

    @callback
    def _on_event(self, bus_event: str, data: dict[str, Any]) -> None:
        raise NotImplementedError


class OpenGymWebhookEvent(_OpenGymEvent):
    """Workout finished / personal record / weigh-in (from the signed webhook)."""

    def __init__(self, coordinator, entry, key, bus_event, event_type, og_type, icon) -> None:
        super().__init__(coordinator, entry, key)
        self._bus_event = bus_event
        self._event_type = event_type
        self._og_type = og_type
        self._attr_event_types = [event_type]
        self._attr_icon = icon

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._listen(self._bus_event)

    @callback
    def _on_event(self, bus_event: str, data: dict[str, Any]) -> None:
        self._trigger_event(self._event_type, logic.event_attributes(self._og_type, data))
        self.async_write_ha_state()


class OpenGymCoachEvent(_OpenGymEvent):
    """Coach results Home Assistant asked for: an answer or a workout debrief."""

    _attr_event_types = ["answer", "debrief", "failed"]
    _attr_icon = "mdi:account-tie-voice"

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry, "coach_event")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._listen(EVENT_COACH_ANSWER)
        self._listen(EVENT_COACH_DEBRIEF)

    @callback
    def _on_event(self, bus_event: str, data: dict[str, Any]) -> None:
        data.pop("entry_id", None)
        etype = "answer" if bus_event == EVENT_COACH_ANSWER else "debrief"
        if data.get("status") == "failed":
            etype = "failed"
        self._trigger_event(etype, data)
        self.async_write_ha_state()
