"""pytest-homeassistant-custom-component setup for the smoke test in tests_ha/."""

from pathlib import Path

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"

_CC = str(Path(__file__).resolve().parents[1] / "custom_components")


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    # The plugin's own testing_config owns the `custom_components` package;
    # add this repository's folder to it so the loader finds `opengym`.
    import custom_components

    if _CC not in custom_components.__path__:
        custom_components.__path__.append(_CC)
    yield
