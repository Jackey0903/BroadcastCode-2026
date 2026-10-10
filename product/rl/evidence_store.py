#!/usr/bin/env python3
"""Frozen HOU/DAL facts for tool-policy training and sourced video explanations.

This module assembles official facts and deterministic derived metrics. It does
not call an LLM, infer identities, or claim that an evidence bundle was trained.
"""
import argparse
from collections import Counter
import copy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
from urllib.parse import urlparse

from depth_tasks import validate_cohort

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DEFAULT_STORE = HERE / "data/evidence/store.json"
TEAMS = {1610612742: "DAL", 1610612745: "HOU"}
FAMILIES = ("basic", "advanced", "gravity", "leverage", "shotdifficulty")
BASIC = ("PTS", "FGM", "FGA", "FG3M", "FG3A", "FTM", "FTA", "AST", "REB", "OREB", "DREB", "TOV", "STL", "BLK", "MIN")
DEPTH_FIELDS = {
    "gravity": ("OVERALL_GRAV", "ON_BALL_PERIM_GRAV", "ON_BALL_INTERIOR_GRAV", "OFF_BALL_PERIM_GRAV", "OFF_BALL_INTERIOR_GRAV"),
    "leverage": ("TOT_LVG", "OFF_LVG", "DEF_LVG", "ON_BALL_DEF_LVG", "SHOT_LVG", "CREATION_LVG", "REB_LVG", "TOV_LVG"),
    "shotdifficulty": ("AVGSHOTQUALITY", "AVGSHOTQUALITY2PT", "AVGSHOTQUALITY3PT", "FGPCT", "FGPCTABOVEEXPECTED", "FG3PCT", "FG3PCTABOVEEXPECTED", "AVGDEFENDERPRESSURESCORE"),
}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def record_id(record):
    return "e" + sha({k: v for k, v in record.items() if k != "evidenceId"})[:12]


def _record(family, metric, value, unit, player_id, team_id, game_id, grain, period, source, **extra):
    item = {"family": family, "metric": metric, "value": value, "unit": unit,
            "playerId": str(player_id), "teamId": team_id, "gameId": game_id,
            "grain": grain, "period": copy.deepcopy(period), "asOf": None,
            "source": copy.deepcopy(source), "claimType": "official_fact", **extra}
    item["evidenceId"] = record_id(item)
    return item


