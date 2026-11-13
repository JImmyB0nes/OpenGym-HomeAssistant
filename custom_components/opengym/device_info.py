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
