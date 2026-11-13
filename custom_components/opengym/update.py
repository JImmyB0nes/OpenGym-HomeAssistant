"""Update entity: is your openGym instance behind the upstream release?"""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from homeassistant.components.update import UpdateEntity, UpdateEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import OpenGymDataCoordinator
from .device_info import open_gym_device_info

_LOGGER = logging.getLogger(__name__)

RELEASES_URL = "https://api.github.com/repos/DuarteSantos8/openGym/releases/latest"


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the update entity."""
    coordinator: OpenGymDataCoordinator = entry.runtime_data.coordinator
    async_add_entities([OpenGymUpdateEntity(coordinator, entry)])


class OpenGymUpdateEntity(CoordinatorEntity[OpenGymDataCoordinator], UpdateEntity):
    """Compares the instance version with the latest openGym release."""

    _attr_has_entity_name = True
    _attr_translation_key = "instance_update"
    _attr_name = "openGym Instanz"
    _attr_title = "openGym"
    _attr_supported_features = UpdateEntityFeature.RELEASE_NOTES
    _attr_should_poll = True

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_update"
        self._attr_device_info = open_gym_device_info(entry)
        self._session = async_get_clientsession(coordinator.hass)
        self._installed: str | None = None
        self._latest: str | None = None
        self._release_notes_body: str | None = None

    async def async_update(self) -> None:
        """Read the instance version and the latest upstream release."""
        # Instance version: openGym reports it nowhere in the API, so ask its
        # web UI (the served HTML carries the build string); fall back silently.
        base = self.coordinator.client._url
        try:
            async with self._session.get(
                f"{base}/api/health", timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    health = await resp.json()
                    version = health.get("version")
                    if version:
                        self._installed = str(version)
        except (aiohttp.ClientError, TimeoutError):
            pass

        try:
            async with self._session.get(
                RELEASES_URL,
                headers={"Accept": "application/vnd.github+json"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 200:
                    latest = await resp.json()
                    self._latest = latest.get("tag_name")
                    self._release_notes_body = latest.get("body")
        except (aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.debug("openGym: upstream release check failed (%s)", err)

    @property
    def installed_version(self) -> str | None:
        return self._installed

    @property
    def latest_version(self) -> str | None:
        return self._latest

    @property
    def release_summary(self) -> str | None:
        if self._release_notes_body:
            return self._release_notes_body[:256]
        return None

    async def async_release_notes(self) -> str | None:
        return self._release_notes_body
