"""Parsed openGym state document and everything derived from it.

`OpenGymState` wraps one snapshot of `GET /api/data` (workouts, weigh-ins,
routines, the weekly plan) and computes what the entities and cards show:
week volume and streaks, muscle coverage, the fatigue model, 1RM estimates
and progress series. Pure Python, no Home Assistant imports, so it is
cheap to unit-test.
"""

from __future__ import annotations

import gzip
import json
import logging
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from . import logic
from .const import (
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
    SECONDARY_WEIGHT,
    _CANON,
)

_LOGGER = logging.getLogger(__name__)


def _load_exercise_db() -> dict[str, dict[str, Any]]:
    """openGym's exercise catalogue: id -> {n, de, bp, muscleWeights}.

    Generated from openGym's catalogue by scripts/build_exercise_db.mjs. Drawing
    ids (EXALIAS) resolve to the exercise they show, like the app does.
    """
    try:
        with gzip.open(Path(__file__).parent / "exercises.json.gz", "rt", encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, ValueError) as err:  # pragma: no cover
        _LOGGER.warning("openGym: exercise catalogue unavailable (%s)", err)
        return {}
    out: dict[str, dict[str, Any]] = {}
    for ex_id, (name, name_de, bp, weights) in (raw.get("ex") or {}).items():
        out[ex_id] = {"n": name, "de": name_de, "bp": bp, "muscleWeights": weights}
    for alias, target in (raw.get("alias") or {}).items():
        if target in out and alias not in out:
            out[alias] = out[target]
    return out


