"""Number platform: the rest-timer length used from Home Assistant.

`opengym.start_rest_timer` without `seconds`, the next-workout card's button
and Assist ("start the rest timer") use this value. It lives in Home
Assistant (restored across restarts); until you change it, it follows
openGym's own rest setting (`restSec`, else 90 s).
"""

from __future__ import annotations

from homeassistant.components.number import NumberMode, RestoreNumber
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import OpenGymDataCoordinator
from .device_info import open_gym_device_info, suggested_entity_id

DEFAULT_REST = 90


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: OpenGymDataCoordinator = entry.runtime_data.coordinator
    async_add_entities([RestDurationNumber(coordinator, entry)])


class RestDurationNumber(CoordinatorEntity[OpenGymDataCoordinator], RestoreNumber):
    """Rest-timer length in seconds (15 s steps, 15 s .. 10 min)."""

    _attr_has_entity_name = True
    _attr_translation_key = "rest_duration"
    _attr_icon = "mdi:timer-cog-outline"
    _attr_native_min_value = 15
    _attr_native_max_value = 600
    _attr_native_step = 15
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_mode = NumberMode.SLIDER
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_rest_duration"
        self._attr_device_info = open_gym_device_info(entry)
        self.entity_id = suggested_entity_id(entry, "number", self._attr_translation_key)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last is not None and last.native_value:
            self.coordinator.rest_override = int(last.native_value)

    @property
    def available(self) -> bool:
        return True  # a local setting; works while openGym is unreachable

    @property
    def native_value(self) -> float:
        value = self.coordinator.rest_default_seconds()
        return float(value) if value else float(DEFAULT_REST)

    async def async_set_native_value(self, value: float) -> None:
        self.coordinator.rest_override = int(value)
        self.coordinator.async_update_listeners()
