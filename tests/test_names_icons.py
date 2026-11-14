"""0.10.1: routine icons, exercise names, catalogue muscles, week streak."""

from __future__ import annotations

import unittest
from datetime import date, timedelta

import stub_ha

coord = stub_ha.setup()
OpenGymState = coord.OpenGymState
logic = coord.logic  # the same module the coordinator uses

TODAY = date(2026, 11, 14)  # Saturday
MONDAY = TODAY - timedelta(days=TODAY.weekday())


class RoutineIcons(unittest.TestCase):
    def test_keys(self):
        self.assertEqual(logic.routine_icon("pullup"), "mdi:human-handsup")
        self.assertEqual(logic.routine_icon("dumbbell"), "mdi:dumbbell")
        self.assertEqual(logic.routine_icon("figureRun"), "mdi:run")

    def test_legacy_emoji(self):
        self.assertEqual(logic.routine_icon("💪"), "mdi:arm-flex")
        self.assertEqual(logic.routine_icon("🏋️‍♀️"), "mdi:dumbbell")
        self.assertEqual(logic.routine_icon("🧘\ufe0f"), "mdi:yoga")

    def test_unknown_and_empty(self):
        self.assertEqual(logic.routine_icon("somethingNew"), "mdi:dumbbell")
        self.assertEqual(logic.routine_icon("🦄"), "mdi:dumbbell")
        self.assertEqual(logic.routine_icon(None), "mdi:weight-lifter")  # openGym DEFAULT_GLYPH

    def test_every_key_has_an_icon(self):
        for key in set(logic.GLYPH_LEGACY.values()):
            self.assertIn(key, logic.GLYPH_MDI)


def user_state() -> OpenGymState:
    """Shaped like the reported dashboard: library ids, an icon key."""
    ex = [{"id": i, "sets": 3, "reps": 10} for i in ("2291", "1046", "0215", "1607")]
    s = OpenGymState({
        "routines": [{"id": "r1", "name": "Rücken & Bizeps", "emoji": "pullup", "ex": ex}],
        "week": {"6": "r1", "2": "r1"},
        "customEx": [{"id": "c1", "n": "Mein Zug", "bp": "back"}],
        "workouts": [
            {"d": (MONDAY + timedelta(days=1)).isoformat(), "name": "Rücken & Bizeps", "entries": [
                {"id": "2291", "sets": [{"w": 85, "r": 10, "done": True}] * 3},
                {"id": "c1", "sets": [{"w": 50, "r": 10, "done": True}] * 2},
            ]},
        ],
    })
    return s


class ExerciseNames(unittest.TestCase):
    def test_library_ids_resolve(self):
        s = user_state()
        self.assertEqual(s.exercise_name("2291"), "Cable Wide Grip Lat Pulldown")
        self.assertEqual(s.exercise_name("2291", "de"), "Latzug mit weitem Griff am Kabelzug")
        self.assertEqual(s.exercise_name("1607", "de-DE"), "Bizeps-Curl am Kabelzug (SZ-Stange)")

    def test_custom_and_unknown(self):
        s = user_state()
        self.assertEqual(s.exercise_name("c1", "de"), "Mein Zug")
        self.assertEqual(s.exercise_name("999999"), "#999999")  # never a bare id

    def test_next_workout_carries_names_icon_muscles(self):
        s = user_state()
        s.lang = "de"
        nxt = s.next_workout(TODAY)
        self.assertEqual(nxt["icon"], "mdi:human-handsup")
        self.assertEqual(nxt["exercises"][0]["name"], "Latzug mit weitem Griff am Kabelzug")
        self.assertEqual(nxt["exercises"][0]["names"]["en"], "Cable Wide Grip Lat Pulldown")
        self.assertIn("upper-back", nxt["muscles"])
        self.assertIn("biceps", nxt["muscles"])
        self.assertIn("deltoids", nxt["muscles"])

    def test_day_view_and_plan_have_icons(self):
        s = user_state()
        days = {d["date"]: d for d in s.day_view(TODAY)}
        self.assertEqual(days[TODAY.isoformat()]["icon"], "mdi:human-handsup")
        self.assertTrue(all(d["icon"] for d in s.planned_week(TODAY) if d["name"]))


class CatalogueMuscles(unittest.TestCase):
    def test_library_exercises_count(self):
        ws = user_state().week_sets(TODAY)
        self.assertEqual(ws["upper-back"], 3 + 2 * 0.75)  # 2291 primary + custom "back"
        self.assertAlmostEqual(ws["biceps"], 1.2)
        self.assertEqual(ws["lower-back"], 0.5)

    def test_catalogue_size(self):
        self.assertGreater(len(coord._MUSCLE_MAP), 5000)

    def test_custom_weights(self):
        self.assertEqual(logic.custom_muscle_weights({"tg": "lats", "sm": ["biceps"]}),
                         {"upper-back": 1.0, "biceps": 0.4})
        self.assertEqual(logic.custom_muscle_weights({"bp": "chest"}), {"chest": 1.0})
        self.assertEqual(logic.custom_muscle_weights({"muscleWeights": {"chest": 0.5, "x": 1}}), {"chest": 0.5})


class WeekStreak(unittest.TestCase):
    def test_open_current_week(self):
        days = [MONDAY - timedelta(weeks=w) for w in (1, 2, 3)]
        info = logic.week_streak(days, TODAY)
        self.assertEqual(info["current"], 3)
        self.assertFalse(info["this_week_done"])

    def test_freeze_covers_a_gap(self):
        days = [MONDAY - timedelta(weeks=w) for w in (2, 3, 4, 5)] + [MONDAY]
        info = logic.week_streak(days, TODAY)
        self.assertEqual(info["current"], 5)  # 4 trained earn a freeze for week -1
        self.assertEqual(info["freezes"], 0)

    def test_break_without_freeze(self):
        days = [MONDAY - timedelta(weeks=3), MONDAY]
        self.assertEqual(logic.week_streak(days, TODAY)["current"], 1)

    def test_state_helper(self):
        self.assertEqual(user_state().week_streak(TODAY)["current"], 1)


if __name__ == "__main__":
    unittest.main()
