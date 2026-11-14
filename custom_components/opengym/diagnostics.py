"""Diagnostics for the openGym integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .api import OpenGymError
from .const import CONF_SECRET, CONF_TOKEN, CONF_URL, CONF_WEBHOOK_ID


def _mask(value: str | None) -> str | None:
    return f"…{value[-4:]}" if value else value


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
    # the webhook id is the URL's only secret: keep the tail openGym also shows
    data[CONF_WEBHOOK_ID] = _mask(data.get(CONF_WEBHOOK_ID))

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
            "last_exception": repr(coordinator.last_exception)
            if coordinator and coordinator.last_exception
            else None,
            "consecutive_failures": getattr(coordinator, "consecutive_failures", None),
            "is_admin": getattr(coordinator, "is_admin", None),
            "has_presence": getattr(coordinator, "presence", None) is not None,
            "rev": getattr(coordinator, "rev", None),
            "rev_fast_path": getattr(coordinator, "rev_supported", None),
            "full_fetches": getattr(coordinator, "full_fetches", None),
            "rev_skips": getattr(coordinator, "rev_skips", None),
        },
        "features": {
            "nudge_check": getattr(coordinator, "nudge_supported", None),
            "coach": getattr(coordinator, "coach_enabled", None),
            "watch": getattr(coordinator, "watch_supported", None),
            "watches_paired": len(getattr(coordinator, "watch_links", None) or []),
            "integrations": getattr(coordinator, "integrations_enabled", None),
        },
    }

    # (9) our webhook connection(s) in openGym and their delivery log
    if coordinator is not None and getattr(coordinator, "integrations_enabled", None):
        conns = []
        for conn in getattr(coordinator, "connections", None) or []:
            item = {
                k: conn.get(k)
                for k in (
                    "id", "label", "status", "paused", "events", "failures",
                    "queued", "failed", "lastOk", "lastError", "createdAt",
                )
            }
            item["url"] = (conn.get("info") or {}).get("url")  # already masked by openGym
            try:
                log = await coordinator.client.integration_log(str(conn.get("id")))
                item["log"] = (log.get("log") or [])[:50]
            except OpenGymError as err:
                item["log_error"] = str(err)
            conns.append(item)
        diag["integrations"] = conns

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
