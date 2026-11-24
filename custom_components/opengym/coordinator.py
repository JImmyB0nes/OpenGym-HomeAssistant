"""Polling coordinator for openGym.

Polls `GET /api/data` (the whole app state, parsed into `OpenGymState`) plus
the small live endpoints (presence, nudge-check, Coach, watch, integrations).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from . import logic
from .api import (
    OpenGymApiClient,
    OpenGymError,
    OpenGymFeatureOffError,
    OpenGymUnauthorizedError,
)
from .const import (
    COACH_POLL_SECONDS,
    CONF_COACH_AUTO_DEBRIEF,
    CONF_IMPORT_STATISTICS,
    DEFAULT_COACH_AUTO_DEBRIEF,
    DEFAULT_IMPORT_STATISTICS,
    DOMAIN,
    EVENT_COACH_ANSWER,
    EVENT_COACH_DEBRIEF,
    SCAN_INTERVAL,
)
from .statistics import async_import_statistics
from .state import _MUSCLE_MAP, OpenGymState, _day  # noqa: F401  (re-exported)

__all__ = ["OpenGymDataCoordinator", "OpenGymState"]

_LOGGER = logging.getLogger(__name__)


class OpenGymDataCoordinator(DataUpdateCoordinator[OpenGymState]):
    """Polls openGym's state document, plus the small live endpoints.

    Two cadences:
    - the regular refresh (poll interval, default 15 min) — with a fast
      path: `GET /api/data/rev` first, the whole document only when the
      revision moved;
    - a fast tick (`rev_interval`, default 30 s) that only reads the
      revision (refreshing on change) and the live bits: presence, watch
      queue, a running Coach job and the rest timer.
    Optional features (Coach, watch, integrations, nudge-check) switch
    themselves off quietly when the instance answers 404/503.
    """

    def __init__(self, hass: HomeAssistant, entry, client: OpenGymApiClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=SCAN_INTERVAL,
        )
        self.client = client
        self.entry = entry
        # live presence (admin endpoint, None when not admin)
        self.uid: str | None = None
        self.is_admin: bool | None = None
        self.presence: dict[str, Any] | None = None
        self.consecutive_failures = 0
        # (1) revision fast path
        self.rev: int | None = None
        self.rev_supported = True
        self.full_fetches = 0
        self.rev_skips = 0
        self._unsub_fast: Any = None
        # (3) nudge-check
        self.nudge: dict[str, Any] | None = None
        self.nudge_supported = True
        # (4) rest timer started from HA
        self.rest_timer_end: datetime | None = None
        self.rest_timer_seconds: int | None = None
        # rest-timer length picked in HA (number entity); None = openGym's restSec
        self.rest_override: int | None = None
        # long-term statistics import after each full fetch (option)
        self.import_statistics = bool(
            entry.options.get(CONF_IMPORT_STATISTICS, DEFAULT_IMPORT_STATISTICS)
        )
        # history fingerprint last fed to the recorder (None = never)
        self._stats_digest: str | None = None
        # (8) coach
        self.coach_enabled: bool | None = None
        self.coach: dict[str, Any] | None = None
        # Coach jobs Home Assistant started: job id -> {kind, question, notify}.
        # Only these answers are picked up (and an `ask` cleared) here — a
        # question asked in the app stays for the app.
        self.coach_jobs: dict[str, dict[str, Any]] = {}
        self.coach_results: dict[str, dict[str, Any]] = {}
        self.coach_last_answer: dict[str, Any] | None = None
        self.coach_last_debrief: dict[str, Any] | None = None
        self.coach_auto_debrief = bool(
            entry.options.get(CONF_COACH_AUTO_DEBRIEF, DEFAULT_COACH_AUTO_DEBRIEF)
        )
        # workout ids seen in the last full fetch (None = not fetched yet)
        self._known_workouts: set[str] | None = None
        # (9) integrations
        self.integrations_enabled: bool | None = None
        self.connections: list[dict[str, Any]] = []
        # (12) watch
        self.watch_supported: bool | None = None
        self.watch_links: list[dict[str, Any]] = []
        self.watch_queue: dict[str, Any] | None = None
        self.watch_hr: dict[str, Any] | None = None

    # --- regular refresh ------------------------------------------------------

    def _fail(self, err: OpenGymError) -> UpdateFailed:
        self.consecutive_failures += 1
        if self.consecutive_failures >= 3:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                f"connection_error_{self.entry.entry_id}",
                is_fixable=False,  # no repairs flow; clears itself
                severity=ir.IssueSeverity.ERROR,
                translation_key="connection_error",
                translation_placeholders={"error": str(err)[:120]},
            )
        return UpdateFailed(f"openGym polling failed: {err}")

    async def _async_update_data(self) -> OpenGymState:
        try:
            if self.data is not None and self.rev_supported and self.rev is not None:
                try:
                    rev = await self.client.get_rev()
                except OpenGymFeatureOffError:
                    self.rev_supported = False
                else:
                    if rev == self.rev:
                        # (1) nothing changed: keep the parsed document
                        self.rev_skips += 1
                        self._ok()
                        await self._async_update_presence()
                        await self._async_update_extras()
                        return self.data
            state, rev = await self.client.get_state()
        except OpenGymUnauthorizedError as err:
            # session gone (revoked or paired device unpaired): ask for a new code
            self.entry.async_start_reauth(self.hass)
            raise UpdateFailed(f"openGym session invalid: {err}") from err
        except OpenGymError as err:
            raise self._fail(err) from err
        self._ok()
        self.full_fetches += 1
        self.rev = rev
        await self._async_update_presence()
        snapshot = OpenGymState(state)
        snapshot.lang = getattr(self.hass.config, "language", None) or "en"
        await self._async_update_extras()
        self._maybe_auto_debrief(snapshot)
        digest = snapshot.history_digest() if self.import_statistics else None
        if digest is not None and digest != self._stats_digest:
            # history -> long-term statistics, only when the history actually
            # moved (a rev bump from settings or a plan edit alone is not worth
            # re-feeding the whole series into the recorder)
            self._stats_digest = digest
            self.hass.async_create_task(
                async_import_statistics(
                    self.hass, self.entry.entry_id, self.entry.title or "openGym", snapshot
                ),
                name="openGym statistics import",
            )
        return snapshot

    def _ok(self) -> None:
        self.consecutive_failures = 0
        ir.async_delete_issue(
            self.hass, DOMAIN, f"connection_error_{self.entry.entry_id}"
        )

    async def _async_update_presence(self) -> None:
        """Read live presence from the admin endpoint (once per session)."""
        if self.uid is None:
            try:
                me = await self.client.me()
                self.uid = str((me.get("user") or {}).get("id"))
            except OpenGymError:
                return
        if self.is_admin is False:
            self.presence = None
            return
        try:
            users = await self.client.admin_users()
        except OpenGymError:
            return
        if users is None:
            self.is_admin = False
            self.presence = None
            return
        self.is_admin = True
        row = next((u for u in users if str(u.get("id")) == self.uid), None)
        self.presence = (row or {}).get("live")

    async def _async_update_extras(self) -> None:
        """Nudge-check, Coach, watch and integrations; each one optional."""
        await self._async_update_nudge()
        await self._async_update_coach()
        await self._async_update_watch(links=True)
        await self._async_update_integrations()

    async def _async_update_nudge(self) -> None:
        if not self.nudge_supported:
            return
        try:
            self.nudge = await self.client.nudge_check(dt_util.now().date().isoformat())
        except OpenGymFeatureOffError:
            self.nudge_supported = False
            self.nudge = None
        except OpenGymError as err:
            _LOGGER.debug("openGym: nudge-check failed: %s", err)

    async def _async_update_coach(self) -> None:
        if self.coach_enabled is False:
            return
        try:
            self.coach = await self.client.coach_status()
            self.coach_enabled = True
        except OpenGymFeatureOffError:
            self.coach_enabled = False
            self.coach = None
            return
        except OpenGymError as err:
            _LOGGER.debug("openGym: coach status failed: %s", err)
            return
        if self.coach_jobs:
            await self._async_collect_coach_results()

    # --- Coach jobs started from Home Assistant ---------------------------------

    async def async_start_coach_job(
        self,
        kind: str,
        *,
        question: str | None = None,
        workout_id: str | None = None,
        lang: str | None = None,
        notify: bool = False,
    ) -> str:
        """Queue an `ask` or `debrief` job; returns its id. Raises OpenGymError."""
        if kind == "ask":
            answer = await self.client.coach_ask(question or "", lang)
        else:
            answer = await self.client.coach_debrief(workout_id, lang)
        job_id = str(((answer or {}).get("job") or {}).get("id") or "")
        if not job_id:
            raise OpenGymError("the Coach queued no job")
        self.coach_enabled = True
        self.coach_results.pop(job_id, None)  # never hand out a stale result for a reused id
        self.coach_jobs[job_id] = {"kind": kind, "question": question, "notify": notify}
        # make the fast tick follow the job even before the next status poll
        self.coach = {**(self.coach or {}), "job": {"id": job_id, "kind": kind, "state": "queued"}}
        self.async_update_listeners()
        return job_id

    async def async_wait_coach(self, job_id: str, timeout: float) -> dict[str, Any] | None:
        """Poll the Coach until job `job_id` has a result, at most `timeout` s.

        None means still running: the result arrives later as an event (and,
        when the job was started with `notify`, as a notification).
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + max(0.0, timeout)
        while True:
            if (result := self.coach_results.get(job_id)) is not None:
                return result
            if loop.time() >= deadline or job_id not in self.coach_jobs:
                return self.coach_results.get(job_id)
            await asyncio.sleep(COACH_POLL_SECONDS)
            await self._async_update_coach()

    @callback
    def coach_notify_when_done(self, job_id: str) -> None:
        """A caller stopped waiting: deliver the result as a notification."""
        if job_id in self.coach_jobs:
            self.coach_jobs[job_id]["notify"] = True

    async def _async_collect_coach_results(self) -> None:
        """Pick up answers/debriefs (and failures) of the jobs HA started."""
        status = self.coach or {}
        pending = status.get("pending") or {}
        pid = str(pending.get("id") or "")
        if pid and pid in self.coach_jobs:
            job = self.coach_jobs.pop(pid)
            if job["kind"] == "ask":
                result = {
                    "status": "answered", "job_id": pid, "question": job.get("question"),
                    "answer": str(pending.get("answer") or pending.get("summary") or ""),
                }
                try:
                    # read here: clear it, so the app's Coach screen is free again
                    await self.client.coach_resolve()
                except OpenGymError as err:
                    _LOGGER.debug("openGym: could not clear the Coach answer: %s", err)
                self.coach_last_answer = {**result, "at": dt_util.utcnow().isoformat()}
                event = EVENT_COACH_ANSWER
            else:
                # a debrief stays for the app (and the Accept button) to file
                result = {"status": "answered", "job_id": pid, **logic.debrief_summary(pending)}
                self.coach_last_debrief = {**result, "at": dt_util.utcnow().isoformat()}
                event = EVENT_COACH_DEBRIEF
            self._coach_done(pid, job, result, event)
        last = status.get("last") or {}
        lid = str(last.get("id") or "")
        if lid and lid in self.coach_jobs and last.get("outcome") in (
            "failed", "dismissed", "expired", "nochange",
        ):
            job = self.coach_jobs.pop(lid)
            result = {
                "status": "failed", "job_id": lid, "kind": job["kind"],
                "question": job.get("question"),
                "error": str(last.get("message") or last.get("reading") or last.get("errorClass") or last.get("outcome")),
            }
            # failures go out on the same bus event, with status "failed"
            self._coach_done(
                lid, job, result, EVENT_COACH_ANSWER if job["kind"] == "ask" else EVENT_COACH_DEBRIEF
            )

    @callback
    def _coach_done(self, job_id: str, job: dict[str, Any], result: dict[str, Any], event: str | None) -> None:
        self.coach_results[job_id] = result
        while len(self.coach_results) > 20:
            self.coach_results.pop(next(iter(self.coach_results)))
        if event:
            self.hass.bus.async_fire(event, {**result, "entry_id": self.entry.entry_id})
        if job.get("notify"):
            from homeassistant.components import persistent_notification

            lang = getattr(self.hass.config, "language", None)
            title, message = logic.coach_notification(job["kind"], result, lang)
            persistent_notification.async_create(
                self.hass, message, title, f"{DOMAIN}_coach_{job_id}"
            )
        self.async_update_listeners()

    @callback
    def _maybe_auto_debrief(self, snapshot: OpenGymState) -> None:
        """Option: ask the Coach for a debrief of each new recent workout."""
        ids = {str(w.get("id")) for w in snapshot.workouts if w.get("id") is not None}
        known, self._known_workouts = self._known_workouts, ids
        if known is None or not self.coach_auto_debrief or not self.coach_enabled:
            return
        today = dt_util.now().date()
        fresh = [
            w for w in snapshot.workouts
            if w.get("id") is not None and str(w.get("id")) not in known
            and (day := _day(w.get("d"))) is not None and (today - day).days <= 1
        ]
        if not fresh:
            return
        workout_id = str(fresh[-1]["id"])

        async def _debrief() -> None:
            try:
                await self.async_start_coach_job(
                    "debrief", workout_id=workout_id,
                    lang=getattr(self.hass.config, "language", None),
                )
            except OpenGymError as err:
                _LOGGER.info("openGym: automatic Coach debrief not started (%s)", err)

        self.hass.async_create_task(_debrief(), name="openGym Coach debrief")

    async def _async_update_watch(self, links: bool = False) -> bool:
        """Paired watches (on refresh) and the queued watch events (peek only)."""
        if self.watch_supported is False:
            return False
        before = (self.watch_hr, len(self.watch_links))
        try:
            if links:
                self.watch_links = await self.client.watch_links()
                self.watch_supported = True
            if self.watch_links:
                self.watch_queue = await self.client.watch_events()
                self.watch_hr = logic.latest_watch_hr(
                    (self.watch_queue or {}).get("events")
                ) or self.watch_hr
            else:
                self.watch_queue = None
                self.watch_hr = None
        except OpenGymFeatureOffError:
            self.watch_supported = False
            self.watch_links, self.watch_queue, self.watch_hr = [], None, None
        except OpenGymError as err:
            _LOGGER.debug("openGym: watch read failed: %s", err)
        return before != (self.watch_hr, len(self.watch_links))

    async def _async_update_integrations(self) -> None:
        """Our webhook connection(s); raise a repair issue when deliveries fail."""
        if self.integrations_enabled is False:
            return
        try:
            data = await self.client.list_integrations_optional()
        except OpenGymFeatureOffError:
            self.integrations_enabled = False
            self.connections = []
            return
        except OpenGymError as err:
            _LOGGER.debug("openGym: integrations read failed: %s", err)
            return
        self.integrations_enabled = True
        self.connections = logic.our_connections(
            data.get("connections") or [], self.entry.data.get("webhook_id")
        )
        issue_id = f"webhook_delivery_failed_{self.entry.entry_id}"
        failing = next((c for c in self.connections if logic.failing_connection(c)), None)
        if failing:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                issue_id,
                is_fixable=True,
                severity=ir.IssueSeverity.WARNING,
                translation_key="webhook_delivery_failed",
                translation_placeholders={
                    "label": str(failing.get("label") or "Home Assistant"),
                    "failed": str(failing.get("failed") or 0),
                    "error": str((failing.get("lastError") or {}).get("msg") or "-")[:160],
                },
                data={"entry_id": self.entry.entry_id, "connection_id": failing.get("id")},
            )
        else:
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)

    # --- fast tick ------------------------------------------------------------

    @callback
    def async_start_fast_tick(self, seconds: int) -> None:
        """Start the revision/live tick (0 = off)."""
        self.async_stop_fast_tick()
        if seconds and seconds > 0:
            self._unsub_fast = async_track_time_interval(
                self.hass, self._async_fast_tick, timedelta(seconds=seconds),
                name=f"openGym fast tick {self.entry.entry_id}",
            )

    @callback
    def async_stop_fast_tick(self) -> None:
        if self._unsub_fast:
            self._unsub_fast()
            self._unsub_fast = None

    async def _async_fast_tick(self, _now: Any = None) -> None:
        if self.data is None or not self.last_update_success:
            return
        if self.rev_supported:
            try:
                rev = await self.client.get_rev()
            except OpenGymFeatureOffError:
                self.rev_supported = False
            except OpenGymError as err:
                _LOGGER.debug("openGym: rev check failed: %s", err)
                return
            else:
                if rev != self.rev:
                    await self.async_request_refresh()
                    return
        changed = False
        if self.is_admin:
            old = self.presence
            await self._async_update_presence()
            changed |= old != self.presence
        changed |= await self._async_update_watch()
        if self.coach_enabled and ((self.coach or {}).get("job") or self.coach_jobs):
            old_coach = self.coach
            await self._async_update_coach()
            changed |= old_coach != self.coach
        if self.rest_timer_end and dt_util.utcnow() >= self.rest_timer_end:
            self.rest_timer_end = None
            changed = True
        if changed:
            self.async_update_listeners()

    def rest_default_seconds(self) -> float | None:
        """Rest length for a timer started without seconds: HA's number
        entity first, then openGym's own `restSec` setting."""
        if self.rest_override:
            return float(self.rest_override)
        return self.data.rest_seconds() if self.data else None

    @callback
    def set_rest_timer(self, seconds: int | None) -> None:
        """Remember a rest timer started (or cancelled with None) from HA."""
        self.rest_timer_seconds = seconds
        self.rest_timer_end = (
            dt_util.utcnow() + timedelta(seconds=seconds) if seconds else None
        )
        self.async_update_listeners()

    @callback
    def ingest_event(self, event_type: str, event: dict[str, Any]) -> None:
        """A signed webhook arrived: the document changed, fetch it (debounced)."""
        if self.data:
            self.hass.async_create_task(self.async_request_refresh())
