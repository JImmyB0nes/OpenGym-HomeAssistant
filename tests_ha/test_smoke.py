"""Smoke test of openGym in a real Home Assistant core with a mocked openGym API.

Not part of CI (needs pytest-homeassistant-custom-component):

    pip install pytest-homeassistant-custom-component
    pytest tests_ha -q
"""
from __future__ import annotations

import json
from datetime import date, timedelta

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er, issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

URL = "https://og.test"
H = {"Content-Type": "application/json"}
WEBHOOK_ID = "abcdef0123457f3a"
TODAY = date.today()


def _log(*args):
    print(*args)


def _state(rev_extra=None):
    mon = TODAY - timedelta(days=TODAY.weekday())
    wd = (TODAY.weekday() + 1) % 7
    tomorrow_wd = (wd + 1) % 7
    return {
        "unit": "kg", "restSec": 120, "targetW": 78,
        "routines": [
            {"id": "push", "name": "Push", "emoji": "💪", "ex": [{"id": "0025", "sets": 3, "reps": 8, "inc": 2.5}]},
            {"id": "pull", "name": "Pull", "ex": [{"id": "0007", "sets": 4, "repsMin": 8, "repsMax": 10}]},
        ],
        "week": {str(wd): "push", str(tomorrow_wd): ["pull"]},
        "dayPlan": {},
        "bodyweight": [{"d": (TODAY - timedelta(days=3)).isoformat(), "w": 81.0}, {"d": TODAY.isoformat(), "w": 80.2}],
        "workouts": [
            {"d": mon.isoformat(), "name": "Push", "vol": 5000, "prs": ["0025"], "hr": {"avg": 131, "max": 168},
             "entries": [{"id": "0025", "sets": [{"w": 80, "r": 8, "done": True, "hr": {"avg": 120, "max": 140}}] * 3}]},
        ],
        "exWeights": {"0007": {"w": 70}},
    }


PENDING = {
    "id": "prop1", "kind": "review", "createdAt": 1, "expiresAt": 2, "planHash": "h", "summary": "More sets",
    "changes": [
        {"id": "c1", "type": "sets", "why": "volume", "before": 3, "after": 4, "target": {"routineId": "push", "exId": "0025"}},
        {"id": "c2", "type": "reps", "why": "x", "before": 12, "after": 10, "target": {"routineId": "push", "exId": "0025"}},
    ],
}


def _mock_all(aioclient_mock, *, coach=True, watch=True, integrations=True, rev=True, failing=False):
    aioclient_mock.get(f"{URL}/api/data", headers=H, json={"state": _state(), "rev": 7})
    aioclient_mock.get(f"{URL}/api/me", headers=H, json={"user": {"id": "u1", "name": "Jessica"}})
    aioclient_mock.get(f"{URL}/api/admin/users", headers=H, json={"users": [{"id": "u1", "live": {
        "name": "Push", "exIdx": 1, "exTotal": 4, "setsDone": 5, "setsTotal": 12, "startedAt": 1_700_000_000_000, "updatedAt": 1_700_000_060_000}}]})
    if rev:
        aioclient_mock.get(f"{URL}/api/data/rev", headers=H, json={"rev": 7, "wid": None})
    else:
        aioclient_mock.get(f"{URL}/api/data/rev", status=404, text="not found")
    aioclient_mock.get(f"{URL}/api/nudge-check", headers=H, json={"date": TODAY.isoformat(), "done": False, "nudge": True, "rev": 7})
    if coach:
        aioclient_mock.get(f"{URL}/api/coach/status", headers=H, json={"job": None, "pending": PENDING, "cap": {}, "maxMessageLen": 2000, "last": None})
        aioclient_mock.post(f"{URL}/api/coach/pending/resolve", headers=H, json={"ok": True})
        aioclient_mock.post(f"{URL}/api/coach/review", status=202, headers=H, json={"job": {"id": "j1", "kind": "review", "state": "queued"}})
    else:
        aioclient_mock.get(f"{URL}/api/coach/status", status=503, headers=H, json={"error": "Coach off", "code": "off"})
        aioclient_mock.post(f"{URL}/api/coach/review", status=503, headers=H, json={"error": "Coach off", "code": "off"})
    if watch:
        aioclient_mock.get(f"{URL}/api/watch/links", headers=H, json={"links": [{"id": "w1", "name": "Balance", "created": 1, "seen": 1_700_000_000_000}]})
        aioclient_mock.get(f"{URL}/api/watch/events", headers=H, json={"events": [
            {"type": "setDone", "wid": "x", "exId": "0025", "entryIdx": 0, "setIdx": 0, "w": 80, "r": 8, "at": 5, "hr": {"avg": 150, "max": 162}}],
            "paired": 1, "seen": 1})
    else:
        aioclient_mock.get(f"{URL}/api/watch/links", status=404, text="nope")
    conn = {"id": "c_ha", "provider": "webhook", "label": "Home Assistant", "status": "attention" if failing else "connected",
            "info": {"url": "https://ha/api/webhook/…7f3a"}, "failures": 3 if failing else 0, "queued": 0, "failed": 2 if failing else 0,
            "lastError": {"at": 1, "msg": "connect ECONNREFUSED", "code": "net"} if failing else None, "events": ["workout.finished"]}
    if integrations:
        aioclient_mock.get(f"{URL}/api/integrations", headers=H, json={"providers": [], "connections": [conn]})
        aioclient_mock.get(f"{URL}/api/integrations/log", headers=H, json={"log": [{"at": 1, "ev": "workout.finished", "ok": False, "status": 0, "ms": 3, "msg": "refused"}], "queued": 0, "failed": 2})
        aioclient_mock.post(f"{URL}/api/integrations/retry", headers=H, json={"requeued": 2, "connection": conn})
    else:
        aioclient_mock.get(f"{URL}/api/integrations", status=404, text="off")
    aioclient_mock.post(f"{URL}/api/push/rest-timer", headers=H, json={"ok": True})
    aioclient_mock.post(f"{URL}/api/push/rest-timer/cancel", headers=H, json={"ok": True})


