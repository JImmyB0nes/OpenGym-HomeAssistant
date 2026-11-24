"""0.12: event attributes, training recommendation, Coach results."""

from __future__ import annotations

import unittest
from datetime import date, timedelta

import stub_ha

coord = stub_ha.setup()
OpenGymState = coord.OpenGymState
logic = coord.logic

TODAY = date(2026, 11, 24)  # Tuesday


def done_sets(w, r, n):
    return [{"w": w, "r": r, "done": True}] * n


class Recommendation(unittest.TestCase):
    ROUTINES = [
        {"id": "push", "name": "Push", "ex": [{"id": "0025", "sets": 4}]},
        {"id": "pull", "name": "Pull", "ex": [{"id": "2291", "sets": 4}, {"id": "1607", "sets": 3}]},
    ]

    def test_skips_fatigued_and_picks_matching_routine(self):
        s = OpenGymState({"routines": self.ROUTINES, "workouts": [
            {"d": (TODAY - timedelta(days=1)).isoformat(), "entries": [{"id": "0025", "sets": done_sets(80, 8, 5)}]}]})
        rec = s.recommendation(TODAY)
        self.assertEqual(rec["kind"], "train")
        self.assertIn("chest", rec["fatigued"])
        self.assertNotIn("chest", rec["muscles"])
        self.assertEqual(rec["muscles"][0], "upper-back")  # biggest untouched group first
        self.assertEqual((rec["routine"], rec["routine_id"]), ("Pull", "pull"))
        self.assertEqual(logic.recommendation_text(rec, "de"),
                         "Heute ideal: oberer Rücken, Bizeps und Waden. Dazu passt deine Routine Pull.")
        self.assertEqual(logic.recommendation_state(rec, "en"), "upper back, biceps and calves")

    def test_rest_when_nothing_recovered(self):
        entries = [{"id": i, "sets": done_sets(50, 10, 12)} for i in
                   ("0025", "2291", "1607", "0043", "0032", "0041", "1373", "0001", "0002", "0003")]
        s = OpenGymState({"workouts": [{"d": TODAY.isoformat(), "entries": entries}] * 3})
        rec = s.recommendation(TODAY)
        if rec["kind"] == "rest":
            self.assertTrue(logic.recommendation_text(rec, "de").startswith("Heute lieber Pause"))
            self.assertEqual(logic.recommendation_state(rec, "de"), "Pause")
        else:  # some muscle not hit by the catalogue sample: never recommend a tired one
            self.assertFalse(set(rec["muscles"]) & set(rec["fatigued"]))

    def test_free_choice_when_targets_met(self):
        s = OpenGymState({"muscleTargets": {m: [0, 0] for m in
                          ("chest", "upper-back", "deltoids", "biceps", "triceps", "quadriceps",
                           "hamstring", "gluteal", "calves", "abs")}})
        rec = s.recommendation(TODAY)
        self.assertEqual(rec["kind"], "free")
        self.assertEqual(logic.recommendation_state(rec, "de"), "Freie Wahl")


class Events(unittest.TestCase):
    def test_workout_attributes(self):
        ev = {"test": False, "data": {"workout": {
            "name": "Push", "date": "2026-11-24", "durationMin": 54, "unit": "kg",
            "totals": {"exercises": 5, "sets": 18, "reps": 140, "volume": 12400},
            "records": [{"id": "0025", "name": "Bench Press"}]}}}
        self.assertEqual(logic.event_attributes("workout.finished", ev), {
            "test": False, "name": "Push", "date": "2026-11-24", "duration_min": 54, "volume": 12400,
            "sets": 18, "reps": 140, "exercises": 5, "unit": "kg", "records": ["Bench Press"]})

    def test_pr_and_weighin_attributes(self):
        pr = {"data": {"unit": "kg", "workout": {"name": "Push", "date": "2026-11-24"},
                       "records": [{"name": "Bench Press", "weight": 100, "reps": 3, "id": "x"}]}}
        self.assertEqual(logic.event_attributes("workout.pr", pr)["records"],
                         [{"name": "Bench Press", "weight": 100, "reps": 3}])
        wi = {"test": True, "data": {"weighin": {"date": "2026-11-24", "weight": 80.4, "unit": "kg"}}}
        self.assertEqual(logic.event_attributes("weighin.logged", wi),
                         {"test": True, "weight": 80.4, "unit": "kg", "date": "2026-11-24"})


class CoachResults(unittest.TestCase):
    PENDING = {"id": "j1", "kind": "debrief", "score": 8, "summary": "Solid session.",
               "highlights": ["Bench +2.5 kg"], "watch": ["Short rests"], "nextTime": ["Add a set"],
               "workout": {"name": "Push", "d": "2026-11-24"}}

    def test_debrief_summary_and_speech(self):
        r = logic.debrief_summary(self.PENDING)
        self.assertEqual(r["score"], 8)
        self.assertEqual(r["next_time"], ["Add a set"])
        self.assertEqual(r["workout"], "Push")
        self.assertEqual(logic.speech_debrief(r, "de"), "8 von 10 Punkten. Solid session.")
        self.assertEqual(logic.coach_logbook_message("debrief", r, "en"), "Coach rated Push: 8/10 – Solid session.")
        title, msg = logic.coach_notification("debrief", r, "de")
        self.assertIn("Trainingsauswertung", title)
        self.assertIn("**Nächstes Mal**\n- Add a set", msg)

    def test_answer_logbook_and_notification(self):
        r = {"status": "answered", "question": "Beine heute?", "answer": "Ja. " * 120}
        line = logic.coach_logbook_message("ask", r, "de")
        self.assertTrue(line.startswith("Coach: Ja.") and line.endswith("…") and len(line) < 215)
        title, msg = logic.coach_notification("ask", r, "de")
        self.assertTrue(msg.startswith("**Beine heute?**"))
        failed = {"status": "failed", "error": "daily limit"}
        self.assertEqual(logic.coach_notification("ask", failed, "en")[1], "The Coach could not answer: daily limit")


if __name__ == "__main__":
    unittest.main()
