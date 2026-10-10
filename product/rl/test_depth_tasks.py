"""Key offline reward-boundary checks; no torch/network/model dependency."""
import copy
import hashlib
import json
import unittest

import depth_tasks as dt


class DepthTasks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cohort = json.loads(dt.DEFAULT_COHORT.read_text())
        cls.tasks = dt.generate_tasks(cls.cohort)

    def task(self, category="lookup", metric=None):
        return next(t for t in self.tasks if t["category"] == category
                    and (metric is None or t["request"]["metric"] == metric))

    def score(self, task, answer):
        return dt.score_answer(task, answer, [dt.lookup(self.cohort, task["request"])])

    def test_oracles_agree_with_actual_tool_and_generation_is_deterministic(self):
        self.assertEqual(self.tasks, dt.generate_tasks(self.cohort))
        for task in self.tasks:
            with self.subTest(task=task["id"]):
                self.assertEqual(self.score(task, task["oracle"]["answer"])["total"], 0.998)
                view = dt.policy_view(task)
                self.assertNotIn("oracle", view)
                self.assertNotIn("toolResult", view)
                self.assertNotIn("category", view)

    def test_two_team_group_split_stays_disjoint_and_tampering_rejected(self):
        pids = sorted(p["playerId"] for p in self.cohort["players"])
        left, right = set(pids[:10]), set(pids[10:])
        for group in (left, right):
            subset = dt.generate_tasks(self.cohort, group)
            self.assertTrue(all(set(t["request"]["playerIds"]) <= group for t in subset))
        corrupt = copy.deepcopy(self.cohort)
        corrupt["families"]["gravity"]["rows"][0]["metrics"]["OVERALL_GRAV"] += 1
        with self.assertRaises(ValueError):
            dt.generate_tasks(corrupt)

    def test_unavailable_and_boundary_fabrications_are_negative(self):
        for category in ("missing_family", "event_boundary", "as_of_boundary", "season_boundary",
                         "team_boundary", "causal_boundary"):
            task = self.task(category)
            wrong = copy.deepcopy(task["oracle"]["answer"])
            wrong.update(status="ok", value=0.0, reasonCode=None, claimType="source_fact")
            with self.subTest(category=category):
                self.assertLess(self.score(task, wrong)["total"], 0)
        task = self.task()
        wrong = copy.deepcopy(task["oracle"]["answer"])
        wrong["explanation"] = "他吸引包夹，所以这次队友获得空位。"
        self.assertLess(self.score(task, wrong)["total"], 0)

    def test_unit_source_date_and_team_cannot_be_swapped(self):
        task = self.task(metric="AVGDEFENDERBALLDISTANCE")
        self.assertEqual(task["oracle"]["answer"]["unit"], "unknown")
        for key, value in [("unit", "feet"), ("dataAsOf", "2026-01-04"),
                           ("snapshotTeamIds", [123]), ("season", "2024-25"),
                           ("sourceSeason", "2024-25")]:
            wrong = copy.deepcopy(task["oracle"]["answer"])
            wrong[key] = value
            self.assertLess(self.score(task, wrong)["total"], 0)
        wrong = copy.deepcopy(task["oracle"]["answer"])
        wrong["evidence"]["sourceSha256"] = "0" * 64
        self.assertLess(self.score(task, wrong)["total"], 0)
        wrong = copy.deepcopy(task["oracle"]["answer"])
        wrong["evidence"]["retrievedAt"] = "2026-01-04T00:00:00+08:00"
        self.assertLess(self.score(task, wrong)["total"], 0)

    def test_numeric_tolerance_sign_comparison_and_nonfinite(self):
        task = next(t for t in self.tasks if t["category"] == "lookup"
                    and t["oracle"]["answer"]["value"] < 0)
        answer = copy.deepcopy(task["oracle"]["answer"])
        answer["value"] += dt.NUMERIC_TOLERANCE / 2
        self.assertGreater(self.score(task, answer)["total"], 0)
        for value in [abs(task["oracle"]["answer"]["value"]), float("nan"), float("inf"), True]:
            answer["value"] = value
            self.assertLess(self.score(task, answer)["total"], 0)
        task = self.task("compare")
        result = dt.lookup(self.cohort, task["request"])
        self.assertAlmostEqual(task["oracle"]["answer"]["value"],
                               result["records"][0]["value"] - result["records"][1]["value"], places=6)

    def test_actual_null_stays_missing_and_tools_never_add_reward(self):
        modified = copy.deepcopy(self.cohort)
        modified["families"]["gravity"]["rows"][0]["metrics"]["OVERALL_GRAV"] = None
        content = {"families": modified["families"], "players": modified["players"]}
        modified["reproducibility"]["selectedContentSha256"] = hashlib.sha256(
            json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        missing = next(t for t in dt.generate_tasks(modified) if t["category"] == "missing_value")
        self.assertIsNone(missing["oracle"]["answer"]["value"])
        self.assertEqual(missing["oracle"]["answer"]["reasonCode"], "metric_value_missing")
        task = self.task()
        answer, trace = task["oracle"]["answer"], dt.lookup(self.cohort, task["request"])
        one = dt.score_answer(task, answer, [trace])["total"]
        two = dt.score_answer(task, answer, [trace, trace])["total"]
        self.assertLess(two, one)
        self.assertLess(dt.score_answer(task, answer)["total"], 0)


if __name__ == "__main__":
    unittest.main()
