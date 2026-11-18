"""Regression tests for the 0.11.4 fixes.

Each test fails on 0.11.3 and passes now:

1. `muscle_days` broke out of the search too early (len(MUSCLES) instead of
   the slugs openGym's map actually knows), so a muscle trained only in older
   sessions was reported as 999 days — and its binary_sensor never said
   "recovering".
2. `week_sets` counts openGym's extra map slugs (serratus, obliques,
   hip-flexors, tibialis) that have no `weekly_sets_*` entity of their own.
   The muscle-balance total and the 12-week history must use the same basis
   as the sensors, otherwise state and sensors disagree.
3. `OpenGymOptionsFlow` must get the config entry from core, not read
   `.config_entry` off a plain `OptionsFlow` (AttributeError on 2024.11.0).
"""

from __future__ import annotations

import unittest
from datetime import date, timedelta

import stub_ha

coord = stub_ha.setup()
OpenGymState = coord.OpenGymState
const = stub_ha.load("const")
MUSCLES = const.MUSCLES
COMP = stub_ha.COMPONENT

SUNDAY = date(2026, 11, 22)
MONDAY = SUNDAY - timedelta(days=SUNDAY.weekday())


def state_with(*workouts) -> OpenGymState:
    return OpenGymState({"unit": "kg", "workouts": list(workouts),
                         "routines": [], "week": {}})


class MuscleDays(unittest.TestCase):
    """The break must wait for *all* map slugs, not the 14 entity groups."""

    def test_muscle_from_old_workout_is_not_999(self):
        # 1012 (shoulder press) also credits triceps/traps/abs; 1010 is the
        # leg compound. Recent sessions only cover 1012, so the loop used to
        # stop before it ever reached the leg day.
        workouts = [
            {"d": (MONDAY + timedelta(days=6)).isoformat(), "entries":
                [{"id": "1012", "sets": [{"w": 40, "r": 8, "done": True}]}]},
            {"d": (MONDAY + timedelta(days=5)).isoformat(), "entries":
                [{"id": "1012", "sets": [{"w": 40, "r": 8, "done": True}]}]},
            {"d": (MONDAY + timedelta(days=4)).isoformat(), "entries":
                [{"id": "1012", "sets": [{"w": 40, "r": 8, "done": True}]}]},
            {"d": (MONDAY + timedelta(days=3)).isoformat(), "entries":
                [{"id": "1012", "sets": [{"w": 40, "r": 8, "done": True}]}]},
            {"d": (MONDAY + timedelta(days=2)).isoformat(), "entries":
                [{"id": "1012", "sets": [{"w": 40, "r": 8, "done": True}]}]},
            {"d": (MONDAY + timedelta(days=1)).isoformat(), "entries":
                [{"id": "1012", "sets": [{"w": 40, "r": 8, "done": True}]}]},
            # the only leg day, long ago
            {"d": (MONDAY - timedelta(days=120)).isoformat(), "entries":
                [{"id": "1010", "sets": [{"w": 100, "r": 5, "done": True}]}]},
        ]
        days = state_with(*workouts).muscle_days(SUNDAY)
        self.assertEqual(days["gluteal"], 126)   # trained in the old leg day
        self.assertEqual(days["hamstring"], 126)
        self.assertEqual(days["deltoids"], 0)    # trained today
        self.assertEqual(days["biceps"], 999)    # never trained

    def test_last_days_view_follows(self):
        # muscle_last_days is keyed by openGym's own slugs (incl. `forearm`);
        # the two views must agree about which muscles were ever trained.
        workouts = [
            {"d": (MONDAY + timedelta(days=1)).isoformat(), "entries":
                [{"id": "1012", "sets": [{"w": 40, "r": 8, "done": True}]}]},
            {"d": (MONDAY - timedelta(days=30)).isoformat(), "entries":
                [{"id": "1010", "sets": [{"w": 100, "r": 5, "done": True}]}]},
        ]
        state = state_with(*workouts)
        days = state.muscle_days(SUNDAY)
        view = state.muscle_last_days(SUNDAY)
        self.assertEqual(view["gluteal"], (SUNDAY - timedelta(days=days["gluteal"])).isoformat())
        self.assertEqual(days["biceps"], 999)
        self.assertIsNone(view["biceps"])


