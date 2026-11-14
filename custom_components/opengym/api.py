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

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class OpenGymConflictError(OpenGymError):
    """PUT /api/data was refused with 409: another client wrote first.

    Carries the server's current document and revision so the caller can
    re-apply its change and retry (openapi: putData 409).
    """

    def __init__(self, rev: int, state: dict[str, Any] | None) -> None:
        super().__init__(f"revision conflict (server rev {rev})")
        self.rev = rev
        self.state = state


class OpenGymFeatureOffError(OpenGymError):
    """The instance does not offer this feature (Coach 503 `off`, integrations 404)."""


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
        params: dict[str, str] | None = None,
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
                params=params,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 401:
                    raise OpenGymUnauthorizedError("not signed in")
                if resp.status == 409 and method == "PUT" and path == "/api/data":
                    try:
                        body = await resp.json(content_type=None)
                    except ValueError:
                        body = {}
                    raise OpenGymConflictError(
                        int((body or {}).get("rev") or 0), (body or {}).get("state")
                    )
                if resp.status >= 400:
                    body = await resp.text()
                    raise OpenGymConnectionError(
                        f"{method} {path} -> {resp.status}: {body[:200]}",
                        status=resp.status,
                    )
                if resp.content_type and "json" in resp.content_type:
                    return await resp.json()
                return {}
        except (aiohttp.ClientError, TimeoutError) as err:
            # aiohttp raises a bare TimeoutError on ClientTimeout(total=...)
            raise OpenGymConnectionError(
                f"{method} {path}: {err!r}"
            ) from err
        except ValueError as err:  # malformed JSON / invalid URL
            raise OpenGymConnectionError(f"{method} {path}: {err}") from err

    async def _optional(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        """A request to a feature the instance may not offer.

        404 (route unknown / integrations switched off) and 503 (Coach not set
        up) become OpenGymFeatureOffError, so callers can hide the feature
        without logging an error.
        """
        try:
            return await self._request(method, path, **kwargs)
        except OpenGymConnectionError as err:
            if err.status in (404, 503):
                raise OpenGymFeatureOffError(str(err)) from err
            raise

    # --- bootstrap / auth -------------------------------------------------

    async def check_connection(self) -> None:
        """Public endpoint, no auth needed. Raises on unreachable host.

        Also raises when the answer is not openGym's JSON (e.g. an HTML page
        from a reverse proxy or the wrong port), so the user gets
        "cannot connect" right away instead of a confusing pairing error.
        """
        data = await self._request("GET", "/api/config", auth=False)
        if not isinstance(data, dict) or "invite_only" not in data:
            raise OpenGymConnectionError(
                "GET /api/config did not return openGym's JSON config"
            )

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
            if err.status == 403:
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

    async def get_rev(self) -> int:
        """`GET /api/data/rev`: the document revision without the document."""
        data = await self._optional("GET", "/api/data/rev")
        return int(data.get("rev") or 0)

    async def nudge_check(self, day: str) -> dict[str, Any]:
        """`GET /api/nudge-check?date=YYYY-MM-DD` -> {date, done, nudge, rev}."""
        return await self._optional("GET", "/api/nudge-check", params={"date": day})

    # --- push / rest timer ------------------------------------------------

    async def start_rest_timer(self, seconds: float, device_id: str | None = None) -> None:
        """`POST /api/push/rest-timer` {seconds, deviceId?} (1..3600 s)."""
        payload: dict[str, Any] = {"seconds": seconds}
        if device_id:
            payload["deviceId"] = device_id
        await self._request("POST", "/api/push/rest-timer", payload=payload)

    async def cancel_rest_timer(self, device_id: str | None = None) -> None:
        """`POST /api/push/rest-timer/cancel` {deviceId?} (idempotent)."""
        payload: dict[str, Any] = {"deviceId": device_id} if device_id else {}
        await self._request("POST", "/api/push/rest-timer/cancel", payload=payload)

    # --- coach ------------------------------------------------------------

    async def coach_status(self) -> dict[str, Any]:
        """`GET /api/coach/status` (CoachStatus); FeatureOff when the Coach is off."""
        return await self._optional("GET", "/api/coach/status")

    async def coach_review(self, note: str | None = None, lang: str | None = None) -> dict[str, Any]:
        """`POST /api/coach/review` {note?, lang?} -> 202 job queued."""
        payload: dict[str, Any] = {}
        if note:
            payload["note"] = note
        if lang:
            payload["lang"] = lang
        return await self._optional("POST", "/api/coach/review", payload=payload)

    async def coach_resolve(
        self,
        accepted: list[str] | None = None,
        rejected: list[str] | None = None,
        dismissed: bool = False,
    ) -> None:
        """`POST /api/coach/pending/resolve` {accepted?, rejected?, dismissed?}."""
        payload: dict[str, Any] = {}
        if accepted is not None:
            payload["accepted"] = accepted
        if rejected is not None:
            payload["rejected"] = rejected
        if dismissed:
            payload["dismissed"] = True
        await self._optional("POST", "/api/coach/pending/resolve", payload=payload)

    # --- watch ------------------------------------------------------------

    async def watch_links(self) -> list[dict[str, Any]]:
        """`GET /api/watch/links` -> the paired watches {id, name, created, seen}."""
        data = await self._optional("GET", "/api/watch/links")
        return list(data.get("links") or [])

    async def watch_events(self) -> dict[str, Any]:
        """`GET /api/watch/events` -> {events, paired, seen}. Read-only peek, never acked."""
        return await self._optional("GET", "/api/watch/events")

    # --- integrations -----------------------------------------------------

    async def list_integrations(self) -> dict[str, Any]:
        return await self._request("GET", "/api/integrations")

    async def list_integrations_optional(self) -> dict[str, Any]:
        """Like list_integrations, but FeatureOff when integrations are switched off."""
        return await self._optional("GET", "/api/integrations")

    async def integration_log(self, connection_id: str) -> dict[str, Any]:
        """`GET /api/integrations/log?id=` -> {log[], queued, failed}."""
        return await self._optional(
            "GET", "/api/integrations/log", params={"id": connection_id}
        )

    async def retry_integration(self, connection_id: str) -> dict[str, Any]:
        """`POST /api/integrations/retry` {id} -> {requeued, connection}."""
        return await self._optional(
            "POST", "/api/integrations/retry", payload={"id": connection_id}
        )

    async def test_event(self, connection_id: str, event_type: str) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/api/integrations/test",
            payload={"id": connection_id, "type": event_type},
        )
