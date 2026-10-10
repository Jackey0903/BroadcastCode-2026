#!/usr/bin/env python3
"""Offline, source-grounded tasks for the HOU/DAL depth-metric snapshot.

This is a task/reward package, NOT a trained policy or an xFG predictor. It never
reads shots.jsonl, fetches an API, or exposes season aggregates to RL-SCOUT's xFG
prediction task. No third-party packages are needed.

    python3 product/rl/depth_tasks.py
    python3 -m unittest discover -s product/rl -p test_depth_tasks.py

Pure API: generate_tasks(cohort), policy_view(task), lookup(cohort, request),
score_answer(task, answer, tool_results=[actual_lookup_result]). The trainer must
keep task['oracle'] private and record real tool results itself. A policy may
not supply its own tool trace. All answer fields are structured: arbitrary prose
is rejected, so this scorer makes no claim to validate free-form causal language.
"""
import argparse
import copy
from collections import Counter
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re

DEFAULT_COHORT = Path(__file__).resolve().parent / "data/depth/two-team-context.json"
ALLOWED_TEAMS = {"HOU": 1610612745, "DAL": 1610612742}
TOOL_COST = 0.002
NUMERIC_TOLERANCE = 0.0005  # Half of the finest 3-decimal source display unit.
TEAM_SEMANTICS = "source_snapshot_label_not_historical_membership"
TASK_SCHEMA = "rl-scout-depth-task-v1"
FIELDS = {
    "gravity": ("OVERALL_GRAV", "ON_BALL_PERIM_GRAV", "ON_BALL_INTERIOR_GRAV",
                "OFF_BALL_PERIM_GRAV", "OFF_BALL_INTERIOR_GRAV"),
    "leverage": ("TOT_LVG", "OFF_LVG", "DEF_LVG", "ON_BALL_DEF_LVG", "SHOT_LVG",
                 "CREATION_LVG", "REB_LVG", "TOV_LVG"),
    "shotdifficulty": ("AVGSHOTQUALITY", "FGPCT", "FGPCTABOVEEXPECTED",
                       "AVGDEFENDERBALLDISTANCE", "AVGDEFENDERPRESSURESCORE"),
}
ANSWER_KEYS = frozenset({"status", "family", "metric", "playerIds", "season", "seasonType",
                         "requestedScope", "sourceGrain", "sourceSeason", "sourceSeasonType",
                         "snapshotTeamIds", "teamSemantics",
                         "requestedAsOf", "dataAsOf", "operation", "value", "unit",
                         "reasonCode", "claimType", "evidence"})


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def validate_cohort(cohort):
    """Validate the allowed cohort, source identities and reproducible content hash."""
    if cohort.get("schema") != "rl-scout-two-team-official-context-v1":
        raise ValueError("Unsupported depth cohort schema")
    declared = {k: v.get("teamId") for k, v in cohort.get("allowedTeams", {}).items()}
    if declared != ALLOWED_TEAMS:
        raise ValueError("Only the HOU/DAL cohort is authorized")
    content = {"families": cohort.get("families"), "players": cohort.get("players")}
    digest = hashlib.sha256(_canonical(content).encode()).hexdigest()
    if digest != cohort.get("reproducibility", {}).get("selectedContentSha256"):
        raise ValueError("Cohort content hash mismatch")
    players = {p["playerId"]: p for p in cohort["players"]}
    if len(players) != len(cohort["players"]):
        raise ValueError("Duplicate cohort player")
    for player in players.values():
        if ALLOWED_TEAMS.get(player["snapshotTeamAbbreviation"]) != player["snapshotTeamId"]:
            raise ValueError("Player is outside the authorized team cohort")
    if set(cohort["families"]) != set(FIELDS):
        raise ValueError("Unexpected metric family")
    for family, source in cohort["families"].items():
        if (source["grain"] != "player-season" or source["season"] != cohort["season"]
                or source["seasonType"] != cohort["seasonType"]):
            raise ValueError("Mixed source scope")
        if not re.fullmatch(r"[0-9a-f]{64}", source["sourceSha256"]):
            raise ValueError("Invalid source hash")
        if not source["sourceUrl"].startswith("https://api.nba.cn/nba-web/api/web/inside/"):
            raise ValueError("Unexpected source URL")
        if datetime.fromisoformat(source["sourceRetrievedAt"]).tzinfo is None:
            raise ValueError("Retrieval time requires a timezone")
        seen = set()
        for row in source["rows"]:
            pid = row["playerId"]
            if pid not in players or pid in seen:
                raise ValueError("Missing or duplicate player identity")
            seen.add(pid)
            if (row["snapshotTeamId"] != players[pid]["snapshotTeamId"]
                    or ALLOWED_TEAMS.get(row["snapshotTeamAbbreviation"]) != row["snapshotTeamId"]):
                raise ValueError("Conflicting team label")
            for metric in FIELDS[family]:
                value = row["metrics"].get(metric)
                if value is not None and not _finite(value):
                    raise ValueError("Non-finite/non-numeric source metric")
                if metric not in source["metricUnits"]:
                    raise ValueError("Metric unit metadata missing")
    return True