class TrackedWeekSets(unittest.TestCase):
    """Balance total, history total and the weekly_sets_* sensors: one basis."""

    def setUp(self):
        self.state = OpenGymState({
            "unit": "kg",
            "workouts": [
                {"d": (MONDAY + timedelta(days=1)).isoformat(), "vol": 100,
                 "entries": [{"id": "1010", "sets": [
                     {"w": 100, "r": 5, "done": True},
                     {"w": 100, "r": 5, "done": True}]}]},
                {"d": (MONDAY + timedelta(days=3)).isoformat(), "vol": 50,
                 "entries": [{"id": "1012", "sets": [
                     {"w": 40, "r": 8, "done": True},
                     {"w": 40, "r": 8, "done": True, "warmup": True}]}]},
            ],
            "routines": [], "week": {},
        })

    def test_raw_counts_extra_slugs(self):
        raw = self.state.week_sets(SUNDAY)
        self.assertIn("obliques", raw)          # no weekly_sets_* entity for it
        self.assertEqual(round(sum(raw.values()), 4), 9.8)

    def test_tracked_folds_into_the_entity_groups(self):
        raw = self.state.week_sets(SUNDAY)
        tracked = self.state.tracked_week_sets(SUNDAY)
        self.assertEqual(set(tracked), set(MUSCLES))
        self.assertEqual(round(sum(tracked.values()), 4), 9.4)
        # nothing is lost: every raw slug lands in exactly one tracked group
        self.assertEqual(round(sum(raw.values()), 4), round(sum(tracked.values()), 4) + raw["obliques"])

    def test_history_total_matches_the_sensors(self):
        hist = self.state.week_history(SUNDAY)
        cur = hist[-1]
        self.assertEqual(cur["sets"], round(sum(self.state.tracked_week_sets(SUNDAY).values()), 1))
        # per-muscle detail keeps openGym's full map, so nothing disappears
        self.assertIn("obliques", cur["muscles"])

    def test_forearm_alias_is_not_double_counted(self):
        # openGym spells forearms `forearm` (1013 credits it 0.4); the group
        # must appear once and fold into `forearms`, not leak as `forearm`.
        state = OpenGymState({"workouts": [
            {"d": MONDAY.isoformat(), "entries": [
                {"id": "1013", "sets": [{"w": 30, "r": 10, "done": True}]}]}]})
        raw = state.week_sets(SUNDAY)
        self.assertIn("forearm", raw)
        tracked = state.tracked_week_sets(SUNDAY)
        self.assertEqual(set(tracked), set(MUSCLES))
        self.assertEqual(tracked["forearms"], raw["forearm"])


class FlowWiring(unittest.TestCase):
    """The options flow must get its entry from core, not from a property
    that 2024.11.0–2024.11.3 do not have on OptionsFlow."""

    def test_options_flow_keeps_its_own_entry_reference(self):
        src = (COMP / "config_flow.py").read_text()
        # core calls async_get_options_flow(entry) -> we must forward it
        factory = src[src.index("def async_get_options_flow"):src.index("class OpenGymOptionsFlow")]
        self.assertIn("OpenGymOptionsFlow(config_entry)", factory)
        # and the flow must read its options through that reference
        flow = src[src.index("class OpenGymOptionsFlow"):]
        self.assertIn("def __init__(self, config_entry: ConfigEntry)", flow)
        self.assertIn("self.entry.options.get(", flow)
        # the deprecated base would also work, but core logs it as a problem
        self.assertNotIn("from homeassistant.config_entries import (\n    ConfigEntry,\n    ConfigFlow,\n    OptionsFlowWithConfigEntry", src)
        self.assertNotIn("class OpenGymOptionsFlow(OptionsFlowWithConfigEntry)", src)
        # nothing may read the property the old core lacks
        self.assertNotIn("self.config_entry.options", src)

class DeviceTriggerDefaults(unittest.TestCase):
    def test_test_filter_defaults_to_real_deliveries_only(self):
        src = (COMP / "device_trigger.py").read_text()
        self.assertIn('not config.get("test", False)', src)


class LogbookIcon(unittest.TestCase):
    def test_unknown_event_type_does_not_raise(self):
        # An openGym release that adds an event type must not raise KeyError
        # while formatting the logbook line.
        src = (COMP / "logbook.py").read_text()
        self.assertIn('LOGBOOK_ICONS.get(og_type, "mdi:dumbbell")', src)


if __name__ == "__main__":
    unittest.main()
