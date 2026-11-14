"""Sensor platform for the openGym integration."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfMass, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import logic
from .const import (
    CONF_MAX_HEART_RATE,
    DEFAULT_MAX_HEART_RATE,
    FATIGUE_HALF_LIFE_DEFAULT_H,
    FATIGUE_HALF_LIFE_H,
    INTEGRATION_VERSION,
    MUSCLES,
    _CANON,
)
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
    ("muscle_fatigue", "Muscle fatigue", "fatigue"),
    ("week_history", "Weekly training history", "history"),
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
    # (11) long-term statistics: weekly sets per muscle
    entities += [
        MuscleWeeklySetsSensor(coordinator, entry, muscle, label)
        for muscle, label in MUSCLES.items()
    ]
    # (2) live workout + rest timer started from HA
    entities += [LiveProgressSensor(coordinator, entry), RestTimerSensor(coordinator, entry)]
    # (8) Coach — only when the instance runs it (503 "off" / 404 = not created)
    if coordinator.coach_enabled:
        entities.append(CoachStatusSensor(coordinator, entry))
    # (12) watch — only when the watch endpoints exist
    if coordinator.watch_supported:
        entities += [
            WatchPairedSensor(coordinator, entry),
            WatchHeartRateSensor(coordinator, entry),
            WatchHeartRateZoneSensor(coordinator, entry),
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
        self._entry_id = entry.entry_id
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
            # Weekly volume resets each week — a measurement, not a counter.
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_native_unit_of_measurement = "sets"
        elif kind == "fatigue":
            self._attr_icon = "mdi:sleep"
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_native_unit_of_measurement = "×"
        elif kind == "history":
            self._attr_icon = "mdi:grid"
            self._attr_native_unit_of_measurement = "wk"
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
        if self._kind == "fatigue":
            values = state.fatigue(date.today())
            return sum(1 for v in values.values() if v > 0.5)
        if self._kind == "history":
            return sum(1 for w in state.week_history(date.today()) if w["workouts"])
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
            nxt = state.next_workout(date.today())
            if nxt:
                # `exercises` stays the count (pre-0.10 automations); details below.
                return {
                    "routine_id": nxt["routine_id"],
                    "exercises": len(nxt["exercises"]),
                    "date": nxt["date"],
                    "name": nxt["name"],
                    "emoji": nxt["emoji"],
                    "days_until": nxt["days_until"],
                    "total_sets": nxt["total_sets"],
                    "muscles": nxt["muscles"],
                    "exercise_list": nxt["exercises"],
                    "rest_sec": state.rest_seconds(),
                    "unit": state.unit,
                    "entry_id": self._entry_id,
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
            fatigue_map = state.fatigue(today)
            goal = state.goal_weight()
            current = (state.last_weighin() or {}).get("w")
            return {
                "week_start": state.week_start(today).isoformat(),
                "sets": state.week_sets(today),
                "targets": {m: list(r) for m, r in targets.items()},
                "last_trained": state.muscle_last_days(today),
                "best_1rm": {
                    m: round(v, 1) for m, v in state.best_muscle_1rm().items()
                },
                "fatigue": fatigue_map,
                "planned": state.planned_muscles(today),
                "planned_week": state.planned_week(today),
                "day_view": state.day_view(today),
                "history": state.week_history(today),
                "trends": state.muscle_trends(today),
                # (6) card stats
                "week_prs": state.week_prs(today),
                "weight_trend": state.weight_trend(),
                "goal_weight": goal,
                "goal_delta": (
                    round(current - goal, 1)
                    if goal is not None and current is not None
                    else None
                ),
                "last_hr": state.last_workout_hr(),
                # (5) lets the card ask *this* entry for muscle details
                "entry_id": self._entry_id,
                "version": INTEGRATION_VERSION,
                "unit": state.unit,
            }
        if self._kind == "fatigue":
            today = date.today()
            fatigue_map = state.fatigue(today)
            return {
                m: {
                    "value": v,
                    "state": state.fatigue_state(v),
                    "half_life_h": FATIGUE_HALF_LIFE_H.get(m, FATIGUE_HALF_LIFE_DEFAULT_H),
                }
                for m, v in sorted(fatigue_map.items(), key=lambda kv: -kv[1])
            }
        if self._kind == "history":
            return {"weeks": state.week_history(date.today())}
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


class _Base(CoordinatorEntity[OpenGymDataCoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, key: str, name: str) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_translation_key = key
        self._attr_name = name
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = open_gym_device_info(entry)


class MuscleWeeklySetsSensor(_Base):
    """Effective sets this week for one muscle — recorded as long-term statistics."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "sets"
    _attr_icon = "mdi:chart-bar"
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator, entry, muscle: str, label: str) -> None:
        super().__init__(
            coordinator, entry, f"weekly_sets_{muscle.replace('-', '_')}", f"{label} weekly sets"
        )
        self._muscle = muscle
        # openGym's map spells forearms `forearm`
        self._slugs = {muscle} | {s for s, canon in _CANON.items() if canon == muscle}

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def native_value(self) -> float | None:
        state = self.coordinator.data
        if state is None:
            return None
        sets = state.week_sets(date.today())
        return round(sum(sets.get(s, 0) for s in self._slugs), 1)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        state = self.coordinator.data
        if state is None:
            return {}
        today = date.today()
        last = state.week_sets(today, -1)
        target = state.muscle_targets().get(self._muscle)
        return {
            "week_start": state.week_start(today).isoformat(),
            "last_week": round(sum(last.get(s, 0) for s in self._slugs), 1),
            "target": list(target) if target else None,
        }


