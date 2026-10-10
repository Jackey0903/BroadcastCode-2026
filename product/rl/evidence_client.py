"""Bounded runtime for the trained evidence selector; numbers come only from the store.

The invoker returns {generation, lineage}, never just text. A caller supplies the
deployment descriptor it verified during packaging/deployment. This client binds
every response to that descriptor and the frozen local facts before using it.
"""
import copy
import hashlib
import json
import re
import time
from typing import TypedDict

import evidence_env as env
import evidence_store as facts

MODEL = "Qwen/Qwen2.5-3B-Instruct"
POLICY = "evidence-v1"
PROTOCOL = "qwen2.5-evidence-training-chat-v1"
MAX_MODEL_CALLS = 4
LINEAGE_KEYS = ("schema", "model", "baseModel", "sourceTrainingJob", "selectedStage", "actualRL",
                "storeSha256", "storeContentSha256", "policy", "optimizerUpdateSteps", "semanticValidationRequired")


class RequiredMetric(TypedDict):
    family: str
    metric: str
    grain: str


class MetricRequest(TypedDict):
    playerId: str
    gameId: str
    eventId: int
    requiredMetrics: list[RequiredMetric]
    requiredRelations: list[str]
    grain: str


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def training_store_hash(store):
    """Same full-store canonical hash as train_evidence.digest (not the file hash)."""
    return hashlib.sha256(canonical(store).encode()).hexdigest()


def render_qwen(messages):
    """Exact plain Qwen2.5 chat form used by first_ids/middle_ids in training."""
    for message in messages:
        if message["role"] not in {"system", "user", "assistant"} or not isinstance(message["content"], str):
            raise ValueError("invalid_chat_message")
        if "<|im_start|>" in message["content"] or "<|im_end|>" in message["content"]:
            raise ValueError("embedded_chat_control_token")
    return "".join(f"<|im_start|>{m['role']}\n{m['content']}<|im_end|>\n" for m in messages) + "<|im_start|>assistant\n"


def sagemaker_invoker(endpoint_name, client=None, max_tokens=256):
    """A real, bounded SageMaker call. Local CLI uses nba; workload uses its IAM role."""
    if not isinstance(endpoint_name, str) or not endpoint_name:
        raise ValueError("endpoint_name_required")
    if not 1 <= max_tokens <= 512:
        raise ValueError("max_tokens_out_of_range")
    if client is None:
        import boto3
        from botocore.config import Config
        session = boto3.Session(profile_name="nba", region_name="us-east-1")
        client = session.client("sagemaker-runtime", config=Config(
            connect_timeout=3, read_timeout=25, retries={"total_max_attempts": 1}))

    def invoke(prompt):
        response = client.invoke_endpoint(EndpointName=endpoint_name, ContentType="application/json",
            Body=canonical({"prompt": prompt, "max_tokens": max_tokens}).encode())
        payload = json.loads(response["Body"].read())
        if not isinstance(payload, dict):
            raise ValueError("invalid_endpoint_response")
        return payload

    invoke.endpoint_name = endpoint_name
    invoke.request_timeout_seconds = 28
    return invoke


def default_request(story_id, depth_family="gravity", store=None):
    """Only the two independently registered practice events; no identity inference."""
    store = store if store is not None else facts.load_store()
    if story_id not in {"flagg", "amen"} or depth_family not in env.TOOLS[2:]:
        raise ValueError("unsupported_practice_request")
    event = next(e for e in store["events"] if e["storyId"] == story_id)
    depth_metric = {"gravity": "OFF_BALL_PERIM_GRAV", "leverage": "CREATION_LVG",
                    "shotdifficulty": "AVGSHOTQUALITY"}[depth_family]
    return {"playerId": event["playerId"], "gameId": event["gameId"], "eventId": event["eventId"],
        "requiredMetrics": [{"family": "basic", "metric": "PTS", "grain": "player-game"},
                            {"family": "advanced", "metric": "EFG_PCT", "grain": "player-game"},
                            {"family": depth_family, "metric": depth_metric, "grain": "player-season"}],
        "requiredRelations": ["volume_efficiency_context", env.RELATION_FOR[depth_family]],
        "grain": "mixed_game_season_context"}


