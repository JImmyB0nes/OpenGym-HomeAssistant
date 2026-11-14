"""WebSocket commands for the openGym integration.

The bundled muscle card uses these to fetch per-muscle detail data (which is
too fine-grained for sensor attributes) and to check that the served card
version matches the backend — the version check surfaces stale browser caches
after a HACS update instead of silently running an old card.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN, INTEGRATION_VERSION, MAP_SLUGS

_LOGGER = logging.getLogger(__name__)


@callback
def async_setup_ws(hass: HomeAssistant) -> None:
    """Register the openGym WebSocket commands (idempotent)."""
    if any(
        key == f"{DOMAIN}_detail"
        for key in getattr(hass, "_opengym_ws_registered", set()) or set()
    ):
        return
    websocket_api.async_register_command(hass, ws_detail)
    websocket_api.async_register_command(hass, ws_version)
    hass.data.setdefault("_opengym_ws_registered", set()).add(f"{DOMAIN}_detail")
    hass.data["_opengym_ws_registered"].add(f"{DOMAIN}_version")


@websocket_api.websocket_command(
    {
        vol.Required("type"): "opengym:detail",
        vol.Required("muscle"): str,
        vol.Optional("entry_id"): str,
        vol.Optional("entity_id"): str,
    }
)
@callback
def ws_detail(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return the muscle detail for one muscle.

    With several openGym profiles the card passes `entry_id` (from the
    sensor's attributes) or its `entity_id`; without either the first
    entry answers, as before.
    """
    from .coordinator import OpenGymDataCoordinator  # local import: avoid cycles

    entry = _resolve_entry(hass, msg.get("entry_id"), msg.get("entity_id"))
    if entry is None or getattr(entry, "runtime_data", None) is None:
        connection.send_error(msg["id"], websocket_api.ERR_NOT_FOUND, "no openGym entry")
        return
    coordinator: OpenGymDataCoordinator | None = getattr(
        entry.runtime_data, "coordinator", None
    )
    state = coordinator.data if coordinator else None
    if state is None:
        connection.send_error(msg["id"], websocket_api.ERR_NOT_READY, "openGym data not ready")
        return
    muscle = msg.get("muscle")
    if muscle not in MAP_SLUGS:
        connection.send_error(msg["id"], websocket_api.ERR_INVALID_FORMAT, "unknown muscle")
        return
    connection.send_result(msg["id"], state.muscle_detail(muscle, date.today()))


def _resolve_entry(hass: HomeAssistant, entry_id: str | None, entity_id: str | None):
    """Config entry by id, else by the entity it owns, else the first loaded one."""
    if not entry_id and entity_id:
        from homeassistant.helpers import entity_registry as er

        reg_entry = er.async_get(hass).async_get(entity_id)
        entry_id = reg_entry.config_entry_id if reg_entry else None
    if entry_id:
        entry = hass.config_entries.async_get_entry(entry_id)
        return entry if entry is not None and entry.domain == DOMAIN else None
    return next(
        (
            e
            for e in hass.config_entries.async_entries(DOMAIN)
            if getattr(e, "runtime_data", None) is not None
        ),
        None,
    )


@websocket_api.websocket_command({"type": "opengym:version"})
@callback
def ws_version(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Report the installed integration version (card cache check)."""
    connection.send_result(msg["id"], {"version": INTEGRATION_VERSION})
