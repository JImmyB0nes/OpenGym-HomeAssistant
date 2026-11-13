"""Device actions for the openGym integration.

Exposes the `log_weighin` service as a device action so automations can use
it from the UI without referencing services directly.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.device_automation import DeviceAutomationType
from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_PLATFORM, CONF_TYPE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.typing import ConfigType, TemplateVarsType

from .const import DOMAIN, SERVICE_LOG_WEIGHIN

ACTION_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PLATFORM): DeviceAutomationType.ACTION,
        vol.Required(CONF_DOMAIN): DOMAIN,
        vol.Required(CONF_DEVICE_ID): str,
        vol.Required(CONF_TYPE): vol.In([SERVICE_LOG_WEIGHIN]),
    }
)


def _entry_from_device(hass: HomeAssistant, device_id: str):
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        return None
    for domain, identifier in device.identifiers:
        if domain == DOMAIN:
            for entry in hass.config_entries.async_entries(DOMAIN):
                if entry.entry_id == identifier:
                    return entry
    return None


async def async_get_actions(
    hass: HomeAssistant, device_id: str
) -> list[dict[str, Any]]:
    if _entry_from_device(hass, device_id) is None:
        return []
    return [
        {
            CONF_PLATFORM: DeviceAutomationType.ACTION,
            CONF_DOMAIN: DOMAIN,
            CONF_DEVICE_ID: device_id,
            CONF_TYPE: SERVICE_LOG_WEIGHIN,
        }
    ]


async def async_get_action_capabilities(
    hass: HomeAssistant, config: ConfigType
) -> dict[str, vol.Schema]:
    return {
        "fields": vol.Schema(
            {
                vol.Required("weight"): vol.Coerce(float),
                vol.Optional("unit", default="kg"): vol.In(["kg", "lb"]),
                vol.Optional("date"): cv.date,
            }
        )
    }


async def async_call_action_from_config(
    hass: HomeAssistant,
    config: ConfigType,
    variables: TemplateVarsType,
    context: Any,
) -> None:
    entry = _entry_from_device(hass, config[CONF_DEVICE_ID])
    if entry is None:
        raise ValueError("openGym device not found")
    await hass.services.async_call(
        DOMAIN,
        SERVICE_LOG_WEIGHIN,
        {
            "weight": config["weight"],
            "unit": config.get("unit", "kg"),
            "date": config.get("date"),
            "entry_id": entry.entry_id,
        },
        blocking=True,
        context=context,
    )
