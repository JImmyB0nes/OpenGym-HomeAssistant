"""Sensor platform for the openGym integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import OpenGymCoordinator

# sensor key -> (event type, friendly name, icon)
SENSORS: dict[str, tuple[str, str, str]] = {
    "last_workout": ("workout.finished", "Letztes Workout", "mdi:weight-lifter"),
    "last_record": ("workout.pr", "Letzter Rekord", "mdi:trophy"),
    "last_weighin": ("weighin.logged", "Letzte Waegung", "mdi:scale-bathroom"),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up openGym sensors."""
    coordinator: OpenGymCoordinator = entry.runtime_data.coordinator
    async_add_entities(
        OpenGymSensor(coordinator, entry, key, event_type, name, icon)
        for key, (event_type, name, icon) in SENSORS.items()
    )


class OpenGymSensor(CoordinatorEntity[OpenGymCoordinator], SensorEntity):
    """Sensor exposing the most recent event of one openGym event type."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: OpenGymCoordinator,
        entry: ConfigEntry,
        key: str,
        event_type: str,
        name: str,
        icon: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._event_type = event_type
        self._attr_name = name
        self._attr_icon = icon
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="openGym",
            manufacturer="openGym",
            model="Webhook events",
        )

    @property
    def available(self) -> bool:
        """Sensor is available once at least one event of its type arrived."""
        return self.coordinator.async_get_last(self._event_type) is not None

    @property
    def native_value(self) -> str | None:
        """Short human-readable state for the event."""
        event = self.coordinator.async_get_last(self._event_type)
        if not event:
            return None
        data = event.get("data", {})
        if self._event_type == "workout.finished":
            workout = data.get("workout", {})
            name = workout.get("name", "Workout")
            minutes = workout.get("durationMin")
            return f"{name} ({minutes} min)" if minutes else name
        if self._event_type == "workout.pr":
            records = data.get("records", [])
            if records:
                rec = records[0]
                return f"{rec.get('name', '?')} {rec.get('weight', '?')}{data.get('unit', '')} x{rec.get('reps', '?')}"
            return "Personal Record"
        if self._event_type == "weighin.logged":
            weighin = data.get("weighin", {})
            weight = weighin.get("weight")
            unit = weighin.get("unit", "")
            return f"{weight} {unit}".strip() if weight is not None else None
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Full event payload as attributes."""
        event = self.coordinator.async_get_last(self._event_type)
        if not event:
            return {}
        return {
            "event_id": event.get("event_id"),
            "created_at": event.get("created_at"),
            "test": event.get("test"),
            "data": event.get("data", {}),
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()
