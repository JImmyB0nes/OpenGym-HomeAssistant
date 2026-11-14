"""Calendar platform for the openGym training plan."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

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
    async_add_entities(
        [
            TrainingPlanCalendar(coordinator, entry),
            WorkoutHistoryCalendar(coordinator, entry),
        ]
    )


class TrainingPlanCalendar(CoordinatorEntity[OpenGymDataCoordinator], CalendarEntity):
    """The weekly plan (and day overrides) as calendar events."""

    _attr_has_entity_name = True
    _attr_translation_key = "training_plan"
    _attr_name = "Training plan"

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_plan"
        self._attr_device_info = open_gym_device_info(entry)

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    @staticmethod
    def _describe(state, routine) -> str:
        """One line per exercise, names resolved like the app shows them."""
        lines = []
        for ex in routine.get("ex") or []:
            if not isinstance(ex, dict):
                continue
            name = state.exercise_name(ex.get("id"), state.lang, ex)
            sets, reps = ex.get("sets"), ex.get("reps")
            if ex.get("repsMin") and ex.get("repsMax"):
                reps = f"{ex['repsMin']}–{ex['repsMax']}"
            lines.append(f"{name}: {sets} × {reps}" if sets and reps else name)
        return "\n".join(lines) or "–"

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
                emoji = routine.get("emoji")
                # openGym stores an icon *key* ("pullup") there now; only a real
                # emoji from an older profile is worth putting in the title.
                if isinstance(emoji, str) and emoji and not emoji.isascii():
                    name = f"{emoji} {name}"
                events.append(
                    CalendarEvent(
                        start=date(day.year, day.month, day.day),
                        end=date(day.year, day.month, day.day) + timedelta(days=1),
                        summary=name,
                        description=self._describe(state, routine),
                    )
                )
            day += timedelta(days=1)
        return events

    @property
    def event(self) -> CalendarEvent | None:
        today = dt_util.start_of_local_day()
        events = self._events(today, today + timedelta(days=1))
        return events[0] if events else None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        return self._events(start_date, end_date)


class WorkoutHistoryCalendar(CoordinatorEntity[OpenGymDataCoordinator], CalendarEntity):
    """Completed workouts as calendar events (history, not plan)."""

    _attr_has_entity_name = True
    _attr_translation_key = "workout_history"
    _attr_name = "Workout history"

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_workout_history"
        self._attr_device_info = open_gym_device_info(entry)

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    @staticmethod
    def _events(state, start: datetime, end: datetime) -> list[CalendarEvent]:
        events: list[CalendarEvent] = []
        for workout in state.workouts:
            day = workout.get("d")
            if not day:
                continue
            try:
                d = date.fromisoformat(day[:10])
            except ValueError:
                continue
            if not (start.date() <= d < end.date()):
                continue
            started, ended = workout.get("start"), workout.get("end")
            s: datetime | date
            e: datetime | date
            if (
                isinstance(started, (int, float))
                and isinstance(ended, (int, float))
                and ended > started
            ):
                # HA requires timezone-aware datetimes for timed events
                s = dt_util.as_local(dt_util.utc_from_timestamp(started / 1000))
                e = dt_util.as_local(dt_util.utc_from_timestamp(ended / 1000))
            else:
                # no times recorded: all-day event
                s, e = d, d + timedelta(days=1)
            sets = sum(len(e_.get("sets") or []) for e_ in workout.get("entries") or [])
            events.append(
                CalendarEvent(
                    start=s,
                    end=e,
                    summary=workout.get("name") or "Workout",
                    description=(
                        f"{sets} Saetze - {workout.get('vol') or 0:.0f} {state.unit} Volumen"
                    ),
                )
            )
        return events

    @property
    def event(self) -> CalendarEvent | None:
        state = self.coordinator.data
        if state is None:
            return None
        today = dt_util.start_of_local_day()
        events = self._events(state, today, today + timedelta(days=1))
        return events[-1] if events else None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        state = self.coordinator.data
        if state is None:
            return []
        return self._events(state, start_date, end_date)
