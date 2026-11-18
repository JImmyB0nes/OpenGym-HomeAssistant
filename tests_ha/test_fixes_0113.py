"""0.11.3: the deep-review fixes — stable unique_id, clean service errors,
statistics only on real history changes, total_lifting as measurement."""
from __future__ import annotations

import hashlib

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from test_smoke import H, URL, _setup


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_config_flow_unique_id_is_the_user(hass: HomeAssistant, aioclient_mock) -> None:
    """Pairing the same openGym account twice aborts instead of duplicating."""
    from test_smoke import _mock_all

    _mock_all(aioclient_mock)
    aioclient_mock.get(f"{URL}/api/config", headers=H, json={"invite_only": False})
    aioclient_mock.post(f"{URL}/api/pair/redeem", headers=H, json={"token": "tok-new"})
    aioclient_mock.get(f"{URL}/api/me", headers=H, json={"user": {"id": "u1", "name": "Jessica"}})

    flow = await hass.config_entries.flow.async_init("opengym", context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(flow["flow_id"], {"url": URL})
    assert result["type"] == "form" and result["step_id"] == "pair"
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"code": "12345678", "auto_webhook": False, "secret": ""}
    )
    assert result["type"] == "create_entry"
    entry = result["result"]
    assert entry.unique_id == hashlib.sha256(b"u1").hexdigest()[:32]

    # second pairing of the same account: abort, no second entry
    flow = await hass.config_entries.flow.async_init("opengym", context={"source": "user"})
    await hass.config_entries.flow.async_configure(flow["flow_id"], {"url": URL})
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"code": "87654321", "auto_webhook": False, "secret": ""}
    )
    assert result["type"] == "abort" and result["reason"] == "already_configured"
    assert len(hass.config_entries.async_entries("opengym")) == 1


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_trigger_test_without_connection(hass: HomeAssistant, aioclient_mock) -> None:
    """No webhook connection in openGym: a readable error, not ValueError."""
    entry = await _setup(hass, aioclient_mock)
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{URL}/api/integrations", headers=H, json={"providers": [], "connections": []})
    with pytest.raises(ServiceValidationError) as exc:
        await hass.services.async_call("opengym", "trigger_test_event", {}, blocking=True)
    assert exc.value.translation_key == "no_webhook_connection"
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_total_lifting_is_a_measurement(hass: HomeAssistant, aioclient_mock) -> None:
    """Deleting a workout in openGym must not book a negative jump."""
    entry = await _setup(hass, aioclient_mock)
    from test_features_011 import _ids

    ids = _ids(hass, entry)
    assert hass.states.get(ids["total_lifting"]).attributes["state_class"] == "measurement"
    assert hass.states.get(ids["total_lifting"]).state == "5000"


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_statistics_import_once_per_history(
    hass: HomeAssistant, aioclient_mock, monkeypatch
) -> None:
    """A rev bump alone must not re-feed the whole history to the recorder."""
    import custom_components.opengym.coordinator as coord_mod

    calls: list[int] = []
    real = coord_mod.async_import_statistics

    async def counting(hass_, entry_id, title, state):
        calls.append(entry_id)
        return await real(hass_, entry_id, title, state)

    monkeypatch.setattr(coord_mod, "async_import_statistics", counting)
    entry = await _setup(hass, aioclient_mock)
    assert len(calls) == 1  # the first full fetch
    coordinator = entry.runtime_data.coordinator
    assert coordinator._stats_digest  # fingerprint remembered

    # a service write: PUT bumps the rev, but the polled history is unchanged
    async def put_effect(method, url, data):
        from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMockResponse

        return AiohttpClientMockResponse(method, url, status=200, headers=H,
                                         json={"ok": True, "ts": 1, "rev": 8, "wid": None})

    aioclient_mock.put(f"{URL}/api/data", side_effect=put_effect)
    await hass.services.async_call("opengym", "set_rest_day", {"date": "2030-01-02"}, blocking=True)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    # the document was fetched again, but its history digest is unchanged:
    # the statistics import skips it
    assert len(calls) == 1
    assert await hass.config_entries.async_unload(entry.entry_id)
