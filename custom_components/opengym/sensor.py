"""Sensor platform for the openGym integration."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfMass, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MUSCLES
from .coordinator import OpenGymDataCoordinator, OpenGymState
from .device_info import open_gym_device_info

# (key, name, kind) — kind selects the value function below.
STATIC_SENSORS = (
    ("last_workout", "Last workout", "workout"),
    ("last_record", "Last personal record", "record"),
    ("last_weighin", "Last weigh-in", "weighin"),
    ("week_volume", "Volume this week", "volume"),
    ("week_workouts", "Workouts this week", "count"),
    ("streak", "Workout streak", "streak"),
    ("next_session", "Next session", "next"),
    ("total_lifting", "Total lifted", "total"),
    ("goal_weight", "Goal weight", "goal"),
    ("days_since_workout", "Days since last workout", "days_since"),
    ("personal_records", "Personal records", "prs"),
    ("workout_heart_rate", "Workout heart rate", "hr"),
    ("best_one_rm", "Estimated 1RM", "one_rm"),
    ("custom_exercises", "Custom exercises", "custom_ex"),
    ("muscle_balance", "Muscle balance", "balance"),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up openGym sensors."""
    coordinator: OpenGymDataCoordinator = entry.runtime_data.coordinator
    entities: list[SensorEntity] = [
        OpenGymSensor(coordinator, entry, key, name, kind)
        for key, name, kind in STATIC_SENSORS
    ]
    entities += [
        MuscleDaysSensor(coordinator, entry, muscle, label) for muscle, label in MUSCLES.items()
    ]
    async_add_entities(entities)


