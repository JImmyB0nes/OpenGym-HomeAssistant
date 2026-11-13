"""Coordinator holding the latest openGym events for sensors."""

from __future__ import annotations

from typing import Any, Callable

from homeassistant.core import HomeAssistant, callback

from .const import EVENT_TYPES


class OpenGymCoordinator:
    """Track the most recent event of each openGym event type."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.listeners: set[Callable[[], None]] = set()
        # event_type -> last event dict
        self.last: dict[str, dict[str, Any]] = {}

    def update(self, event_type: str, event: dict[str, Any]) -> None:
        """Remember the newest event of its kind."""
        self.last[event_type] = event

    @callback
    def async_get_last(self, event_type: str) -> dict[str, Any] | None:
        """Return the last event of a type, or None."""
        return self.last.get(event_type)

    @callback
    def async_listen(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Register a listener notified when any event arrives."""
        self.listeners.add(listener)

        @callback
        def _remove() -> None:
            self.listeners.discard(listener)

        return _remove