def _task_from_request(request, store):
    if not isinstance(request, dict) or set(request) != set(MetricRequest.__required_keys__):
        raise ValueError("invalid_typed_request_fields")
    if (not isinstance(request["playerId"], str) or not request["playerId"].isdigit()
            or not isinstance(request["gameId"], str) or not re.fullmatch(r"\d{10}", request["gameId"])
            or type(request["eventId"]) is not int or request["eventId"] < 0
            or request["grain"] != "mixed_game_season_context"):
        raise ValueError("invalid_identity_or_grain")
    event = next((e for e in store["events"] if (e["playerId"], e["gameId"], e["eventId"]) ==
                  (request["playerId"], request["gameId"], request["eventId"])), None)
    if event is None:
        raise ValueError("unverified_event_identity")
    required, relations = request["requiredMetrics"], request["requiredRelations"]
    if not isinstance(required, list) or not 3 <= len(required) <= 5 or not isinstance(relations, list):
        raise ValueError("invalid_required_metrics")
    keys, records, families = set(), [], []
    for spec in required:
        if not isinstance(spec, dict) or set(spec) != {"family", "metric", "grain"} or not all(isinstance(v, str) for v in spec.values()):
            raise ValueError("invalid_metric_specification")
        key = (spec["family"], spec["metric"], spec["grain"])
        if key in keys or spec["family"] not in env.TOOLS:
            raise ValueError("duplicate_or_unknown_metric")
        keys.add(key)
        matches = [r for r in env._records(store, request["playerId"], spec["family"], request["gameId"])
                   if (r["family"], r["metric"], r["grain"]) == key]
        if len(matches) != 1:
            raise ValueError("required_metric_unavailable_or_ambiguous:" + ":".join(key))
        records.append(matches[0])
        if spec["family"] not in families:
            families.append(spec["family"])
    if not {"basic", "advanced"} <= set(families) or not set(families) & set(env.TOOLS[2:]):
        raise ValueError("three_layers_required")
    expected_relations = {"volume_efficiency_context"} | {env.RELATION_FOR[f] for f in families if f in env.TOOLS[2:]}
    if (not all(isinstance(r, str) for r in relations) or len(set(relations)) != len(relations)
            or set(relations) != expected_relations):
        raise ValueError("invalid_required_relations")
    player = next(p for p in store["players"] if p["playerId"] == request["playerId"])
    labels = [env.LABELS.get(r["metric"], r["metric"]) for r in records]
    prompt = "选择本场" + "、".join(labels[:2]) + "，再补充赛季" + "、".join(labels[2:]) + "背景。保留本场与赛季范围，不作因果归因。"
    # Types constrain the request, but expected IDs and numeric answers stay private.
    prompt += "\n严格指标要求：" + canonical({"requiredMetrics": required, "requiredRelations": relations,
                                                       "eventId": request["eventId"], "grain": request["grain"]})
    task = env._task(env.store_digest(store), player, "runtime", "joint_three_layer", prompt,
                     families, records=records, relations=relations, game_id=request["gameId"])
    return task, copy.deepcopy(event)


