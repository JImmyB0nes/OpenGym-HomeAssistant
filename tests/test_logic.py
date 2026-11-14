"""Pure helpers in logic.py: plan edits, Coach apply, HR zones, watch HR."""

from __future__ import annotations

import copy
import importlib.util
import unittest
from datetime import date
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "custom_components" / "opengym" / "logic.py"
_spec = importlib.util.spec_from_file_location("opengym_logic", _PATH)
logic = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(logic)

MON = date(2026, 11, 9)   # a Monday
TUE = date(2026, 11, 10)
SAT = date(2026, 11, 14)


def _state():
    return {
        "routines": [
            {"id": "push", "name": "Push", "ex": [{"id": "0025", "sets": 3, "reps": 8, "inc": 2.5}]},
            {"id": "pull", "name": "Pull", "ex": [{"id": "0007", "sets": 4, "reps": 10}]},
        ],
        # openGym: Sunday=0 … Saturday=6
        "week": {"1": "push", "2": ["pull"], "3": "rest"},
        "dayPlan": {},
    }


class TestPlanEdits(unittest.TestCase):
    def test_planned_routine_from_week_and_override(self):
        s = _state()
        self.assertEqual(logic.planned_routine_id(s, MON), "push")
        self.assertEqual(logic.planned_routine_id(s, TUE), "pull")  # list form
        self.assertIsNone(logic.planned_routine_id(s, date(2026, 11, 11)))
        s["dayPlan"][MON.isoformat()] = "pull"
        self.assertEqual(logic.planned_routine_id(s, MON), "pull")

    def test_set_and_clear_rest_day(self):
        s = logic.set_rest_day(_state(), MON)
        self.assertEqual(s["dayPlan"]["2026-11-09"], "rest")
        self.assertIsNone(logic.planned_routine_id(s, MON))
        s = logic.clear_day_override(s, MON)
        self.assertEqual(logic.planned_routine_id(s, MON), "push")

    def test_move_day(self):
        s = logic.move_day(_state(), MON, SAT)
        self.assertEqual(s["dayPlan"], {"2026-11-14": "push", "2026-11-09": "rest"})

    def test_move_day_errors(self):
        with self.assertRaises(logic.PlanEditError) as ctx:
            logic.move_day(_state(), date(2026, 11, 11), SAT)
        self.assertEqual(ctx.exception.key, "nothing_planned")
        with self.assertRaises(logic.PlanEditError):
            logic.move_day(_state(), MON, MON)

    def test_day_note(self):
        s = logic.add_day_note(_state(), MON, SAT, 123, "sick", "  Grippe  ")
        self.assertEqual(s["dayNotes"]["2026-11-09"], {"_ts": 123, "tag": "sick", "text": "Grippe"})
        cleared = logic.add_day_note(s, MON, SAT, 456)
        self.assertEqual(cleared["dayNotes"]["2026-11-09"], {"_ts": 456})
        long = logic.add_day_note(_state(), SAT, SAT, 1, None, "x" * 900)
        self.assertEqual(len(long["dayNotes"]["2026-11-14"]["text"]), 500)

    def test_day_note_rules(self):
        with self.assertRaises(logic.PlanEditError) as ctx:
            logic.add_day_note(_state(), date(2026, 11, 15), SAT, 1, "rest")
        self.assertEqual(ctx.exception.key, "note_future")
        with self.assertRaises(logic.PlanEditError):
            logic.add_day_note(_state(), SAT, SAT, 1, "party")

    def test_weighin_upsert(self):
        s = logic.set_weighin({"bodyweight": [{"d": "2026-11-10", "w": 80}]}, "2026-11-09", 81.2, "kg")
        self.assertEqual([b["d"] for b in s["bodyweight"]], ["2026-11-09", "2026-11-10"])
        s = logic.set_weighin(s, "2026-11-10", 79.9, "kg")
        self.assertEqual(s["bodyweight"][1]["w"], 79.9)

    def test_edits_reapply_on_fresh_document(self):
        """Conflict retry re-runs the same edit on the server's newer copy."""
        server = _state()
        server["dayPlan"]["2026-11-12"] = "pull"  # another device wrote this
        edit = lambda st: logic.set_rest_day(st, MON)  # noqa: E731
        mine = edit(copy.deepcopy(_state()))
        merged = edit(copy.deepcopy(server))
        self.assertNotIn("2026-11-12", mine["dayPlan"])
        self.assertEqual(merged["dayPlan"], {"2026-11-12": "pull", "2026-11-09": "rest"})


