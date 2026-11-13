"""Binary sensor platform for the openGym integration."""

from __future__ import annotations

from datetime import date

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MUSCLES, RECOVERY_DAYS
from .device_info import open_gym_device_info
from .coordinator import OpenGymDataCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up openGym binary sensors."""
    coordinator: OpenGymDataCoordinator = entry.runtime_data.coordinator
    entities: list[BinarySensorEntity] = [RestDaySensor(coordinator, entry)]
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
