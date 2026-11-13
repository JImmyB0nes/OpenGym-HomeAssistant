"""Device triggers for the openGym integration.

Lets automations trigger on openGym events from the UI ("When the openGym
device finishes a workout…") instead of raw event triggers.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.device_automation import (
    DeviceAutomationType,
    TriggerDeviceAutomationSchema,
)
from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_PLATFORM, CONF_TYPE
from homeassistant.core import CALLBACK_TYPE, HassJob, HomeAssistant, callback
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, EVENT_TYPES

# trigger type -> HA event name
TRIGGER_TYPES: dict[str, str] = {
    "workout_finished": "opengym_workout_finished",
    "personal_record": "opengym_personal_record",
    "weighin_logged": "opengym_weighin_logged",
}

TRIGGER_SCHEMA = TriggerDeviceAutomationSchema.extend(
    {
        vol.Required(CONF_TYPE): vol.In(list(TRIGGER_TYPES)),
        vol.Optional("test"): cv.boolean,
    }
)


def _entry_from_device(hass: HomeAssistant, device_id: str):
    """Config entry owning this device, or None."""
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        return None
    for domain, identifier in device.identifiers:
        if domain == DOMAIN:
            for entry in hass.config_entries.async_entries(DOMAIN):
                if entry.entry_id == identifier:
                    return entry
    return None


async def async_get_triggers(
    hass: HomeAssistant, device_id: str
) -> list[dict[str, Any]]:
    """List the triggers this openGym device offers."""
    if _entry_from_device(hass, device_id) is None:
        return []
    return [
        {
            CONF_PLATFORM: DeviceAutomationType.TRIGGER,
            CONF_DOMAIN: DOMAIN,
            CONF_DEVICE_ID: device_id,
            CONF_TYPE: trigger_type,
        }
        for trigger_type in TRIGGER_TYPES
    ]


async def async_get_trigger_capabilities(
    hass: HomeAssistant, config: ConfigType
) -> dict[str, vol.Schema]:
    """Offer an optional "only real deliveries" filter in the UI."""
    return {
        "extra_fields": vol.Schema(
            {vol.Optional("test", default=False): cv.boolean}
        )
    }


async def async_attach_trigger(
    hass: HomeAssistant,
    config: ConfigType,
    action: TriggerActionType,
    trigger_info: TriggerInfo,
) -> CALLBACK_TYPE:
    """Listen for one openGym event type."""
    event_name = TRIGGER_TYPES[config[CONF_TYPE]]
    entry = _entry_from_device(hass, config[CONF_DEVICE_ID])
    only_real = config.get("test") is False
    job = HassJob(action)

    @callback
    def _handle(event) -> None:
        if entry is not None and event.data.get("entry_id") != entry.entry_id:
            return
        if only_real and event.data.get("test"):
            return
        hass.async_run_hass_job(
            job,
            {
                "trigger": {
                    "platform": "device",
                    "domain": DOMAIN,
                    "device_id": config[CONF_DEVICE_ID],
                    "type": config[CONF_TYPE],
                    "description": event_name,
                    "message": event.data,
                }
            },
            event.context,
        )

    return hass.bus.async_listen(event_name, _handle)
