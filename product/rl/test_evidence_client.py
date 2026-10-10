"""Focused runtime safety checks; invocations are explicitly fake, no AWS calls."""
import copy
import io
import json
import unittest

import evidence_client as client
import evidence_env as env
import evidence_store as facts


class FakeInvoker:
    request_timeout_seconds = 0

    def __init__(self, generations, lineage):
        self.generations, self.lineage, self.prompts = iter(generations), lineage, []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        return {"generation": client.canonical(next(self.generations)), "lineage": copy.deepcopy(self.lineage)}


class EvidenceClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = facts.load_store()

    def setup_runtime(self, store=None, story="flagg"):
        store = store or self.store
        request = client.default_request(story, store=store)
        task, _ = client._task_from_request(request, store)
        lineage = {"schema": "rl-scout-evidence-lineage-v1", "model": client.MODEL, "baseModel": client.MODEL,
                   "sourceTrainingJob": "rl-scout-evidence-3b-two-teams-1010-052032", "selectedStage": "rl",
                   "actualRL": True, "storeSha256": client.training_store_hash(store), "policy": client.POLICY,
                   "storeContentSha256": store["contentSha256"], "trainingSelectedStage": "sft", "optimizerUpdateSteps": 7,
                   "rawEvaluationReleaseGatePassed": False, "semanticValidationRequired": True}
        expected = {**lineage, "endpoint": "offline-test-endpoint"}
        return request, task, lineage, expected

    def test_real_store_success_preserves_numbers_and_exact_training_chat(self):
        request, task, lineage, expected = self.setup_runtime()
        invoker = FakeInvoker(env.teacher_actions(task), lineage)
        runtime = client.EvidenceClient(invoker, expected, store=self.store)
        result = runtime.analyse(request)
        self.assertTrue(result["available"], result)
        self.assertEqual(result["modelCalls"], 2)
        self.assertTrue(result["actualRL"] and result["lineageVerified"])
        self.assertEqual(result["event"]["eventId"], 666)
        source = {r["evidenceId"]: r for r in self.store["records"]}
        self.assertEqual(result["evidence"], [source[eid] for eid in task["oracle"]["answer"]["evidenceIds"]])
        self.assertEqual(invoker.prompts[0], "<|im_start|>system\n" + env.SYSTEM + "<|im_end|>\n<|im_start|>user\n"
            + env.policy_view(task) + "<|im_end|>\n<|im_start|>assistant\n")
        middle = "\n<|im_start|>user\n" + client.canonical({"toolResults": result["trace"][0]["toolResults"]}) + "<|im_end|>\n<|im_start|>assistant\n"
        # Corresponds to first_ids + sampled assistant (including im_end) + middle_ids.
        self.assertEqual(invoker.prompts[1], invoker.prompts[0] + client.canonical(env.teacher_actions(task)[0]) + "<|im_end|>" + middle)
        self.assertNotIn('"oracle"', invoker.prompts[0])
        self.assertFalse(result["lineage"]["rawEvaluationReleaseGatePassed"])

    def test_wrong_metric_even_when_values_equal_requires_actual_model_correction(self):
        # Deliberate synthetic in-memory arithmetic fixture: both percentages equal .5.
        store = copy.deepcopy(self.store)
        for row in store["records"]:
            if row["playerId"] == "1642843" and row["gameId"] == "0022500701" and row["family"] == "advanced":
                row["value"] = .5
                row["derivation"]["operands"] = {"FGA": 10, "FTA": 0, "PTS": 10, "FGM": 5, "FG3M": 0}
                row["source"] = {"url": "https://test.nba.com/synthetic-offline-fixture", "sha256": "0" * 64,
                                 "rowKey": "synthetic_arithmetic_fixture", "retrievedAt": "2026-10-10T00:00:00Z"}
                row["evidenceId"] = facts.record_id(row)
        store["contentSha256"] = facts.sha({k: v for k, v in store.items() if k != "contentSha256"})
        request, task, lineage, expected = self.setup_runtime(store)
        wrong = copy.deepcopy(task["oracle"]["answer"])
        ts = next(r for r in store["records"] if r["playerId"] == request["playerId"] and r["gameId"] == request["gameId"] and r["metric"] == "TS_PCT")
        efg = next(r for r in store["records"] if r["playerId"] == request["playerId"] and r["gameId"] == request["gameId"] and r["metric"] == "EFG_PCT")
        self.assertEqual(ts["value"], efg["value"])
        wrong["evidenceIds"] = [ts["evidenceId"] if eid == efg["evidenceId"] else eid for eid in wrong["evidenceIds"]]
        invoker = FakeInvoker([env.teacher_actions(task)[0], wrong, task["oracle"]["answer"]], lineage)
        result = client.EvidenceClient(invoker, expected, store=store).analyse(request)
        self.assertTrue(result["available"] and result["correctionUsed"], result)
        self.assertEqual(result["modelCalls"], 3)
        self.assertIn("metric_or_grain_mismatch", result["trace"][1]["validation"]["errors"])
        self.assertIn("TS_PCT与EFG_PCT是不同指标", invoker.prompts[2])

    def test_external_unreturned_id_and_second_failure_are_safe(self):
        request, task, lineage, expected = self.setup_runtime()
        wrong = copy.deepcopy(task["oracle"]["answer"])
        foreign = next(r for r in self.store["records"] if r["playerId"] != request["playerId"])
        wrong["evidenceIds"][0] = foreign["evidenceId"]
        invoker = FakeInvoker([env.teacher_actions(task)[0], wrong, wrong], lineage)
        result = client.EvidenceClient(invoker, expected, store=self.store).analyse(request)
        self.assertFalse(result["available"])
        self.assertEqual(result["error"], "selection_invalid_after_one_correction")
        self.assertEqual(result["evidence"], [])
        self.assertEqual(result["provenance"], [])
        self.assertEqual(len(invoker.prompts), 3)

    def test_no_tools_lineage_mismatch_and_unregistered_event_fail_closed(self):
        request, task, lineage, expected = self.setup_runtime()
        for generations, returned_lineage in (([task["oracle"]["answer"]] * 2, lineage),
                ([env.teacher_actions(task)[0]], {**lineage, "model": "Qwen/Qwen2.5-0.5B-Instruct"})):
            invoker = FakeInvoker(generations, returned_lineage)
            result = client.EvidenceClient(invoker, expected, store=self.store).analyse(request)
            self.assertFalse(result["available"])
            self.assertEqual(result["evidence"], [])
        invoker = FakeInvoker([], lineage)
        result = client.EvidenceClient(invoker, expected, store=self.store).analyse({**request, "eventId": 667})
        self.assertFalse(result["available"])
        self.assertFalse(result["modelInvoked"])
        with self.assertRaises(ValueError):
            client.EvidenceClient(invoker, {**expected, "selectedStage": "sft"}, store=self.store)

    def test_sagemaker_payload_and_bounded_calls(self):
        request, task, lineage, expected = self.setup_runtime()
        class Runtime:
            def invoke_endpoint(self, **kwargs):
                self.call = kwargs
                return {"Body": io.BytesIO(client.canonical({"generation": "{}", "lineage": lineage}).encode())}
        sdk = Runtime()
        invoke = client.sagemaker_invoker(expected["endpoint"], client=sdk)
        self.assertEqual(invoke("qwen prompt")["lineage"], lineage)
        self.assertEqual(json.loads(sdk.call["Body"]), {"prompt": "qwen prompt", "max_tokens": 256})
        self.assertEqual(sdk.call["EndpointName"], expected["endpoint"])
        invoker = FakeInvoker([{"tools": ["basic"]}] * 4, lineage)
        result = client.EvidenceClient(invoker, expected, store=self.store).analyse(request)
        self.assertFalse(result["available"])
        self.assertEqual(result["modelCalls"], 4)


if __name__ == "__main__":
    unittest.main()
