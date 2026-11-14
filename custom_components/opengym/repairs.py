"""Repairs: re-queue failed webhook deliveries in openGym."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import data_entry_flow
from homeassistant.components.repairs import ConfirmRepairFlow, RepairsFlow
from homeassistant.core import HomeAssistant

from .api import OpenGymError


class WebhookRetryFlow(RepairsFlow):
    """Confirm, then `POST /api/integrations/retry` for the failing connection."""

    def __init__(self, entry_id: str | None, connection_id: str | None) -> None:
        self._entry_id = entry_id
        self._connection_id = connection_id

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> data_entry_flow.FlowResult:
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> data_entry_flow.FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            entry = self.hass.config_entries.async_get_entry(self._entry_id or "")
            runtime = getattr(entry, "runtime_data", None) if entry else None
            if runtime is None or not self._connection_id:
                return self.async_abort(reason="not_loaded")
            try:
                await runtime.client.retry_integration(self._connection_id)
            except OpenGymError:
                errors["base"] = "retry_failed"
            else:
                await runtime.coordinator.async_refresh()
                return self.async_create_entry(data={})
        return self.async_show_form(
            step_id="confirm", data_schema=vol.Schema({}), errors=errors
        )


async def async_create_fix_flow(
    hass: HomeAssistant, issue_id: str, data: dict[str, Any] | None
) -> RepairsFlow:
    if issue_id.startswith("webhook_delivery_failed") and data:
        return WebhookRetryFlow(data.get("entry_id"), data.get("connection_id"))
    return ConfirmRepairFlow()
