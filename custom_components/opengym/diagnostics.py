"""Diagnostics for the openGym integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_SECRET, CONF_TOKEN, CONF_URL, CONF_WEBHOOK_ID, DOMAIN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics with secrets removed."""
    runtime = getattr(entry, "runtime_data", None)
    coordinator = getattr(runtime, "coordinator", None) if runtime else None
    state = coordinator.data if coordinator else None

    data = dict(entry.data)
    for key in (CONF_TOKEN, CONF_SECRET):
        if data.get(key):
            data[key] = "**redacted**"

    diag: dict[str, Any] = {
        "config_entry": {
            "url": data.get(CONF_URL),
            "webhook_id": data.get(CONF_WEBHOOK_ID),
            "title": entry.title,
            "options": dict(entry.options),
            "data": data,
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success
            if coordinator
            else None,
            "last_update_time": str(coordinator.last_update_time)
            if coordinator and coordinator.last_update_time
            else None,
            "consecutive_failures": getattr(coordinator, "consecutive_failures", None),
            "is_admin": getattr(coordinator, "is_admin", None),
            "has_presence": getattr(coordinator, "presence", None) is not None,
        },
    }

    if state is not None:
        diag["state"] = {
            "unit": state.unit,
            "workouts": len(state.workouts),
            "weigh_ins": len(state.bodyweight),
            "routines": len(state.routines),
            "custom_exercises": state.custom_ex_count(),
            "last_workout": state.workouts[-1].get("d") if state.workouts else None,
        }

    return diag
