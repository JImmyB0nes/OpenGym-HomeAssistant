"""Button platform: accept or reject the openGym Coach's waiting proposal.

`POST /api/coach/pending/resolve` only records the decision — applying a
proposal is the client's job (openapi: coachResolve). Home Assistant applies
the scalar changes itself (sets, reps, rep range, seconds, increment, routine
name) with a conditional PUT; proposals with structural changes or a whole
new plan (`bundle`) must be accepted in the app; pressing "Accept" then
says so. Without a waiting proposal a press reports "nothing pending". Both buttons only exist when the instance runs the Coach.
"""

from __future__ import annotations

import time
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import logic
from .api import OpenGymError
from .const import DOMAIN
from .coordinator import OpenGymDataCoordinator
from .device_info import open_gym_device_info, prune_entities


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: OpenGymDataCoordinator = entry.runtime_data.coordinator
    if not coordinator.coach_enabled:
        if coordinator.coach_enabled is False:
            prune_entities(hass, entry, "button", ("coach_accept", "coach_reject"))
        return  # Coach off on this instance: no buttons, no errors
    async_add_entities([
        CoachAcceptButton(coordinator, entry),
        CoachRejectButton(coordinator, entry),
    ])


class _CoachButton(CoordinatorEntity[OpenGymDataCoordinator], ButtonEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, key: str, name: str) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_translation_key = key
        self._attr_name = name
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = open_gym_device_info(entry)

    @property
    def _pending(self) -> dict[str, Any] | None:
        return (self.coordinator.coach or {}).get("pending") or None

    @property
    def available(self) -> bool:
        return (
            self.coordinator.last_update_success
            and bool(self.coordinator.coach_enabled)
        )

    def _require_pending(self) -> dict[str, Any]:
        pending = self._pending
        if not pending:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="coach_nothing_pending")
        return pending

    async def _resolve(self, **kwargs: Any) -> None:
        try:
            await self.coordinator.client.coach_resolve(**kwargs)
        except OpenGymError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="coach_failed",
                translation_placeholders={"error": str(err)[:200]},
            ) from err
        await self.coordinator.async_refresh()


class CoachAcceptButton(_CoachButton):
    _attr_icon = "mdi:check-circle"

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry, "coach_accept", "Accept coach proposal")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"mode": logic.coach_accept_mode(self._pending)}

    async def async_press(self) -> None:
        pending = self._require_pending()
        mode = logic.coach_accept_mode(pending)
        if mode is None:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="coach_use_app")
        if mode == "ack":
            await self._resolve(accepted=[], rejected=[], dismissed=False)
            return
        result: dict[str, list[str]] = {"accepted": [], "stale": []}

        def _apply(state: dict[str, Any]) -> dict[str, Any]:
            result["accepted"], result["stale"] = logic.apply_coach_changes(
                state, pending, int(time.time() * 1000)
            )
            return state

        runtime = self._entry.runtime_data
        if pending.get("changes"):
            try:
                await runtime.async_mutate_state(_apply)
            except OpenGymError as err:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="write_failed",
                    translation_placeholders={"error": str(err)[:200]},
                ) from err
        await self._resolve(accepted=result["accepted"], rejected=result["stale"])


class CoachRejectButton(_CoachButton):
    _attr_icon = "mdi:close-circle"

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry, "coach_reject", "Reject coach proposal")

    async def async_press(self) -> None:
        pending = self._require_pending()
        if pending.get("kind") == "review":
            ids = [str(c.get("id")) for c in pending.get("changes") or [] if isinstance(c, dict)]
            await self._resolve(accepted=[], rejected=ids)
        else:
            # a plan (create) or a debrief: dismiss it as a whole
            await self._resolve(dismissed=True)