def build_store(context_path=None, cohort_path=None):
    context_path = Path(context_path or HERE / "data/three_layer/context.json")
    cohort_path = Path(cohort_path or HERE / "data/depth/two-team-context.json")
    basic = json.loads(context_path.read_text())
    cohort = json.loads(cohort_path.read_text())
    validate_cohort(cohort)
    if basic.get("schema") != "rl-scout-three-layer-basic-advanced-v1":
        raise ValueError("Unsupported basic/advanced snapshot")
    players = {p["playerId"]: {"playerId": p["playerId"], "teamId": p["snapshotTeamId"],
               "displayName": p["displayName"], "teamSemantics": "source_snapshot_label"}
               for p in cohort["players"]}
    records, unavailable = [], []
    verified_files = set()
    for row in basic["records"]:
        pid, tid, gid = str(row["playerId"]), row["teamId"], row["gameId"]
        if tid not in TEAMS:
            raise ValueError("Player-game outside HOU/DAL")
        if pid in players and players[pid]["teamId"] != tid:
            raise ValueError("Conflicting current/game team membership; resolve explicitly")
        players.setdefault(pid, {"playerId": pid, "teamId": tid, "displayName": row["playerName"],
                                "teamSemantics": "observed_in_selected_games"})
        source = row["source"]
        source_path = ROOT / source["path"]
        if source_path not in verified_files:
            if file_sha(source_path) != source["sha256"]:
                raise ValueError("Boxscore source hash mismatch")
            verified_files.add(source_path)
        for metric in BASIC:
            value = row["basic"].get(metric)
            if metric == "MIN" and (not isinstance(value, str) or not re.fullmatch(r"\d{1,3}:[0-5]\d", value)):
                unavailable.append({"playerId": pid, "gameId": gid, "family": "basic", "metric": metric,
                                    "reasonCode": "source_duration_not_standard_mm_ss"})
                continue
            if value is not None:
                records.append(_record("basic", metric, value, "mm:ss" if metric == "MIN" else "count",
                    pid, tid, gid, "player-game", row["period"], source,
                    participation=row["status"], teamSemantics="event_game_team"))
        for metric in ("EFG_PCT", "TS_PCT"):
            value = row["advanced"].get(metric)
            if value is None:
                unavailable.append({"playerId": pid, "gameId": gid, "family": "advanced", "metric": metric,
                                    "reasonCode": row["advancedStatus"][metric]})
                continue
            records.append(_record("advanced", metric, value, "fraction", pid, tid, gid,
                "player-game", row["period"], source, claimType="derived_arithmetic",
                derivation=copy.deepcopy(row["derived"][metric]), teamSemantics="event_game_team"))
    for family in DEPTH_FIELDS:
        source = cohort["families"][family]
        if file_sha(cohort_path.parent / source["sourceFile"]) != source["sourceSha256"]:
            raise ValueError("Depth source hash mismatch")
        for row in source["rows"]:
            reference = {"url": source["sourceUrl"], "sha256": source["sourceSha256"],
                "path": str((cohort_path.parent / source["sourceFile"]).relative_to(ROOT)),
                "rowKey": f"data.{'shots' if family == 'shotdifficulty' else 'players'}[{row['sourceRowIndex']}]",
                "retrievedAt": source["sourceRetrievedAt"]}
            for metric in DEPTH_FIELDS[family]:
                value = row["metrics"].get(metric)
                if value is None:
                    continue
                records.append(_record(family, metric, value, source["metricUnits"][metric]["rawUnit"],
                    row["playerId"], row["snapshotTeamId"], None, "player-season",
                    {"season": source["season"], "seasonType": source["seasonType"], "range": "source_season_snapshot"},
                    reference, teamSemantics="source_snapshot_label_not_historical_membership"))
    # Bind only the two independently verified practice events; no inferred video mappings.
    events = []
    retrievals = {r["name"]: r for r in json.loads((ROOT / "product/research/sources/retrieval.json").read_text())}
    for story, event_id in (("flagg", 666), ("amen", 396)):
        path = ROOT / f"product/research/sources/gpshot-{story}.json"
        raw = json.loads(path.read_text())["data"]
        shot = next(r for r in raw["shotList"] if r["eventId"] == event_id)
        source = {"url": f"https://api.nba.cn/nba-web/api/web/inside/gpShot?gameId={raw['gameId']}&playerId={raw['playerId']}",
                  "sha256": file_sha(path), "path": str(path.relative_to(ROOT)),
                  "rowKey": f"data.shotList[eventId={event_id}]", "retrievedAt": retrievals[f"gpshot-{story}"]["retrievedAt"]}
        if source["sha256"] != retrievals[f"gpshot-{story}"]["sha256"]:
            raise ValueError("Verified event snapshot changed")
        events.append({"storyId": story, "gameId": raw["gameId"], "eventId": event_id,
            "playerId": str(raw["playerId"]), "teamId": raw["teamId"], "shotDesc": shot["shotDesc"],
            "shotType": shot["shotType"], "made": shot["success"], "xfg": shot["value"],
            "period": shot["period"], "grain": "shot-event", "source": source,
            "mapping": "existing_verified_practice_mapping_not_automatic_video_identification"})
    report = {"schema": "rl-scout-evidence-store-v1", "allowedTeams": TEAMS,
        "scope": "postgame_and_retrospective_season_context_not_pre_shot_prediction",
        "players": sorted(players.values(), key=lambda p: (p["teamId"], p["playerId"])),
        "records": sorted(records, key=lambda r: (r["playerId"], r["gameId"] or "", r["family"], r["metric"])),
        "unavailable": unavailable, "events": events,
        "inputHashes": {"basicAdvanced": file_sha(context_path), "depthCohort": file_sha(cohort_path)},
        "coverage": {"players": len(players), "games": sorted({r["gameId"] for r in basic["records"]}),
                     "recordsByFamily": dict(Counter(r["family"] for r in records))}}
    report["contentSha256"] = sha(report)
    validate_store(report)
    return report


