"""0.12: event entities, training recommendation, Coach questions and debriefs."""
from __future__ import annotations

from datetime import timedelta

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er, intent
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMockResponse

from test_smoke import H, TODAY, URL, WEBHOOK_ID, _calls, _mock_all, _setup, _state

COORD = "custom_components.opengym.coordinator"


def _ids(hass, entry) -> dict[str, str]:
    reg = er.async_get(hass)
    return {e.translation_key: e.entity_id for e in er.async_entries_for_config_entry(reg, entry.entry_id)}


class CoachServer:
    """A tiny openGym Coach: queued -> running -> answer/debrief pending."""

    def __init__(self, polls_until_done: int = 2, fail: str | None = None) -> None:
        self.polls_until_done = polls_until_done
        self.fail = fail
        self.job: dict | None = None
        self.polls = 0
        self.resolved = 0

    async def post_ask(self, method, url, data):
        self.job, self.polls = {"id": "a1b2c3d4e5f60718", "kind": "ask", "text": data["text"]}, 0
        return AiohttpClientMockResponse(method, url, status=202, headers=H, json={"job": {"id": self.job["id"]}})

    async def post_debrief(self, method, url, data):
        self.job, self.polls = {"id": "d1e2b3r4i5e6f708", "kind": "debrief", "workout": (data or {}).get("workoutId")}, 0
        return AiohttpClientMockResponse(method, url, status=202, headers=H, json={"job": {"id": self.job["id"]}})

    async def post_resolve(self, method, url, data):
        self.resolved += 1
        self.job = None
        return AiohttpClientMockResponse(method, url, headers=H, json={"ok": True})

    async def get_status(self, method, url, data):
        body = {"job": None, "pending": None, "cap": {}, "maxMessageLen": 2000, "last": None}
        if self.job:
            self.polls += 1
            if self.polls < self.polls_until_done:
                body["job"] = {"id": self.job["id"], "kind": self.job["kind"], "state": "running"}
            elif self.fail:
                body["last"] = {"id": self.job["id"], "kind": self.job["kind"], "outcome": "failed",
                                "errorClass": "quota", "message": self.fail}
            elif self.job["kind"] == "ask":
                body["pending"] = {"id": self.job["id"], "kind": "ask", "answer": f"Ja, {self.job['text']} passt heute."}
            else:
                body["pending"] = {"id": self.job["id"], "kind": "debrief", "score": 8, "summary": "Starke Einheit.",
                                   "highlights": ["Bankdrücken +2,5 kg"], "nextTime": ["Einen Satz mehr"],
                                   "workout": {"name": "Push", "d": TODAY.isoformat()}}
        return AiohttpClientMockResponse(method, url, headers=H, json=body)


