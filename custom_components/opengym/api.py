"""HTTP client for the openGym REST API (api/openapi.yaml of DuarteSantos8/openGym)."""

from __future__ import annotations

from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession


class OpenGymError(Exception):
    """Base error."""


class OpenGymUnauthorizedError(OpenGymError):
    """Session invalid or expired."""


class OpenGymConnectionError(OpenGymError):
    """Server unreachable or bad response."""


class OpenGymApiClient:
    """Talks to one openGym instance, authenticated with a Bearer token."""

    def __init__(
        self,
        hass: HomeAssistant,
        url: str,
        token: str | None = None,
    ) -> None:
        self._session = async_get_clientsession(hass)
        self._url = url.rstrip("/")
        self.token = token

    async def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        auth: bool = True,
    ) -> dict[str, Any]:
        headers: dict[str, str] = {}
        if auth and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            async with self._session.request(
                method,
                f"{self._url}{path}",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 401:
                    raise OpenGymUnauthorizedError("not signed in")
                if resp.status >= 400:
                    body = await resp.text()
                    raise OpenGymConnectionError(
                        f"{method} {path} -> {resp.status}: {body[:200]}"
                    )
                if resp.content_type and "json" in resp.content_type:
                    return await resp.json()
                return {}
        except aiohttp.ClientError as err:
            raise OpenGymConnectionError(str(err)) from err

    # --- bootstrap / auth -------------------------------------------------

    async def check_connection(self) -> None:
        """Public endpoint, no auth needed. Raises on unreachable host."""
        await self._request("GET", "/api/config", auth=False)

    async def redeem_pairing_code(self, code: str) -> str:
        """Turn an 8-character pairing code into a Bearer token."""
        data = await self._request(
            "POST", "/api/pair/redeem", payload={"code": code}, auth=False
        )
        token = data.get("token")
        if not token:
            raise OpenGymError("pair/redeem returned no token")
        self.token = token
        return token

    async def me(self) -> dict[str, Any]:
        """Who am I; may hand back a renewed token for Bearer sessions."""
        data = await self._request("GET", "/api/me")
        if token := data.get("token"):
            self.token = token
        return data

    async def admin_users(self) -> list[dict[str, Any]] | None:
        """Admin rows with live presence; None when not an admin."""
        try:
            data = await self._request("GET", "/api/admin/users")
        except OpenGymConnectionError as err:
            if "403" in str(err):
                return None
            raise
        return data.get("users") or []

    async def connect_webhook(
        self, url: str, label: str, events: list[str]
    ) -> dict[str, Any]:
        """Create a webhook connection; the answer reveals the secret once."""
        return await self._request(
            "POST",
            "/api/integrations/connect",
            payload={
                "provider": "webhook",
                "url": url,
                "label": label,
                "events": events,
            },
        )

    # --- state ------------------------------------------------------------

    async def get_state(self) -> tuple[dict[str, Any] | None, int]:
        """The whole app state and its server revision."""
        data = await self._request("GET", "/api/data")
        return data.get("state"), int(data.get("rev", 0))

    async def put_state(self, state: dict[str, Any], base_rev: int) -> dict[str, Any]:
        """Conditional write; 409 on revision mismatch."""
        return await self._request(
            "PUT", "/api/data", payload={"state": state, "baseRev": base_rev}
        )

    # --- integrations -----------------------------------------------------

    async def list_integrations(self) -> dict[str, Any]:
        return await self._request("GET", "/api/integrations")

    async def test_event(self, connection_id: str, event_type: str) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/api/integrations/test",
            payload={"id": connection_id, "type": event_type},
        )
