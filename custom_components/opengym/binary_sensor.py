"""Binary sensor platform for the openGym integration."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import logic
from .const import MUSCLES, RECOVERY_DAYS
from .device_info import open_gym_device_info, prune_entities
from .coordinator import OpenGymDataCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up openGym binary sensors."""
    coordinator: OpenGymDataCoordinator = entry.runtime_data.coordinator
    entities: list[BinarySensorEntity] = [
        RestDaySensor(coordinator, entry),
        WorkedOutTodaySensor(coordinator, entry),
        WorkedOutThisWeekSensor(coordinator, entry),
        DayDoneSensor(coordinator, entry),
        NudgePendingSensor(coordinator, entry),
    ]
    # openGym only shares presence with admins: without admin rights the
    # sensor could never be anything but unavailable, so it is not created.
    if coordinator.is_admin:
        entities.append(ActiveWorkoutSensor(coordinator, entry))
    elif coordinator.is_admin is False:
        prune_entities(hass, entry, "binary_sensor", ("active_workout",))
    entities += [
        MuscleRecoverySensor(coordinator, entry, muscle, label)
        for muscle, label in MUSCLES.items()
    ]
    async_add_entities(entities)


class RestDaySensor(CoordinatorEntity[OpenGymDataCoordinator], BinarySensorEntity):
    """On when no session is planned for today."""

    _attr_has_entity_name = True
    _attr_translation_key = "rest_day"
    _attr_name = "Rest day"
    _attr_icon = "mdi:couch"

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_rest_day"
        self._attr_device_info = open_gym_device_info(entry)

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def is_on(self) -> bool | None:
        state = self.coordinator.data
        if state is None:
            return None
        return state.routine_for(date.today()) is None


class ActiveWorkoutSensor(CoordinatorEntity[OpenGymDataCoordinator], BinarySensorEntity):
    """On while a workout is running right now (live presence).

    openGym only exposes live presence through the admin endpoint; without
    admin rights the sensor is not created.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "active_workout"
    _attr_name = "Active workout"
    _attr_icon = "mdi:dumbbell"

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_active_workout"
        self._attr_device_info = open_gym_device_info(entry)

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def is_on(self) -> bool | None:
        if not self.available:
            return None
        return self.coordinator.presence is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        presence = self.coordinator.presence or {}
        state = self.coordinator.data
        attrs: dict[str, Any] = {
            "rest_default": state.rest_seconds() if state else None,
            "rest_timer_ends": (
                self.coordinator.rest_timer_end.isoformat()
                if self.coordinator.rest_timer_end
                else None
            ),
        }
        if not presence:
            return attrs
        progress = logic.presence_progress(presence)
        return {
            **attrs,
            "name": presence.get("name"),
            # kept from 0.9: "x/y" strings
            "exercise": f"{presence.get('exIdx', 0) + 1}/{presence.get('exTotal', 0)}",
            "sets": f"{presence.get('setsDone', 0)}/{presence.get('setsTotal', 0)}",
            **progress,
            "started_at": _iso_ms(presence.get("startedAt")),
            "updated_at": _iso_ms(presence.get("updatedAt")),
        }


class _WorkedOutSensor(CoordinatorEntity[OpenGymDataCoordinator], BinarySensorEntity):
    """Base for "did we train" sensors."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:dumbbell"

    def __init__(self, coordinator, entry, key: str) -> None:
        super().__init__(coordinator)
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = open_gym_device_info(entry)

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success


class WorkedOutTodaySensor(_WorkedOutSensor):
    """On when a workout was logged today."""

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry, "worked_out_today")
        self._attr_name = "Heute trainiert"

    @property
    def is_on(self) -> bool | None:
        state = self.coordinator.data
        if state is None:
            return None
        day = state.last_workout_day()
        return day == date.today() if day else False


class WorkedOutThisWeekSensor(_WorkedOutSensor):
    """On when any workout happened in the last 7 days."""

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry, "worked_out_this_week")
        self._attr_name = "Diese Woche trainiert"

    @property
    def is_on(self) -> bool | None:
        state = self.coordinator.data
        if state is None:
            return None
        day = state.last_workout_day()
        if not day:
            return False
        return (date.today() - day).days < 7


class MuscleRecoverySensor(CoordinatorEntity[OpenGymDataCoordinator], BinarySensorEntity):
    """On while a muscle group is still in its recovery window."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:sleep"

    def __init__(self, coordinator, entry, muscle: str, label: str) -> None:
        super().__init__(coordinator)
        self._muscle = muscle
        self._attr_translation_key = f"muscle_{muscle.replace('-', '_')}_recovering"
        self._attr_name = f"{label} recovering"
        self._attr_unique_id = f"{entry.entry_id}_muscle_{muscle}_recovering"
        self._attr_device_info = open_gym_device_info(entry)

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def is_on(self) -> bool | None:
        state = self.coordinator.data
        if state is None:
            return None
        days = state.muscle_days(date.today()).get(self._muscle)
        if days is None:
            return None
        return 0 <= days <= RECOVERY_DAYS


def _iso_ms(value: Any) -> str | None:
    """openGym presence times are epoch milliseconds."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat()


class _NudgeBase(CoordinatorEntity[OpenGymDataCoordinator], BinarySensorEntity):
    """Today's standing from GET /api/nudge-check (the app's own nudge rule)."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, key: str, name: str) -> None:
        super().__init__(coordinator)
        self._attr_translation_key = key
        self._attr_name = name
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = open_gym_device_info(entry)

    @property
    def available(self) -> bool:
        return (
            self.coordinator.last_update_success
            and bool(self.coordinator.nudge_supported)
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        nudge = self.coordinator.nudge or {}
        return {"date": nudge.get("date"), "rev": nudge.get("rev")}


class DayDoneSensor(_NudgeBase):
    """On once today has a workout or a day note (sick, travel...)."""

    _attr_icon = "mdi:check-decagram"

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry, "day_done", "Today done")

    @property
    def is_on(self) -> bool | None:
        nudge = self.coordinator.nudge
        return bool(nudge.get("done")) if nudge else None


class NudgePendingSensor(_NudgeBase):
    """On while openGym's nudge rule would still remind you today."""

    _attr_icon = "mdi:bell-ring"

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry, "nudge_pending", "Workout reminder due")

    @property
    def is_on(self) -> bool | None:
        nudge = self.coordinator.nudge
        return bool(nudge.get("nudge")) if nudge else None