async def _setup_coach(hass, aioclient_mock, monkeypatch, server: CoachServer, options=None):
    """Like _setup, but the Coach endpoints are served by `server` (registered first: first match wins)."""
    monkeypatch.setattr(f"{COORD}.COACH_POLL_SECONDS", 0)
    aioclient_mock.get(f"{URL}/api/coach/status", side_effect=server.get_status)
    aioclient_mock.post(f"{URL}/api/coach/ask", side_effect=server.post_ask)
    aioclient_mock.post(f"{URL}/api/coach/debrief", side_effect=server.post_debrief)
    aioclient_mock.post(f"{URL}/api/coach/pending/resolve", side_effect=server.post_resolve)
    _mock_all(aioclient_mock)
    entry = MockConfigEntry(domain="opengym", title="openGym", data={
        "url": URL, "token": "tok", "webhook_id": WEBHOOK_ID, "secret": "", "auto_webhook": False,
    }, options={"rev_interval": 0, **(options or {})})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_event_entities_follow_webhooks(hass: HomeAssistant, aioclient_mock, hass_client_no_auth) -> None:
    entry = await _setup(hass, aioclient_mock)
    ids = _ids(hass, entry)
    for key in ("workout_finished", "personal_record", "weigh_in", "coach_event"):
        assert key in ids, key
    assert ids["workout_finished"] == "event.opengym_workout_finished"
    assert hass.states.get(ids["workout_finished"]).state == "unknown"
    client = await hass_client_no_auth()
    resp = await client.post(f"/api/webhook/{WEBHOOK_ID}", json={
        "version": 1, "id": "dlv1", "type": "workout.finished", "createdAt": "2026-11-24T18:00:00Z",
        "data": {"workout": {"name": "Push", "date": TODAY.isoformat(), "durationMin": 54, "unit": "kg",
                             "totals": {"exercises": 4, "sets": 18, "reps": 140, "volume": 12400}, "records": []}}})
    assert resp.status == 200
    await hass.async_block_till_done()
    st = hass.states.get(ids["workout_finished"])
    assert st.state != "unknown"
    assert st.attributes["event_type"] == "workout_finished"
    assert st.attributes["name"] == "Push" and st.attributes["volume"] == 12400 and st.attributes["sets"] == 18
    # the other event entities did not fire
    assert hass.states.get(ids["weigh_in"]).state == "unknown"
    await client.post(f"/api/webhook/{WEBHOOK_ID}", json={
        "version": 1, "id": "dlv2", "type": "weighin.logged", "test": True,
        "data": {"weighin": {"date": TODAY.isoformat(), "weight": 80.4, "unit": "kg"}}})
    await hass.async_block_till_done()
    wi = hass.states.get(ids["weigh_in"]).attributes
    assert wi["weight"] == 80.4 and wi["test"] is True
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_event_entities_without_coach(hass: HomeAssistant, aioclient_mock) -> None:
    entry = await _setup(hass, aioclient_mock, coach=False)
    ids = _ids(hass, entry)
    assert "workout_finished" in ids and "coach_event" not in ids
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_recommendation_sensor_and_voice(hass: HomeAssistant, aioclient_mock) -> None:
    assert await async_setup_component(hass, "intent", {})
    entry = await _setup(hass, aioclient_mock)
    ids = _ids(hass, entry)
    st = hass.states.get(ids["recommendation"])
    assert st.entity_id == "sensor.opengym_training_recommendation"
    assert st.attributes["kind"] in ("train", "rest", "free")
    if st.attributes["kind"] == "train":
        assert st.attributes["muscles"] and not set(st.attributes["muscles"]) & set(st.attributes["fatigued"])
    resp = await intent.async_handle(hass, "test", "OpenGymRecommendation", {}, language="de")
    assert resp.speech["plain"]["speech"] == st.attributes["text"].replace("Ideal today", "Heute ideal") or \
        resp.speech["plain"]["speech"].startswith(("Heute ideal", "Heute lieber Pause", "Alles ist erholt"))
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_coach_ask_service(hass: HomeAssistant, aioclient_mock, monkeypatch) -> None:
    server = CoachServer(polls_until_done=3)
    entry = await _setup_coach(hass, aioclient_mock, monkeypatch, server)
    ids = _ids(hass, entry)
    events = []
    hass.bus.async_listen("opengym_coach_answer", events.append)
    res = await hass.services.async_call(
        "opengym", "coach_ask", {"question": "Beine", "lang": "de"}, blocking=True, return_response=True)
    assert res["status"] == "answered" and res["answer"] == "Ja, Beine passt heute.", res
    assert _calls(aioclient_mock, "POST", "/api/coach/ask")[-1][2] == {"text": "Beine", "lang": "de"}
    assert server.resolved == 1  # read here -> cleared, the app's Coach screen is free again
    await hass.async_block_till_done()
    assert events and events[0].data["answer"] == "Ja, Beine passt heute."
    coach = hass.states.get(ids["coach_event"])
    assert coach.attributes["event_type"] == "answer" and coach.attributes["question"] == "Beine"
    assert hass.states.get(ids["coach_status"]).attributes["last_answer"]["answer"] == "Ja, Beine passt heute."
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_coach_answer_from_the_app_is_left_alone(hass: HomeAssistant, aioclient_mock, monkeypatch) -> None:
    """A question asked in the app must reach the app, not be swallowed by HA."""
    server = CoachServer()
    entry = await _setup_coach(hass, aioclient_mock, monkeypatch, server)
    server.job = {"id": "fromtheapp000001", "kind": "ask", "text": "x"}
    server.polls = 99
    await entry.runtime_data.coordinator._async_update_coach()
    assert server.resolved == 0
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_coach_late_answer_becomes_notification(hass: HomeAssistant, aioclient_mock, monkeypatch) -> None:
    assert await async_setup_component(hass, "persistent_notification", {})
    server = CoachServer(polls_until_done=50)
    entry = await _setup_coach(hass, aioclient_mock, monkeypatch, server)
    res = await hass.services.async_call(
        "opengym", "coach_ask", {"question": "Beine", "wait": 0, "notify": True}, blocking=True, return_response=True)
    assert res == {"job_id": "a1b2c3d4e5f60718", "status": "pending"}
    server.polls = 99  # the Coach finishes later
    await entry.runtime_data.coordinator._async_fast_tick()
    await hass.async_block_till_done()
    from homeassistant.components import persistent_notification

    notes = persistent_notification._async_get_or_create_notifications(hass)
    note = notes.get("opengym_coach_a1b2c3d4e5f60718")
    assert note and "Ja, Beine passt heute." in note["message"]
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_coach_refusal_and_failure(hass: HomeAssistant, aioclient_mock, monkeypatch) -> None:
    from homeassistant.exceptions import HomeAssistantError

    server = CoachServer(polls_until_done=1, fail="Tageslimit erreicht")
    entry = await _setup_coach(hass, aioclient_mock, monkeypatch, server)
    res = await hass.services.async_call(
        "opengym", "coach_debrief", {}, blocking=True, return_response=True)
    assert res["status"] == "failed" and res["error"] == "Tageslimit erreicht"
    assert hass.states.get(_ids(hass, entry)["coach_event"]).attributes["event_type"] == "failed"
    assert await hass.config_entries.async_unload(entry.entry_id)
    # 409 busy: openGym's own message reaches the user
    aioclient_mock.clear_requests()
    aioclient_mock.post(f"{URL}/api/coach/ask", status=409, headers=H,
                        json={"error": "the Coach is already thinking about your training", "code": "busy"})
    entry2 = await _setup(hass, aioclient_mock)
    with pytest.raises(HomeAssistantError) as exc:
        await hass.services.async_call("opengym", "coach_ask", {"question": "x"}, blocking=True, return_response=True)
    assert "already thinking" in str(exc.value.translation_placeholders)
    assert await hass.config_entries.async_unload(entry2.entry_id)


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_coach_voice(hass: HomeAssistant, aioclient_mock, monkeypatch) -> None:
    assert await async_setup_component(hass, "intent", {})
    server = CoachServer(polls_until_done=2)
    entry = await _setup_coach(hass, aioclient_mock, monkeypatch, server)

    async def ask(name, slots=None):
        slots = {k: {"value": v} for k, v in (slots or {}).items()}
        return (await intent.async_handle(hass, "test", name, slots, language="de")).speech["plain"]["speech"]

    assert await ask("OpenGymCoachAsk", {"question": "Beine"}) == "Ja, Beine passt heute."
    assert await ask("OpenGymCoachDebrief") == "8 von 10 Punkten. Starke Einheit."
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_auto_debrief_after_new_workout(hass: HomeAssistant, aioclient_mock, monkeypatch) -> None:
    server = CoachServer(polls_until_done=1)
    entry = await _setup_coach(hass, aioclient_mock, monkeypatch, server, options={"coach_auto_debrief": True})
    coordinator = entry.runtime_data.coordinator
    assert not _calls(aioclient_mock, "POST", "/api/coach/debrief")  # nothing new at startup
    newer = _state()
    newer["workouts"].append({"id": "w-new", "d": TODAY.isoformat(), "name": "Pull", "vol": 3000, "entries": []})
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{URL}/api/data", headers=H, json={"state": newer, "rev": 8})
    aioclient_mock.get(f"{URL}/api/data/rev", headers=H, json={"rev": 8})
    aioclient_mock.get(f"{URL}/api/coach/status", side_effect=server.get_status)
    aioclient_mock.post(f"{URL}/api/coach/debrief", side_effect=server.post_debrief)
    _mock_all(aioclient_mock)
    debriefs = []
    hass.bus.async_listen("opengym_coach_debrief", debriefs.append)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert _calls(aioclient_mock, "POST", "/api/coach/debrief")[-1][2]["workoutId"] == "w-new"
    await coordinator._async_fast_tick()
    await hass.async_block_till_done()
    assert debriefs and debriefs[0].data["score"] == 8
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_coach_sentences_end_to_end(hass: HomeAssistant, aioclient_mock, monkeypatch) -> None:
    pytest.importorskip("hassil")
    pytest.importorskip("home_assistant_intents")
    from homeassistant.components import conversation
    from homeassistant.core import Context

    for component in ("homeassistant", "conversation", "intent"):
        assert await async_setup_component(hass, component, {})
    server = CoachServer(polls_until_done=1)
    entry = await _setup_coach(hass, aioclient_mock, monkeypatch, server)

    async def say(text, lang):
        result = await conversation.async_converse(hass, text, None, Context(), language=lang)
        return result.response.speech["plain"]["speech"]

    assert (await say("Frag den Coach, ob ich heute Beine trainieren soll", "de")).startswith("Ja, ob ich heute Beine")
    assert (await say("ask the coach whether I should rest", "en")).startswith("Ja, I should rest")
    assert (await say("Wie war mein letztes Training?", "de")).startswith("8 von 10")
    assert (await say("Was soll ich heute trainieren?", "de")).startswith(("Heute ideal", "Heute lieber", "Alles ist"))
    assert (await say("what should I train today", "en")).startswith(("Ideal today", "Better take", "Everything"))
    assert await hass.config_entries.async_unload(entry.entry_id)
