"""Small product payload for the verified RL selector and official comparisons.

The caller owns question planning, identity verification, narration and rendering.
This bridge invokes the existing policy once, or explicitly replays a pinned real
receipt for UI integration. It never marks an existing video as using RL.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone

from evidence_client import (EvidenceClient, MODEL, POLICY, canonical,
                             default_request, sagemaker_invoker, training_store_hash)
from evidence_store import load_store
from player_comparison import build_story_context, LABELS, _format

HERE = Path(__file__).resolve().parent
HANDOFF = HERE / "results/evidence-v1/runtime-handoff.json"
FOCUSES = {"spacing": "gravity", "creation": "leverage", "shot_quality": "shotdifficulty"}
MAX_PRESENTATION_BYTES = 48000
TOOL_SPEC = {"name": "query_rl_scout", "description":
    "For a registered video, select three-layer evidence with the trained RL data scout. "
    "Choose spacing, creation or shot_quality based on the user question; optionally select "
    "an opposing player for deterministic profile comparison. This does not identify a defender.",
    "inputSchema": {"type": "object", "additionalProperties": False, "required": ["storyId", "focus"],
        "properties": {"storyId": {"type": "string", "enum": ["flagg", "amen"]},
            "focus": {"type": "string", "enum": list(FOCUSES)}, "opponentId": {"type": "string", "pattern": "^[0-9]+$"}}}}


def _public_profile(profile, card, scoped):
    return {"player": profile["player"], "gameId": profile["gameId"], "sections": profile["sections"],
        "facts": [card(r) for r in profile["facts"]], "derived": [scoped(r) for r in profile["derived"]],
        "missingMetrics": profile["missingMetrics"], "scopeLabels": profile["scopeLabels"]}


class ProductBridge:
    def __init__(self, selector):
        if not isinstance(selector, EvidenceClient):
            raise ValueError("verified_evidence_client_required")
        self.selector = selector
        self.store = selector.store

    def _request(self, story_id, focus):
        if focus not in FOCUSES:
            raise ValueError("unsupported_focus")
        return default_request(story_id, FOCUSES[focus], self.store)

    def _format(self, story_id, focus, context, raw, mode, receipt=None):
        request = self._request(story_id, focus)
        event = context["event"]
        accepted, error = False, raw.get("error")
        if raw.get("available") is True:
            try:
                if not all(raw.get(k) is True for k in ("modelInvoked", "lineageVerified", "actualRL", "threeLayersCovered")):
                    raise ValueError("incomplete_verified_model_state")
                self.selector._verify_lineage({"generation": "", "lineage": raw.get("lineage")})
                expected = self.selector.expected
                for key in ("model", "sourceTrainingJob", "selectedStage", "policy", "endpoint"):
                    if raw.get(key) != expected.get(key):
                        raise ValueError("result_identity_mismatch:" + key)
                if raw.get("request") != request or raw.get("event") != event:
                    raise ValueError("result_event_or_request_mismatch")
                if raw.get("storeSha256") != training_store_hash(self.store) or raw.get("storeContentSha256") != self.store["contentSha256"]:
                    raise ValueError("result_store_mismatch")
                rows = {r["evidenceId"]: r for r in self.store["records"]}
                selected = raw.get("evidence", [])
                required = {(r["family"], r["metric"], r["grain"]) for r in request["requiredMetrics"]}
                if not isinstance(selected, list) or len(selected) != len(required):
                    raise ValueError("incomplete_evidence")
                if any(not isinstance(r, dict) or r != rows.get(r.get("evidenceId")) for r in selected):
                    raise ValueError("changed_or_unknown_evidence")
                actual = {(r["family"], r["metric"], r["grain"]) for r in selected}
                if actual != required or any(r["playerId"] != event["playerId"] or
                    (r["grain"] == "player-game" and r["gameId"] != event["gameId"]) for r in selected):
                    raise ValueError("wrong_evidence_scope")
                if sorted(raw.get("relations", [])) != sorted(request["requiredRelations"]):
                    raise ValueError("wrong_context_relations")
                accepted, error = True, None
            except (ValueError, KeyError, TypeError) as exc:
                error = str(exc)

        sources, periods = {}, {}
        def period_ref(period):
            if period is None:
                return None
            key = "p" + hashlib.sha256(canonical(period).encode()).hexdigest()[:16]
            periods[key] = copy.deepcopy(period)
            return key

        def scoped(record):
            return {**{k: copy.deepcopy(v) for k, v in record.items() if k != "period"},
                    "periodRef": period_ref(record.get("period"))}

        def card(row):
            source = row["source"]
            source_id = "s" + hashlib.sha256(canonical(source).encode()).hexdigest()[:16]
            sources[source_id] = copy.deepcopy(source)
            return {"evidenceId": row["evidenceId"], "family": row["family"], "metric": row["metric"],
                "label": row.get("label", LABELS.get(row["metric"], row["metric"])),
                "value": row["value"], "unit": row["unit"], "display": _format(row["value"], row["unit"]),
                "playerId": row["playerId"], "gameId": row["gameId"], "grain": row["grain"],
                "periodRef": period_ref(row["period"]), "claimType": row["claimType"], "sourceRef": source_id}

        comparison = context["comparison"]
        scout = {"available": accepted, "trainedModelUsed": accepted, "selectionVerified": accepted,
            "lineageVerified": accepted, "actualRL": accepted, "modelInvoked": raw.get("modelInvoked") is True,
            "modelInvokedThisRequest": mode == "live" and raw.get("modelInvoked") is True,
            "invocationMode": mode, "status": ("verified_live_selection" if mode == "live" else "verified_recorded_selection") if accepted else "unavailable",
            "badge": "RL 数据球探" if accepted else None,
            "statusLabel": ("本次已调用模型" if mode == "live" else "已生成的真实模型选证回放") if accepted else "模型选证未通过；官方数据可查看",
            "model": MODEL, "sourceTrainingJob": self.selector.expected["sourceTrainingJob"],
            "modelIdentity": {k: self.selector.expected[k] for k in
                ("sagemakerModel", "endpointConfig", "adapterSha256", "mergedWeightsSha256", "optimizerUpdateSteps")
                if k in self.selector.expected},
            "selectedStage": "rl", "policy": POLICY, "endpoint": self.selector.expected["endpoint"],
            "evidence": [card(r) for r in raw["evidence"]] if accepted else [],
            "relations": raw.get("relations", []) if accepted else [], "threeLayersCovered": accepted,
            "correctionUsed": raw.get("correctionUsed") is True, "modelCalls": raw.get("modelCalls", 0),
            "elapsedSeconds": raw.get("elapsedSeconds"), "error": error,
            "traceSteps": [{"step": i + 1, "tools": [r.get("tool") for r in turn.get("toolResults", [])],
                "validationErrors": turn.get("validation", {}).get("errors", [])} for i, turn in enumerate(raw.get("trace", []))],
            "receipt": copy.deepcopy(receipt)}
        profile = {"trainedModelUsed": False, "inferenceSource": "deterministic_official_data_and_arithmetic",
            "matchupVerified": False, "defenderPlayerId": None,
            "attacker": _public_profile(context["attacker"], card, scoped), "opponentChoices": context["opponentChoices"],
            "selectedOpponentId": context["selectedOpponentId"],
            "opponent": _public_profile(comparison["right"], card, scoped) if comparison else None,
            "comparisons": [scoped(r) for r in comparison["comparisons"]] if comparison else [],
            "unavailableComparisons": comparison["unavailable"] if comparison else []}
        presentation = {"schema": "rl-scout-product-bridge-v1", "sample": story_id,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "gameId": event["gameId"], "eventId": event["eventId"], "playerId": event["playerId"],
            "focus": focus, "planSource": "caller_selected_focus_not_free_text_question_planning",
            "storeContentSha256": self.store["contentSha256"], "scout": scout,
            "playerComparison": profile, "sources": sources, "periods": periods,
            "videoUse": {"narrativeUsed": False, "burnedIntoVideo": False, "evidenceIdsUsed": []}}
        if len(canonical(presentation).encode()) > MAX_PRESENTATION_BYTES:
            raise ValueError("product_payload_exceeds_48kb")
        return {"presentation": presentation, "audit": {"rawSelectorResult": copy.deepcopy(raw),
            "invocationMode": mode, "receipt": copy.deepcopy(receipt)}}

    def analyse(self, story_id, focus="spacing", opponent_id=None):
        request = self._request(story_id, focus)
        # Validate selection before any billable call; missing opponent cannot become a guessed defender.
        context = build_story_context(self.store, story_id, opponent_id)
        raw = self.selector.analyse(request)
        return self._format(story_id, focus, context, raw, "live")

    def replay(self, path, expected_sha256, story_id, focus="spacing", opponent_id=None):
        """Replay a caller-pinned historical receipt; never makes a model call."""
        data = Path(path).read_bytes()
        actual_sha = hashlib.sha256(data).hexdigest()
        if actual_sha != expected_sha256:
            raise ValueError("recorded_receipt_hash_mismatch")
        document = json.loads(data)
        if document.get("complete") is not True:
            raise ValueError("recorded_run_incomplete")
        family = FOCUSES.get(focus)
        cases = [c for c in document.get("cases", []) if c.get("story") == story_id and c.get("depthFamily") == family]
        if len(cases) != 1:
            raise ValueError("recorded_case_missing_or_ambiguous")
        context = build_story_context(self.store, story_id, opponent_id)
        receipt = {"file": Path(path).name, "sha256": actual_sha, "completedAt": document.get("completedAt")}
        return self._format(story_id, focus, context, cases[0]["result"], "recorded_live_replay", receipt)


def create_bridge(runtime_client, handoff_path=HANDOFF):
    """Inject a bounded workload-role SDK client; no implicit local/default profile."""
    if runtime_client is None:
        raise ValueError("explicit_workload_runtime_client_required")
    handoff = json.loads(Path(handoff_path).read_text())
    selector = EvidenceClient(sagemaker_invoker(handoff["endpoint"], client=runtime_client, max_tokens=160),
        expected_lineage=handoff["expectedLineage"], store=load_store())
    return ProductBridge(selector)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--story", choices=("flagg", "amen"), required=True)
    p.add_argument("--focus", choices=tuple(FOCUSES), default="spacing")
    p.add_argument("--opponent")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--replay", type=Path)
    p.add_argument("--receipt-sha256")
    args = p.parse_args()
    audit_path = args.output.with_suffix(".audit.json")
    if args.output.exists() or audit_path.exists():
        raise SystemExit("Choose a new output path; existing evidence is preserved")
    if bool(args.replay) != bool(args.receipt_sha256):
        raise SystemExit("Replay requires its independently pinned receipt hash")
    handoff = json.loads(HANDOFF.read_text())
    if args.replay:
        def no_inference(prompt):
            raise RuntimeError("Replay must never invoke a model")
        bridge = ProductBridge(EvidenceClient(no_inference, handoff["expectedLineage"]))
        result = bridge.replay(args.replay, args.receipt_sha256, args.story, args.focus, args.opponent)
    else:
        import boto3
        from botocore.config import Config
        session = boto3.Session(profile_name="nba", region_name="us-east-1")
        identity = session.client("sts").get_caller_identity()
        if identity["Account"] != "555726205424" or ":assumed-role/NBAHackathonParticipantRole/" not in identity["Arn"]:
            raise SystemExit("Unexpected AWS identity")
        endpoint = session.client("sagemaker").describe_endpoint(EndpointName=handoff["endpoint"])
        if endpoint["EndpointStatus"] != "InService" or endpoint["EndpointConfigName"] != handoff["expectedLineage"]["endpointConfig"]:
            raise SystemExit("Endpoint is not the verified deployed configuration")
        sdk = session.client("sagemaker-runtime", config=Config(connect_timeout=20, read_timeout=25, retries={"total_max_attempts": 1}))
        result = create_bridge(sdk).analyse(args.story, args.focus, args.opponent)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result["presentation"], ensure_ascii=False, indent=1, allow_nan=False) + "\n")
    audit_path.write_text(json.dumps(result["audit"], ensure_ascii=False, indent=1, allow_nan=False) + "\n")
    print(json.dumps({"path": str(args.output), "available": result["presentation"]["scout"]["available"],
        "mode": result["presentation"]["scout"]["invocationMode"], "bytes": len(canonical(result["presentation"]).encode()),
        "videoUsed": False}))


if __name__ == "__main__":
    main()
