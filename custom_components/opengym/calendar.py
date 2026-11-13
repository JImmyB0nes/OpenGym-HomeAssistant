"""Calendar platform for the openGym training plan."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.components.calendar import (
    CalendarEntity,
    CalendarEntityFeature,
    CalendarEvent,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .device_info import open_gym_device_info
from .coordinator import OpenGymDataCoordinator

LOOKAHEAD_DAYS = 30


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the openGym calendar."""
    coordinator: OpenGymDataCoordinator = entry.runtime_data.coordinator
    async_add_entities([TrainingPlanCalendar(coordinator, entry)])


class TrainingPlanCalendar(CoordinatorEntity[OpenGymDataCoordinator], CalendarEntity):
    """The weekly plan (and day overrides) as calendar events."""

    _attr_has_entity_name = True
    _attr_translation_key = "training_plan"
    _attr_name = "Training plan"
    _attr_supported_features = CalendarEntityFeature.EVENT

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_plan"
        self._attr_device_info = open_gym_device_info(entry)

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    def _events(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        state = self.coordinator.data
        if state is None:
            return []
        events: list[CalendarEvent] = []
        day = start.date()
        while day < end.date():
            routine = state.routine_for(day)
            if routine:
                name = routine.get("name") or "Workout"
                if emoji := routine.get("emoji"):
                    name = f"{emoji} {name}"
                events.append(
                    CalendarEvent(
                        start=date(day.year, day.month, day.day),
                        end=date(day.year, day.month, day.day) + timedelta(days=1),
                        summary=name,
                        description=(
                            f"{len(routine.get('ex') or [])} exercises planned"
                        ),
                    )
                )
            day += timedelta(days=1)
        return events

    @property
    def event(self) -> CalendarEvent | None:
        today = datetime.combine(date.today(), datetime.min.time())
        events = self._events(today, today + timedelta(days=1))
        return events[0] if events else None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        return self._events(start_date, end_date)
