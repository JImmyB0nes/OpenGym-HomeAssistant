"""Pure helpers (no Home Assistant imports) for state edits and derived values.

Everything here works on plain dicts so it can be unit-tested without HA and
re-applied to a fresh document after a 409 conflict (see
`OpenGymRuntime.async_mutate_state`).

Shapes follow openGym's `api/openapi.yaml` (State, Presence, CoachProposal,
IntegrationConnection) and the app's own readers:
- `dayPlan`   ISO date -> routine id or "rest" (wins over `week`)
- `dayNotes`  ISO date -> {tag?, text?, _ts}   (frontend/src/lib/day-notes.js)
- coach scalar changes as in frontend/src/lib/coach.js (currentValue / CHANGE_APPLY)
"""

from __future__ import annotations

import copy
from datetime import date, timedelta
from typing import Any

# --- plan editing ---------------------------------------------------------------

DAY_NOTE_TAGS = ("sick", "travel", "rest", "injured")
NOTE_MAX = 500  # frontend/src/lib/history.js NOTE_MAX


class PlanEditError(ValueError):
    """A plan edit that cannot be applied (translated in the service layer)."""

    def __init__(self, key: str, **placeholders: Any) -> None:
        super().__init__(key)
        self.key = key
        self.placeholders = {k: str(v) for k, v in placeholders.items()}


def _routines(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(r["id"]): r
        for r in (state.get("routines") or [])
        if isinstance(r, dict) and "id" in r
    }


def planned_routine_id(state: dict[str, Any], day: date) -> str | None:
    """Routine id planned on `day` (dayPlan override first, then `week`), None for rest."""
    plan = state.get("dayPlan") or {}
    rid = plan.get(day.isoformat()) if isinstance(plan, dict) else None
    if rid is None:
        week = state.get("week") or {}
        # openGym numbers weekdays Sunday=0 .. Saturday=6; a day may hold a list.
        rid = week.get(str((day.weekday() + 1) % 7)) if isinstance(week, dict) else None
        if isinstance(rid, list):
            rid = rid[0] if rid else None
    if not rid or rid == "rest":
        return None
    return str(rid) if str(rid) in _routines(state) else None


def set_rest_day(state: dict[str, Any], day: date) -> dict[str, Any]:
    """Mark `day` as rest via a dayPlan override."""
    plan = dict(state.get("dayPlan") or {})
    plan[day.isoformat()] = "rest"
    state["dayPlan"] = plan
    return state


def clear_day_override(state: dict[str, Any], day: date) -> dict[str, Any]:
    """Drop a dayPlan override so the weekly plan applies again."""
    plan = dict(state.get("dayPlan") or {})
    plan.pop(day.isoformat(), None)
    state["dayPlan"] = plan
    return state


def move_day(state: dict[str, Any], from_day: date, to_day: date) -> dict[str, Any]:
    """Move the session planned on `from_day` to `to_day` (from becomes rest)."""
    if from_day == to_day:
        raise PlanEditError("same_day")
    rid = planned_routine_id(state, from_day)
    if rid is None:
        raise PlanEditError("nothing_planned", date=from_day.isoformat())
    plan = dict(state.get("dayPlan") or {})
    plan[to_day.isoformat()] = rid
    plan[from_day.isoformat()] = "rest"
    state["dayPlan"] = plan
    return state


def add_day_note(
    state: dict[str, Any],
    day: date,
    today: date,
    now_ms: int,
    tag: str | None = None,
    text: str | None = None,
) -> dict[str, Any]:
    """Write a day note (excuses the day from nudges); empty note clears it.

    Like the app, only today and earlier days take a note, and a cleared
    note is a stamped empty entry rather than a deleted key.
    """
    if day > today:
        raise PlanEditError("note_future")
    if tag is not None and tag not in DAY_NOTE_TAGS:
        raise PlanEditError("note_tag", tag=tag)
    clean_text = (text or "").strip()[:NOTE_MAX]
    entry: dict[str, Any] = {"_ts": int(now_ms)}
    if tag:
        entry["tag"] = tag
    if clean_text:
        entry["text"] = clean_text
    notes = dict(state.get("dayNotes") or {})
    notes[day.isoformat()] = entry
    state["dayNotes"] = notes
    return state


