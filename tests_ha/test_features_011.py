"""0.11: translated names, logbook, Assist, statistics, number/select, progress WS."""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er, intent
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMockResponse

from test_smoke import H, TODAY, URL, _calls, _setup


def _ids(hass, entry) -> dict[str, str]:
    reg = er.async_get(hass)
    return {e.translation_key: e.entity_id for e in er.async_entries_for_config_entry(reg, entry.entry_id)}


def _accept_puts(aioclient_mock) -> None:
    async def put_effect(method, url, data):
        return AiohttpClientMockResponse(method, url, status=200, headers=H,
                                         json={"ok": True, "ts": 1, "rev": 8, "wid": None})

    aioclient_mock.put(f"{URL}/api/data", side_effect=put_effect)


def _last_put(aioclient_mock) -> dict:
    return [c for c in aioclient_mock.mock_calls if c[0] == "PUT"][-1][2]


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_entity_ids_and_translated_names(hass: HomeAssistant, aioclient_mock) -> None:
    """Names come from translations; the entity ids stay what README documents."""
    entry = await _setup(hass, aioclient_mock)
    ids = _ids(hass, entry)
    assert ids["muscle_chest"] == "sensor.opengym_chest_idle"
    assert ids["muscle_upper_back"] == "sensor.opengym_upper_back_idle"
    assert ids["weekly_sets_chest"] == "sensor.opengym_chest_weekly_sets"
    assert ids["muscle_chest_recovering"] == "binary_sensor.opengym_chest_recovering"
    assert ids["worked_out_today"] == "binary_sensor.opengym_worked_out_today"
    assert ids["last_workout"] == "sensor.opengym_last_workout"
    assert ids["rest_duration"] == "number.opengym_rest_timer_duration"
    assert ids["today_routine"] == "select.opengym_today_s_routine"
    assert hass.states.get(ids["worked_out_today"]).name == "openGym Worked out today"
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_german_names(hass: HomeAssistant, aioclient_mock) -> None:
    await hass.config.async_update(language="de")
    entry = await _setup(hass, aioclient_mock)
    ids = _ids(hass, entry)
    # German UI, English entity ids
    assert ids["worked_out_today"] == "binary_sensor.opengym_worked_out_today"
    assert hass.states.get(ids["worked_out_today"]).name == "openGym Heute trainiert"
    assert hass.states.get(ids["rest_duration"]).name == "openGym Pausentimer-Dauer"
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_logbook_describes_events(recorder_mock, hass: HomeAssistant, aioclient_mock) -> None:
    assert await async_setup_component(hass, "logbook", {})
    entry = await _setup(hass, aioclient_mock)
    await hass.async_block_till_done()
    from homeassistant.components.logbook import DOMAIN as LOGBOOK

    external = hass.data[LOGBOOK].external_events
    for event_type in ("opengym_workout_finished", "opengym_personal_record", "opengym_weighin_logged"):
        assert event_type in external, event_type
    domain, describe = external["opengym_workout_finished"]
    assert domain == "opengym"

    class _Ev:
        data = {"entry_id": entry.entry_id, "data": {"workout": {
            "name": "Push", "unit": "kg", "durationMin": 54, "totals": {"sets": 18, "volume": 12400}}}}

    line = describe(_Ev())
    assert line["name"] == "openGym"
    assert line["message"] == "finished Push (12,400 kg volume, 18 sets, 54 min)"
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_assist_intents(hass: HomeAssistant, aioclient_mock) -> None:
    assert await async_setup_component(hass, "intent", {})
    entry = await _setup(hass, aioclient_mock)
    _accept_puts(aioclient_mock)

    async def ask(name, slots=None, language="en"):
        slots = {k: {"value": v} for k, v in (slots or {}).items()}
        resp = await intent.async_handle(hass, "test", name, slots, language=language)
        return resp.speech["plain"]["speech"]

    assert (await ask("OpenGymNextWorkout")).startswith("Your next workout is Push, today.")
    assert (await ask("OpenGymNextWorkout", language="de")).startswith("Dein nächstes Training ist Push, heute.")
    week = await ask("OpenGymWeekSummary", language="de")
    assert week == "Diese Woche: 1 Training, 5.000 kg Volumen." or "noch nicht" in week, week
    assert "Push" in await ask("OpenGymLastWorkout")
    # log weight: "80 komma 4" -> PUT with today's weigh-in
    answer = await ask("OpenGymLogWeight", {"weight": "80 komma 4"}, language="de")
    assert answer.startswith("80,4 kg eingetragen."), answer
    body = _last_put(aioclient_mock)["state"]
    assert {"d": TODAY.isoformat(), "w": 80.4} in body["bodyweight"]
    assert await ask("OpenGymLogWeight", {"weight": "viel"}) == "I did not understand the weight."
    # rest timer from voice uses the number entity's value when no seconds are given
    assert await ask("OpenGymStartRestTimer", {"minutes": 2}) == "Rest timer started for 120 seconds."
    assert _calls(aioclient_mock, "POST", "/api/push/rest-timer")[-1][2] == {"seconds": 120}
    assert await ask("OpenGymCancelRestTimer") == "Rest timer stopped."
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_sentences_installed_and_removed(hass: HomeAssistant, aioclient_mock) -> None:
    entry = await _setup(hass, aioclient_mock)
    await hass.async_block_till_done()
    target = Path(hass.config.path("custom_sentences", "de", "opengym.yaml"))
    assert target.exists()
    text = target.read_text("utf-8")
    assert text.startswith("# managed-by: opengym") and "OpenGymNextWorkout" in text
    # a file the user took over (marker removed) is never touched
    own = Path(hass.config.path("custom_sentences", "en", "opengym.yaml"))
    own.write_text("# mine\nlanguage: en\n", "utf-8")
    # switching the option off removes our (managed) file only
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(flow["flow_id"], {
        "poll_interval": 15, "rev_interval": 0, "max_heart_rate": 190,
        "assist_sentences": False, "import_statistics": False})
    await hass.async_block_till_done()
    assert not target.exists()
    assert own.read_text("utf-8") == "# mine\nlanguage: en\n"
    own.unlink()
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_number_and_select(hass: HomeAssistant, aioclient_mock) -> None:
    entry = await _setup(hass, aioclient_mock)
    ids = _ids(hass, entry)
    _accept_puts(aioclient_mock)
    # number follows openGym's restSec until changed in HA
    assert hass.states.get(ids["rest_duration"]).state == "120.0"
    await hass.services.async_call("number", "set_value", {"entity_id": ids["rest_duration"], "value": 75}, blocking=True)
    assert hass.states.get(ids["rest_duration"]).state == "75.0"
    await hass.services.async_call("opengym", "start_rest_timer", {}, blocking=True)
    assert _calls(aioclient_mock, "POST", "/api/push/rest-timer")[-1][2] == {"seconds": 75}
    assert hass.states.get(ids["next_session"]).attributes["rest_sec"] == 75
    # select: today's routine from the weekly plan, options = routines + rest
    sel = hass.states.get(ids["today_routine"])
    assert sel.state == "Push"
    assert sel.attributes["options"] == ["Push", "Pull", "rest"]
    await hass.services.async_call("select", "select_option", {"entity_id": ids["today_routine"], "option": "Pull"}, blocking=True)
    assert _last_put(aioclient_mock)["state"]["dayPlan"] == {TODAY.isoformat(): "pull"}
    await hass.services.async_call("select", "select_option", {"entity_id": ids["today_routine"], "option": "rest"}, blocking=True)
    assert _last_put(aioclient_mock)["state"]["dayPlan"] == {TODAY.isoformat(): "rest"}
    # picking what the weekly plan has anyway drops the override
    await hass.services.async_call("select", "select_option", {"entity_id": ids["today_routine"], "option": "Push"}, blocking=True)
    assert _last_put(aioclient_mock)["state"]["dayPlan"] == {}
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_progress_websocket(hass: HomeAssistant, aioclient_mock, hass_ws_client) -> None:
    entry = await _setup(hass, aioclient_mock)
    ids = _ids(hass, entry)
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": "opengym:progress", "entity_id": ids["best_one_rm"]})
    msg = await client.receive_json()
    assert msg["success"], msg
    res = msg["result"]
    assert res["entry_id"] == entry.entry_id and res["unit"] == "kg"
    bench = res["exercises"][0]
    assert bench["id"] == "0025" and bench["name"] == "Barbell Bench Press"
    assert bench["current"] == pytest.approx(101.3, abs=0.1) and bench["sessions"] == 1
    assert res["weight"]["goal"] == 78 and res["weight"]["current"] == 80.2
    assert [p["w"] for p in res["weight"]["series"]] == [81.0, 80.2]
    assert res["prs"][0]["records"][0]["name"] == "Barbell Bench Press"
    assert res["prs"][0]["records"][0]["weight"] == 80
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_statistics_import(recorder_mock, hass: HomeAssistant, aioclient_mock) -> None:
    from homeassistant.components.recorder.statistics import list_statistic_ids, statistics_during_period
    from pytest_homeassistant_custom_component.components.recorder.common import async_wait_recording_done

    entry = await _setup(hass, aioclient_mock)
    await hass.async_block_till_done()
    await async_wait_recording_done(hass)
    prefix = f"opengym:{entry.entry_id.lower()}"
    found = {s["statistic_id"] for s in await recorder_mock.async_add_executor_job(list_statistic_ids, hass)}
    assert {f"{prefix}_body_weight", f"{prefix}_volume", f"{prefix}_1rm_0025"} <= found, found
    start = TODAY - timedelta(days=30)
    from homeassistant.util import dt as dt_util

    stats = await recorder_mock.async_add_executor_job(
        statistics_during_period, hass, dt_util.start_of_local_day(start), None,
        {f"{prefix}_body_weight", f"{prefix}_volume"}, "day", None, {"mean", "sum", "state"},
    )
    assert [r["mean"] for r in stats[f"{prefix}_body_weight"]] == [81.0, 80.2]
    assert stats[f"{prefix}_volume"][-1]["sum"] == 5000
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_assist_sentences_end_to_end(hass: HomeAssistant, aioclient_mock) -> None:
    """The shipped sentences reach the intents through the built-in agent."""
    pytest.importorskip("hassil")
    pytest.importorskip("home_assistant_intents")
    from homeassistant.components import conversation
    from homeassistant.core import Context

    assert await async_setup_component(hass, "homeassistant", {})
    assert await async_setup_component(hass, "conversation", {})
    assert await async_setup_component(hass, "intent", {})
    entry = await _setup(hass, aioclient_mock)
    await hass.async_block_till_done()
    _accept_puts(aioclient_mock)

    async def say(text, language):
        result = await conversation.async_converse(hass, text, None, Context(), language=language)
        return result.response.speech["plain"]["speech"]

    assert (await say("Wann ist mein nächstes Training?", "de")).startswith("Dein nächstes Training ist Push")
    assert (await say("when is my next workout", "en")).startswith("Your next workout is Push")
    assert (await say("Trag 80,4 Kilo ein", "de")).startswith("80,4 kg eingetragen")
    assert (await say("Starte 90 Sekunden Pause", "de")) == "Pausentimer für 90 Sekunden gestartet."
    assert (await say("stop the rest timer", "en")) == "Rest timer stopped."
    assert "Training" in await say("Wie oft habe ich diese Woche trainiert", "de")
    # every documented example must reach openGym, not a built-in intent
    ours = ("Dein ", "Diese Woche", "Pausentimer", "eingetragen", "Your ", "This week", "Rest timer", "Logged")
    for text, lang in (
        ("Was ist mein nächstes Training", "de"), ("Wann muss ich wieder trainieren", "de"),
        ("Was trainiere ich als nächstes", "de"), ("Wann habe ich zuletzt trainiert", "de"),
        ("Wann war mein letztes Workout", "de"), ("Ich wiege 79,8 Kilo", "de"),
        ("Starte die Pause", "de"), ("Starte den Pausentimer für 2 Minuten", "de"),
        ("Pause für 45 Sekunden", "de"), ("Stoppe die Pause", "de"),
        ("what is my next workout", "en"), ("when did I last work out", "en"),
        ("how often did I work out this week", "en"), ("I weigh 176.5 pounds", "en"),
        ("log 80.4 kilos", "en"), ("start the rest timer", "en"),
        ("start a 90 second rest", "en"), ("rest for 2 minutes", "en"), ("cancel the rest timer", "en"),
    ):
        answer = await say(text, lang)
        assert any(marker in answer for marker in ours), (text, answer)
    # a weight in pounds on a kg profile is converted before it is stored
    assert (await say("I weigh 176.5 pounds", "en")).startswith("Logged 80.1 kg")
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_readme_entity_ids_exist(hass: HomeAssistant, aioclient_mock) -> None:
    """Every concrete entity id the README mentions is what a fresh install creates."""
    import re

    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text("utf-8")
    domains = "sensor|binary_sensor|calendar|update|button|number|select"
    mentioned = set(re.findall(rf"\b(?:{domains})\.opengym_[a-z0-9_]+\b", readme))
    mentioned -= {"update.opengym_opengym_instanz"}  # documented as the pre-0.11 id
    entry = await _setup(hass, aioclient_mock)
    created = set(_ids(hass, entry).values())
    missing = sorted(mentioned - created)
    assert not missing, missing
    assert len(mentioned) > 30
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_review_fixes(hass: HomeAssistant, aioclient_mock, hass_ws_client) -> None:
    """0.11.1: bugs found before going live."""
    entry = await _setup(hass, aioclient_mock)
    ids = _ids(hass, entry)
    _accept_puts(aioclient_mock)
    # weigh-in service without a unit: the profile's unit, never rewritten
    await hass.services.async_call("opengym", "log_weighin", {"weight": 80.4}, blocking=True)
    body = _last_put(aioclient_mock)["state"]
    assert body["unit"] == "kg" and {"d": TODAY.isoformat(), "w": 80.4} in body["bodyweight"]
    await hass.services.async_call("opengym", "log_weighin", {"weight": 176.5, "unit": "lb"}, blocking=True)
    body = _last_put(aioclient_mock)["state"]
    assert body["unit"] == "kg" and {"d": TODAY.isoformat(), "w": 80.1} in body["bodyweight"]
    # websocket before data: a clean error instead of an AttributeError
    coord = entry.runtime_data.coordinator
    saved, coord.data = coord.data, None
    client = await hass_ws_client(hass)
    for i, msg in enumerate(({"type": "opengym:progress"}, {"type": "opengym:detail", "muscle": "chest"}), 1):
        await client.send_json({"id": i, "entry_id": entry.entry_id, **msg})
        res = await client.receive_json()
        assert not res["success"] and res["error"]["code"] == "not_ready", res
    coord.data = saved
    # the rest-timer number marks where its value comes from
    assert hass.states.get(ids["rest_duration"]).attributes["source"] == "opengym"
    await hass.services.async_call("number", "set_value", {"entity_id": ids["rest_duration"], "value": 60}, blocking=True)
    assert hass.states.get(ids["rest_duration"]).attributes["source"] == "home_assistant"
    # weekly counters are measurements (they reset every Monday)
    assert hass.states.get(ids["week_workouts"]).attributes["state_class"] == "measurement"
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_weight_sentences_do_not_hijack(hass: HomeAssistant, aioclient_mock) -> None:
    """Everyday commands must not be taken for a weigh-in."""
    pytest.importorskip("hassil")
    pytest.importorskip("home_assistant_intents")
    from homeassistant.components import conversation
    from homeassistant.core import Context

    assert await async_setup_component(hass, "homeassistant", {})
    assert await async_setup_component(hass, "conversation", {})
    assert await async_setup_component(hass, "intent", {})
    entry = await _setup(hass, aioclient_mock)
    await hass.async_block_till_done()
    _accept_puts(aioclient_mock)
    n_puts = len([c for c in aioclient_mock.mock_calls if c[0] == "PUT"])
    for text, lang in (("Notiere Milch", "de"), ("Trag den Termin ein", "de"), ("Speichere die Szene", "de"),
                       ("record a video", "en"), ("save the date", "en"), ("log the temperature", "en")):
        result = await conversation.async_converse(hass, text, None, Context(), language=lang)
        speech = result.response.speech.get("plain", {}).get("speech", "")
        assert "weight" not in speech.lower() and "gewicht" not in speech.lower(), (text, speech)
    assert len([c for c in aioclient_mock.mock_calls if c[0] == "PUT"]) == n_puts
    # the real thing still works
    result = await conversation.async_converse(hass, "Trag mein Gewicht von 80 Kilo ein", None, Context(), language="de")
    assert result.response.speech["plain"]["speech"].startswith("80 kg eingetragen")
    result = await conversation.async_converse(hass, "log my weight as 80.4", None, Context(), language="en")
    assert result.response.speech["plain"]["speech"].startswith("Logged 80.4 kg")
    assert await hass.config_entries.async_unload(entry.entry_id)
