"""Describe openGym events in the Home Assistant logbook.

Every signed webhook delivery (workout finished, new personal record,
weigh-in) shows up as a readable line, e.g. "openGym finished Push
(12,400 kg volume, 18 sets, 54 min)", without any automation.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.core import Event, HomeAssistant, callback

from . import logic
from .const import DOMAIN, EVENT_TYPES

LOGBOOK_ICONS = {
    "workout.finished": "mdi:weight-lifter",
    "workout.pr": "mdi:trophy",
    "weighin.logged": "mdi:scale-bathroom",
}


@callback
def async_describe_events(
    hass: HomeAssistant,
    async_describe_event: Callable[[str, str, Callable[[Event], dict[str, Any]]], None],
) -> None:
    """Register a describer for each openGym bus event."""

    def _entry_title(entry_id: str | None) -> str:
        entry = hass.config_entries.async_get_entry(entry_id) if entry_id else None
        return (entry.title if entry else None) or "openGym"

    for og_type, bus_event in EVENT_TYPES.items():

        @callback
        def _describe(event: Event, og_type: str = og_type) -> dict[str, Any]:
            data = dict(event.data)
            return {
                "name": _entry_title(data.get("entry_id")),
                "message": logic.logbook_message(og_type, data, hass.config.language),
                "icon": LOGBOOK_ICONS.get(og_type, "mdi:dumbbell"),
            }

        async_describe_event(DOMAIN, bus_event, _describe)