_MUSCLE_MAP = _load_exercise_db()


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
        # Home Assistant's language, for exercise names (set by the coordinator).
        self.lang: str = "en"

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
        # A finished workout may carry the session's HR (lib/heart-rate.js: {avg, max, src, n}).
        session = logic.hr_value(w.get("hr"))
        if session:
            return {"avg": float(session["avg"]), "max": float(session["max"])}
        sets = [
            hr
            for e in w.get("entries") or []
            for s in e.get("sets") or []
            if (hr := logic.hr_value(s.get("hr")))
        ]
        if not sets:
            return None
        return {
            "avg": round(sum(h["avg"] for h in sets) / len(sets), 1),
            "max": float(max(h["max"] for h in sets)),
        }

    def week_prs(self, today: date) -> int:
        return logic.week_prs(self.workouts, self.week_start(today), today)

    def weight_trend(self, points: int = 12) -> list[dict[str, Any]]:
        return logic.weight_trend(self.bodyweight, points)

    def rest_seconds(self) -> float | None:
        """The app's default rest-timer seconds (`restSec`)."""
        for source in (self.raw, self.raw.get("settings") or {}):
            value = source.get("restSec")
            if isinstance(value, (int, float)) and value > 0:
                return float(value)
        return None

    def _custom(self, key: str) -> dict[str, Any] | None:
        for ex in self.raw.get("customEx") or []:
            if isinstance(ex, dict) and str(ex.get("id")) == key:
                return ex
        return None

    def _info(self, ex_id: Any, entry: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """Muscle info for an exercise: catalogue, then custom exercise, then a
        snapshot the history entry carries (deleted custom exercises)."""
        key = str(ex_id)
        if (info := _MUSCLE_MAP.get(key)) is not None:
            return info
        sources = [self._custom(key)]
        if isinstance(entry, dict):
            sources += [entry.get("exercise"), entry.get("muscleSnapshot"), entry]
        for src in sources:
            if isinstance(src, dict) and (weights := logic.custom_muscle_weights(src)):
                return {"n": src.get("n"), "muscleWeights": weights}
        return None

    def exercise_name(self, ex_id: Any, lang: str = "en", entry: dict[str, Any] | None = None) -> str:
        """Display name as openGym shows it: custom name, else the catalogue
        title in the language (German pack where it has one, else English)."""
        key = str(ex_id)
        custom = self._custom(key)
        if custom and custom.get("n"):
            return str(custom["n"])
        info = _MUSCLE_MAP.get(key)
        if info:
            if lang.lower().startswith("de") and info.get("de"):
                return str(info["de"])
            return str(info["n"])
        for src in (entry or {}, (entry or {}).get("exercise") or {}):
            if isinstance(src, dict) and src.get("n"):
                return logic.cap_words(str(src["n"]))
        return f"#{key}" if key and key != "None" else "?"

    def exercise_names(self, ex_id: Any, entry: dict[str, Any] | None = None) -> dict[str, str]:
        return {"en": self.exercise_name(ex_id, "en", entry), "de": self.exercise_name(ex_id, "de", entry)}

    def week_streak(self, today: date) -> dict[str, Any]:
        """openGym's week streak (weeks in a row with a workout, freezes)."""
        sunday_first = (self.raw.get("weekStart") or (self.raw.get("settings") or {}).get("weekStart")) == 0
        days = [d for w in self.workouts if (d := _day(w.get("d")))]
        return logic.week_streak(days, today, 6 if sunday_first else 0)

    def next_workout(self, today: date) -> dict[str, Any] | None:
        """The next planned session with its exercises, for the next-workout card."""
        nxt = self.next_session(today)
        if not nxt:
            return None
        routine, day = nxt
        memory = self.raw.get("exWeights") or {}
        exercises = []
        muscles: dict[str, float] = {}
        for ex in routine.get("ex") or []:
            if not isinstance(ex, dict):
                continue
            ex_id = str(ex.get("id"))
            last = memory.get(ex_id) if isinstance(memory, dict) else None
            exercises.append({
                "id": ex_id,
                "name": self.exercise_name(ex_id, self.lang),
                "names": self.exercise_names(ex_id),
                "sets": ex.get("sets"),
                "reps": ex.get("reps"),
                "reps_min": ex.get("repsMin"),
                "reps_max": ex.get("repsMax"),
                "sec": ex.get("sec"),
                "min": ex.get("min"),
                "mode": ex.get("mode") or "reps",
                "weight": ex.get("weight") or ((last or {}).get("w") if isinstance(last, dict) else None),
            })
            info = self._info(ex_id)
            if info:
                for m, w in self._entry_muscles(info).items():
                    if w >= 1.0:
                        muscles[m] = muscles.get(m, 0) + float(ex.get("sets") or 0)
        return {
            "routine_id": routine.get("id"),
            "name": routine.get("name") or "Workout",
            "emoji": routine.get("emoji"),
            "glyph": logic.routine_glyph(routine.get("emoji")),
            "icon": logic.routine_icon(routine.get("emoji")),
            "date": day.isoformat(),
            "days_until": (day - today).days,
            "exercises": exercises,
            "total_sets": sum(int(e["sets"] or 0) for e in exercises if isinstance(e["sets"], (int, float))),
            "muscles": sorted(muscles, key=lambda m: -muscles[m])[:6],
        }

    # --- plan ---------------------------------------------------------------

    def routine_for(self, day: date) -> dict[str, Any] | None:
        planned = self.day_plan.get(day.isoformat())
        if planned is None:
            # openGym numbers weekdays Sunday=0 .. Saturday=6.
            planned = self.week.get((day.weekday() + 1) % 7)
        if isinstance(planned, list):  # newer openGym: a day may hold several routines
            planned = planned[0] if planned else None
        if not planned or planned == "rest":
            return None
        return self.routines.get(str(planned))

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
                info = self._info(entry.get("id"), entry)
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
                info = self._info(entry.get("id"), entry)
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
                info = self._info(entry.get("id"), entry)
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
                info = self._info(entry.get("id"), entry)
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
                info = self._info(entry.get("id"), entry)
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
            info = self._info(ex.get("id"), ex)
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
                    "icon": logic.routine_icon(routine.get("emoji")) if routine else None,
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
                    "icon": logic.routine_icon(routine.get("emoji")) if routine else None,
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
                    info = self._info(entry.get("id"), entry)
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
                info = self._info(entry.get("id"), entry)
                if not info:
                    continue
                weight = self._entry_muscles(info).get(muscle, 0)
                if weight <= 0:
                    continue
                sets = self._working_sets(entry.get("sets"))
                if sets:
                    key = self.exercise_name(entry.get("id"), self.lang, entry)
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

    # --- progress series (long-term statistics, progress card) ----------------

    @staticmethod
    def _set_1rm(s: dict[str, Any]) -> float | None:
        """Epley estimate of one logged set (warm-ups and empty sets skipped)."""
        if s.get("warmup") is True or s.get("phase") == "warmup":
            return None
        w, r = s.get("w"), s.get("r")
        if not isinstance(w, (int, float)) or isinstance(w, bool) or w <= 0:
            return None
        return w * (1 + (r or 0) / EPLEY_K) if (r or 0) > 1 else float(w)

    def daily_weights(self) -> list[tuple[date, float]]:
        """One body-weight value per day (the day's last weigh-in)."""
        out: dict[date, float] = {}
        for b in self.bodyweight:
            day, w = _day(b.get("d")), b.get("w")
            if day and isinstance(w, (int, float)) and not isinstance(w, bool) and w > 0:
                out[day] = float(w)
        return sorted(out.items())

    def daily_volume(self) -> list[tuple[date, float]]:
        """Lifted volume per training day (several workouts a day add up)."""
        out: dict[date, float] = {}
        for w in self.workouts:
            day = _day(w.get("d"))
            vol = w.get("vol")
            if day and isinstance(vol, (int, float)) and not isinstance(vol, bool):
                out[day] = out.get(day, 0.0) + float(vol)
        return sorted(out.items())

    def exercise_sessions(self) -> dict[str, int]:
        """Exercise id -> number of workouts with at least one weighted set."""
        count: dict[str, int] = {}
        for w in self.workouts:
            seen = set()
            for entry in w.get("entries") or []:
                ex_id = str(entry.get("id"))
                if ex_id in seen or not any(self._set_1rm(s) for s in entry.get("sets") or []):
                    continue
                seen.add(ex_id)
                count[ex_id] = count.get(ex_id, 0) + 1
        return count

    def top_exercises(self, n: int = 8) -> list[str]:
        """The `n` most-trained weighted exercises (most sessions first)."""
        sessions = self.exercise_sessions()
        return sorted(sessions, key=lambda k: (-sessions[k], k))[:n]

    def exercise_1rm_series(self, ex_id: str) -> list[tuple[date, float]]:
        """Best estimated 1RM per training day for one exercise."""
        out: dict[date, float] = {}
        key = str(ex_id)
        for w in self.workouts:
            day = _day(w.get("d"))
            if not day:
                continue
            for entry in w.get("entries") or []:
                if str(entry.get("id")) != key:
                    continue
                for s in entry.get("sets") or []:
                    if (est := self._set_1rm(s)) and est > out.get(day, 0):
                        out[day] = round(est, 1)
        return sorted(out.items())

    def pr_timeline(self, limit: int = 12) -> list[dict[str, Any]]:
        """Workouts that set records, newest first, with the exercises' names."""
        out = []
        for w in reversed(self.workouts):
            prs = w.get("prs") or []
            if not isinstance(prs, list) or not prs:
                continue
            records = []
            for ex_id in prs:
                best = None
                for entry in w.get("entries") or []:
                    if str(entry.get("id")) != str(ex_id):
                        continue
                    for s in entry.get("sets") or []:
                        wt = s.get("w")
                        if self._set_1rm(s) and (best is None or wt > best["weight"]):
                            best = {"weight": wt, "reps": s.get("r")}
                records.append({
                    "id": str(ex_id),
                    "name": self.exercise_name(ex_id, self.lang),
                    "names": self.exercise_names(ex_id),
                    **(best or {}),
                })
            out.append({"date": w.get("d"), "workout": w.get("name") or "Workout", "records": records})
            if len(out) >= limit:
                break
        return out

    def progress(self, today: date, days: int = 365, exercises: int = 8) -> dict[str, Any]:
        """Everything the progress card shows, in one payload."""
        since = today - timedelta(days=days)
        ex_out = []
        sessions = self.exercise_sessions()
        for ex_id in self.top_exercises(exercises):
            series = self.exercise_1rm_series(ex_id)
            recent = [(d, v) for d, v in series if d >= since]
            if not recent:
                continue
            first, last = recent[0][1], recent[-1][1]
            ex_out.append({
                "id": ex_id,
                "name": self.exercise_name(ex_id, self.lang),
                "names": self.exercise_names(ex_id),
                "sessions": sessions.get(ex_id, 0),
                "best": max(v for _, v in series),
                "current": last,
                "change": round(last - first, 1),
                "change_pct": round((last - first) / first * 100, 1) if first else None,
                "series": [{"d": d.isoformat(), "v": v} for d, v in recent],
            })
        weights = [(d, w) for d, w in self.daily_weights() if d >= since]
        return {
            "unit": self.unit,
            "days": days,
            "exercises": ex_out,
            "weight": {
                "goal": self.goal_weight(),
                "current": weights[-1][1] if weights else None,
                "start": weights[0][1] if weights else None,
                "series": [{"d": d.isoformat(), "w": w} for d, w in weights],
            },
            "prs": self.pr_timeline(),
        }
