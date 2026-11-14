"""Minimal Home Assistant stubs.

Lets the integration's pure logic (OpenGymState, fatigue model, week math)
run under plain `python3 -m unittest` without a Home Assistant install —
the cheap half of CI until pytest-homeassistant is wired up.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "opengym"


def _module(name: str, attrs=()) -> types.ModuleType:
    m = types.ModuleType(name)
    m.__path__ = []
    for attr in attrs:
        setattr(m, attr, type(attr, (), {}))
    sys.modules[name] = m
    return m


class _DataUpdateCoordinator:
    def __class_getitem__(cls, item):
        return cls

    def __init__(self, *args, **kwargs):
        pass

    def async_update_listeners(self):
        pass


def install() -> None:
    ha = _module("homeassistant")
    _module("homeassistant.core", ["HomeAssistant", "CoreState", "ServiceCall", "SupportsResponse"])
    sys.modules["homeassistant.core"].callback = lambda f: f
    uc = _module("homeassistant.helpers.update_coordinator", ["UpdateFailed"])
    uc.DataUpdateCoordinator = _DataUpdateCoordinator
    _module("homeassistant.helpers")
    _module("homeassistant.helpers.issue_registry", ["IssueRegistry"])
    _module("homeassistant.components", ["websocket_api", "webhook"])
    _module("homeassistant.config_entries", ["ConfigEntry", "ConfigFlow", "OptionsFlow", "ConfigFlowResult"])
    _module("homeassistant.const", ["CONF_URL", "Platform", "UnitOfMass", "UnitOfTime", "EVENT_HOMEASSISTANT_START"])
    cvm = _module("homeassistant.helpers.config_validation")
    cvm.config_entry_only_config_schema = lambda domain: None
    _module("homeassistant.helpers.typing")
    _module("homeassistant.helpers.network", ["NoURLAvailableError"])
    _module("homeassistant.util")
    _module("homeassistant.util.dt")
    _module("aiohttp")
    client = _module("homeassistant.helpers.aiohttp_client", ["async_get_clientsession"])
    client.async_get_clientsession = lambda hass: None
    ha.core = sys.modules["homeassistant.core"]
    ha.helpers = sys.modules["homeassistant.helpers"]


def load(name: str):
    """Import `custom_components/opengym/<name>.py` as `opengym.<name>`."""
    path = COMPONENT / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"opengym.{name}", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"opengym.{name}"] = mod
    spec.loader.exec_module(mod)
    return mod


def setup():
    install()
    pkg = types.ModuleType("opengym")
    pkg.__path__ = [str(COMPONENT)]
    sys.modules["opengym"] = pkg
    load("const")
    load("api")
    return load("coordinator")