class LiveProgressSensor(_Base):
    """Progress of the workout running in openGym right now (admin presence)."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_icon = "mdi:progress-check"

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry, "live_progress", "Live workout progress")

    @property
    def available(self) -> bool:
        # openGym only shares presence with admins (GET /api/admin/users)
        return self.coordinator.last_update_success and bool(self.coordinator.is_admin)

    @property
    def native_value(self) -> int | None:
        if not self.coordinator.presence:
            return None
        return logic.presence_progress(self.coordinator.presence)["progress"]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        p = self.coordinator.presence
        if not p:
            return {"active": False}
        return {"active": True, "name": p.get("name"), **logic.presence_progress(p)}


class RestTimerSensor(_Base):
    """When the rest timer started from Home Assistant ends."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:timer-sand"

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry, "rest_timer", "Rest timer")

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def native_value(self):
        return self.coordinator.rest_timer_end

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        state = self.coordinator.data
        return {
            "seconds": self.coordinator.rest_timer_seconds,
            "default_seconds": state.rest_seconds() if state else None,
        }


class CoachStatusSensor(_Base):
    """openGym Coach: idle, queued, running or a proposal waiting for you."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["idle", "queued", "running", "proposal"]
    _attr_icon = "mdi:account-tie-voice"

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry, "coach_status", "Coach")

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and bool(self.coordinator.coach_enabled)

    @property
    def native_value(self) -> str | None:
        return logic.coach_summary(self.coordinator.coach)["state"]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        summary = logic.coach_summary(self.coordinator.coach)
        summary.pop("state")
        return summary


class _WatchBase(_Base):
    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and bool(self.coordinator.watch_supported)


class WatchPairedSensor(_WatchBase):
    """Number of paired watches (GET /api/watch/links)."""

    _attr_icon = "mdi:watch"
    _attr_native_unit_of_measurement = "watches"

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry, "watch_paired", "Paired watches")

    @property
    def native_value(self) -> int:
        return len(self.coordinator.watch_links)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        links = self.coordinator.watch_links
        seen = [link.get("seen") for link in links if isinstance(link.get("seen"), (int, float))]
        return {
            "watches": [{"name": link.get("name"), "seen": link.get("seen")} for link in links],
            "last_seen": dt_from_ms(max(seen)) if seen else None,
            "queued_events": len((self.coordinator.watch_queue or {}).get("events") or []),
        }


class WatchHeartRateSensor(_WatchBase):
    """Newest heart rate the watch reported (set or rest HR)."""

    _attr_native_unit_of_measurement = "bpm"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:heart-pulse"

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry, "watch_heart_rate", "Watch heart rate")

    @property
    def available(self) -> bool:
        return super().available and bool(self.coordinator.watch_links)

    @property
    def native_value(self) -> int | None:
        hr = self.coordinator.watch_hr
        return hr["avg"] if hr else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        hr = self.coordinator.watch_hr or {}
        return {
            "max": hr.get("max"),
            "phase": hr.get("phase"),
            "event": hr.get("type"),
            "measured_at": dt_from_ms(hr["at"]) if hr.get("at") else None,
        }


class WatchHeartRateZoneSensor(_WatchBase):
    """Heart-rate zone 1-5 (% of max HR from the integration options)."""

    _attr_icon = "mdi:heart-flash"

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry, "watch_hr_zone", "Heart rate zone")

    @property
    def _max_hr(self) -> float:
        return float(self._entry.options.get(CONF_MAX_HEART_RATE, DEFAULT_MAX_HEART_RATE))

    @property
    def available(self) -> bool:
        return super().available and bool(self.coordinator.watch_links)

    @property
    def native_value(self) -> int | None:
        hr = self.coordinator.watch_hr
        return logic.hr_zone(hr["avg"], self._max_hr) if hr else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"max_heart_rate": self._max_hr, **logic.hr_zone_bounds(self._max_hr)}


def dt_from_ms(ms: float) -> str:
    """openGym timestamps are epoch milliseconds."""
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()
