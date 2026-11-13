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

# Reverse: HA event name -> openGym type (for device triggers)
HA_EVENT_TO_OPENGYM: Final = {v: k for k, v in EVENT_TYPES.items()}

# Max clock skew accepted in the signature timestamp (seconds)
SIGNATURE_MAX_AGE = 300

DEFAULT_POLL_INTERVAL = 15  # minutes
MIN_POLL_INTERVAL = 1
SCAN_INTERVAL = timedelta(minutes=DEFAULT_POLL_INTERVAL)

STORAGE_VERSION = 1

# Services
SERVICE_LOG_WEIGHIN = "log_weighin"
SERVICE_TRIGGER_TEST = "trigger_test_event"

# Muscle groups we surface for the coverage / recovery sensors. These follow the
# coarse grouping openGym's own muscle map uses; the key is the catalogue tag,
# the value is the display name.
MUSCLE_GROUPS: Final[dict[str, str]] = {
    "chest": "Chest",
    "back": "Back",
    "shoulders": "Shoulders",
    "biceps": "Biceps",
    "triceps": "Triceps",
    "legs": "Legs",
    "glutes": "Glutes",
    "core": "Core",
    "forearms": "Forearms",
    "traps": "Traps",
    "lats": "Lats",
}
