"""State polling and derived values for openGym.

Polls `GET /api/data` (the whole app state) and exposes workouts, weigh-ins,
the weekly plan and muscle coverage to the platforms.
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    OpenGymApiClient,
    OpenGymConnectionError,
    OpenGymError,
    OpenGymUnauthorizedError,
)
from .const import (
    DOMAIN,
    EPLEY_K,
    MAP_SLUGS,
    MUSCLE_TARGETS,
    MUSCLES,
    RECOVERY_DAYS,
    SCAN_INTERVAL,
    SECONDARY_WEIGHT,
    _CANON,
)

_LOGGER = logging.getLogger(__name__)


def _load_muscle_map() -> dict[str, dict[str, Any]]:
    try:
        raw = (Path(__file__).parent / "muscle_map.json").read_text()
        return json.loads(raw)
    except (FileNotFoundError, ValueError) as err:  # pragma: no cover
        _LOGGER.warning("openGym: muscle map unavailable (%s)", err)
        return {}


_MUSCLE_MAP = _load_muscle_map()


def _day(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


class OpenGymState:
    """A parsed snapshot of the user's app state."""

    def __init__(self, state: dict[str, Any] | None) -> None:
        self.raw = state or {}
        self.unit: str = self.raw.get("unit", "kg")
        self.workouts: list[dict[str, Any]] = sorted(
            self.raw.get("workouts") or [], key=lambda w: w.get("d") or ""
        )
        self.bodyweight: list[dict[str, Any]] = sorted(
            self.raw.get("bodyweight") or [], key=lambda b: b.get("d") or ""
        )
        self.routines: dict[str, dict[str, Any]] = {
            r["id"]: r for r in (self.raw.get("routines") or []) if "id" in r
        }
        # weekday 0=Sunday .. 6=Saturday -> routine id (openGym's `week`)
        self.week: dict[int, str] = {
            int(k): v for k, v in (self.raw.get("week") or {}).items()
        }
        self.day_plan: dict[str, str] = self.raw.get("dayPlan") or {}

    # --- workouts ---------------------------------------------------------

    def last_workout(self) -> dict[str, Any] | None:
        return self.workouts[-1] if self.workouts else None

    def workouts_between(self, start: date, end: date) -> list[dict[str, Any]]:
        return [w for w in self.workouts if (_day(w.get("d")) and start <= _day(w.get("d")) <= end)]

    def week_volume(self, today: date) -> float:
        monday = today - timedelta(days=today.weekday())
        return sum(w.get("vol") or 0 for w in self.workouts_between(monday, today))

    def week_count(self, today: date) -> int:
        monday = today - timedelta(days=today.weekday())
        return len(self.workouts_between(monday, today))

    def streak(self, today: date) -> int:
        """Workout days in a row, counting back from today (or yesterday)."""
        days = {_day(w.get("d")) for w in self.workouts}
        days.discard(None)
        if today not in days and (today - timedelta(days=1)) not in days:
            return 0
        cursor = today if today in days else today - timedelta(days=1)
        count = 0
        while cursor in days:
            count += 1
            cursor -= timedelta(days=1)
        return count

    # --- weigh-ins ----------------------------------------------------------

    def last_weighin(self) -> dict[str, Any] | None:
        return self.bodyweight[-1] if self.bodyweight else None

    def goal_weight(self) -> float | None:
        """openGym's goal weight (flat `targetW` setting, also under settings)."""
        settings = self.raw.get("settings") or {}
        for source in (self.raw, settings):
            value = source.get("targetW")
            if isinstance(value, (int, float)) and value > 0:
                return float(value)
        return None

    # --- recency / records --------------------------------------------------

    def last_workout_day(self) -> date | None:
        w = self.last_workout()
        return _day(w.get("d")) if w else None

    def best_1rm(self) -> dict[str, float]:
        """Epley 1RM estimate per exercise id, best set wins."""
        best: dict[str, float] = {}
        for workout in self.workouts:
            for entry in workout.get("entries") or []:
                ex_id = str(entry.get("id"))
                for s in entry.get("sets") or []:
                    w, r = s.get("w"), s.get("r")
                    if not isinstance(w, (int, float)) or not w:
                        continue
                    est = w * (1 + (r or 0) / EPLEY_K)
                    if est > best.get(ex_id, 0):
                        best[ex_id] = est
        return best

    def custom_ex_count(self) -> int:
        return len(self.raw.get("customEx") or [])

    def pr_map(self) -> dict[str, dict[str, Any]]:
        """Best logged weight per exercise (openGym's `exWeights`)."""
        out: dict[str, dict[str, Any]] = {}
        for ex_id, info in (self.raw.get("exWeights") or {}).items():
            if isinstance(info, dict) and isinstance(info.get("w"), (int, float)):
                out[str(ex_id)] = {
                    "weight": float(info["w"]),
                    "date": info.get("d"),
                }
        return out

    def last_workout_hr(self) -> dict[str, float] | None:
        """Average/max heart rate of the last workout, if any set carried one."""
        w = self.last_workout()
        if not w:
            return None
        values = [
            float(s["hr"])
            for e in w.get("entries") or []
            for s in e.get("sets") or []
            if isinstance(s.get("hr"), (int, float))
        ]
        if not values:
            return None
        return {"avg": round(sum(values) / len(values), 1), "max": max(values)}

    # --- plan ---------------------------------------------------------------

    def routine_for(self, day: date) -> dict[str, Any] | None:
        planned = self.day_plan.get(day.isoformat())
        if planned is None:
            # openGym numbers weekdays Sunday=0 .. Saturday=6.
            planned = self.week.get((day.weekday() + 1) % 7)
        if not planned or planned == "rest":
            return None
        return self.routines.get(planned)

    def next_session(self, today: date) -> tuple[dict[str, Any], date] | None:
        """First planned routine from today on, up to 14 days out."""
        for offset in range(15):
            day = today + timedelta(days=offset)
            if routine := self.routine_for(day):
                return routine, day
        return None

    # --- muscle coverage ----------------------------------------------------

    @staticmethod
    def _entry_muscles(info: dict[str, Any]) -> dict[str, float]:
        """Muscle -> weight for one exercise map entry (primaries 1.0, secondaries 0.4)."""
        weights = info.get("muscleWeights")
        if isinstance(weights, dict):
            return {m: float(w) for m, w in weights.items() if isinstance(w, (int, float)) and w > 0}
        out = {m: 1.0 for m in info.get("primaries") or []}
        for m in info.get("secondaries") or []:
            out.setdefault(m, SECONDARY_WEIGHT)
        return out

    @staticmethod
    def _working_sets(sets: list[dict[str, Any]] | None) -> int:
        """Sets actually ticked off, warm-ups left out (openGym's counting)."""
        n = 0
        for s in sets or []:
            if s.get("warmup") is True or s.get("phase") == "warmup":
                continue
            sides = s.get("sides") or {}
            done = s.get("done")
            if done is None and sides:
                done = sides.get("L", {}).get("done") is True and sides.get("R", {}).get("done") is True
            if done:
                n += 1
        return n

    def week_start(self, today: date) -> date:
        return today - timedelta(days=today.weekday())

    def week_sets(self, today: date) -> dict[str, float]:
        """Effective working sets per muscle for this calendar week.

        A set credits each primary muscle with 1.0 and each supporting muscle
        with 0.4 — the same weighting openGym's own muscle map uses.
        """
        monday = self.week_start(today)
        load: dict[str, float] = {}
        for workout in self.workouts_between(monday, today):
            for entry in workout.get("entries") or []:
                info = _MUSCLE_MAP.get(str(entry.get("id")))
                if not info:
                    continue
                sets = self._working_sets(entry.get("sets"))
                if not sets:
                    continue
                for muscle, weight in self._entry_muscles(info).items():
                    load[muscle] = round(load.get(muscle, 0) + weight * sets, 4)
        return load

    def muscle_last_days(self, today: date) -> dict[str, str | None]:
        """ISO date each muscle was last trained (primaries + weighted secondaries)."""
        last: dict[str, date] = {}
        for workout in reversed(self.workouts):
            day = _day(workout.get("d"))
            if not day:
                continue
            for entry in workout.get("entries") or []:
                info = _MUSCLE_MAP.get(str(entry.get("id")))
                if not info:
                    continue
                for muscle in self._entry_muscles(info):
                    last.setdefault(muscle, day)
            if len(last) >= len(MAP_SLUGS):
                break
        return {m: (d.isoformat() if (d := last.get(m)) else None) for m in MAP_SLUGS}

    def muscle_targets(self) -> dict[str, tuple[int, int]]:
        """Weekly [low, high] set ranges: openGym defaults, user overrides win."""
        out = dict(MUSCLE_TARGETS)
        raw = self.raw.get("muscleTargets") or {}
        for slug, pair in raw.items():
            if isinstance(pair, (list, tuple)) and len(pair) == 2:
                try:
                    lo, hi = int(pair[0]), int(pair[1])
                except (TypeError, ValueError):
                    continue
                if 0 <= lo <= hi <= 40:
                    out[slug] = (lo, hi)
        return out

    def best_muscle_1rm(self) -> dict[str, float]:
        """Best Epley 1RM estimate per muscle (primary credit only)."""
        best: dict[str, float] = {}
        for workout in self.workouts:
            for entry in workout.get("entries") or []:
                info = _MUSCLE_MAP.get(str(entry.get("id")))
                if not info:
                    continue
                for s in entry.get("sets") or []:
                    w, r = s.get("w"), s.get("r")
                    if not isinstance(w, (int, float)) or not w:
                        continue
                    est = w * (1 + (r or 0) / EPLEY_K)
                    for muscle, weight in self._entry_muscles(info).items():
                        if weight >= 1.0:
                            best[muscle] = max(best.get(muscle, 0), est)
        return best

    def muscle_days(self, today: date) -> dict[str, int]:
        """Days since each muscle group was last trained (primaries + weighted
        secondaries). Muscles never trained get 999."""
        last: dict[str, date] = {}
        for workout in reversed(self.workouts):
            day = _day(workout.get("d"))
            if not day:
                continue
            for entry in workout.get("entries") or []:
                info = _MUSCLE_MAP.get(str(entry.get("id")))
                if not info:
                    continue
                muscles = set(info.get("primaries") or [])
                weights = info.get("muscleWeights") or {}
                muscles |= {m for m, w in weights.items() if w and w >= 0.3}
                for muscle in muscles:
                    last.setdefault(_CANON.get(muscle, muscle), day)
            if len(last) >= len(MUSCLES):
                break
        return {
            muscle: (today - last[muscle]).days if muscle in last else 999
            for muscle in MUSCLES
        }