def validate_store(store):
    if store.get("schema") != "rl-scout-evidence-store-v1":
        raise ValueError("Unsupported evidence store")
    # JSON stringifies dictionary keys; normalize before comparison.
    if {int(k): v for k, v in store["allowedTeams"].items()} != TEAMS:
        raise ValueError("Unexpected team scope")
    if sha({k: v for k, v in store.items() if k != "contentSha256"}) != store["contentSha256"]:
        raise ValueError("Evidence store content hash mismatch")
    ids = set()
    players = {p["playerId"]: p for p in store["players"]}
    for row in store["records"]:
        if row["playerId"] not in players or row["teamId"] not in TEAMS or row["family"] not in FAMILIES:
            raise ValueError("Record outside registered scope")
        if row["evidenceId"] != record_id(row) or row["evidenceId"] in ids:
            raise ValueError("Invalid or duplicate evidence id")
        ids.add(row["evidenceId"])
        value = row["value"]
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            raise ValueError("Invalid source value")
        if isinstance(value, (int, float)) and not math.isfinite(value):
            raise ValueError("Non-finite source value")
        host = urlparse(row["source"]["url"]).hostname or ""
        if not (host == "nba.com" or host.endswith(".nba.com") or host == "nba.cn" or host.endswith(".nba.cn")):
            raise ValueError("Non-official data source")
        if row["claimType"] == "derived_arithmetic":
            op = row["derivation"]["operands"]
            denominator = op["FGA"] if row["metric"] == "EFG_PCT" else 2 * (op["FGA"] + .44 * op["FTA"])
            numerator = op["FGM"] + .5 * op["FG3M"] if row["metric"] == "EFG_PCT" else op["PTS"]
            if denominator <= 0 or not math.isclose(value, numerator / denominator, abs_tol=1e-10):
                raise ValueError("Derived efficiency disagrees with official operands")
    return True


def load_store(path=DEFAULT_STORE):
    store = json.loads(Path(path).read_text())
    validate_store(store)
    return store


def query(store, player_id, families, game_id=None):
    pid = str(player_id)
    if not isinstance(families, (list, tuple)) or not families or set(families) - set(FAMILIES):
        raise ValueError("Unknown metric family")
    known = any(p["playerId"] == pid for p in store["players"])
    rows = [r for r in store["records"] if r["playerId"] == pid and r["family"] in families
            and (game_id is None or r["gameId"] is None or r["gameId"] == game_id)]
    present = {r["family"] for r in rows}
    return {"playerId": pid, "gameId": game_id, "records": copy.deepcopy(rows),
            "missing": [{"family": f, "reasonCode": "family_unavailable" if known else "player_unavailable"}
                        for f in families if f not in present], "storeSha256": store["contentSha256"]}


def build_bundle(store, player_id, game_id=None, event_id=None):
    """Deterministic context for the existing Agent; no trained-policy claim."""
    result = query(store, player_id, list(FAMILIES), game_id)
    wanted = {"basic": {"PTS", "FGM", "FGA", "FG3M", "FTA", "AST", "REB"},
              "advanced": {"EFG_PCT", "TS_PCT"},
              "gravity": {"OVERALL_GRAV", "OFF_BALL_PERIM_GRAV", "ON_BALL_PERIM_GRAV"},
              "leverage": {"CREATION_LVG", "DEF_LVG", "SHOT_LVG"},
              "shotdifficulty": {"AVGSHOTQUALITY", "AVGSHOTQUALITY2PT", "FGPCT", "FGPCTABOVEEXPECTED"}}
    result["records"] = [r for r in result["records"] if r["metric"] in wanted[r["family"]]]
    result["event"] = next((copy.deepcopy(e) for e in store["events"] if e["playerId"] == str(player_id)
                            and e["gameId"] == game_id and e["eventId"] == event_id), None)
    if event_id is not None and result["event"] is None:
        raise ValueError("Event identity has not been verified; no substitution")
    present = {r["family"] for r in result["records"]}
    result.update(schema="rl-scout-video-evidence-bundle-v1", inferenceSource="deterministic_official_evidence_assembly",
        trainedModelUsed=False, threeLayersAvailable=("basic" in present and "advanced" in present and bool(present & set(DEPTH_FIELDS))),
        usage={"basicAdvanced": "本场赛后统计；效率由官方计数计算", "depth": "赛季背景；不证明本回合因果",
               "event": "仅匹配的官方出手指标", "selection": "Downstream select relevant facts; do not render every metric"})
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, default=DEFAULT_STORE)
    args = p.parse_args()
    store = build_store()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(store, ensure_ascii=False, indent=1, allow_nan=False) + "\n")
    for event in store["events"]:
        bundle = build_bundle(store, event["playerId"], event["gameId"], event["eventId"])
        (args.output.parent / f"bundle-{event['storyId']}.json").write_text(json.dumps(bundle, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps({"path": str(args.output), "coverage": store["coverage"], "contentSha256": store["contentSha256"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
