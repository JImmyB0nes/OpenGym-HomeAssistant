"""Constants for the openGym integration."""

from __future__ import annotations

DOMAIN = "opengym"

CONF_WEBHOOK_ID = "webhook_id"
CONF_SECRET = "secret"
CONF_NAME = "name"

ATTR_EVENT_ID = "event_id"
ATTR_EVENT_TYPE = "event_type"
ATTR_CREATED_AT = "created_at"
ATTR_TEST = "test"

HEADER_SIGNATURE = "X-OpenGym-Signature"
HEADER_EVENT = "X-OpenGym-Event"
HEADER_DELIVERY = "X-OpenGym-Delivery"

# openGym event type -> Home Assistant event bus name
EVENT_TYPES = {
    "workout.finished": "opengym_workout_finished",
    "workout.pr": "opengym_personal_record",
    "weighin.logged": "opengym_weighin_logged",
}

# Max clock skew accepted in the signature timestamp (seconds)
SIGNATURE_MAX_AGE = 300

STORAGE_VERSION = 1
