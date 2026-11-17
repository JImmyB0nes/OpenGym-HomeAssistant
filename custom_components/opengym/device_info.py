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


def _english_names() -> dict[str, dict[str, str]]:
    """platform -> translation_key -> English entity name (translations/en.json)."""
    import json
    from pathlib import Path

    try:
        data = json.loads((Path(__file__).parent / "translations" / "en.json").read_text("utf-8"))
    except (OSError, ValueError):  # pragma: no cover
        return {}
    return {
        platform: {key: str(v.get("name") or key) for key, v in keys.items() if isinstance(v, dict)}
        for platform, keys in (data.get("entity") or {}).items()
    }


_EN_NAMES = _english_names()


def suggested_entity_id(entry: ConfigEntry, platform: str, key: str | None) -> str:
    """English entity id for a new entity, whatever language HA runs in.

    Names are translated, and Home Assistant would build ids of new entities
    from the translated name in many languages (German included). The ids
    stay `<device>_<english name>` as before 0.11, so README, cards and
    automations keep working; existing entities keep their registry ids.
    """
    from homeassistant.util import slugify

    name = _EN_NAMES.get(platform, {}).get(key or "", key or "")
    device = entry.title or "openGym"
    return f"{platform}.{slugify(device + ' ' + name)}"
