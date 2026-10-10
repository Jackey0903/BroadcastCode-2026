"""Offline evidence-selection reward checks using the frozen official two-team store."""
import copy
import json
from pathlib import Path
import unittest

import evidence_env as env


class EvidenceEnvironment(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = json.loads((Path(__file__).parent / "data/evidence/store.json").read_text())
        cls.tasks = env.make_tasks(cls.store)

    def task(self, category):
        return next(t for t in self.tasks if t["category"] == category)

    def ready(self, task):
        episode = env.Environment(task, self.store)
        for family in task["oracle"]["requiredFamilies"]:
            episode.execute(family)
        return episode

    def test_all_real_source_teachers_succeed_with_minimal_tools(self):
        for task in self.tasks:
            with self.subTest(task=task["id"], category=task["category"]):
                score = env.run_episode(task, self.store, env.teacher_actions(task))
                self.assertTrue(score["valid"], score)
                self.assertEqual(score["coverage"], 1.0)
                self.assertAlmostEqual(score["total"], 1 - env.TOOL_COST * len(task["oracle"]["requiredFamilies"]))

    def test_split_precedes_expansion_and_three_layers_are_required(self):
        by_player = {}
        for task in self.tasks:
            by_player.setdefault(task["request"]["playerId"], set()).add(task["split"])
            view = env.policy_view(task)
            self.assertNotIn("oracle", view)
            self.assertNotIn("requiredEvidenceIds", view)
        self.assertTrue(all(len(splits) == 1 for splits in by_player.values()))
        self.assertEqual(by_player["1642843"], {"val"})
        self.assertEqual({t["split"] for t in self.tasks}, {"train", "val", "test"})
        joint = [t for t in self.tasks if t["category"] == "joint_three_layer"]
        self.assertTrue(joint)
        self.assertEqual({t["oracle"]["requiredFamilies"][-1] for t in joint}, {"gravity", "leverage", "shotdifficulty"})
        for task in joint:
            self.assertEqual(len(task["oracle"]["requiredEvidenceIds"]), 3)
            self.assertEqual(len(task["oracle"]["requiredRelations"]), 2)
            episode = self.ready(task)
            self.assertTrue(all(len(call["result"]["records"]) <= 13 for call in episode.trace))
            self.assertTrue(all("source" not in r for call in episode.trace for r in call["result"]["records"]))

    def test_sampled_malformed_actions_and_fields_never_crash(self):
        for text in ('prefix {"tools":["basic"]}', '{"tools":[{"name":"basic"}]}',
                     '{"tools":["basic","basic"]}', '{"tools":[]}', '[]', 'null', '{"value":1}'):
            self.assertTrue(env.parse_action(text)[2])
        task = self.task("joint_three_layer")
        for field, value in (("status", {}), ("reasonCode", []), ("evidenceIds", [False]), ("relations", {})):
            answer = copy.deepcopy(task["oracle"]["answer"])
            answer[field] = value
            self.assertLess(self.ready(task).score(answer)["total"], 0)

    def test_oracle_copy_without_trace_and_wrong_evidence_are_negative(self):
        task = self.task("joint_three_layer")
        answer = copy.deepcopy(task["oracle"]["answer"])
        self.assertLess(env.Environment(task, self.store).score(answer)["total"], 0)
        answer["evidenceIds"][0] = "invented-source"
        self.assertLess(self.ready(task).score(answer)["total"], 0)
        answer = copy.deepcopy(task["oracle"]["answer"])
        answer["value"] = 999
        self.assertLess(self.ready(task).score(answer)["total"], 0)

    def test_scope_missing_and_causal_boundaries_cannot_be_overridden(self):
        for category in ("missing_family", "as_of_boundary", "event_boundary", "causal_boundary"):
            task = self.task(category)
            wrong = {"status": "ok", "evidenceIds": [], "relations": [], "reasonCode": None}
            self.assertLess(self.ready(task).score(wrong)["total"], 0)
            self.assertLess(env.Environment(task, self.store).score(task["oracle"]["answer"])["total"], 0)
        task = self.task("basic_lookup")
        refuse = {"status": "unavailable", "evidenceIds": [], "relations": [], "reasonCode": "metric_not_available"}
        self.assertLess(self.ready(task).score(refuse)["total"], 0)

    def test_coverage_denominator_is_fixed_and_irrelevant_relations_fail(self):
        task = self.task("joint_three_layer")
        episode = self.ready(task)
        complete = episode.score(task["oracle"]["answer"])
        partial = copy.deepcopy(task["oracle"]["answer"])
        partial["relations"] = []
        partial["evidenceIds"] = partial["evidenceIds"][:1]
        score = episode.score(partial)
        self.assertFalse(score["valid"])
        self.assertEqual(score["coverage"], 1 / 5)
        self.assertLess(score["total"], complete["total"])
        wrong = copy.deepcopy(task["oracle"]["answer"])
        wrong["relations"] = list(env.RELATIONS)
        self.assertLess(episode.score(wrong)["total"], 0)

    def test_store_tampering_and_extra_calls_never_improve_reward(self):
        task = self.task("basic_lookup")
        tampered = copy.deepcopy(self.store)
        tampered["records"][0]["value"] = 123456
        with self.assertRaises(ValueError):
            env.Environment(task, tampered)
        episode = self.ready(task)
        before = episode.score(task["oracle"]["answer"])["total"]
        returned = episode.execute("basic")
        returned["records"].clear()
        self.assertTrue(episode.trace[-1]["result"]["records"])
        self.assertLess(episode.score(task["oracle"]["answer"])["total"], before)


if __name__ == "__main__":
    unittest.main()