class OpenGymDataCoordinator(DataUpdateCoordinator[OpenGymState]):
    """Polls openGym's state document."""

    def __init__(self, hass: HomeAssistant, entry, client: OpenGymApiClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=SCAN_INTERVAL,
        )
        self.client = client
        self.entry = entry
        # webhook deliveries land here; merged into the polled state
        self.pending_events: list[dict[str, Any]] = []
        # live presence (admin endpoint, None when not admin)
        self.uid: str | None = None
        self.is_admin: bool | None = None
        self.presence: dict[str, Any] | None = None
        self.consecutive_failures = 0

    async def _async_update_data(self) -> OpenGymState:
        try:
            state, rev = await self.client.get_state()
        except OpenGymUnauthorizedError as err:
            # session gone (revoked or paired device unpaired): ask for a new code
            self.entry.async_start_reauth(self.hass)
            raise UpdateFailed(f"openGym session invalid: {err}") from err
        except OpenGymError as err:
            self.consecutive_failures += 1
            if self.consecutive_failures >= 3:
                ir.async_create_issue(
                    self.hass,
                    DOMAIN,
                    f"connection_error_{self.entry.entry_id}",
                    is_fixable=True,
                    severity=ir.IssueSeverity.ERROR,
                    translation_key="connection_error",
                    translation_placeholders={"error": str(err)[:120]},
                )
            raise UpdateFailed(f"openGym polling failed: {err}") from err
        self.consecutive_failures = 0
        ir.async_delete_issue(
            self.hass, DOMAIN, f"connection_error_{self.entry.entry_id}"
        )
        await self._async_update_presence()
        snapshot = OpenGymState(state)
        snapshot._rev = rev  # noqa: SLF001  (needed for conditional writes)
        return snapshot

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

    @callback
    def ingest_event(self, event_type: str, event: dict[str, Any]) -> None:
        """Remember the newest webhook delivery of each type between polls."""
        self.pending_events = [
            e for e in self.pending_events if e.get("type") != event_type
        ]
        self.pending_events.append({"type": event_type, **event})
        if self.data:
            self.async_update_listeners()
