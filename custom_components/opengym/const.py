"""Constants for the openGym integration."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Final

DOMAIN = "opengym"

MANIFEST_PATH = Path(__file__).parent / "manifest.json"
try:
    INTEGRATION_VERSION: Final[str] = json.loads(
        MANIFEST_PATH.read_text(encoding="utf-8")
    ).get("version", "0.0.0")
except (OSError, ValueError):  # pragma: no cover
    INTEGRATION_VERSION = "0.0.0"

# Static path the bundled frontend (card + body geometry) is served from.
URL_BASE: Final[str] = "/opengym"
JSMODULES: Final[list[dict[str, str]]] = [
    {
        "name": "openGym Muscle Card",
        "filename": "opengym-muscle-card.js",
        "version": INTEGRATION_VERSION,
    }
]

CONF_URL = "url"
CONF_TOKEN = "token"
CONF_SECRET = "secret"
CONF_NAME = "name"
CONF_WEBHOOK_ID = "webhook_id"
CONF_POLL_INTERVAL = "poll_interval"
CONF_AUTO_WEBHOOK = "auto_webhook"

ATTR_EVENT_ID = "event_id"
ATTR_EVENT_TYPE = "event_type"
ATTR_CREATED_AT = "created_at"
ATTR_TEST = "test"

HEADER_SIGNATURE = "X-OpenGym-Signature"
HEADER_EVENT = "X-OpenGym-Event"
HEADER_DELIVERY = "X-OpenGym-Delivery"

# openGym event type -> Home Assistant event bus name
EVENT_TYPES: Final = {
    "workout.finished": "opengym_workout_finished",
    "workout.pr": "opengym_personal_record",
    "weighin.logged": "opengym_weighin_logged",
}

# Max clock skew accepted in the signature timestamp (seconds)
SIGNATURE_MAX_AGE = 300

DEFAULT_POLL_INTERVAL = 15  # minutes
MIN_POLL_INTERVAL = 1
MAX_POLL_INTERVAL = 1440

# Fast tick: revision check + live bits (seconds, 0 = off)
CONF_REV_INTERVAL = "rev_interval"
DEFAULT_REV_INTERVAL = 30
MAX_REV_INTERVAL = 3600
# Max heart rate for the watch HR zones (bpm)
CONF_MAX_HEART_RATE = "max_heart_rate"
DEFAULT_MAX_HEART_RATE = 190

# Services
SERVICE_LOG_WEIGHIN = "log_weighin"
SERVICE_TRIGGER_TEST = "trigger_test_event"
SERVICE_GET_WORKOUT_HISTORY = "get_workout_history"
SERVICE_GET_ROUTINES = "get_routines"
SERVICE_START_REST_TIMER = "start_rest_timer"
SERVICE_CANCEL_REST_TIMER = "cancel_rest_timer"
SERVICE_COACH_REVIEW = "coach_review"
SERVICE_SET_REST_DAY = "set_rest_day"
SERVICE_MOVE_DAY = "move_day"
SERVICE_ADD_DAY_NOTE = "add_day_note"

# Muscle groups from openGym's exercise-muscle map (primaries vocabulary).
MUSCLES: Final[dict[str, str]] = {
    "chest": "Chest",
    "upper-back": "Upper Back",
    "lower-back": "Lower Back",
    "trapezius": "Traps",
    "deltoids": "Shoulders",
    "biceps": "Biceps",
    "triceps": "Triceps",
    "forearms": "Forearms",
    # (kept for entity-id stability; openGym's map calls this `forearm`, see _CANON)
    "quadriceps": "Quadriceps",
    "hamstring": "Hamstrings",
    "adductors": "Adductors",
    "calves": "Calves",
    "gluteal": "Glutes",
    "abs": "Core",
}

# openGym's muscle map spells a few slugs differently than our entity keys.
_CANON: Final[dict[str, str]] = {"forearm": "forearms"}

# Weekly working sets per main muscle group: [low, high] (openGym's hypertrophy
# volume landmarks, same defaults the openGym app ships in muscle-targets.js).
# User overrides live in the state document as `muscleTargets`.
MUSCLE_TARGETS: Final[dict[str, tuple[int, int]]] = {
    "chest": (10, 20),
    "upper-back": (10, 20),
    "deltoids": (8, 20),
    "biceps": (8, 18),
    "triceps": (6, 16),
    "quadriceps": (8, 18),
    "hamstring": (6, 16),
    "gluteal": (4, 16),
    "calves": (8, 16),
    "abs": (6, 16),
}

# Slugs the body map is drawn for, in head-to-toe order (openGym's MUSCLES).
MAP_SLUGS: Final[tuple[str, ...]] = (
    "trapezius", "deltoids", "chest", "upper-back", "serratus",
    "biceps", "triceps", "forearm",
    "abs", "obliques", "lower-back",
    "gluteal", "quadriceps", "hamstring", "adductors", "hip-flexors",
    "calves", "tibialis",
)

# A supporting muscle counts this much against a primary (openGym's SECONDARY).
SECONDARY_WEIGHT: Final[float] = 0.4

# Days a muscle counts as still recovering after being trained.
RECOVERY_DAYS = 2

# --- fatigue model (mirrors openGym's frontend/src/lib/recovery.js) ---------
# Fatigue stimulus in effective hard sets per muscle, decaying exponentially
# with a muscle-specific half-life. Lower body (heavier loads, more damage)
# recovers slower; small/core muscles share the fast 24 h lane.
FATIGUE_HALF_LIFE_H: Final[dict[str, float]] = {
    "trapezius": 30, "deltoids": 24, "chest": 30, "upper-back": 30,
    "serratus": 24, "biceps": 24, "triceps": 24, "forearm": 24,
    "abs": 24, "obliques": 24, "lower-back": 48, "gluteal": 48,
    "quadriceps": 48, "hamstring": 48, "adductors": 48, "hip-flexors": 24,
    "calves": 48, "tibialis": 24,
}
FATIGUE_HALF_LIFE_DEFAULT_H: Final[float] = 30

# One full session (~8 hard sets, the per-session growth plateau) scores 1.0.
FATIGUE_SETS_PER_UNIT: Final[float] = 8.0
# Beyond ~12 sets the growth response plateaus — junk volume must not
# extend the red tail linearly.
FATIGUE_MAX_SETS_PER_SESSION: Final[int] = 12
# Scan bound: after 30 days even a 24 h half-life retains < 1e-9.
FATIGUE_SCAN_DAYS: Final[int] = 30

# Fatigue buckets (openGym's FATIGUE_STATES): < 0.25 ready, 0.25–0.5
# recovering, above that fatigued.
FATIGUE_READY_MAX: Final[float] = 0.25
FATIGUE_RECOVERING_MAX: Final[float] = 0.5

# Presence counts as "training now" for at most this many seconds after the
# last heartbeat (openGym expires live entries after 70 s).
PRESENCE_MAX_AGE = 90

# Epley estimate for 1RM: w * (1 + r / K)
EPLEY_K = 30

SCAN_INTERVAL = timedelta(minutes=DEFAULT_POLL_INTERVAL)