def set_weighin(
    state: dict[str, Any], day: str, weight: float, unit: str
) -> dict[str, Any]:
    """Upsert the day's weigh-in (`bodyweight[].w`)."""
    entries = [dict(b) for b in (state.get("bodyweight") or []) if isinstance(b, dict)]
    existing = next((b for b in entries if b.get("d") == day), None)
    if existing:
        existing["w"] = weight
    else:
        entries.append({"d": day, "w": weight})
    entries.sort(key=lambda b: b.get("d") or "")
    state["bodyweight"] = entries
    state["unit"] = unit
    return state


# --- coach ----------------------------------------------------------------------

# Scalar change types Home Assistant applies itself (mirrors coach.js
# currentValue/CHANGE_APPLY for exactly these). Everything structural
# (add/remove/swap exercise, reorder, week, plan bundles...) stays in the app.
COACH_SCALAR_FIELDS = {
    "sets": "sets", "reps": "reps", "repsMin": "repsMin", "repsMax": "repsMax",
    "sec": "sec", "inc": "inc", "exercise-prog": "prog", "warmup": "warmup",
}
COACH_ROUTINE_FIELDS = {"rename-routine": "name", "routine-prog": "prog"}
COACH_APPLICABLE = set(COACH_SCALAR_FIELDS) | set(COACH_ROUTINE_FIELDS)
COACH_SNAPSHOT_MAX = 3  # coach.js SNAPSHOT_MAX
ROUTINE_NAME_SEEN = 80  # coach.js ROUTINE_NAME_SEEN


def coach_accept_mode(pending: dict[str, Any] | None) -> str | None:
    """How HA can accept the waiting proposal.

    "ack"    debrief: nothing to apply, accepting just records it
    "apply"  review whose every change is a scalar HA can apply
    None     nothing pending, or a plan bundle / structural change (use the app)
    """
    if not isinstance(pending, dict):
        return None
    kind = pending.get("kind")
    if kind == "debrief":
        return "ack"
    if kind == "review":
        changes = pending.get("changes") or []
        if all(isinstance(c, dict) and c.get("type") in COACH_APPLICABLE for c in changes):
            return "apply"
    return None


def _coach_current(state: dict[str, Any], change: dict[str, Any]) -> Any:
    target = change.get("target") or {}
    routine = _routines(state).get(str(target.get("routineId")))
    if routine is None:
        return KeyError
    if change.get("type") == "rename-routine":
        name = routine.get("name")
        return None if name is None else str(name)[:ROUTINE_NAME_SEEN]
    if change.get("type") in COACH_ROUTINE_FIELDS:
        return routine.get(COACH_ROUTINE_FIELDS[change["type"]])
    ex = next((e for e in routine.get("ex") or [] if e.get("id") == target.get("exId")), None)
    if ex is None:
        return KeyError
    return ex.get(COACH_SCALAR_FIELDS[change["type"]])


def apply_coach_changes(
    state: dict[str, Any], pending: dict[str, Any], now_ms: int
) -> tuple[list[str], list[str]]:
    """Apply a review's scalar changes in place; returns (accepted_ids, stale_ids).

    A change is stale (skipped, reported as rejected) when what it names is
    gone or `before` no longer matches the plan, like the app's markStale.
    Before touching anything a {routines, week} snapshot is pushed onto
    `coach.snapshots` (max 3) so the app's "Undo" can revert it.
    """
    accepted: list[str] = []
    stale: list[str] = []
    todo: list[dict[str, Any]] = []
    for change in pending.get("changes") or []:
        cid = str(change.get("id"))
        cur = _coach_current(state, change)
        if cur is KeyError or ("before" in change and cur != change["before"]):
            stale.append(cid)
        else:
            todo.append(change)
    if not todo:
        return accepted, stale
    coach = state.setdefault("coach", {})
    if not isinstance(coach, dict):
        coach = state["coach"] = {}
    snaps = list(coach.get("snapshots") or [])
    snaps.append({
        "at": int(now_ms),
        "proposalId": pending.get("id"),
        "label": (pending.get("summary") or "")[:120],
        "routines": copy.deepcopy(state.get("routines") or []),
        "week": copy.deepcopy(state.get("week") or {}),
    })
    coach["snapshots"] = snaps[-COACH_SNAPSHOT_MAX:]
    routines = _routines(state)
    for change in todo:
        target = change.get("target") or {}
        routine = routines[str(target.get("routineId"))]
        if change["type"] == "rename-routine":
            routine["name"] = str(change.get("after") or routine.get("name") or "")[:80]
        elif change["type"] in COACH_ROUTINE_FIELDS:
            routine[COACH_ROUTINE_FIELDS[change["type"]]] = change.get("after")
        else:
            ex = next(e for e in routine.get("ex") or [] if e.get("id") == target.get("exId"))
            ex[COACH_SCALAR_FIELDS[change["type"]]] = change.get("after")
        accepted.append(str(change.get("id")))
    return accepted, stale