def _entry():
    return MockConfigEntry(domain="opengym", title="openGym", data={
        "url": URL, "token": "tok", "webhook_id": WEBHOOK_ID, "secret": "", "auto_webhook": False,
    }, options={"rev_interval": 0})


def _calls(aioclient_mock, method, path):
    return [c for c in aioclient_mock.mock_calls if c[0] == method and str(c[1]).split("?")[0] == f"{URL}{path}"]


async def _setup(hass, aioclient_mock, **kw):
    _mock_all(aioclient_mock, **kw)
    entry = _entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_full_features(hass: HomeAssistant, aioclient_mock, caplog, hass_ws_client) -> None:
    entry = await _setup(hass, aioclient_mock, failing=True)
    reg = er.async_get(hass)
    ids = {e.translation_key: e.entity_id for e in er.async_entries_for_config_entry(reg, entry.entry_id)}
    for key in ("live_progress", "rest_timer", "coach_status", "watch_paired", "watch_heart_rate", "watch_hr_zone",
                "day_done", "nudge_pending", "coach_accept", "coach_reject", "weekly_sets_chest", "next_session"):
        assert key in ids, key
    _log("\nENTITY IDS:", json.dumps({k: ids[k] for k in sorted(ids) if not k.startswith(("muscle_", "weekly_sets_")) or k == "weekly_sets_chest"}, indent=1))
    st = lambda k: hass.states.get(ids[k])  # noqa: E731
    assert st("live_progress").state == "42"
    assert st("coach_status").state == "proposal"
    assert st("watch_heart_rate").state == "150"
    assert st("watch_hr_zone").state == "3"
    assert st("nudge_pending").state == "on" and st("day_done").state == "off"
    assert st("coach_accept").state != "unavailable"
    ws = st("weekly_sets_chest")
    assert ws.attributes["state_class"] == "measurement" and ws.attributes["unit_of_measurement"] == "sets"
    bal = hass.states.get(ids["muscle_balance"]).attributes
    assert bal["entry_id"] == entry.entry_id and bal["week_prs"] == 1 and bal["goal_delta"] == 2.2
    assert bal["last_hr"] == {"avg": 131.0, "max": 168.0}
    nxt = st("next_session").attributes
    _log("NEXT:", nxt)
    assert nxt["exercise_list"] and nxt["rest_sec"] == 120
    act = hass.states.get(ids["active_workout"]).attributes
    assert act["exercise_index"] == 2 and act["sets_total"] == 12 and act["progress"] == 42
    # (9) repair issue
    issue = ir.async_get(hass).async_get_issue("opengym", f"webhook_delivery_failed_{entry.entry_id}")
    assert issue is not None and issue.is_fixable
    # (4) rest timer
    await hass.services.async_call("opengym", "start_rest_timer", {}, blocking=True)
    body = _calls(aioclient_mock, "POST", "/api/push/rest-timer")[-1][2]
    assert body == {"seconds": 120}, body
    assert st("rest_timer").state not in ("unknown", "unavailable")
    await hass.services.async_call("opengym", "cancel_rest_timer", {}, blocking=True)
    assert st("rest_timer").state == "unknown"
    # (10) plan edit with conflict retry: first PUT 409 hands back a newer doc
    newer = _state(); newer["dayPlan"] = {"2030-01-01": "pull"}
    from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMockResponse
    puts_seen = {"n": 0}

    async def put_effect(method, url, data):
        puts_seen["n"] += 1
        if puts_seen["n"] == 1:
            return AiohttpClientMockResponse(method, url, status=409, headers=H,
                                             json={"error": "conflict", "rev": 8, "state": newer})
        return AiohttpClientMockResponse(method, url, status=200, headers=H,
                                         json={"ok": True, "ts": 1, "rev": 9, "wid": None})

    aioclient_mock.put(f"{URL}/api/data", side_effect=put_effect)
    n_before = len(aioclient_mock.mock_calls)
    await hass.services.async_call("opengym", "set_rest_day", {"date": "2030-01-02"}, blocking=True)
    puts = [c for c in aioclient_mock.mock_calls[n_before:] if c[0] == "PUT"]
    assert len(puts) == 2, puts
    assert puts[0][2]["baseRev"] == 7 and puts[1][2]["baseRev"] == 8
    assert puts[1][2]["state"]["dayPlan"] == {"2030-01-01": "pull", "2030-01-02": "rest"}
    # move_day / add_day_note
    await hass.services.async_call("opengym", "move_day", {"from_date": TODAY.isoformat(), "to_date": (TODAY + timedelta(days=2)).isoformat()}, blocking=True)
    await hass.services.async_call("opengym", "add_day_note", {"tag": "sick", "text": "Grippe"}, blocking=True)
    last_put = [c for c in aioclient_mock.mock_calls if c[0] == "PUT"][-1][2]
    assert last_put["state"]["dayNotes"][TODAY.isoformat()]["tag"] == "sick"
    from homeassistant.exceptions import ServiceValidationError
    with pytest.raises(ServiceValidationError) as exc:
        await hass.services.async_call("opengym", "add_day_note", {"date": (TODAY + timedelta(days=3)).isoformat(), "tag": "rest"}, blocking=True)
    _log("VALIDATION:", exc.value)
    # (8) coach: accept applies c1, reports c2 stale
    n_before = len(aioclient_mock.mock_calls)
    await hass.services.async_call("button", "press", {"entity_id": ids["coach_accept"]}, blocking=True)
    put = [c for c in aioclient_mock.mock_calls[n_before:] if c[0] == "PUT"][0][2]
    assert put["state"]["routines"][0]["ex"][0]["sets"] == 4
    assert put["state"]["coach"]["snapshots"][0]["proposalId"] == "prop1"
    res = [c for c in aioclient_mock.mock_calls[n_before:] if c[0] == "POST" and str(c[1]).endswith("/resolve")][0][2]
    assert res == {"accepted": ["c1"], "rejected": ["c2"]}, res
    await hass.services.async_call("button", "press", {"entity_id": ids["coach_reject"]}, blocking=True)
    res = [c for c in aioclient_mock.mock_calls if c[0] == "POST" and str(c[1]).endswith("/resolve")][-1][2]
    assert res == {"accepted": [], "rejected": ["c1", "c2"]}
    r = await hass.services.async_call("opengym", "coach_review", {"note": "Knie", "lang": "de"}, blocking=True, return_response=True)
    _log("COACH REVIEW RESPONSE:", r)
    # (5) websocket with entry_id / entity_id
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": "opengym:detail", "muscle": "chest", "entry_id": entry.entry_id})
    msg = await client.receive_json(); assert msg["success"], msg
    await client.send_json({"id": 2, "type": "opengym:detail", "muscle": "chest", "entity_id": ids["muscle_balance"]})
    msg = await client.receive_json(); assert msg["success"], msg
    await client.send_json({"id": 3, "type": "opengym:detail", "muscle": "chest", "entry_id": "nope"})
    msg = await client.receive_json(); assert not msg["success"]
    # (9) diagnostics
    from custom_components.opengym.diagnostics import async_get_config_entry_diagnostics
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["integrations"][0]["log"][0]["ev"] == "workout.finished"
    assert diag["config_entry"]["data"]["webhook_id"] == "…7f3a"
    _log("DIAG:", json.dumps(diag["features"]), json.dumps(diag["coordinator"]))
    # repair flow
    from homeassistant.components.repairs import DOMAIN as REPAIRS
    from homeassistant.setup import async_setup_component
    assert await async_setup_component(hass, REPAIRS, {})
    from homeassistant.components.repairs import repairs_flow_manager
    mgr = repairs_flow_manager(hass)
    flow = await mgr.async_init("opengym", data={"issue_id": f"webhook_delivery_failed_{entry.entry_id}"})
    assert flow["step_id"] == "confirm"
    flow = await mgr.async_configure(flow["flow_id"], {})
    assert flow["type"] == "create_entry", flow
    assert _calls(aioclient_mock, "POST", "/api/integrations/retry")[-1][2] == {"id": "c_ha"}
    # (1) rev fast path: unchanged rev -> no new GET /api/data
    coord = entry.runtime_data.coordinator
    n_data = len(_calls(aioclient_mock, "GET", "/api/data"))
    await coord.async_refresh()
    assert len(_calls(aioclient_mock, "GET", "/api/data")) == n_data
    assert coord.rev_skips >= 1
    await coord._async_fast_tick()
    assert len(_calls(aioclient_mock, "GET", "/api/data")) == n_data
    assert await hass.config_entries.async_unload(entry.entry_id)
    errors = [r for r in caplog.records if r.levelname in ("ERROR", "CRITICAL")]
    assert not errors, [r.getMessage() for r in errors]


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_features_off(hass: HomeAssistant, aioclient_mock, caplog) -> None:
    entry = await _setup(hass, aioclient_mock, coach=False, watch=False, integrations=False, rev=False)
    reg = er.async_get(hass)
    keys = {e.translation_key for e in er.async_entries_for_config_entry(reg, entry.entry_id)}
    for key in ("coach_status", "coach_accept", "coach_reject", "watch_paired", "watch_heart_rate", "watch_hr_zone"):
        assert key not in keys, key
    coord = entry.runtime_data.coordinator
    assert coord.coach_enabled is False and coord.watch_supported is False and coord.integrations_enabled is False
    n = len(_calls(aioclient_mock, "GET", "/api/data"))
    await coord.async_refresh()
    assert coord.rev_supported is False
    assert len(_calls(aioclient_mock, "GET", "/api/data")) == n + 1  # full poll fallback
    from homeassistant.exceptions import ServiceValidationError
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call("opengym", "coach_review", {}, blocking=True)
    assert await hass.config_entries.async_unload(entry.entry_id)
    bad = [r for r in caplog.records if r.levelname in ("WARNING", "ERROR", "CRITICAL") and "opengym" in r.name]
    assert not bad, [r.getMessage() for r in bad]


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_options_and_fast_tick(hass: HomeAssistant, aioclient_mock) -> None:
    _mock_all(aioclient_mock)
    entry = MockConfigEntry(domain="opengym", title="openGym", data={
        "url": URL, "token": "tok", "webhook_id": WEBHOOK_ID, "secret": "", "auto_webhook": False})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coord = entry.runtime_data.coordinator
    assert coord._unsub_fast is not None  # default 30 s tick running
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    keys = [str(k) for k in flow["data_schema"].schema]
    assert {"poll_interval", "rev_interval", "max_heart_rate"} <= set(keys), keys
    res = await hass.config_entries.options.async_configure(flow["flow_id"], {"poll_interval": 15, "rev_interval": 0, "max_heart_rate": 200})
    assert res["type"] == "create_entry"
    await hass.async_block_till_done()
    coord = entry.runtime_data.coordinator
    assert coord._unsub_fast is None
    assert await hass.config_entries.async_unload(entry.entry_id)
