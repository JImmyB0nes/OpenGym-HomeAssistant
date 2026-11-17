"""Import openGym's history into Home Assistant's long-term statistics.

Sensors only record from the day the integration was installed. openGym
already knows everything since the first workout, so after each full fetch
of the state document the integration writes it as *external statistics*
(`opengym:<entry>_…`), visible in statistics graphs and the history:

- `…_body_weight`        one value per weigh-in day (mean/min/max)
- `…_volume`             volume per training day (a sum: the graph's
                         "change" per day/week/month is the lifted volume)
- `…_1rm_<exercise>`     best estimated 1RM per training day, for the most
                         trained exercises

Re-importing is idempotent: the recorder updates rows that exist.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .state import OpenGymState

_LOGGER = logging.getLogger(__name__)

TOP_EXERCISES = 8


def statistic_prefix(entry_id: str) -> str:
    """`opengym:<entry>` — statistic ids must be lowercase slugs."""
    return f"{DOMAIN}:{re.sub(r'[^a-z0-9_]', '_', entry_id.lower())}"


def _slug(value: str) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]", "_", str(value).lower())).strip("_") or "x"


def _start(day: date) -> datetime:
    """Statistics rows start on a full hour: local midnight of the day."""
    return dt_util.start_of_local_day(day)


def build_statistics(state: OpenGymState, entry_id: str, title: str = "openGym") -> list[tuple[dict[str, Any], list[dict[str, Any]]]]:
    """(metadata, rows) per series. Pure apart from the time zone helper."""
    prefix = statistic_prefix(entry_id)
    unit = "lb" if state.unit == "lb" else "kg"
    out: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []

    weights = state.daily_weights()
    if weights:
        out.append((
            _meta(f"{prefix}_body_weight", f"{title} body weight", unit, mean=True),
            [{"start": _start(d), "mean": w, "min": w, "max": w, "state": w} for d, w in weights],
        ))

    volume = state.daily_volume()
    if volume:
        total = 0.0
        rows = []
        for d, v in volume:
            total += v
            rows.append({"start": _start(d), "state": round(v, 1), "sum": round(total, 1)})
        out.append((_meta(f"{prefix}_volume", f"{title} volume", unit, mean=False), rows))

    for ex_id in state.top_exercises(TOP_EXERCISES):
        series = state.exercise_1rm_series(ex_id)
        if not series:
            continue
        name = state.exercise_name(ex_id, state.lang)
        out.append((
            _meta(f"{prefix}_1rm_{_slug(ex_id)}", f"{title} 1RM {name}", unit, mean=True),
            [{"start": _start(d), "mean": v, "min": v, "max": v, "state": v} for d, v in series],
        ))
    return out


def _meta(statistic_id: str, name: str, unit: str, *, mean: bool) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "source": DOMAIN,
        "statistic_id": statistic_id,
        "name": name,
        "unit_of_measurement": unit,
        "has_sum": not mean,
        "has_mean": mean,
    }
    try:  # newer cores: mean_type replaces has_mean, later unit_class joins it
        from homeassistant.components.recorder.models import (
            StatisticMeanType,
            StatisticMetaData,
        )
    except ImportError:  # pragma: no cover - older cores
        return meta
    meta.pop("has_mean")
    meta["mean_type"] = StatisticMeanType.ARITHMETIC if mean else StatisticMeanType.NONE
    # only where the recorder knows the key: an unknown key would break the import
    if "unit_class" in getattr(StatisticMetaData, "__annotations__", {}):
        meta["unit_class"] = "mass"
    return meta


async def async_import_statistics(hass: HomeAssistant, entry_id: str, title: str, state: OpenGymState) -> int:
    """Queue the import with the recorder; returns the number of series."""
    if "recorder" not in hass.config.components:
        return 0
    from homeassistant.components.recorder.statistics import async_add_external_statistics

    series = build_statistics(state, entry_id, title)
    for meta, rows in series:
        try:
            async_add_external_statistics(hass, meta, rows)  # type: ignore[arg-type]
        except Exception as err:  # noqa: BLE001 - statistics must never break polling
            _LOGGER.warning("openGym: could not import statistics %s (%s)", meta["statistic_id"], err)
    _LOGGER.debug("openGym: imported %d statistics series", len(series))
    return len(series)
