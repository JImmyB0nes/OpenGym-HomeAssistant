"""Select platform: which routine is planned for today.

Options are your openGym routines plus "Rest day". Picking one writes a
day override into openGym's plan (the same `dayPlan` the app writes when you
swap a day); picking what the weekly plan has anyway drops the override.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import logic
from .api import OpenGymError
from .const import DOMAIN
from .coordinator import OpenGymDataCoordinator
from .device_info import open_gym_device_info, suggested_entity_id

REST_OPTION = "rest"


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: OpenGymDataCoordinator = entry.runtime_data.coordinator
    async_add_entities([TodayRoutineSelect(coordinator, entry)])


def routine_options(routines: dict[str, dict[str, Any]]) -> dict[str, str | None]:
    """Option label -> routine id (None = rest). Duplicate names get a suffix."""
    out: dict[str, str | None] = {}
    for rid, routine in routines.items():
        label = str(routine.get("name") or rid).strip() or str(rid)
        if label == REST_OPTION or label in out:
            n = 2
            while f"{label} ({n})" in out:
                n += 1
            label = f"{label} ({n})"
        out[label] = str(rid)
    out[REST_OPTION] = None
    return out


class TodayRoutineSelect(CoordinatorEntity[OpenGymDataCoordinator], SelectEntity):
    """Today's routine (or rest), written back to openGym."""

    _attr_has_entity_name = True
    _attr_translation_key = "today_routine"

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_today_routine"
        self._attr_device_info = open_gym_device_info(entry)
        self.entity_id = suggested_entity_id(entry, "select", self._attr_translation_key)

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self.coordinator.data is not None

    def _options(self) -> dict[str, str | None]:
        state = self.coordinator.data
        return routine_options(state.routines if state else {})

    @property
    def options(self) -> list[str]:
        return list(self._options())

    @property
    def current_option(self) -> str | None:
        state = self.coordinator.data
        if state is None:
            return None
        routine = state.routine_for(dt_util.now().date())
        if routine is None:
            return REST_OPTION
        rid = str(routine.get("id"))
        return next((label for label, value in self._options().items() if value == rid), None)

    @property
    def icon(self) -> str:
        state = self.coordinator.data
        routine = state.routine_for(dt_util.now().date()) if state else None
        return logic.routine_icon(routine.get("emoji")) if routine else "mdi:sofa-outline"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        state = self.coordinator.data
        today = dt_util.now().date()
        planned = logic.weekly_routine_id(state.raw, today) if state else None
        return {
            "date": today.isoformat(),
            "overridden": bool(state and today.isoformat() in state.day_plan),
            "weekly_plan": (state.routines.get(planned) or {}).get("name") if state and planned else None,
        }

    async def async_select_option(self, option: str) -> None:
        options = self._options()
        if option not in options:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="plan_unknown_routine",
                translation_placeholders={"routine": option},
            )
        routine_id = options[option]
        today = dt_util.now().date()
        try:
            await self._entry.runtime_data.async_mutate_state(
                lambda doc: logic.set_day_routine(doc, today, routine_id)
            )
        except logic.PlanEditError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key=f"plan_{err.key}",
                translation_placeholders=err.placeholders,
            ) from err
        except OpenGymError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="write_failed",
                translation_placeholders={"error": str(err)[:200]},
            ) from err