class TestCoach(unittest.TestCase):
    def _review(self, *changes):
        return {"id": "p1", "kind": "review", "summary": "More volume", "changes": list(changes)}

    def test_accept_mode(self):
        self.assertIsNone(logic.coach_accept_mode(None))
        self.assertEqual(logic.coach_accept_mode({"kind": "debrief"}), "ack")
        self.assertIsNone(logic.coach_accept_mode({"kind": "create", "bundle": {}}))
        ok = self._review({"id": "c1", "type": "sets"})
        self.assertEqual(logic.coach_accept_mode(ok), "apply")
        mixed = self._review({"id": "c1", "type": "sets"}, {"id": "c2", "type": "swap"})
        self.assertIsNone(logic.coach_accept_mode(mixed))

    def test_apply_scalar_changes_with_snapshot(self):
        s = _state()
        p = self._review(
            {"id": "c1", "type": "sets", "before": 3, "after": 4,
             "target": {"routineId": "push", "exId": "0025"}},
            {"id": "c2", "type": "rename-routine", "before": "Pull", "after": "Pull A",
             "target": {"routineId": "pull"}},
            {"id": "c3", "type": "reps", "before": 12, "after": 10,  # stale: is 8
             "target": {"routineId": "push", "exId": "0025"}},
            {"id": "c4", "type": "inc", "before": 1, "after": 2,  # gone
             "target": {"routineId": "legs", "exId": "x"}},
        )
        accepted, stale = logic.apply_coach_changes(s, p, 999)
        self.assertEqual(accepted, ["c1", "c2"])
        self.assertEqual(stale, ["c3", "c4"])
        self.assertEqual(s["routines"][0]["ex"][0]["sets"], 4)
        self.assertEqual(s["routines"][0]["ex"][0]["reps"], 8)
        self.assertEqual(s["routines"][1]["name"], "Pull A")
        snap = s["coach"]["snapshots"][-1]
        self.assertEqual(snap["proposalId"], "p1")
        self.assertEqual(snap["routines"][0]["ex"][0]["sets"], 3)  # pre-change copy

    def test_snapshots_capped(self):
        s = _state()
        s["coach"] = {"snapshots": [{"at": i} for i in range(3)]}
        p = self._review({"id": "c1", "type": "sec", "after": 30,
                          "target": {"routineId": "push", "exId": "0025"}})
        logic.apply_coach_changes(s, p, 5)
        self.assertEqual(len(s["coach"]["snapshots"]), 3)
        self.assertEqual(s["coach"]["snapshots"][-1]["at"], 5)

    def test_summary(self):
        self.assertEqual(logic.coach_summary(None)["state"], "idle")
        self.assertEqual(logic.coach_summary({"job": {"state": "queued", "kind": "review"}})["state"], "queued")
        summ = logic.coach_summary({"pending": self._review({"id": "a", "type": "sets"})})
        self.assertEqual((summ["state"], summ["changes"], summ["accept_mode"]), ("proposal", 1, "apply"))


class TestHeartRate(unittest.TestCase):
    def test_hr_value(self):
        self.assertEqual(logic.hr_value({"avg": 120.4, "max": 150}), {"avg": 120, "max": 150})
        self.assertEqual(logic.hr_value(130), {"avg": 130, "max": 130})
        self.assertIsNone(logic.hr_value({"avg": 160, "max": 150}))
        self.assertIsNone(logic.hr_value({"avg": 10, "max": 20}))
        self.assertIsNone(logic.hr_value("x"))

    def test_zones(self):
        self.assertEqual(logic.hr_zone(80, 190), 0)
        self.assertEqual(logic.hr_zone(95, 190), 1)
        self.assertEqual(logic.hr_zone(133, 190), 3)
        self.assertEqual(logic.hr_zone(180, 190), 5)
        self.assertIsNone(logic.hr_zone(None, 190))
        self.assertEqual(logic.hr_zone_bounds(200)["zone_5"], [180, 200])

    def test_latest_watch_hr(self):
        events = [
            {"type": "setDone", "at": 100, "hr": {"avg": 120, "max": 140}},
            {"type": "setHr", "at": 300, "restHr": {"avg": 100, "max": 110}},
            {"type": "setDone", "at": 200, "hr": {"avg": 150, "max": 160}},
            {"type": "weighIn", "at": 400},
        ]
        hr = logic.latest_watch_hr(events)
        self.assertEqual((hr["avg"], hr["phase"], hr["at"]), (100, "rest", 300))
        self.assertIsNone(logic.latest_watch_hr([]))


class TestMisc(unittest.TestCase):
    def test_presence_progress(self):
        p = logic.presence_progress({"exIdx": 1, "exTotal": 5, "setsDone": 6, "setsTotal": 20})
        self.assertEqual(p, {"exercise_index": 2, "exercise_total": 5, "sets_done": 6,
                             "sets_total": 20, "progress": 30})
        self.assertIsNone(logic.presence_progress(None)["progress"])

    def test_rest_seconds(self):
        self.assertEqual(logic.clamp_rest_seconds(None, None), 90)
        self.assertEqual(logic.clamp_rest_seconds(None, 120), 120)
        self.assertEqual(logic.clamp_rest_seconds(9999, 60), 3600)

    def test_week_prs_and_trend(self):
        ws = [{"d": "2026-11-08", "prs": ["a"]}, {"d": "2026-11-10", "prs": ["a", "b"]},
              {"d": "2026-11-12"}]
        self.assertEqual(logic.week_prs(ws, MON, SAT), 2)
        trend = logic.weight_trend([{"d": "2026-11-02", "w": 81}, {"d": "2026-11-01", "w": 82},
                                    {"d": "x"}], 5)
        self.assertEqual([t["w"] for t in trend], [82.0, 81.0])

    def test_our_connections(self):
        conns = [
            {"id": "1", "provider": "webhook", "label": "Other", "info": {"url": "https://x/…aaaa"}},
            {"id": "2", "provider": "webhook", "label": "HA", "info": {"url": "https://ha/api/webhook/…7f3a"}},
            {"id": "3", "provider": "ntfy", "label": "Home Assistant"},
        ]
        self.assertEqual([c["id"] for c in logic.our_connections(conns, "abc7f3a")], ["2"])
        conns[1]["info"]["url"] = "…zzzz"
        conns[0]["label"] = "Home Assistant"
        self.assertEqual([c["id"] for c in logic.our_connections(conns, "abc7f3a")], ["1"])
        self.assertTrue(logic.failing_connection({"status": "attention"}))
        self.assertTrue(logic.failing_connection({"status": "connected", "failed": 2}))
        self.assertFalse(logic.failing_connection({"status": "connected", "failed": 0}))


if __name__ == "__main__":
    unittest.main()
