"""Shared device info for openGym entities."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo

from .const import CONF_URL, DOMAIN


def open_gym_device_info(entry: ConfigEntry) -> DeviceInfo:
    """One openGym device per config entry."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title or "openGym",
        manufacturer="openGym",
        model="Self-hosted instance",
        configuration_url=entry.data.get(CONF_URL),
    )


def prune_entities(hass, entry: ConfigEntry, platform: str, keys) -> None:
    """Drop registry entries of optional entities this setup does not create.

    Without this, an entity created once (e.g. before the Coach was switched
    off, or while admin rights were granted) lingers as "unavailable".
    """
    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    for key in keys:
        entity_id = registry.async_get_entity_id(platform, DOMAIN, f"{entry.entry_id}_{key}")
        if entity_id:
            registry.async_remove(entity_id)
