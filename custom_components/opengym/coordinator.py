"""State polling and derived values for openGym.

Polls `GET /api/data` (the whole app state) and exposes workouts, weigh-ins,
the weekly plan and muscle coverage to the platforms.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, time, timedelta
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
    FATIGUE_HALF_LIFE_DEFAULT_H,
    FATIGUE_HALF_LIFE_H,
    FATIGUE_MAX_SETS_PER_SESSION,
    FATIGUE_READY_MAX,
    FATIGUE_RECOVERING_MAX,
    FATIGUE_SCAN_DAYS,
    FATIGUE_SETS_PER_UNIT,
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
                # openGym: a set counts done once either side is ticked.
                done = any(
                    (sides.get(side) or {}).get("done") is True for side in ("L", "R")
                )
            if done:
                n += 1
        return n

    def week_start(self, today: date) -> date:
        return today - timedelta(days=today.weekday())

    def week_sets(self, today: date, week_offset: int = 0) -> dict[str, float]:
        """Effective working sets per muscle for a calendar week.

        A set credits each primary muscle with 1.0 and each supporting muscle
        with 0.4 — the same weighting openGym's own muscle map uses.
        `week_offset` -1 is the previous week, 0 the current one.
        """
        monday = self.week_start(today) + timedelta(weeks=week_offset)
        end = monday + timedelta(days=6)
        load: dict[str, float] = {}
        for workout in self.workouts_between(monday, end):
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
                for muscle in self._entry_muscles(info):
                    last.setdefault(_CANON.get(muscle, muscle), day)
            if len(last) >= len(MUSCLES):
                break
        return {
            muscle: (today - last[muscle]).days if muscle in last else 999
            for muscle in MUSCLES
        }

    # --- fatigue model -------------------------------------------------------
    #
    # Mirrors openGym's frontend/src/lib/recovery.js: stimulus in effective
    # hard sets per muscle (session-capped, secondaries weighted), decaying
    # exponentially with a muscle-specific half-life.

    def _muscle_set_events(
        self, since: date, until: date
    ) -> dict[str, list[tuple[date, float]]]:
        """Per muscle: (day, weighted sets) events of every session in range."""
        events: dict[str, list[tuple[date, float]]] = {}
        for workout in self.workouts_between(since, until):
            day = _day(workout.get("d"))
            if not day:
                continue
            for entry in workout.get("entries") or []:
                info = _MUSCLE_MAP.get(str(entry.get("id")))
                if not info:
                    continue
                sets = self._working_sets(entry.get("sets"))
                if not sets:
                    continue
                sets = min(sets, FATIGUE_MAX_SETS_PER_SESSION)
                for muscle, weight in self._entry_muscles(info).items():
                    events.setdefault(muscle, []).append((day, weight * sets))
        return events

    def fatigue(self, today: date) -> dict[str, float]:
        """Remaining fatigue stimulus per muscle, 0.0–1.0+.

        A muscle's stimulus is the sum of its per-session doses (each capped
        and weighted), each decayed by `0.5 ** (age / half_life)`.
        """
        since = today - timedelta(days=FATIGUE_SCAN_DAYS)
        now = datetime.combine(today, time.max)
        out: dict[str, float] = {}
        for muscle, events in self._muscle_set_events(since, today).items():
            half_life = FATIGUE_HALF_LIFE_H.get(muscle, FATIGUE_HALF_LIFE_DEFAULT_H)
            value = 0.0
            for day, dose in events:
                age_h = max(0.0, (now - datetime.combine(day, time(12))).total_seconds() / 3600)
                value += (dose / FATIGUE_SETS_PER_UNIT) * (0.5 ** (age_h / half_life))
            out[muscle] = round(value, 4)
        return out

    @staticmethod
    def fatigue_state(value: float) -> str:
        if value < FATIGUE_READY_MAX:
            return "ready"
        if value <= FATIGUE_RECOVERING_MAX:
            return "recovering"
        return "fatigued"

    def planned_muscles(self, today: date) -> dict[str, float]:
        """Set-weighted muscle load the *next* planned session would bring.

        Lets the card paint the plan ("what would this session hit") over the
        body map without any workout history.
        """
        nxt = self.next_session(today)
        if not nxt:
            return {}
        routine, _day = nxt
        load: dict[str, float] = {}
        for ex in routine.get("ex") or []:
            info = _MUSCLE_MAP.get(str(ex.get("id")))
            if not info:
                continue
            sets = float(ex.get("sets") or 0)
            if sets <= 0:
                continue
            for muscle, weight in self._entry_muscles(info).items():
                load[muscle] = round(load.get(muscle, 0) + weight * sets, 4)
        return load

    def day_view(self, today: date, days: int = 14) -> list[dict[str, Any]]:
        """Per-day plan vs. reality for the week card: planned routine or done workout.

        Starts at this week's Monday so past days of the week show what was
        actually lifted; later days show the plan.
        """
        done: dict[str, dict[str, Any]] = {}
        for workout in self.workouts:
            day = _day(workout.get("d"))
            if day:
                done[day.isoformat()] = {
                    "name": workout.get("name") or "Workout",
                    "volume": workout.get("vol"),
                    "sets": sum(
                        len(e.get("sets") or []) for e in workout.get("entries") or []
                    ),
                }
        out = []
        for offset in range(days):
            day = self.week_start(today) + timedelta(days=offset)
            routine = self.routine_for(day)
            entry = done.get(day.isoformat())
            out.append(
                {
                    "date": day.isoformat(),
                    "planned": routine.get("name") if routine else None,
                    "emoji": routine.get("emoji") if routine else None,
                    "done": entry,
                }
            )
        return out

    def planned_week(self, today: date, days: int = 7) -> list[dict[str, Any]]:
        """Per-day plan for this calendar week: routine name/emoji or rest."""
        out = []
        for offset in range(days):
            day = self.week_start(today) + timedelta(days=offset)
            routine = self.routine_for(day)
            out.append(
                {
                    "date": day.isoformat(),
                    "weekday": day.isoweekday(),
                    "name": routine.get("name") if routine else None,
                    "emoji": routine.get("emoji") if routine else None,
                    "exercises": len(routine.get("ex") or []) if routine else 0,
                }
            )
        return out

    def week_history(self, today: date, weeks: int = 12) -> list[dict[str, Any]]:
        """Per-week summary for the streak heatmap: date, sets, workouts, volume."""
        out = []
        for offset in range(weeks - 1, -1, -1):
            monday = self.week_start(today) - timedelta(weeks=offset)
            sunday = monday + timedelta(days=6)
            in_week = self.workouts_between(monday, sunday)
            by_muscle = self.week_sets(today, -offset)
            out.append(
                {
                    "week_start": monday.isoformat(),
                    "workouts": len(in_week),
                    "sets": round(sum(by_muscle.values()), 1),
                    "volume": round(sum(w.get("vol") or 0 for w in in_week), 1),
                    "muscles": by_muscle,
                }
            )
        return out

    def muscle_trends(self, today: date, weeks: int = 12) -> dict[str, list[float | None]]:
        """Best 1RM per muscle over the last `weeks` weekly windows (None = no data)."""
        best: dict[str, list[float | None]] = {}
        for muscle in MAP_SLUGS:
            best[muscle] = []
        for offset in range(weeks - 1, -1, -1):
            monday = self.week_start(today) - timedelta(weeks=offset)
            end = monday + timedelta(days=6)
            window_best: dict[str, float] = {}
            for workout in self.workouts_between(monday, end):
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
                                window_best[muscle] = max(window_best.get(muscle, 0), est)
            for muscle in best:
                best[muscle].append(round(window_best[muscle], 1) if muscle in window_best else None)
        return best

    def muscle_detail(self, muscle: str, today: date) -> dict[str, Any]:
        """Everything one muscle row/detail panel needs, from the state doc."""
        week = self.week_sets(today)
        trends = self.muscle_trends(today)
        last = self.muscle_last_days(today)
        fatigue_map = self.fatigue(today)
        targets = self.muscle_targets()
        exercises: dict[str, float] = {}
        best = 0.0
        for workout in self.workouts:
            for entry in workout.get("entries") or []:
                info = _MUSCLE_MAP.get(str(entry.get("id")))
                if not info:
                    continue
                weight = self._entry_muscles(info).get(muscle, 0)
                if weight <= 0:
                    continue
                sets = self._working_sets(entry.get("sets"))
                if sets:
                    key = str(info.get("n") or entry.get("id"))
                    exercises[key] = exercises.get(key, 0) + weight * sets
                for s in entry.get("sets") or []:
                    w, r = s.get("w"), s.get("r")
                    if isinstance(w, (int, float)) and w:
                        best = max(best, w * (1 + (r or 0) / EPLEY_K))
        return {
            "week_sets": round(week.get(muscle, 0), 1),
            "target": list(targets.get(muscle, [0, 0])),
            "last_trained": last.get(muscle),
            "fatigue": fatigue_map.get(muscle, 0.0),
            "fatigue_state": self.fatigue_state(fatigue_map.get(muscle, 0.0)),
            "best_1rm": round(best, 1) if best else None,
            "trend": trends.get(muscle, []),
            "exercises": dict(sorted(exercises.items(), key=lambda kv: -kv[1])),
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
