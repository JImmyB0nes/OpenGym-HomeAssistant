"""Assist (voice) intents for openGym.

Home Assistant loads this platform with its `intent` integration. The
sentences that trigger these intents ship in `sentences/<lang>.yaml`; the
integration installs them into `<config>/custom_sentences/<lang>/` (see
`sentences.py`), so "Wann ist mein nächstes Training?" or "Trag 80,4 Kilo
ein" work out of the box with the built-in conversation agent.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, intent
from homeassistant.util import dt as dt_util

from . import logic
from .api import OpenGymConnectionError, OpenGymError, OpenGymFeatureOffError
from .const import COACH_WAIT_VOICE, DOMAIN

INTENT_NEXT_WORKOUT = "OpenGymNextWorkout"
INTENT_WEEK_SUMMARY = "OpenGymWeekSummary"
INTENT_LAST_WORKOUT = "OpenGymLastWorkout"
INTENT_LOG_WEIGHT = "OpenGymLogWeight"
INTENT_START_REST = "OpenGymStartRestTimer"
INTENT_CANCEL_REST = "OpenGymCancelRestTimer"
INTENT_RECOMMEND = "OpenGymRecommendation"
INTENT_COACH_ASK = "OpenGymCoachAsk"
INTENT_COACH_DEBRIEF = "OpenGymCoachDebrief"

INTENTS = (
    INTENT_NEXT_WORKOUT,
    INTENT_WEEK_SUMMARY,
    INTENT_LAST_WORKOUT,
    INTENT_LOG_WEIGHT,
    INTENT_START_REST,
    INTENT_CANCEL_REST,
    INTENT_RECOMMEND,
    INTENT_COACH_ASK,
    INTENT_COACH_DEBRIEF,
)


async def async_setup_intents(hass: HomeAssistant) -> None:
    """Register the openGym intent handlers."""
    for handler in (
        NextWorkoutHandler(),
        WeekSummaryHandler(),
        LastWorkoutHandler(),
        LogWeightHandler(),
        StartRestHandler(),
        CancelRestHandler(),
        RecommendationHandler(),
        CoachAskHandler(),
        CoachDebriefHandler(),
    ):
        intent.async_register(hass, handler)


def _runtime(hass: HomeAssistant) -> Any | None:
    """The first loaded openGym entry's runtime (voice has no entry picker)."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        runtime = getattr(entry, "runtime_data", None)
        if runtime is not None and runtime.coordinator.data is not None:
            return runtime
    return None


class _OpenGymHandler(intent.IntentHandler):
    """Common plumbing: find the entry, answer in the request's language."""

    platforms = None

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        response = intent_obj.create_response()
        lang = intent_obj.language or intent_obj.hass.config.language
        runtime = _runtime(intent_obj.hass)
        if runtime is None:
            response.async_set_speech(logic.speech("no_entry", lang))
            return response
        slots = self.async_validate_slots(intent_obj.slots)
        try:
            text = await self._answer(intent_obj.hass, runtime, slots, lang)
        except (OpenGymError, HomeAssistantError):
            # unreachable, revision conflict, rejected write: say so instead
            # of the agent's generic "an unexpected error occurred"
            text = logic.speech("no_entry", lang)
        response.async_set_speech(text)
        return response

    async def _answer(self, hass: HomeAssistant, runtime: Any, slots: dict, lang: str) -> str:
        raise NotImplementedError


class NextWorkoutHandler(_OpenGymHandler):
    intent_type = INTENT_NEXT_WORKOUT
    description = "Tells when the next openGym workout is planned and what it is"

    async def _answer(self, hass, runtime, slots, lang) -> str:
        today = dt_util.now().date()
        return logic.speech_next(runtime.coordinator.data.next_workout(today), today, lang)


class WeekSummaryHandler(_OpenGymHandler):
    intent_type = INTENT_WEEK_SUMMARY
    description = "Summarises this week's openGym workouts"

    async def _answer(self, hass, runtime, slots, lang) -> str:
        state = runtime.coordinator.data
        today = dt_util.now().date()
        count = state.week_count(today)
        if not count:
            return logic.speech("week_none", lang)
        text = logic.speech(
            "week_one" if count == 1 else "week", lang, n=count, volume=float(round(state.week_volume(today))), unit=state.unit
        )
        streak = state.week_streak(today).get("current") or 0
        if streak > 1:
            text += logic.speech("streak", lang, n=streak)
        return text


class LastWorkoutHandler(_OpenGymHandler):
    intent_type = INTENT_LAST_WORKOUT
    description = "Tells when the last openGym workout was"

    async def _answer(self, hass, runtime, slots, lang) -> str:
        state = runtime.coordinator.data
        last = state.last_workout()
        day = state.last_workout_day()
        if not last or not day:
            return logic.speech("last_none", lang)
        days = (dt_util.now().date() - day).days
        return logic.speech(
            "last", lang, name=last.get("name") or "Workout", when=logic.speech_days_ago(days, lang)
        )