def coach_summary(status: dict[str, Any] | None) -> dict[str, Any]:
    """State + attributes for the Coach status sensor from GET /api/coach/status."""
    status = status or {}
    job = status.get("job") or None
    pending = status.get("pending") or None
    last = status.get("last") or None
    if job:
        state = str(job.get("state") or "running")
    elif pending:
        state = "proposal"
    else:
        state = "idle"
    changes = (pending or {}).get("changes") or []
    return {
        "state": state,
        "job_kind": (job or {}).get("kind"),
        "proposal_kind": (pending or {}).get("kind"),
        "summary": (pending or {}).get("summary"),
        "changes": len(changes),
        "change_list": [
            {"id": c.get("id"), "type": c.get("type"), "why": c.get("why"),
             "before": c.get("before"), "after": c.get("after")}
            for c in changes[:20] if isinstance(c, dict)
        ],
        "score": (pending or {}).get("score"),
        "highlights": (pending or {}).get("highlights"),
        "expires_at": (pending or {}).get("expiresAt"),
        "accept_mode": coach_accept_mode(pending),
        "last_outcome": (last or {}).get("outcome"),
        "last_kind": (last or {}).get("kind"),
        "last_reading": (last or {}).get("reading"),
        "cap": status.get("cap"),
    }


# --- heart rate -----------------------------------------------------------------

BPM_MIN, BPM_MAX = 25, 250  # frontend/src/lib/heart-rate.js
HR_ZONES = ((1, 0.50), (2, 0.60), (3, 0.70), (4, 0.80), (5, 0.90))


def hr_value(raw: Any) -> dict[str, int] | None:
    """openGym stores HR as {avg, max}; older data may hold a plain number."""
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        v = round(raw)
        return {"avg": v, "max": v} if BPM_MIN <= v <= BPM_MAX else None
    if not isinstance(raw, dict):
        return None
    try:
        avg, mx = round(float(raw.get("avg"))), round(float(raw.get("max", raw.get("avg"))))
    except (TypeError, ValueError):
        return None
    if not (BPM_MIN <= avg <= BPM_MAX and BPM_MIN <= mx <= BPM_MAX) or mx < avg:
        return None
    return {"avg": avg, "max": mx}


def hr_zone(bpm: float | None, max_hr: float) -> int | None:
    """Zone 1-5 by % of max HR (50/60/70/80/90 %); 0 below zone 1."""
    if bpm is None or not max_hr:
        return None
    pct = bpm / max_hr
    zone = 0
    for z, lo in HR_ZONES:
        if pct >= lo:
            zone = z
    return zone


def hr_zone_bounds(max_hr: float) -> dict[str, list[int]]:
    bounds = {}
    for i, (z, lo) in enumerate(HR_ZONES):
        hi = HR_ZONES[i + 1][1] if i + 1 < len(HR_ZONES) else 1.0
        bounds[f"zone_{z}"] = [round(max_hr * lo), round(max_hr * hi)]
    return bounds