class OpenGymSensor(CoordinatorEntity[OpenGymDataCoordinator], SensorEntity):
    """A sensor derived from the polled openGym state (and live webhooks)."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, key: str, name: str, kind: str) -> None:
        super().__init__(coordinator)
        self._key = key
        self._kind = kind
        self._attr_translation_key = key
        self._attr_name = name
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = open_gym_device_info(entry)
        if kind == "weighin":
            self._attr_device_class = SensorDeviceClass.WEIGHT
            self._attr_state_class = SensorStateClass.MEASUREMENT
        elif kind == "goal":
            self._attr_device_class = SensorDeviceClass.WEIGHT
            self._attr_icon = "mdi:flag-checkered"
        elif kind == "days_since":
            self._attr_native_unit_of_measurement = UnitOfTime.DAYS
            self._attr_icon = "mdi:calendar-remove"
        elif kind == "prs":
            self._attr_icon = "mdi:medal"
        elif kind == "hr":
            self._attr_native_unit_of_measurement = "bpm"
            self._attr_icon = "mdi:heart-pulse"
        elif kind == "one_rm":
            self._attr_icon = "mdi:weight"
        elif kind == "custom_ex":
            self._attr_icon = "mdi:pencil-ruler"
        elif kind == "balance":
            self._attr_icon = "mdi:human-handsup"
            self._attr_state_class = SensorStateClass.TOTAL
            self._attr_native_unit_of_measurement = "sets"
        elif kind in ("volume", "total"):
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        elif kind == "count":
            self._attr_state_class = SensorStateClass.TOTAL
        elif kind == "streak":
            self._attr_native_unit_of_measurement = UnitOfTime.DAYS
            self._attr_icon = "mdi:fire"
        elif kind == "next":
            self._attr_icon = "mdi:calendar-clock"
        elif kind == "record":
            self._attr_icon = "mdi:trophy"
        elif kind == "workout":
            self._attr_icon = "mdi:weight-lifter"

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def native_unit_of_measurement(self) -> str | None:
        if self._kind in ("weighin", "volume", "total", "goal", "one_rm"):
            state = self.coordinator.data
            if state and state.unit == "lb":
                return UnitOfMass.POUNDS
            return UnitOfMass.KILOGRAMS
        return super().native_unit_of_measurement

    @property
    def native_value(self) -> Any:
        state: OpenGymState | None = self.coordinator.data
        if state is None:
            return None
        today = date.today()
        if self._kind == "workout":
            w = state.last_workout()
            if not w:
                return None
            name = w.get("name") or "Workout"
            return name
        if self._kind == "record":
            w = state.last_workout()
            prs = (w or {}).get("prs") or []
            if not prs:
                return None
            return f"{len(prs)} record(s) in {w.get('name', 'workout')}"
        if self._kind == "weighin":
            b = state.last_weighin()
            return b.get("w") if b else None
        if self._kind == "volume":
            return round(state.week_volume(today), 1)
        if self._kind == "count":
            return state.week_count(today)
        if self._kind == "streak":
            return state.streak(today)
        if self._kind == "next":
            nxt = state.next_session(today)
            if not nxt:
                return "Rest"
            routine, day = nxt
            return f"{routine.get('name', '?')} · {day.isoformat()}"
        if self._kind == "total":
            return round(sum(w.get("vol") or 0 for w in state.workouts), 0)
        if self._kind == "goal":
            return state.goal_weight()
        if self._kind == "days_since":
            day = state.last_workout_day()
            return (date.today() - day).days if day else None
        if self._kind == "prs":
            return len(state.pr_map())
        if self._kind == "hr":
            hr = state.last_workout_hr()
            return hr["avg"] if hr else None
        if self._kind == "one_rm":
            best = state.best_1rm()
            return round(max(best.values()), 1) if best else None
        if self._kind == "custom_ex":
            return state.custom_ex_count()
        if self._kind == "balance":
            return round(sum(state.week_sets(date.today()).values()), 1)
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        state = self.coordinator.data
        if state is None:
            return {}
        if self._kind == "workout":
            w = state.last_workout() or {}
            return {
                "date": w.get("d"),
                "volume": w.get("vol"),
                "sets": sum(
                    len(e.get("sets") or [])
                    for e in w.get("entries") or []
                ),
            }
        if self._kind == "next":
            nxt = state.next_session(date.today())
            if nxt:
                routine, day = nxt
                return {
                    "routine_id": routine.get("id"),
                    "exercises": len(routine.get("ex") or []),
                    "date": day.isoformat(),
                }
        if self._kind == "weighin":
            b = state.last_weighin() or {}
            return {"date": b.get("d")}
        if self._kind == "goal":
            goal = state.goal_weight()
            current = (state.last_weighin() or {}).get("w")
            if goal is None:
                return {}
            result = {"goal": goal}
            if current is not None:
                result["current"] = current
                result["delta"] = round(current - goal, 1)
                result["at_or_below_goal"] = current <= goal
            return result
        if self._kind == "prs":
            pr_map = state.pr_map()
            return {
                f"{ex_id}": f"{info['weight']}{state.unit}"
                + (f" ({info['date']})" if info.get("date") else "")
                for ex_id, info in sorted(pr_map.items())
            }
        if self._kind == "hr":
            hr = state.last_workout_hr()
            return hr or {}
        if self._kind == "days_since":
            day = state.last_workout_day()
            return {"last_workout": day.isoformat() if day else None}
        if self._kind == "one_rm":
            return {
                ex_id: round(est, 1) for ex_id, est in sorted(state.best_1rm().items())
            }
        if self._kind == "custom_ex":
            return {
                str(ex.get("id")): ex.get("n")
                for ex in (state.raw.get("customEx") or [])
                if ex.get("n")
            }
        if self._kind == "balance":
            today = date.today()
            targets = state.muscle_targets()
            return {
                "week_start": state.week_start(today).isoformat(),
                "sets": state.week_sets(today),
                "targets": {m: list(r) for m, r in targets.items()},
                "last_trained": state.muscle_last_days(today),
                "best_1rm": {
                    m: round(v, 1) for m, v in state.best_muscle_1rm().items()
                },
                "unit": state.unit,
            }
        return {}


class MuscleDaysSensor(CoordinatorEntity[OpenGymDataCoordinator], SensorEntity):
    """Days since a muscle group was last trained (999 = never)."""

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTime.DAYS
    _attr_icon = "mdi:human-handsup"

    def __init__(self, coordinator, entry, muscle: str, label: str) -> None:
        super().__init__(coordinator)
        self._muscle = muscle
        self._attr_translation_key = f"muscle_{muscle.replace('-', '_')}"
        self._attr_name = f"{label} idle"
        self._attr_unique_id = f"{entry.entry_id}_muscle_{muscle}"
        self._attr_device_info = open_gym_device_info(entry)

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def native_value(self) -> int | None:
        state = self.coordinator.data
        if state is None:
            return None
        return state.muscle_days(date.today()).get(self._muscle)