def _evidence(source, rows):
    return {"sourceId": source["sourceId"], "sourceSha256": source["sourceSha256"],
            "sourceUrl": source["sourceUrl"], "retrievedAt": source["sourceRetrievedAt"],
            "rowIndices": [r["sourceRowIndex"] for r in rows]}


def _lookup(cohort, request):
    """Internal lookup after cohort validation; performs no I/O or mutations."""
    family, metric = request["family"], request["metric"]
    if family not in FIELDS or metric not in FIELDS[family]:
        raise ValueError("Metric not in the permitted task vocabulary")
    if request["kind"] not in {"lookup", "compare", "causal"}:
        raise ValueError("Unknown task kind")
    pids = request["playerIds"]
    if (not isinstance(pids, list) or not pids or len(set(pids)) != len(pids)
            or len(pids) != (2 if request["kind"] == "compare" else 1)):
        raise ValueError("Invalid player operands")
    players = {p["playerId"]: p for p in cohort["players"]}
    source = cohort["families"][family]
    by_id = {r["playerId"]: r for r in source["rows"]}
    rows = [by_id[pid] for pid in pids if pid in by_id]
    reason = None
    if any(pid not in players for pid in pids):
        reason = "player_not_in_authorized_cohort"
    elif request["season"] != source["season"] or request["seasonType"] != source["seasonType"]:
        reason = "season_not_available"
    elif request.get("teamIds") != [players[pid]["snapshotTeamId"] for pid in pids]:
        reason = "team_label_mismatch"
    elif request.get("asOf") is not None:
        reason = "historical_as_of_not_available"
    elif request["scope"] != "player-season":
        reason = "event_granularity_not_available"
    elif request["kind"] == "causal":
        reason = "causal_evidence_not_available"
    elif len(rows) != len(pids):
        reason = "metric_family_not_in_source_cohort"
    elif any(row["metrics"].get(metric) is None for row in rows):
        reason = "metric_value_missing"
    return {"tool": "official_depth_lookup", "request": copy.deepcopy(request),
            "status": "unavailable" if reason else "ok", "reasonCode": reason,
            "sourceGrain": source["grain"], "sourceSeason": source["season"],
            "sourceSeasonType": source["seasonType"], "dataAsOf": None,
            "teamSemantics": TEAM_SEMANTICS, "unit": source["metricUnits"][metric]["rawUnit"],
            "evidence": _evidence(source, rows),
            # For unsupported queries, do not substitute season values into the requested result.
            "records": [] if reason else [{"playerId": row["playerId"],
                "snapshotTeamId": row["snapshotTeamId"], "metric": metric,
                "value": row["metrics"][metric]} for row in rows],
            "snapshotTeamIds": [players[pid]["snapshotTeamId"] if pid in players else None for pid in pids]}


def lookup(cohort, request):
    """Return source facts/limitations only; comparisons remain the policy's arithmetic."""
    validate_cohort(cohort)
    return copy.deepcopy(_lookup(cohort, request))


def _expected(request, result):
    ok = result["status"] == "ok"
    compare = request["kind"] == "compare"
    values = [r["value"] for r in result["records"]]
    value = round(values[0] - values[1], 6) if ok and compare else values[0] if ok else None
    return {"status": result["status"], "family": request["family"], "metric": request["metric"],
            "playerIds": request["playerIds"], "season": request["season"],
            "seasonType": request["seasonType"], "requestedScope": request["scope"],
            "sourceGrain": result["sourceGrain"], "sourceSeason": result["sourceSeason"],
            "sourceSeasonType": result["sourceSeasonType"], "snapshotTeamIds": result["snapshotTeamIds"],
            "teamSemantics": TEAM_SEMANTICS, "requestedAsOf": request.get("asOf"), "dataAsOf": None,
            "operation": "subtract" if compare else "lookup", "value": value, "unit": result["unit"],
            "reasonCode": result["reasonCode"],
            "claimType": "arithmetic" if ok and compare else "source_fact" if ok else "limitation",
            "evidence": result["evidence"]}


