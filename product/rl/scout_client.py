"""Runtime RL-SCOUT client for the agent: same two-turn protocol and tools as training.

    scout = Scout(invoke=bedrock_invoker(model_arn), tables_path="reference_tables.json")
    result = scout.analyse(official_row, player_id, official_quality)
The model never decides the official number; the difference is computed here. Any failure
returns {"available": False, ...} so the main pipeline can continue without the SCOUT layer.
The prompt/tool version comes from the tables' "policy" field (absent = v2 point scout) and must match
the model on the endpoint. Interval scouts (v3) also return low/high, and the label then compares the
official value with that interval instead of the fixed ±0.08 threshold.
"""
import json
from pathlib import Path

import scout_env as env

DELTA_THRESHOLD = 0.08
SOURCE = "AI 估计（强化学习球探）"


def bedrock_invoker(model_arn, client=None, max_tokens=160):
    """Bedrock imported-model call; tolerant of the response keys used by imported architectures."""
    import boto3
    runtime = client or boto3.Session(region_name="us-east-1").client("bedrock-runtime")

    def invoke(prompt):
        body = json.dumps({"prompt": prompt, "max_tokens": max_tokens, "temperature": 0.0})
        payload = json.loads(runtime.invoke_model(modelId=model_arn, body=body)["body"].read())
        for path in (("generation",), ("outputs", 0, "text"), ("choices", 0, "text"), ("completion",)):
            value = payload
            try:
                for key in path:
                    value = value[key]
                return value
            except (KeyError, IndexError, TypeError):
                continue
        raise ValueError(f"unrecognised response keys: {sorted(payload)}")
    return invoke


def sagemaker_invoker(endpoint_name, client=None, max_tokens=160):
    """SageMaker real-time endpoint serving the merged policy (serve/inference.py)."""
    import boto3
    runtime = client or boto3.Session(region_name="us-east-1").client("sagemaker-runtime")

    def invoke(prompt):
        response = runtime.invoke_endpoint(EndpointName=endpoint_name, ContentType="application/json",
                                           Body=json.dumps({"prompt": prompt, "max_tokens": max_tokens}))
        return json.loads(response["Body"].read())["generation"]
    return invoke


class Scout:
    def __init__(self, invoke, tables_path=None, tables=None, model_name="rl-scout"):
        self.invoke = invoke
        data = tables if tables is not None else json.loads(Path(tables_path).read_text())
        self.policy = data.get("policy", "v2")
        env.use_reward(self.policy)
        self.refs = env.References.from_tables(data)
        self.model_name = model_name

    def analyse(self, official_row, player_id, official_quality=None):
        try:
            env.use_reward(self.policy)
            shot = env.shot_from_official(official_row, player_id)
            messages = env.first_messages(shot)
            first = self.invoke(env.render_qwen(messages))
            kind, payload, invalid = env.parse_action(first)
            tools = []
            if kind == "tools":
                tools = payload
                messages += [{"role": "assistant", "content": first.strip()},
                             env.tool_message(payload, shot, self.refs)]
                kind, payload, invalid_second = env.parse_action(self.invoke(env.render_qwen(messages)))
                invalid = invalid or invalid_second
            if kind != "answer":
                return {"available": False, "error": "policy did not return an answer"}
            if self.policy == "v4" and not env.valid_interval_answer(payload, invalid):
                return {"available": False, "error": "invalid v4 interval answer"}
            typical = float(payload["quality"])
            if not 0 <= typical <= 1:
                return {"available": False, "error": "estimate out of range"}
            span = env._interval(payload, typical) if env.SPEC == "interval" else None
        except Exception as error:  # the SCOUT layer is optional; never break the main pipeline
            return {"available": False, "error": f"{type(error).__name__}: {error}"}
        result = {"available": True, "typicalQuality": round(typical, 3), "reason": str(payload.get("reason", ""))[:80],
                  "toolsUsed": tools, "model": self.model_name, "policy": self.policy, "source": SOURCE}
        if self.policy == "v4":
            result["pointStatistic"] = "conditional_median"
        if span:
            result.update({"low": round(span[0], 3), "high": round(span[1], 3), "interval": "central 60%"})
        if official_quality is not None:
            official = float(official_quality)
            delta = round(official - typical, 3)
            result["difficultyDelta"] = delta
            if span:
                result["label"] = "tougher" if official < span[0] else "easier" if official > span[1] else "typical"
            else:
                result["label"] = "tougher" if delta < -DELTA_THRESHOLD else "easier" if delta > DELTA_THRESHOLD else "typical"
        return result
