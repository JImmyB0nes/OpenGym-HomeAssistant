"""Constants for the openGym integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN = "opengym"

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

# Services
SERVICE_LOG_WEIGHIN = "log_weighin"
SERVICE_TRIGGER_TEST = "trigger_test_event"

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
    "quadriceps": "Quadriceps",
    "hamstring": "Hamstrings",
    "adductors": "Adductors",
    "calves": "Calves",
    "gluteal": "Glutes",
    "abs": "Core",
}

# Days a muscle counts as still recovering after being trained.
RECOVERY_DAYS = 2

# Presence counts as "training now" for at most this many seconds after the
# last heartbeat (openGym expires live entries after 70 s).
PRESENCE_MAX_AGE = 90

# Epley estimate for 1RM: w * (1 + r / K)
EPLEY_K = 30

SCAN_INTERVAL = timedelta(minutes=DEFAULT_POLL_INTERVAL)
