"""Install openGym's Assist sentences for Home Assistant's conversation agent.

Custom integrations cannot add sentences to the built-in agent directly; it
reads `<config>/custom_sentences/<lang>/*.yaml`. The integration copies its
own files there (`opengym.yaml`) and reloads the agent. A file you edited
yourself is left alone: only files that still start with our marker line
are rewritten (delete the first line to take a file over).
"""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

SOURCE_DIR = Path(__file__).parent / "sentences"
LANGUAGES = ("de", "en")
FILE_NAME = "opengym.yaml"
MARKER = "# managed-by: opengym"


def _install(config_dir: Path) -> list[str]:
    """Write/refresh the sentence files; returns the languages changed."""
    changed = []
    for lang in LANGUAGES:
        source = SOURCE_DIR / f"{lang}.yaml"
        if not source.exists():
            continue
        content = f"{MARKER} (delete this line to keep your own edits)\n" + source.read_text("utf-8")
        target = config_dir / "custom_sentences" / lang / FILE_NAME
        if target.exists():
            current = target.read_text("utf-8")
            if not current.startswith(MARKER) or current == content:
                continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, "utf-8")
        changed.append(lang)
    return changed


def _remove(config_dir: Path) -> None:
    for lang in LANGUAGES:
        target = config_dir / "custom_sentences" / lang / FILE_NAME
        if target.exists() and target.read_text("utf-8").startswith(MARKER):
            target.unlink()


async def async_install_sentences(hass: HomeAssistant) -> None:
    """Copy the sentences into the config dir and reload the agent if needed."""
    try:
        changed = await hass.async_add_executor_job(_install, Path(hass.config.config_dir))
    except OSError as err:
        _LOGGER.warning("openGym: could not install Assist sentences (%s)", err)
        return
    if changed and hass.services.has_service("conversation", "reload"):
        for lang in changed:
            await hass.services.async_call("conversation", "reload", {"language": lang}, blocking=False)
        _LOGGER.info("openGym: Assist sentences installed (%s)", ", ".join(changed))


async def async_remove_sentences(hass: HomeAssistant) -> None:
    """Remove our (unedited) sentence files, e.g. when the last entry is removed."""
    try:
        await hass.async_add_executor_job(_remove, Path(hass.config.config_dir))
    except OSError as err:  # pragma: no cover
        _LOGGER.debug("openGym: could not remove Assist sentences (%s)", err)
