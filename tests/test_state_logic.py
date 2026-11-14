"""Pure-logic tests for openGym's OpenGymState (no HA install needed).

Run:  python3 -m unittest discover tests
"""

from __future__ import annotations

import unittest
from datetime import date, timedelta

import stub_ha

coord = stub_ha.setup()
OpenGymState = coord.OpenGymState

# Sunday — so "this week" is Mon 16 .. Sun 22 Nov 2026.
SUNDAY = date(2026, 11, 22)
MONDAY = SUNDAY - timedelta(days=SUNDAY.weekday())

# 1010 = leg-style compound (glutes/hams primary, quads/adductors/calves/low-back secondary)
# 1012 = shoulder press (deltoids primary, triceps/traps/core secondary)
def sample_state() -> OpenGymState:
    return OpenGymState({
        "unit": "kg",
        "workouts": [
            {"d": (MONDAY + timedelta(days=1)).isoformat(), "vol": 100,
             "entries": [{"id": "1010", "sets": [
                 {"w": 100, "r": 5, "done": True}, {"w": 100, "r": 5, "done": True}]}]},
            {"d": (MONDAY + timedelta(days=3)).isoformat(), "vol": 50,
             "entries": [{"id": "1012", "sets": [
                 {"w": 40, "r": 8, "done": True},
                 {"w": 40, "r": 8, "done": True, "warmup": True}]}]},
        ],
        "routines": [{"id": "r1", "name": "Push", "emoji": "💪",
                      "ex": [{"id": "1012", "sets": 3}]}],
        "week": {1: "r1"},
    })


class WeekSets(unittest.TestCase):
    def test_current_week(self):
        ws = sample_state().week_sets(SUNDAY)
        self.assertEqual(ws["gluteal"], 2.0)          # 2 working sets, primary
        self.assertEqual(ws["quadriceps"], 0.8)       # 2 × 0.4 secondary
        self.assertEqual(ws["deltoids"], 1.0)         # warm-up set must not count
        self.assertEqual(ws["triceps"], 0.4)

    def test_previous_week_is_empty(self):
        self.assertEqual(sample_state().week_sets(SUNDAY, -1), {})

    def test_side_sets_count_once(self):
        state = OpenGymState({"workouts": [{"d": MONDAY.isoformat(), "entries": [
            {"id": "1012", "sets": [{"sides": {"L": {"done": True}, "R": {"done": False}}}]}]}]})
        self.assertEqual(state.week_sets(SUNDAY)["deltoids"], 1.0)


class Fatigue(unittest.TestCase):
    def test_decays_with_half_life(self):
        state = sample_state()
        fat = state.fatigue(SUNDAY)
        # gluteal trained Tue (5 days ago), 48 h half-life -> (2/8) * 0.5**(5*24/48)
        expected = 0.25 * 0.5 ** 2.5
        self.assertAlmostEqual(fat["gluteal"], expected, delta=0.01)

    def test_never_trained_absent(self):
        self.assertNotIn("tibialis", sample_state().fatigue(SUNDAY))

    def test_state_buckets(self):
        s = sample_state()
        self.assertEqual(s.fatigue_state(0.1), "ready")
        self.assertEqual(s.fatigue_state(0.3), "recovering")
        self.assertEqual(s.fatigue_state(0.9), "fatigued")

    def test_session_cap(self):
        # 20 sets must not score more than the 12-set cap.
        state = OpenGymState({"workouts": [{"d": SUNDAY.isoformat(), "entries": [
            {"id": "1012", "sets": [{"w": 40, "r": 8, "done": True}] * 20}]}]})
        self.assertLessEqual(state.fatigue(SUNDAY)["deltoids"], 12 / 8)


class Plan(unittest.TestCase):
    def test_next_session_and_planned_muscles(self):
        state = sample_state()
        nxt = state.next_session(SUNDAY)
        self.assertIsNotNone(nxt)
        self.assertEqual(nxt[1], SUNDAY + timedelta(days=1))  # next Monday (23rd)
        planned = state.planned_muscles(SUNDAY)
        self.assertEqual(planned["deltoids"], 3.0)
        self.assertEqual(planned["triceps"], 1.2)  # 3 × 0.4

    def test_rest_week(self):
        state = OpenGymState({"workouts": [], "routines": {}, "week": {}})
        self.assertIsNone(state.next_session(SUNDAY))
        self.assertEqual(state.planned_muscles(SUNDAY), {})

    def test_planned_week_shape(self):
        pw = sample_state().planned_week(SUNDAY)
        self.assertEqual(len(pw), 7)
        self.assertEqual(pw[0]["name"], "Push")   # Monday plan
        self.assertEqual(pw[0]["date"], MONDAY.isoformat())
        self.assertIsNone(pw[6]["name"])          # Saturday rest


class History(unittest.TestCase):
    def test_twelve_weeks(self):
        hist = sample_state().week_history(SUNDAY)
        self.assertEqual(len(hist), 12)
        self.assertEqual(hist[-1]["workouts"], 2)
        self.assertEqual(hist[-1]["sets"], 9.8)
        self.assertEqual(hist[-1]["muscles"]["gluteal"], 2.0)
        self.assertEqual(hist[0]["week_start"], "2026-08-31")  # 11 weeks back

    def test_trends(self):
        trends = sample_state().muscle_trends(SUNDAY)
        self.assertEqual(len(trends["gluteal"]), 12)
        self.assertEqual(trends["gluteal"][-1], 116.7)  # 100 kg × 5 reps Epley
        self.assertIsNone(trends["gluteal"][0])

    def test_day_view(self):
        dv = sample_state().day_view(SUNDAY, days=3)
        self.assertEqual(len(dv), 3)
        # day_view starts at this week's Monday: offset 0 = Mon (planned), 1 = Tue (done).
        self.assertIsNone(dv[0]["done"])
        self.assertEqual(dv[0]["planned"], "Push")
        self.assertEqual(dv[1]["done"]["name"], "Workout")


class Detail(unittest.TestCase):
    def test_detail_fields(self):
        d = sample_state().muscle_detail("gluteal", SUNDAY)
        self.assertEqual(d["week_sets"], 2.0)
        self.assertEqual(d["target"], [4, 16])
        self.assertEqual(d["best_1rm"], 116.7)
        self.assertEqual(d["fatigue_state"], "ready")
        self.assertTrue(d["last_trained"])
        # exercises keyed by human name from the muscle map
        self.assertTrue(all(not k.isdigit() or len(k) > 3 for k in d["exercises"]))

    def test_muscle_days(self):
        days = sample_state().muscle_days(SUNDAY)
        self.assertEqual(days["gluteal"], 5)   # trained Tuesday
        self.assertEqual(days["calves"], 5)    # secondary credit counts too
        self.assertEqual(days["biceps"], 999)  # never

    def test_streak_and_counts(self):
        s = sample_state()
        self.assertEqual(s.week_count(SUNDAY), 2)
        self.assertEqual(s.week_volume(SUNDAY), 150)
        self.assertEqual(s.streak(SUNDAY), 0)  # last session was Thursday


if __name__ == "__main__":
    unittest.main()
