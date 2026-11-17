"""0.11: logbook lines, Assist answers, plan select, progress series."""

from __future__ import annotations

import unittest
from datetime import date, timedelta

import stub_ha

coord = stub_ha.setup()
OpenGymState = coord.OpenGymState
logic = coord.logic

TODAY = date(2026, 11, 18)  # Wednesday


class Logbook(unittest.TestCase):
    def test_workout_finished(self):
        ev = {"data": {"workout": {"name": "Push", "unit": "kg", "durationMin": 54,
                                   "totals": {"sets": 18, "volume": 12400.5}}}}
        self.assertEqual(logic.logbook_message("workout.finished", ev, "en"),
                         "finished Push (12,400.5 kg volume, 18 sets, 54 min)")
        self.assertEqual(logic.logbook_message("workout.finished", ev, "de-DE"),
                         "hat Push beendet (12.400,5 kg Volumen, 18 Sätze, 54 min)")

    def test_workout_without_totals_and_test_flag(self):
        ev = {"test": True, "data": {"workout": {}}}
        self.assertEqual(logic.logbook_message("workout.finished", ev, "en"), "finished a workout (test)")

    def test_records(self):
        ev = {"data": {"unit": "kg", "records": [
            {"id": "0025", "name": "Bench Press", "weight": 100, "reps": 3}, {"id": "x", "name": "Row"}]}}
        self.assertEqual(logic.logbook_message("workout.pr", ev, "en"),
                         "set 2 new personal records: Bench Press 100 kg × 3, Row")
        one = {"data": {"records": [{"name": "Kniebeuge", "weight": 140.5}]}}
        self.assertEqual(logic.logbook_message("workout.pr", one, "de"),
                         "hat einen neuen Rekord aufgestellt: Kniebeuge 140,5 kg")

    def test_weighin(self):
        ev = {"data": {"weighin": {"date": "2026-11-18", "weight": 80.4, "unit": "kg"}}}
        self.assertEqual(logic.logbook_message("weighin.logged", ev, "de"), "hat eine Wägung eingetragen: 80,4 kg")


class Speech(unittest.TestCase):
    def test_next(self):
        nxt = {"name": "Pull", "date": (TODAY + timedelta(days=3)).isoformat(),
               "exercises": [1, 2, 3], "total_sets": 12}
        self.assertEqual(logic.speech_next(nxt, TODAY, "de"),
                         "Dein nächstes Training ist Pull, in 3 Tagen am Samstag. 3 Übungen, 12 Sätze.")
        nxt["date"] = (TODAY + timedelta(days=1)).isoformat()
        self.assertTrue(logic.speech_next(nxt, TODAY, "en").startswith("Your next workout is Pull, tomorrow."))
        self.assertEqual(logic.speech_next(None, TODAY, "fr"), "No workout is planned for the next two weeks.")

    def test_spoken_numbers(self):
        for raw, want in (("80,4", 80.4), ("80.4", 80.4), ("80 komma 4", 80.4), ("80 point 4", 80.4),
                          ("81 kilo", 81.0), (79, 79.0)):
            self.assertEqual(logic.parse_spoken_number(raw), want, raw)
        self.assertIsNone(logic.parse_spoken_number("viel"))

    def test_convert_weight(self):
        self.assertEqual(logic.convert_weight(176.5, "lb", "kg"), 80.1)
        self.assertEqual(logic.convert_weight(80, "kg", "lb"), 176.4)
        self.assertEqual(logic.convert_weight(80.04, "kg", "kg"), 80.0)


class DayRoutine(unittest.TestCase):
    def doc(self):
        # TODAY is a Wednesday = openGym weekday 3
        return {"routines": [{"id": "push"}, {"id": "pull"}], "week": {"3": "push"}, "dayPlan": {}}

    def test_override_and_back(self):
        doc = logic.set_day_routine(self.doc(), TODAY, "pull")
        self.assertEqual(doc["dayPlan"], {TODAY.isoformat(): "pull"})
        doc = logic.set_day_routine(doc, TODAY, None)
        self.assertEqual(doc["dayPlan"], {TODAY.isoformat(): "rest"})
        doc = logic.set_day_routine(doc, TODAY, "push")  # the weekly plan anyway
        self.assertEqual(doc["dayPlan"], {})

    def test_unknown(self):
        with self.assertRaises(logic.PlanEditError):
            logic.set_day_routine(self.doc(), TODAY, "legs")


def progress_state() -> OpenGymState:
    def bench(day, w, r, prs=False):
        return {"d": day.isoformat(), "name": "Push", "vol": w * r * 3, "prs": ["0025"] if prs else [],
                "entries": [{"id": "0025", "sets": [{"w": 20, "r": 10, "warmup": True}] + [{"w": w, "r": r, "done": True}] * 3}]}
    s = OpenGymState({
        "unit": "kg", "targetW": 78,
        "bodyweight": [{"d": "2026-10-01", "w": 82.0}, {"d": "2026-11-01", "w": 80.5}, {"d": "2026-11-01", "w": 80.2}],
        "workouts": [bench(TODAY - timedelta(days=21), 80, 8), bench(TODAY - timedelta(days=14), 85, 6, True),
                     bench(TODAY - timedelta(days=14), 60, 1),  # same day, lighter: day best stays
                     bench(TODAY - timedelta(days=7), 90, 5, True)],
    })
    return s


class Progress(unittest.TestCase):
    def test_series(self):
        s = progress_state()
        self.assertEqual(s.daily_weights(), [(date(2026, 10, 1), 82.0), (date(2026, 11, 1), 80.2)])
        series = s.exercise_1rm_series("0025")
        self.assertEqual(len(series), 3)
        self.assertEqual(series[0][1], round(80 * (1 + 8 / 30), 1))  # warm-up ignored
        self.assertEqual(series[1][1], 102.0)
        self.assertEqual(s.top_exercises(), ["0025"])
        self.assertEqual(s.exercise_sessions(), {"0025": 4})
        vol = dict(s.daily_volume())
        self.assertEqual(vol[TODAY - timedelta(days=14)], 85 * 6 * 3 + 60 * 3)

    def test_progress_payload(self):
        p = progress_state().progress(TODAY)
        ex = p["exercises"][0]
        self.assertEqual(ex["name"], "Barbell Bench Press")
        self.assertEqual(ex["current"], 105.0)
        self.assertEqual(ex["change"], round(105.0 - round(80 * (1 + 8 / 30), 1), 1))
        self.assertEqual(p["weight"]["goal"], 78)
        self.assertEqual(p["weight"]["current"], 80.2)
        self.assertEqual([x["date"] for x in p["prs"]],
                         [(TODAY - timedelta(days=7)).isoformat(), (TODAY - timedelta(days=14)).isoformat()])
        self.assertEqual(p["prs"][0]["records"][0]["weight"], 90)

    def test_window(self):
        p = progress_state().progress(TODAY, days=10)
        self.assertEqual(len(p["exercises"][0]["series"]), 1)
        self.assertEqual(p["weight"]["series"], [])


if __name__ == "__main__":
    unittest.main()
