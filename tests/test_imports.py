"""Import smoke tests — every integration module must import cleanly.

This is what HA actually does when it loads the integration (loader.py ->
importlib.import_module). A NameError/ImportError here is exactly the
"Exception importing custom_components.opengym.config_flow" failure users
see on startup. The TYPE_CHECKING bug (v0.8.1) slipped through every
logic test because no test ever imported the package.

Run:  python3 -m unittest test_imports -v
"""

from __future__ import annotations

import enum
import importlib
import sys
import types
import unittest

import stub_ha

COMP = stub_ha.COMPONENT


class TestImports(unittest.TestCase):
    """Every module of the integration must import without exceptions."""

    MODULES = (
        "const", "api", "security", "device_info", "coordinator",
        "websocket_api", "sensor", "binary_sensor", "calendar", "update",
        "device_trigger", "device_action", "diagnostics", "config_flow",
        "__init__",
    )

    @classmethod
    def setUpClass(cls):
        cls._saved = {k: v for k, v in sys.modules.items()
                      if k.startswith(("homeassistant", "aiohttp", "voluptuous"))}
        stub_ha.setup()
        # voluptuous is a real dependency of HA; stub it if not installed.
        try:
            import voluptuous  # noqa: F401
        except ImportError:
            vol = types.ModuleType("voluptuous")
            vol.Schema = lambda *a, **k: None
            vol.Required = vol.Optional = lambda *a, **k: None
            vol.Coerce = vol.In = vol.All = vol.Range = lambda *a, **k: None
            vol.Required = type("Required", (), {"__init__": lambda s, k, **kw: None})
            vol.Optional = type("Optional", (), {"__init__": lambda s, k, **kw: None})
            vol.Schema = type("Schema", (), {"__init__": lambda s, *a, **k: None})
            sys.modules["voluptuous"] = vol
            cls._saved["voluptuous"] = None

        def _mod(name, attrs=(), **extra):
            m = stub_ha._module(name, attrs)
            for k, v in extra.items():
                setattr(m, k, v)
            return m

        # Vollständige Stub-Tabelle: deckt alle HA-Importe der Integration ab.
        def _enum(name, *members):
            return enum.Enum(name, " ".join(members))

        ce = _mod("homeassistant.config_entries",
                  ["ConfigEntry", "ConfigFlow", "OptionsFlow", "ConfigFlowResult"])
        ce.ConfigEntry = type("ConfigEntry", (), {"async_start_reauth": lambda *a: None})
        ce.ConfigFlow = type("ConfigFlow", (), {
            "__init_subclass__": classmethod(lambda cls, *, domain=None, **kw: None),
        })
        ce.ConfigFlowResult = type("ConfigFlowResult", (), {})
        ce.OptionsFlow = type("OptionsFlow", (), {})

        const = sys.modules["homeassistant.const"]
        const.Platform = _enum(
            "Platform",
            "SENSOR", "BINARY_SENSOR", "CALENDAR", "UPDATE",
            "DIAGNOSTICS", "DEVICE_TRIGGER", "DEVICE_ACTION",
        )
        const.UnitOfMass = type("UnitOfMass", (), {"KILOGRAMS": "kg", "POUNDS": "lb"})
        const.UnitOfTime = type("UnitOfTime", (), {"DAYS": "d", "SECONDS": "s"})
        const.EVENT_HOMEASSISTANT_START = "homeassistant_start"
        const.CONF_URL = "url"; const.CONF_DEVICE_ID = "device_id"
        const.CONF_DOMAIN = "domain"; const.CONF_PLATFORM = "platform"
        const.CONF_TYPE = "type"

        _mod("homeassistant.helpers.typing", ["ConfigType", "TemplateVarsType"])
        _mod("homeassistant.helpers.event", ["async_call_later", "CALLBACK_TYPE"])
        _mod("homeassistant.helpers.job", ["HassJob"])
        _mod("homeassistant.helpers.entity_platform", ["AddEntitiesCallback"])
        _mod("homeassistant.helpers.entity", ["Entity"])
        _mod("homeassistant.helpers.device_registry", ["DeviceInfo"])
        _mod("homeassistant.helpers.service", [])
        cv = _mod("homeassistant.helpers.config_validation",
                  ["date", "string", "boolean", "positive_time_period"])
        _mod("homeassistant.helpers.network", ["NoURLAvailableError"])
        _mod("homeassistant.helpers.issue_registry", ["IssueRegistry"])
        uc = _mod("homeassistant.helpers.update_coordinator",
                  ["UpdateFailed", "CoordinatorEntity"])

        class _DUC:
            def __class_getitem__(cls, item):
                return cls

            def __init__(self, *a, **k):
                pass

            def async_update_listeners(self):
                pass

        uc.DataUpdateCoordinator = _DUC
        uc.CoordinatorEntity = type("CoordinatorEntity", (), {
            "__class_getitem__": classmethod(lambda cls, item: cls),
            "__init__": lambda self, *a, **k: None,
        })
        _mod("homeassistant.helpers.aiohttp_client", ["async_get_clientsession"])
        _mod("homeassistant.helpers.trigger", ["TriggerActionType", "TriggerInfo"])
        _mod("homeassistant.helpers.action", [])
        _mod("homeassistant.util.dt", ["now", "utcnow"])
        _mod("homeassistant.components.frontend", [])
        _mod("homeassistant.components.http", ["StaticPathConfig"])
        _mod("homeassistant.components.webhook", ["async_register", "async_unregister"])

        class _Chain:
            """Stubs chained schema calls: .extend(...).with_keys(...) etc."""
            def __getattr__(self, _name):
                return lambda *a, **k: self

            def __call__(self, *a, **k):
                return self

        chain = _Chain()
        da = _mod("homeassistant.components.device_automation")
        da.DeviceAutomationType = _enum("DeviceAutomationType", "TRIGGER CONDITION ACTION")
        da.TriggerDeviceAutomationSchema = chain
        da.ActionDeviceAutomationSchema = chain
        da.DEVICE_TRIGGER_BASE_SCHEMA = chain
        cv.DEVICE_ACTION_BASE_SCHEMA = chain
        da.get_device_automation_capabilities = lambda *a: {}

        core = sys.modules["homeassistant.core"]
        core.CALLBACK_TYPE = object
        core.HassJob = type("HassJob", (), {"__init__": lambda s, *a, **k: None})
        core.callback = lambda f: f

        sel = _mod("homeassistant.helpers.selector",
                   ["NumberSelector", "NumberSelectorConfig", "NumberSelectorMode",
                    "SelectSelector", "SelectSelectorConfig", "SelectSelectorMode",
                    "TextSelector", "TextSelectorConfig", "BooleanSelector",
                    "BooleanSelectorConfig", "DateSelector", "DateSelectorConfig",
                    "EntitySelector", "EntitySelectorConfig", "EntitySelectorMode"])
        sel.NumberSelectorMode = _enum("NumberSelectorMode", "BOX SLIDER")
        sel.SelectSelectorMode = _enum("SelectSelectorMode", "DROPDOWN LIST")
        sel.EntitySelectorMode = _enum("EntitySelectorMode", "DROPDOWN MENU")

        sensor = _mod("homeassistant.components.sensor",
                      ["SensorDeviceClass", "SensorEntity", "SensorStateClass"])
        sensor.SensorDeviceClass = type("SensorDeviceClass", (), {"WEIGHT": "weight"})
        sensor.SensorStateClass = type("SensorStateClass", (), {
            "MEASUREMENT": "measurement", "TOTAL": "total",
            "TOTAL_INCREASING": "total_increasing"})

        _mod("homeassistant.components.binary_sensor",
             ["BinarySensorDeviceClass", "BinarySensorEntity"])
        cal = _mod("homeassistant.components.calendar",
                   ["CalendarEntity", "CalendarEntityFeature", "CalendarEvent"])
        cal.CalendarEntityFeature = type("CalendarEntityFeature", (), {"EVENT": 1})

        upd = _mod("homeassistant.components.update",
                   ["UpdateEntity", "UpdateEntityFeature"])
        upd.UpdateEntityFeature = type("UpdateEntityFeature", (), {
            "INSTALL": 1, "RELEASE_NOTES": 2, "PROGRESS": 4, "BACKUP": 8})

        # websocket_api needs callable decorators, not bare types — and the
        # `from homeassistant.components import websocket_api` form resolves
        # through the parent package attribute, so wire both.
        ws = _mod("homeassistant.components.websocket_api")
        ws.websocket_command = lambda schema: (lambda f: f)
        ws.async_register_command = lambda hass, cmd: None
        ws.ActiveConnection = type("ActiveConnection", (), {})
        ws.ERR_NOT_FOUND = "not_found"
        ws.ERR_NOT_READY = "not_ready"
        ws.ERR_INVALID_FORMAT = "invalid_format"
        sys.modules["homeassistant.components"].websocket_api = ws
        sys.modules["homeassistant.components"].webhook = sys.modules[
            "homeassistant.components.webhook"]

        sys.modules["homeassistant.core"].callback = lambda f: f
        # coordinator subclasses DataUpdateCoordinator[...]
        uc = sys.modules["homeassistant.helpers.update_coordinator"]
        class _DUC:
            def __class_getitem__(cls, item):
                return cls
            def __init__(self, *a, **k):
                pass
            def async_update_listeners(self):
                pass
        uc.DataUpdateCoordinator = _DUC

    @classmethod
    def tearDownClass(cls):
        for k in [k for k in sys.modules if k.startswith(("homeassistant", "opengym.",
                                                          "aiohttp", "voluptuous"))]:
            if sys.modules.get(k) is not cls._saved.get(k):
                sys.modules.pop(k, None)
        sys.modules.update(cls._saved)

    def test_all_modules_import(self):
        for name in self.MODULES:
            with self.subTest(module=name):
                mod = stub_ha.load(name)
                self.assertTrue(hasattr(mod, "__name__"))

    def test_config_flow_class_exposed(self):
        cf = stub_ha.load("config_flow")
        self.assertTrue(hasattr(cf, "OpenGymConfigFlow"))

    def test_init_has_setup_entry(self):
        init = stub_ha.load("__init__")
        self.assertTrue(callable(init.async_setup_entry))

    def test_type_checking_guard_is_safe(self):
        # The runtime alias must exist even without TYPE_CHECKING evaluation.
        init = stub_ha.load("__init__")
        self.assertIsNotNone(init.OpenGymConfigEntry)


if __name__ == "__main__":
    unittest.main()