def _task(cohort, request, category):
    result = _lookup(cohort, request)
    ids = "、".join(request["playerIds"])
    base = (f"球员 {ids}；{request['season']} {request['seasonType']}；"
            f"查询 {request['family']}.{request['metric']}，范围 {request['scope']}。")
    if request["kind"] == "compare":
        base += "请计算第一名减第二名的同指标差值，保留原始单位。"
    elif request["kind"] == "causal":
        base += "请判断这个指标是否证明该球员造成了某一回合队友的空位。"
    if request.get("asOf"):
        base += f"仅能使用截至 {request['asOf']} 已发生比赛的统计。"
    base += "依据工具返回的来源与粒度回答；证据不足返回 unavailable，不补零。只输出约定 JSON，不加自由文本。"
    return {"schema": TASK_SCHEMA,
            "id": hashlib.sha256(_canonical(request).encode()).hexdigest()[:20],
            "category": category, "request": copy.deepcopy(request), "prompt": base,
            "oracle": {"answer": _expected(request, result), "toolResult": result}}


def generate_tasks(cohort, player_ids=None):
    """Deterministic task set; optionally restrict to a player-group split first.

    Pass disjoint player_ids for train/eval; generated comparisons stay within that
    split. Held-out source rows may be retrieved in this retrieval benchmark.
    This API never creates or evaluates an xFG prediction training observation.
    """
    validate_cohort(cohort)
    known = {p["playerId"]: p for p in cohort["players"]}
    selected = sorted(known if player_ids is None else set(player_ids))
    if set(selected) - set(known):
        raise ValueError("A task split contains a player outside the authorized cohort")
    tasks = []

    def request(family, metric, pids, **overrides):
        item = {"kind": "lookup", "family": family, "metric": metric, "playerIds": pids,
                "season": cohort["season"], "seasonType": cohort["seasonType"],
                "scope": "player-season", "asOf": None,
                "teamIds": [known[pid]["snapshotTeamId"] for pid in pids]}
        item.update(overrides)
        return item

    for family, metrics in FIELDS.items():
        rows = {r["playerId"]: r for r in cohort["families"][family]["rows"]}
        for pid in selected:
            if pid not in rows:
                tasks.append(_task(cohort, request(family, metrics[0], [pid]), "missing_family"))
                continue
            for metric in metrics:
                category = "missing_value" if rows[pid]["metrics"].get(metric) is None else "lookup"
                tasks.append(_task(cohort, request(family, metric, [pid]), category))
            tasks.append(_task(cohort, request(family, metrics[0], [pid], scope="event"), "event_boundary"))
        # Same-metric comparisons, deterministic adjacent pairs within each team.
        for team in sorted(ALLOWED_TEAMS.values()):
            pids = [pid for pid in selected if pid in rows and known[pid]["snapshotTeamId"] == team]
            for left, right in zip(pids, pids[1:]):
                tasks.append(_task(cohort, request(family, metrics[0], [left, right], kind="compare"), "compare"))
            if pids:
                pid = pids[0]
                tasks.append(_task(cohort, request(family, metrics[0], [pid], asOf="2026-01-04"), "as_of_boundary"))
                tasks.append(_task(cohort, request(family, metrics[0], [pid], season="2024-25"), "season_boundary"))
                wrong_team = next(t for t in sorted(ALLOWED_TEAMS.values()) if t != team)
                tasks.append(_task(cohort, request(family, metrics[0], [pid], teamIds=[wrong_team]), "team_boundary"))
                if family == "gravity":
                    tasks.append(_task(cohort, request(family, metrics[0], [pid], kind="causal"), "causal_boundary"))
    if len({t["id"] for t in tasks}) != len(tasks):
        raise ValueError("Duplicate generated task")
    return tasks


def policy_view(task):
    """Only request/prompt/contract reach the policy; oracle/expected value stay hidden."""
    return {k: copy.deepcopy(task[k]) for k in ("id", "request", "prompt")} | {
        "answerKeys": sorted(ANSWER_KEYS),
        "answerContract": {"status": ["ok", "unavailable"], "value": "finite number or null",
            "dataAsOf": None, "sourceGrain": "player-season", "teamSemantics": TEAM_SEMANTICS,
            "claimType": ["source_fact", "arithmetic", "limitation"],
            "evidence": "sourceId/sourceSha256/sourceUrl/retrievedAt/rowIndices from the tool",
            "unit": "tool raw unit, including unknown when not confirmed",
            "operation": "lookup or subtract; no free-form claims"}}