class LogWeightHandler(_OpenGymHandler):
    intent_type = INTENT_LOG_WEIGHT
    description = "Logs a body-weight measurement in openGym"
    slot_schema = {vol.Required("weight"): cv.string, vol.Optional("unit"): vol.In(["kg", "lb"])}

    async def _answer(self, hass, runtime, slots, lang) -> str:
        state = runtime.coordinator.data
        unit = state.unit if state else "kg"
        weight = logic.parse_spoken_number(slots["weight"]["value"])
        spoken = (slots.get("unit") or {}).get("value") or unit
        if weight is not None:
            # "176 pounds" on a kg profile is stored as kg (and the other way round)
            weight = logic.convert_weight(weight, spoken, unit)
        if weight is None or not 20 <= weight <= 400:
            return logic.speech("bad_weight", lang)
        day = str(dt_util.now().date())
        await runtime.async_mutate_state(
            lambda doc: logic.set_weighin(doc, day, weight, unit)
        )
        goal = runtime.coordinator.data.goal_weight() if runtime.coordinator.data else None
        if goal is None:
            return logic.speech("weighin", lang, weight=weight, unit=unit)
        delta = round(weight - goal, 1)
        if delta <= 0:
            return logic.speech("weighin_at_goal", lang, weight=weight, unit=unit)
        return logic.speech("weighin_goal", lang, weight=weight, unit=unit, delta=float(delta))


class StartRestHandler(_OpenGymHandler):
    intent_type = INTENT_START_REST
    description = "Starts the openGym rest timer on your devices"
    slot_schema = {vol.Optional("seconds"): vol.Coerce(int), vol.Optional("minutes"): vol.Coerce(int)}

    async def _answer(self, hass, runtime, slots, lang) -> str:
        wanted = None
        if "seconds" in slots:
            wanted = slots["seconds"]["value"]
        elif "minutes" in slots:
            wanted = slots["minutes"]["value"] * 60
        coordinator = runtime.coordinator
        default = coordinator.rest_default_seconds()
        seconds = logic.clamp_rest_seconds(wanted, default)
        await runtime.client.start_rest_timer(seconds)
        coordinator.set_rest_timer(seconds)
        return logic.speech("rest_started", lang, seconds=seconds)


class CancelRestHandler(_OpenGymHandler):
    intent_type = INTENT_CANCEL_REST
    description = "Stops the openGym rest timer"

    async def _answer(self, hass, runtime, slots, lang) -> str:
        await runtime.client.cancel_rest_timer()
        runtime.coordinator.set_rest_timer(None)
        return logic.speech("rest_cancelled", lang)


class RecommendationHandler(_OpenGymHandler):
    intent_type = INTENT_RECOMMEND
    description = "Suggests which muscle groups (and routine) suit a session today"

    async def _answer(self, hass, runtime, slots, lang) -> str:
        rec = runtime.coordinator.data.recommendation(dt_util.now().date())
        return logic.recommendation_text(rec, lang)


async def _coach_voice(runtime: Any, kind: str, lang: str, **job: Any) -> str:
    """Start a Coach job, wait a voice-friendly while, speak the result."""
    coordinator = runtime.coordinator
    try:
        job_id = await coordinator.async_start_coach_job(kind, lang=lang, **job)
    except OpenGymFeatureOffError:
        return logic.speech("coach_off", lang)
    except OpenGymConnectionError as err:
        if err.status in (403, 409, 429):
            message, code = err.server_message()
            return logic.coach_refusal_text(code, message, lang)
        raise
    result = await coordinator.async_wait_coach(job_id, COACH_WAIT_VOICE)
    if result is None:
        coordinator.coach_notify_when_done(job_id)
        return logic.speech("coach_thinking", lang)
    if result.get("status") == "failed":
        return logic.speech("coach_failed", lang, reason=result.get("error") or "?")
    if kind == "ask":
        return str(result.get("answer") or "")
    return logic.speech_debrief(result, lang)


class CoachAskHandler(_OpenGymHandler):
    intent_type = INTENT_COACH_ASK
    description = "Asks the openGym Coach a question and reads out the answer"
    slot_schema = {vol.Required("question"): cv.string}

    async def _answer(self, hass, runtime, slots, lang) -> str:
        question = str(slots["question"]["value"]).strip()
        if not question:
            return logic.speech("coach_no_question", lang)
        return await _coach_voice(runtime, "ask", lang, question=question)


class CoachDebriefHandler(_OpenGymHandler):
    intent_type = INTENT_COACH_DEBRIEF
    description = "Has the openGym Coach rate the latest workout"

    async def _answer(self, hass, runtime, slots, lang) -> str:
        return await _coach_voice(runtime, "debrief", lang)


__all__ = ["INTENTS", "async_setup_intents"]
