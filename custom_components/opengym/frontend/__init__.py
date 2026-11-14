"""Serve the bundled openGym Lovelace card and register it as a resource.

The card and the body geometry ship inside the integration, so they always
stay in sync with whatever version HACS just installed. Registration follows
the embedded-card pattern: static path via `http`, resource via Lovelace's
storage-mode collection (YAML-mode users add the URL manually).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

# StaticPathConfig exists since HA 2024.7 (hacs.json requires 2024.11).
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_call_later

from ..const import JSMODULES, URL_BASE

_LOGGER = logging.getLogger(__name__)

FRONTEND_DIR = Path(__file__).parent

# hass.data key of Lovelace's LovelaceData (HassKey "lovelace" in current HA).
LOVELACE_DATA_KEY = "lovelace"
# Give up after this many 30 s retries (YAML-mode dashboards never get a
# writable resource collection, so retrying forever only spams the loop).
MAX_ATTEMPTS = 20


def _resources(hass: HomeAssistant) -> Any | None:
    """The Lovelace resource collection (storage mode), or None."""
    data = hass.data.get(LOVELACE_DATA_KEY)
    if data is None:
        return None
    collection = getattr(data, "resources", None)
    # YAML collections are read-only for us; nothing to register there.
    if collection is None or not hasattr(collection, "async_create_item"):
        return None
    return collection


async def _register_path(hass: HomeAssistant) -> None:
    try:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(URL_BASE, FRONTEND_DIR, False)]
        )
    except RuntimeError:
        _LOGGER.debug("openGym: static path already registered")


async def _register_modules(hass: HomeAssistant, resources: Any) -> None:
    await resources.async_get_info()  # ensure loaded from storage
    for module in JSMODULES:
        url = f"{URL_BASE}/{module['filename']}"
        wanted = f"{url}?v={module['version']}"
        existing = next(
            (
                item
                for item in resources.async_items()
                if str(item.get("url", "")).split("?")[0] == url
            ),
            None,
        )
        if existing is None:
            await resources.async_create_item({"res_type": "module", "url": wanted})
            _LOGGER.info("openGym: registered card resource %s", wanted)
        elif existing.get("url") != wanted:
            await resources.async_update_item(existing["id"], {"url": wanted})
            _LOGGER.info("openGym: updated card resource to %s", wanted)


def async_schedule_frontend(hass: HomeAssistant) -> None:
    """Serve /opengym/* now, add the resource as soon as Lovelace is up."""

    attempts = 0
    path_done = False

    async def _attempt(_now: Any) -> None:
        nonlocal attempts, path_done
        if not path_done:
            await _register_path(hass)
            path_done = True
        resources = _resources(hass)
        if resources is None:
            attempts += 1
            if attempts >= MAX_ATTEMPTS:
                _LOGGER.info(
                    "openGym: no writable Lovelace resource collection (YAML mode?); "
                    "add %s/opengym-muscle-card.js as a module resource manually",
                    URL_BASE,
                )
                return
            _LOGGER.debug("openGym: Lovelace not ready, retrying resource registration")
            async_call_later(hass, 30, _attempt)
            return
        try:
            await _register_modules(hass, resources)
        except Exception:  # noqa: BLE001 — never break setup over UI wiring
            _LOGGER.exception("openGym: could not register the muscle card resource")

    async_call_later(hass, 1, _attempt)