def score_answer(task, answer, tool_results=()):
    """Score source facts and boundaries. Extra tool calls strictly reduce reward.

    The harness must supply observed tool_results; this function does not execute
    tools. Exact match to the deterministic lookup output verifies the requested
    evidence was actually returned. A correct copied answer without a trace cannot
    receive positive grounded reward. No LLM judge or language-number heuristic.
    """
    trace = list(tool_results)
    cost = TOOL_COST * len(trace)
    parts = {"value": 0.0, "scope": 0.0, "evidence": 0.0, "schema": 0.0,
             "toolCalls": len(trace), "criticalErrors": []}
    if isinstance(answer, str):
        try:
            answer = json.loads(answer)
        except (ValueError, TypeError):
            answer = None
    if not isinstance(answer, dict) or set(answer) != ANSWER_KEYS:
        parts.update(total=round(-1.0 - cost, 6), criticalErrors=["invalid_schema_or_free_form_claim"])
        return parts
    parts["schema"] = 1.0
    expected = task["oracle"]["answer"]
    scope_keys = ANSWER_KEYS - {"value", "status", "reasonCode", "evidence"}
    mismatches = [k for k in sorted(scope_keys) if _canonical(answer[k]) != _canonical(expected[k])]
    if mismatches:
        parts["criticalErrors"].append("scope_metric_unit_or_claim_mismatch:" + ",".join(mismatches))
    else:
        parts["scope"] = 1.0
    status_ok = answer["status"] == expected["status"] and answer["reasonCode"] == expected["reasonCode"]
    if expected["status"] == "unavailable":
        value_ok = answer["value"] is None
    else:
        value_ok = _finite(answer["value"]) and abs(answer["value"] - expected["value"]) <= NUMERIC_TOLERANCE
    parts["value"] = float(status_ok and value_ok)
    if not status_ok or not value_ok:
        parts["criticalErrors"].append("incorrect_value_or_unavailable_decision")
    matching_trace = any(_canonical(result) == _canonical(task["oracle"]["toolResult"]) for result in trace)
    if _canonical(answer["evidence"]) == _canonical(expected["evidence"]) and matching_trace:
        parts["evidence"] = 1.0
    else:
        parts["criticalErrors"].append("source_or_observed_tool_evidence_mismatch")
    total = 0.45 * parts["value"] + 0.25 * parts["scope"] + 0.20 * parts["evidence"] + 0.10 * parts["schema"] - cost
    if parts["criticalErrors"]:
        # Event/cause/as-of/source/team errors must never earn a positive partial reward.
        total = min(total, -0.5 - cost)
    parts["total"] = round(total, 6)
    return parts


def summarize_tasks(cohort, tasks):
    """Reviewable plan metadata, not a training/evaluation success claim."""
    return {"schema": "rl-scout-depth-task-plan-v1", "status": "offline_task_package_not_trained",
            "taskCount": len(tasks), "categories": dict(sorted(Counter(t["category"] for t in tasks).items())),
            "families": dict(sorted(Counter(t["request"]["family"] for t in tasks).items())),
            "answerStatus": dict(Counter(t["oracle"]["answer"]["status"] for t in tasks)),
            "allowedTeams": ALLOWED_TEAMS, "players": len({p for t in tasks for p in t["request"]["playerIds"]}),
            "sourceCohortContentSha256": cohort["reproducibility"]["selectedContentSha256"],
            "taskSetSha256": hashlib.sha256(_canonical(tasks).encode()).hexdigest(),
            "sourceHashes": {f: s["sourceSha256"] for f, s in cohort["families"].items()},
            "valueToleranceRawUnits": NUMERIC_TOLERANCE, "toolCost": TOOL_COST,
            "boundaries": ["HOU/DAL only", "Season aggregates never enter xFG prediction task",
                           "Snapshot team labels do not prove historical membership",
                           "retrievedAt is not a historical data cutoff", "No event or causal labels",
                           "No GPU/model invocation; task generator and deterministic reward only"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", type=Path, default=DEFAULT_COHORT)
    parser.add_argument("--plan", type=Path, help="Optionally write the summary plan JSON")
    args = parser.parse_args()
    cohort = json.loads(args.cohort.read_text())
    plan = summarize_tasks(cohort, generate_tasks(cohort))
    if args.plan:
        args.plan.parent.mkdir(parents=True, exist_ok=True)
        args.plan.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(plan, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