class EvidenceClient:
    def __init__(self, invoke, expected_lineage, store=None, store_path=None, timeout_seconds=90, max_model_calls=MAX_MODEL_CALLS):
        self.store = copy.deepcopy(store) if store is not None else facts.load_store(store_path or facts.DEFAULT_STORE)
        facts.validate_store(self.store)
        env.validate_store(self.store)
        self.invoke, self.expected = invoke, copy.deepcopy(expected_lineage)
        self.timeout_seconds = min(90, max(1, timeout_seconds))
        self.max_model_calls = min(MAX_MODEL_CALLS, max(1, max_model_calls))
        required = {"schema": "rl-scout-evidence-lineage-v1", "model": MODEL, "baseModel": MODEL, "selectedStage": "rl",
                    "actualRL": True, "policy": POLICY, "storeSha256": training_store_hash(self.store),
                    "storeContentSha256": self.store["contentSha256"], "semanticValidationRequired": True}
        if any(self.expected.get(k) != v for k, v in required.items()) or self.expected.get("actualRL") is not True:
            raise ValueError("unexpected_model_stage_policy_or_store_lineage")
        if (not isinstance(self.expected.get("sourceTrainingJob"), str) or not self.expected["sourceTrainingJob"]
                or not isinstance(self.expected.get("endpoint"), str) or not self.expected["endpoint"]):
            raise ValueError("expected_training_job_and_endpoint_required")
        if type(self.expected.get("optimizerUpdateSteps")) is not int or self.expected["optimizerUpdateSteps"] <= 0:
            raise ValueError("actual_rl_updates_required")
        if getattr(invoke, "endpoint_name", self.expected["endpoint"]) != self.expected["endpoint"]:
            raise ValueError("invoker_endpoint_mismatch")

    def _verify_lineage(self, payload):
        if not isinstance(payload, dict) or not isinstance(payload.get("generation"), str):
            raise ValueError("endpoint_response_requires_generation_and_lineage")
        lineage = payload.get("lineage")
        if not isinstance(lineage, dict) or any(lineage.get(k) != self.expected[k] for k in LINEAGE_KEYS):
            raise ValueError("endpoint_lineage_mismatch")
        for key in ("adapterSha256", "tasksSha256", "baseRevision", "trainingSelectedStage",
                    "rawEvaluationReleaseGatePassed", "updateGroups"):
            if key in self.expected and lineage.get(key) != self.expected[key]:
                raise ValueError("endpoint_lineage_mismatch:" + key)
        if lineage.get("actualRL") is not True:
            raise ValueError("endpoint_rl_identity_not_verified")
        return copy.deepcopy(lineage)

    def _validate(self, request, answer, executor):
        score = executor.score(answer)
        errors = list(score["criticalErrors"])
        observed = {r["evidenceId"]: r for call in executor.trace if call["result"]["status"] == "ok"
                    for r in call["sourceRecords"]}
        ids = answer.get("evidenceIds", []) if isinstance(answer, dict) else []
        selected = [observed[eid] for eid in ids if isinstance(eid, str) and eid in observed] if isinstance(ids, list) else []
        required = {(s["family"], s["metric"], s["grain"]) for s in request["requiredMetrics"]}
        actual = {(r["family"], r["metric"], r["grain"]) for r in selected}
        if required != actual:
            errors.append("metric_or_grain_mismatch")
        for row in selected:
            if row["playerId"] != request["playerId"] or (row["family"] in {"basic", "advanced"} and row["gameId"] != request["gameId"]):
                errors.append("entity_or_game_mismatch")
            if (row["evidenceId"] != facts.record_id(row) or not re.fullmatch(r"[a-f0-9]{64}", row["source"].get("sha256", ""))):
                errors.append("source_hash_mismatch")
        if not score["valid"]:
            errors.append("incomplete_required_coverage")
        return sorted(set(errors)), selected, score

    def analyse(self, request):
        started, turns, calls, corrected, lineage = time.monotonic(), [], 0, False, None
        result = {"available": False, "endpoint": self.expected["endpoint"], "model": MODEL,
            "sourceTrainingJob": self.expected["sourceTrainingJob"], "selectedStage": "rl", "actualRL": False,
            "storeSha256": training_store_hash(self.store), "storeContentSha256": self.store["contentSha256"],
            "policy": POLICY, "protocol": PROTOCOL, "lineageVerified": False, "modelInvoked": False,
            "request": copy.deepcopy(request), "evidence": [], "relations": [], "provenance": [],
            "toolsUsed": [], "trace": turns, "correctionUsed": False}
        for key in ("sagemakerModel", "endpointConfig", "packageJob"):
            if key in self.expected:
                result[key] = self.expected[key]
        try:
            task, event = _task_from_request(request, self.store)
            executor = env.Environment(task, self.store)
            messages = [{"role": "system", "content": env.SYSTEM}, {"role": "user", "content": env.policy_view(task)}]
            while calls < self.max_model_calls:
                remaining = self.timeout_seconds - (time.monotonic() - started)
                if remaining <= getattr(self.invoke, "request_timeout_seconds", 0):
                    raise ValueError("runtime_deadline_exceeded")
                calls += 1
                result["modelInvoked"] = True
                payload = self.invoke(render_qwen(messages))
                lineage = self._verify_lineage(payload)
                result.update(lineageVerified=True, actualRL=True, lineage=lineage)
                text = payload["generation"].strip()
                messages.append({"role": "assistant", "content": text})
                turn = {"assistant": text}
                turns.append(turn)
                kind, answer, invalid = env.parse_action(text)
                if kind == "tools" and not invalid:
                    if len(executor.trace) + len(answer) > env.MAX_CALLS:
                        raise ValueError("tool_budget_exceeded")
                    results = [executor.execute(family) for family in answer]
                    turn["toolResults"] = results
                    result["toolsUsed"] = [call["result"]["tool"] for call in executor.trace]
                    messages.append({"role": "user", "content": canonical({"toolResults": results})})
                    continue
                errors, selected, score = self._validate(request, answer if kind == "answer" and not invalid else None, executor)
                turn["validation"] = {"errors": errors, "coverage": score["coverage"]}
                if not errors:
                    result.update(available=True, evidence=copy.deepcopy(selected), relations=answer["relations"],
                        event=event, coverage=1.0, threeLayersCovered=True,
                        provenance=[{"evidenceId": r["evidenceId"], **copy.deepcopy(r["source"])} for r in selected],
                        eventProvenance=copy.deepcopy(event["source"]),
                        interpretation="model_selected_evidence_and_context_relations_only",
                        scope="postgame_statistics_and_season_context_not_event_causal_measurement")
                    break
                if corrected:
                    result["error"] = "selection_invalid_after_one_correction"
                    result["validationErrors"] = errors
                    break
                corrected = result["correctionUsed"] = True
                feedback = {"validationErrors": errors, "requiredMetrics": request["requiredMetrics"],
                    "requiredRelations": request["requiredRelations"],
                    "instruction": "仅纠正一次：依据本次工具记录的metric和grain选择证据。TS_PCT与EFG_PCT是不同指标，即使数值相同也不能替换。不得猜测ID。"}
                messages.append({"role": "user", "content": canonical(feedback)})
            if not result["available"]:
                result.setdefault("error", "model_call_budget_exhausted")
        except Exception as error:
            result["error"] = f"{type(error).__name__}: {error}"
        result.update(modelCalls=calls, elapsedSeconds=round(time.monotonic() - started, 3))
        return result

    def analyse_story(self, story_id, depth_family="gravity"):
        return self.analyse(default_request(story_id, depth_family, self.store))
