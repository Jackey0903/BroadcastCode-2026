"""Adapter checks use saved real receipts or explicitly simulated model replies."""
import copy
import hashlib
import json
from pathlib import Path
import unittest

import evidence_client as ec
import evidence_env as env
from evidence_store import load_store
from player_comparison import build_story_context
import product_bridge as pb


class ProductBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = load_store()
        cls.expected = json.loads(pb.HANDOFF.read_text())["expectedLineage"]
        cls.path = Path(__file__).parent / "results/evidence-v1/service-connection-recovery-20261010.json"
        cls.digest = hashlib.sha256(cls.path.read_bytes()).hexdigest()
        cls.record = json.loads(cls.path.read_text())["cases"][0]["result"]

    def bridge(self, invoke=None):
        def no_calls(prompt):
            raise AssertionError("No model call expected")
        return pb.ProductBridge(ec.EvidenceClient(invoke or no_calls, self.expected, store=self.store))

    def test_saved_real_receipt_replay_has_explicit_origin_and_small_payload(self):
        result = self.bridge().replay(self.path, self.digest, "flagg", "spacing", "1641708")
        p = result["presentation"]
        self.assertTrue(p["scout"]["available"], p["scout"])
        self.assertTrue(p["scout"]["modelInvoked"])
        self.assertFalse(p["scout"]["modelInvokedThisRequest"])
        self.assertEqual(p["scout"]["invocationMode"], "recorded_live_replay")
        self.assertFalse(p["videoUse"]["burnedIntoVideo"])
        self.assertFalse(p["playerComparison"]["trainedModelUsed"])
        self.assertFalse(p["playerComparison"]["matchupVerified"])
        self.assertEqual(len(p["scout"]["evidence"]), 3)
        self.assertLess(len(ec.canonical(p).encode()), pb.MAX_PRESENTATION_BYTES)
        for card in p["scout"]["evidence"]:
            self.assertIn(card["sourceRef"], p["sources"])
            self.assertIn(card["periodRef"], p["periods"])
        self.assertNotIn("rawSelectorResult", ec.canonical(p))

    def test_changed_receipt_hash_and_wrong_case_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "hash_mismatch"):
            self.bridge().replay(self.path, "0" * 64, "flagg")
        with self.assertRaisesRegex(ValueError, "case_missing"):
            self.bridge().replay(self.path, self.digest, "flagg", "shot_quality")

    def test_tampered_value_or_model_cannot_display_rl_badge(self):
        context = build_story_context(self.store, "flagg")
        for kind in ("value", "model", "event", "relations"):
            raw = copy.deepcopy(self.record)
            if kind == "value":
                raw["evidence"][0]["value"] = 9999
            elif kind == "model":
                raw["lineage"]["model"] = "unverified-small-model"
            elif kind == "event":
                raw["event"]["eventId"] = 667
            else:
                raw["relations"] = []
            p = self.bridge()._format("flagg", "spacing", context, raw, "live")["presentation"]
            self.assertFalse(p["scout"]["available"])
            self.assertIsNone(p["scout"]["badge"])
            self.assertEqual(p["scout"]["evidence"], [])
            self.assertTrue(p["playerComparison"]["attacker"]["facts"])

    def test_live_path_with_simulated_policy_does_not_mark_video_used(self):
        request = ec.default_request("flagg", store=self.store)
        task, _ = ec._task_from_request(request, self.store)
        replies = iter(env.teacher_actions(task))
        def simulated(prompt):
            return {"generation": ec.canonical(next(replies)), "lineage": copy.deepcopy(self.expected)}
        p = self.bridge(simulated).analyse("flagg", opponent_id="1641708")["presentation"]
        self.assertTrue(p["scout"]["available"])
        self.assertTrue(p["scout"]["modelInvokedThisRequest"])
        self.assertEqual(p["scout"]["modelCalls"], 2)
        self.assertFalse(p["videoUse"]["narrativeUsed"])
        self.assertEqual(p["videoUse"]["evidenceIdsUsed"], [])

    def test_failed_model_still_provides_source_backed_profile(self):
        def unavailable(prompt):
            raise TimeoutError("simulated bounded timeout")
        p = self.bridge(unavailable).analyse("flagg")["presentation"]
        self.assertFalse(p["scout"]["trainedModelUsed"])
        self.assertFalse(p["scout"]["available"])
        self.assertTrue(p["playerComparison"]["attacker"]["facts"])
        self.assertEqual(p["playerComparison"]["selectedOpponentId"], None)

    def test_invalid_opponent_focus_and_implicit_client_reject_before_call(self):
        calls = []
        def never(prompt):
            calls.append(prompt)
            raise AssertionError("Must reject before inference")
        bridge = self.bridge(never)
        with self.assertRaises(ValueError):
            bridge.analyse("flagg", opponent_id="1642843")
        with self.assertRaises(ValueError):
            bridge.analyse("flagg", focus="arbitrary_question")
        with self.assertRaises(ValueError):
            pb.create_bridge(None)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