def latest_watch_hr(events: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    """Newest heart rate in the watch queue (setDone/setHr `hr`, or `restHr`)."""
    best: dict[str, Any] | None = None
    for i, ev in enumerate(events or []):
        if not isinstance(ev, dict):
            continue
        for key, phase in (("hr", "set"), ("restHr", "rest")):
            hr = hr_value(ev.get(key))
            if not hr:
                continue
            at = ev.get("at") if isinstance(ev.get("at"), (int, float)) else None
            rank = (at or 0, i)
            if best is None or rank >= best["_rank"]:
                best = {**hr, "phase": phase, "at": at, "type": ev.get("type"), "_rank": rank}
    if best:
        best.pop("_rank", None)
    return best


# --- live workout / rest timer --------------------------------------------------


def presence_progress(presence: dict[str, Any] | None) -> dict[str, Any]:
    """Exercise x/y and sets done/total from a Presence snapshot."""
    p = presence or {}

    def _int(key: str) -> int | None:
        v = p.get(key)
        return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None

    ex_idx, ex_total = _int("exIdx"), _int("exTotal")
    done, total = _int("setsDone"), _int("setsTotal")
    return {
        "exercise_index": ex_idx + 1 if ex_idx is not None else None,
        "exercise_total": ex_total,
        "sets_done": done,
        "sets_total": total,
        "progress": round(100 * done / total) if done is not None and total else None,
    }


def clamp_rest_seconds(seconds: float | None, default: float | None) -> int:
    """Seconds for POST /api/push/rest-timer: 1..3600, falling back to restSec / 90."""
    value = seconds if seconds else (default if isinstance(default, (int, float)) and default > 0 else 90)
    return int(max(1, min(3600, round(float(value)))))


# --- stats for the card ---------------------------------------------------------


def week_prs(workouts: list[dict[str, Any]], monday: date, today: date) -> int:
    """Personal records set in workouts of this calendar week (`prs` ids)."""
    count = 0
    for w in workouts:
        d = str(w.get("d") or "")[:10]
        if monday.isoformat() <= d <= today.isoformat():
            count += len(w.get("prs") or [])
    return count


def weight_trend(bodyweight: list[dict[str, Any]], points: int = 12) -> list[dict[str, Any]]:
    """The last `points` weigh-ins as [{d, w}], oldest first."""
    rows = [
        {"d": b.get("d"), "w": float(b["w"])}
        for b in bodyweight
        if isinstance(b, dict) and isinstance(b.get("w"), (int, float)) and b.get("d")
    ]
    rows.sort(key=lambda r: r["d"])
    return rows[-points:]


# --- integrations ---------------------------------------------------------------


def our_connections(
    connections: list[dict[str, Any]], webhook_id: str | None
) -> list[dict[str, Any]]:
    """The webhook connections that point at this HA entry.

    openGym masks `info.url` (`https://ha…/api/webhook/…7f3a`), so match on
    the visible tail of our webhook id, falling back to the default label.
    """
    hooks = [c for c in connections or [] if c.get("provider") == "webhook" or c.get("kind") == "webhook"]
    if webhook_id:
        tail = webhook_id[-4:]
        mine = [c for c in hooks if str((c.get("info") or {}).get("url") or "").endswith(tail)]
        if mine:
            return mine
    return [c for c in hooks if c.get("label") == "Home Assistant"]


def failing_connection(conn: dict[str, Any]) -> bool:
    """A connection that needs attention (deliveries failed for good)."""
    return conn.get("status") == "attention" or int(conn.get("failed") or 0) > 0


# --- routine icons ----------------------------------------------------------------
#
# openGym stores an icon *key* in a routine's `emoji` field (frontend/src/lib/glyphs.js),
# older profiles still an emoji. The app draws its own SVGs for the keys; Home Assistant
# gets the closest Material Design icon instead, so nothing has to be bundled.

GLYPH_MDI: dict[str, str] = {
    # Strength
    "figureStrength": "mdi:weight-lifter",
    "arm": "mdi:arm-flex",
    "abs": "mdi:human",
    "legs": "mdi:walk",
    "pullup": "mdi:human-handsup",
    # Equipment
    "dumbbell": "mdi:dumbbell",
    "barbell": "mdi:weight-lifter",
    "kettlebell": "mdi:kettlebell",
    "plate": "mdi:circle-double",
    "machine": "mdi:cog",
    # Cardio
    "figureRun": "mdi:run",
    "bike": "mdi:bike",
    "swim": "mdi:swim",
    "boxing": "mdi:boxing-glove",
    "timer": "mdi:timer-outline",
    # Recovery
    "stretch": "mdi:yoga",
    "moon": "mdi:weather-night",
    "heart": "mdi:heart-pulse",
    "flame": "mdi:fire",
    "bolt": "mdi:lightning-bolt",
    # the first picker's keys and what old emoji map onto
    "trophy": "mdi:trophy",
    "medal": "mdi:medal",
    "crown": "mdi:crown",
    "flag": "mdi:flag-checkered",
    "star": "mdi:star",
    "target": "mdi:target",
    "shield": "mdi:shield",
}
GLYPH_DEFAULT = "figureStrength"  # glyphs.js DEFAULT_GLYPH: a routine without an icon
GLYPH_FALLBACK_MDI = "mdi:dumbbell"  # a key this version does not know yet

# glyphs.js LEGACY: emoji stored before the icon picker -> icon key
GLYPH_LEGACY: dict[str, str] = {
    "💪": "arm", "🦾": "arm", "🫸": "figureStrength", "🫷": "pullup",
    "🏋️": "dumbbell", "🏋": "dumbbell", "🏋️‍♀️": "dumbbell",
    "🦵": "legs", "🍑": "legs",
    "🔥": "flame", "⚡": "bolt", "💥": "bolt", "🧨": "bolt", "😤": "flame",
    "🏃": "figureRun", "🏃‍♀️": "figureRun", "🚴": "bike", "🏊": "swim",
    "🤸": "stretch", "🧘": "stretch", "🧘‍♀️": "stretch",
    "🥊": "boxing", "🧗": "pullup", "⛰️": "figureRun", "🏔️": "figureRun", "🚀": "bolt",
    "🎯": "target", "🏆": "trophy", "🥇": "medal", "⭐": "star", "🌟": "star",
    "👑": "crown", "🛡️": "shield", "⚔️": "shield", "❤️‍🔥": "heart",
    "🦍": "kettlebell", "🐂": "barbell", "🐻": "kettlebell", "🦁": "boxing",
    "🐺": "figureRun", "🦈": "swim", "🤖": "machine",
}


def routine_glyph(raw: Any) -> str | None:
    """openGym's icon key for a routine's `emoji` value (glyphs.js glyphOf).

    None for a value that is neither a known key nor a known emoji.
    """
    if not raw or not isinstance(raw, str):
        return GLYPH_DEFAULT
    value = raw.strip()
    if value in GLYPH_MDI:
        return value
    if value in GLYPH_LEGACY:
        return GLYPH_LEGACY[value]
    base = [c for c in value if c not in ("\ufe0f", "\u200d")]
    if base and base[0] in GLYPH_LEGACY:
        return GLYPH_LEGACY[base[0]]
    return None


def routine_icon(raw: Any) -> str:
    """Material Design icon for a routine's `emoji` value; never the raw key."""
    key = routine_glyph(raw)
    return GLYPH_MDI.get(key or "", GLYPH_FALLBACK_MDI)


# --- exercise muscles (custom exercises) ---------------------------------------------
#
# Catalogue exercises come pre-computed from openGym's own muscleWeightsOf() (see
# scripts/build_exercise_db.mjs). Custom exercises carry free text or just a body part;
# this mirrors frontend/src/lib/muscles.js for them.

MUSCLE_SLUGS = (
    "trapezius", "deltoids", "chest", "upper-back", "serratus",
    "biceps", "triceps", "forearm",
    "abs", "obliques", "lower-back",
    "gluteal", "quadriceps", "hamstring", "adductors", "hip-flexors",
    "calves", "tibialis",
)
MUSCLE_ALIAS: dict[str, str | None] = {
    "abs": "abs", "pectorals": "chest", "biceps": "biceps", "glutes": "gluteal",
    "delts": "deltoids", "triceps": "triceps", "upper back": "upper-back",
    "lats": "upper-back", "calves": "calves", "quads": "quadriceps",
    "forearms": "forearm", "hamstrings": "hamstring", "spine": "lower-back",
    "traps": "trapezius", "adductors": "adductors", "serratus anterior": "serratus",
    "abductors": "gluteal", "levator scapulae": "trapezius",
    "shoulders": "deltoids", "deltoids": "deltoids", "rear deltoids": "deltoids",
    "rotator cuff": "deltoids", "quadriceps": "quadriceps", "core": "abs",
    "abdominals": "abs", "lower abs": "abs", "chest": "chest", "upper chest": "chest",
    "hip flexors": "hip-flexors", "obliques": "obliques", "lower back": "lower-back",
    "rhomboids": "upper-back", "trapezius": "trapezius", "back": "upper-back",
    "latissimus dorsi": "upper-back", "brachialis": "biceps", "soleus": "calves",
    "shins": "tibialis", "wrists": "forearm", "wrist flexors": "forearm",
    "wrist extensors": "forearm", "grip muscles": "forearm", "groin": "adductors",
    "inner thighs": "adductors",
    "ankles": None, "feet": None, "hands": None, "ankle stabilizers": None,
    "sternocleidomastoid": None,
}
MUSCLES_BY_BODYPART: dict[str, dict[str, float]] = {
    "chest": {"chest": 1},
    "back": {"upper-back": 0.75, "lower-back": 0.25},
    "shoulders": {"deltoids": 1},
    "upper arms": {"biceps": 0.5, "triceps": 0.5},
    "lower arms": {"forearm": 1},
    "waist": {"abs": 0.7, "obliques": 0.3},
    "upper legs": {"quadriceps": 0.4, "hamstring": 0.35, "gluteal": 0.25},
    "lower legs": {"calves": 0.8, "tibialis": 0.2},
    "neck": {"trapezius": 1},
    "full body": {"chest": 0.2, "upper-back": 0.2, "gluteal": 0.2,
                  "quadriceps": 0.2, "hamstring": 0.1, "abs": 0.1},
    "cardio": {},
}
_SECONDARY = 0.4


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return [] if value is None or value == "" else [value]


def canonical_muscle(value: Any) -> str | None:
    name = str(value or "").lower().strip()
    if name in MUSCLE_SLUGS:
        return name
    return MUSCLE_ALIAS.get(name)


def custom_muscle_weights(ex: dict[str, Any]) -> dict[str, float]:
    """muscles.js weightsOf() for a custom exercise or a history snapshot."""
    weights = ex.get("muscleWeights")
    if isinstance(weights, dict):
        snap = {
            slug: float(w) for slug, w in weights.items()
            if slug in MUSCLE_SLUGS and isinstance(w, (int, float)) and 0 < w <= 1
        }
        if snap:
            return snap
    out: dict[str, float] = {}

    def add(name: Any, w: float) -> None:
        if slug := canonical_muscle(name):
            out[slug] = max(out.get(slug, 0.0), w)

    primary = next((ex[k] for k in ("primaries", "primaryMuscles", "primary") if k in ex), None)
    secondary = next((ex[k] for k in ("secondaries", "secondaryMuscles", "secondary") if k in ex), None)
    parts = [*_as_list(primary), *_as_list(secondary)]
    groups = next((ex[k] for k in ("muscleGroups", "muscles", "targetMuscles") if k in ex), None)
    if any(canonical_muscle(v) for v in parts):
        for m in _as_list(primary):
            add(m, 1.0)
        for m in _as_list(secondary):
            add(m, _SECONDARY)
    elif groups:
        for m in _as_list(groups):
            add(m, 1.0)
    else:
        add(ex.get("tg"), 1.0)
        add(ex.get("mg"), _SECONDARY)
        for m in _as_list(ex.get("sm")):
            add(m, _SECONDARY)
    if not out:
        out = dict(MUSCLES_BY_BODYPART.get(str(ex.get("bp") or ""), {}))
    return {k: float(v) for k, v in out.items() if v > 0}


def cap_words(text: str) -> str:
    """format.js capWords: upper-case the first letter of every word."""
    out = []
    prev = ""
    for ch in text:
        out.append(ch.upper() if (prev == "" or prev in " (-/\t\n") and ch.islower() else ch)
        prev = ch
    return "".join(out)


# --- week streak (frontend/src/lib/streak.js) -------------------------------------------

STREAK_FREEZE_EVERY = 4
STREAK_FREEZE_MAX = 2


def week_streak(workout_days: list[date], today: date, week_start: int = 0) -> dict[str, Any]:
    """openGym's week streak: weeks in a row with a workout, with freezes.

    `week_start` is 0 for Monday, 6 for Sunday (date.weekday()). The current
    week without a workout is open: it neither counts nor breaks the run.
    """

    def key(d: date) -> date:
        return d - timedelta(days=(d.weekday() - week_start) % 7)

    cur = key(today)
    trained = {key(d) for d in workout_days if d and key(d) <= cur}
    empty = {"current": 0, "best": 0, "freezes": 0, "this_week_done": False}
    if not trained:
        return empty
    wk = max(min(trained), cur - timedelta(weeks=1500))
    run = best = freezes = earned = 0
    while wk <= cur:
        if wk in trained:
            run += 1
            earned += 1
            if earned % STREAK_FREEZE_EVERY == 0 and freezes < STREAK_FREEZE_MAX:
                freezes += 1
        elif wk != cur:
            if freezes > 0:
                freezes -= 1
            else:
                run = earned = freezes = 0
        best = max(best, run)
        wk += timedelta(weeks=1)
    return {"current": run, "best": best, "freezes": freezes, "this_week_done": cur in trained}
