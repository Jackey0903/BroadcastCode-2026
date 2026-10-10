"""Deterministic player profiles/comparisons beside the frozen RL policy.

No model call, defender identification, or change to the trained store. Game
statistics describe completed games; depth statistics retain their snapshot.
"""
import argparse
import copy
import json
from pathlib import Path

from evidence_env import LABELS
from evidence_store import FAMILIES, TEAMS, load_store, query, validate_store

LABELS = {**LABELS, "FGM": "投篮命中", "FGA": "投篮出手", "FG3M": "三分命中",
          "FG3A": "三分出手", "FTM": "罚球命中", "FTA": "罚球出手",
          "OREB": "进攻篮板", "DREB": "防守篮板", "STL": "抢断", "BLK": "盖帽", "REB": "总篮板"}
GROUPS = {
    "gameOffense": ("PTS", "FGM", "FGA", "FG3M", "FG3A", "FTM", "FTA", "AST", "TOV", "OREB"),
    "gameDefense": ("STL", "BLK", "DREB"),
    "gameGeneral": ("MIN", "REB"),
    "gameEfficiency": ("EFG_PCT", "TS_PCT"),
    "seasonOffense": ("OVERALL_GRAV", "ON_BALL_PERIM_GRAV", "ON_BALL_INTERIOR_GRAV",
                      "OFF_BALL_PERIM_GRAV", "OFF_BALL_INTERIOR_GRAV", "OFF_LVG", "CREATION_LVG", "SHOT_LVG"),
    "seasonDefense": ("DEF_LVG", "ON_BALL_DEF_LVG"),
    "seasonOverall": ("REB_LVG", "TOV_LVG", "TOT_LVG"),
    # Pressure is experienced by this shooter, not pressure attributed to him as defender.
    "seasonShooting": ("FGPCT", "AVGSHOTQUALITY", "FGPCTABOVEEXPECTED", "FG3PCT",
                       "AVGSHOTQUALITY3PT", "FG3PCTABOVEEXPECTED", "AVGSHOTQUALITY2PT", "AVGDEFENDERPRESSURESCORE"),
}
RATIOS = {
    "GAME_FG_PCT": ("本场投篮命中率", "FGM", "FGA", "fraction"),
    "GAME_FG3_PCT": ("本场三分命中率", "FG3M", "FG3A", "fraction"),
    "GAME_FT_PCT": ("本场罚球命中率", "FTM", "FTA", "fraction"),
    "GAME_AST_TOV": ("本场助攻失误比", "AST", "TOV", "ratio"),
    "GAME_3PA_SHARE": ("本场三分出手占比", "FG3A", "FGA", "fraction"),
}
COMPARABLE = ("PTS", "AST", "TOV", "REB", "STL", "BLK", "DREB", "EFG_PCT", "TS_PCT",
              "OVERALL_GRAV", "OFF_BALL_PERIM_GRAV", "CREATION_LVG", "OFF_LVG", "DEF_LVG",
              "ON_BALL_DEF_LVG", "FGPCT", "AVGSHOTQUALITY", "FGPCTABOVEEXPECTED")


def _format(value, unit):
    if value is None:
        return None
    if unit == "fraction":
        return f"{value * 100:.2f}%"
    if unit in {"fraction_difference", "percentage_points"}:
        scaled = value * 100 if unit == "fraction_difference" else value
        return f"{scaled:+.2f}个百分点"
    if isinstance(value, str):
        return value
    return str(round(value, 3))


def _profile(store, player_id, game_id):
    pid = str(player_id)
    player = next((p for p in store["players"] if p["playerId"] == pid), None)
    rows = query(store, pid, list(FAMILIES), game_id)["records"]
    game_rows = [r for r in rows if r["grain"] == "player-game"]
    if player is None or not game_rows:
        raise ValueError("Player has no official boxscore in this game")
    if not any(r.get("participation") == "played" for r in game_rows):
        raise ValueError("Player did not play; do not display zero as performance")
    teams = {r["teamId"] for r in game_rows}
    if len(teams) != 1 or not teams <= set(TEAMS):
        raise ValueError("Ambiguous game team")
    by_metric = {r["metric"]: r for r in rows}
    if len(by_metric) != len(rows):
        raise ValueError("Ambiguous metric snapshot")
    for r in rows:
        r.update(label=LABELS.get(r["metric"], r["metric"]), displayValue=_format(r["value"], r["unit"]))
    derived = []
    for metric, (label, numerator, denominator, unit) in RATIOS.items():
        operands = [by_metric[m] for m in (numerator, denominator) if m in by_metric]
        available = len(operands) == 2 and operands[1]["value"] > 0
        value = operands[0]["value"] / operands[1]["value"] if available else None
        derived.append({"metric": metric, "label": label, "available": available,
            "reasonCode": None if available else "missing_operand" if len(operands) < 2 else "zero_denominator",
            "value": value, "unit": unit, "displayValue": _format(value, unit),
            "claimType": "derived_arithmetic", "formula": f"{numerator}/{denominator}",
            "grain": "player-game", "gameId": game_id, "period": copy.deepcopy(game_rows[0]["period"]),
            "operands": [{"evidenceId": r["evidenceId"], "metric": r["metric"], "value": r["value"]} for r in operands]})
    for metric, actual, expected in (("SEASON_FG_VS_EXPECTED_PP", "FGPCT", "AVGSHOTQUALITY"),
                                      ("SEASON_FG3_VS_EXPECTED_PP", "FG3PCT", "AVGSHOTQUALITY3PT")):
        operands = [by_metric[m] for m in (actual, expected) if m in by_metric]
        compatible = len(operands) == 2 and all(operands[0][k] == operands[1][k]
            for k in ("unit", "period", "source")) and operands[0]["unit"] == "fraction"
        value = 100 * (operands[0]["value"] - operands[1]["value"]) if compatible else None
        derived.append({"metric": metric, "label": "赛季实际与预期命中率差" if actual == "FGPCT" else "赛季三分实际与预期命中率差",
            "available": compatible, "reasonCode": None if compatible else "missing_or_incompatible_operands",
            "value": value, "unit": "percentage_points", "displayValue": _format(value, "percentage_points"),
            "claimType": "derived_arithmetic", "formula": f"100*({actual}-{expected})",
            "grain": "player-season", "gameId": None,
            "period": copy.deepcopy(operands[0]["period"]) if operands else None,
            "operands": [{"evidenceId": r["evidenceId"], "metric": r["metric"], "value": r["value"]} for r in operands],
            "usage": "赛季快照算术差，可能有源数值舍入；非单次出手表现，不归因于某位防守人"})
    return {"player": {**copy.deepcopy(player), "teamId": next(iter(teams)), "teamSemantics": "official_selected_game"},
        "gameId": game_id, "sections": {group: [by_metric[m]["evidenceId"] for m in metrics if m in by_metric]
            for group, metrics in GROUPS.items()}, "facts": rows, "derived": derived,
        "missingMetrics": [m for metrics in GROUPS.values() for m in metrics if m not in by_metric],
        "scopeLabels": {"game": "本场赛后统计", "season": "2025–26赛季快照；非本回合测量",
            "pressure": "该进攻球员出手时平均承受的防守压力；不是其个人防守能力",
            "leverage": "官方分项影响力；不换算为命中率、胜率或对位优势"}}


def build_player_profile(store, player_id, game_id):
    validate_store(store)
    return {"schema": "rl-scout-player-profile-v1", "storeSha256": store["contentSha256"],
            "inferenceSource": "deterministic_official_evidence_assembly", "trainedModelUsed": False,
            **_profile(store, player_id, game_id)}


def compare_players(store, left_id, right_id, game_id):
    """Left-minus-right same-metric comparisons; never an inferred matchup."""
    validate_store(store)
    if str(left_id) == str(right_id):
        raise ValueError("Select two different players")
    left, right = _profile(store, left_id, game_id), _profile(store, right_id, game_id)
    indexes = [{r["metric"]: r for r in p["facts"]} for p in (left, right)]
    comparisons, missing = [], []
    for metric in COMPARABLE:
        a, b = (idx.get(metric) for idx in indexes)
        if a is None or b is None:
            missing.append({"metric": metric, "reasonCode": "metric_missing_for_selected_player"})
            continue
        same_scope = all(a.get(k) == b.get(k) for k in ("family", "unit", "grain", "gameId", "period"))
        same_snapshot = all(a["source"].get(k) == b["source"].get(k) for k in ("url", "sha256"))
        if not same_scope or not same_snapshot:
            missing.append({"metric": metric, "reasonCode": "incompatible_scope_or_source_snapshot"})
            continue
        unit = a["unit"]
        scale = 100 if unit in {"fraction", "fraction_difference"} else 1
        difference = (a["value"] - b["value"]) * scale
        difference_unit = "percentage_points" if scale == 100 else unit
        comparisons.append({"metric": metric, "label": LABELS.get(metric, metric),
            "leftValue": a["value"], "rightValue": b["value"], "sourceUnit": unit,
            "difference": difference, "differenceUnit": difference_unit,
            "displayDifference": _format(difference, difference_unit),
            "formula": "(left-right)*100" if scale == 100 else "left-right",
            "claimType": "derived_arithmetic", "grain": a["grain"], "period": copy.deepcopy(a["period"]),
            "evidenceIds": [a["evidenceId"], b["evidenceId"]]})
    return {"schema": "rl-scout-player-comparison-v1", "storeSha256": store["contentSha256"],
        "gameId": game_id, "left": left, "right": right, "comparisons": comparisons, "unavailable": missing,
        "inferenceSource": "deterministic_official_evidence_comparison", "trainedModelUsed": False,
        "matchupVerified": False, "defenderPlayerId": None,
        "comparisonMeaning": "左侧减右侧；同场或同赛季快照的同指标差，不代表两人直接交手、限制效果或因果"}


def build_story_context(store, story_id, opponent_id=None):
    validate_store(store)
    event = next((e for e in store["events"] if e["storyId"] == story_id), None)
    if event is None:
        raise ValueError("Story has no verified official event")
    game_id, shooter_id = event["gameId"], event["playerId"]
    players = {p["playerId"]: p for p in store["players"]}
    roster = {}
    for r in store["records"]:
        if r["gameId"] == game_id and r["family"] == "basic" and r.get("participation") == "played":
            roster[r["playerId"]] = {"playerId": r["playerId"], "displayName": players[r["playerId"]]["displayName"],
                "teamId": r["teamId"], "team": TEAMS[r["teamId"]], "playedInGame": True,
                "onCourtAtEventVerified": False, "defenderAtEventVerified": False}
    opponents = [p for p in roster.values() if p["teamId"] != event["teamId"]]
    if opponent_id is not None and str(opponent_id) not in {p["playerId"] for p in opponents}:
        raise ValueError("Opponent must have played for the opposing team in this game")
    return {"schema": "rl-scout-story-player-context-v1", "storyId": story_id,
        "storeSha256": store["contentSha256"], "event": copy.deepcopy(event),
        "attacker": _profile(store, shooter_id, game_id),
        "opponentChoices": sorted(opponents, key=lambda p: p["playerId"]),
        "selectedOpponentId": str(opponent_id) if opponent_id is not None else None,
        "comparison": compare_players(store, shooter_id, opponent_id, game_id) if opponent_id is not None else None,
        "defenderIdentity": {"verified": False, "playerId": None, "reasonCode": "event_defender_not_in_verified_sources"},
        "inferenceSource": "deterministic_official_evidence_assembly", "trainedModelUsed": False,
        "usage": "选择对手查看其防守数据；未核实主防人前标为对手球员对比，不标为本回合对位。"}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--story", choices=("flagg", "amen"), required=True)
    p.add_argument("--opponent")
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if args.output.exists():
        raise SystemExit("Output exists; choose a new artifact path")
    result = build_story_context(load_store(), args.story, args.opponent)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=1, allow_nan=False) + "\n")
    print(json.dumps({"path": str(args.output), "opponents": len(result["opponentChoices"]),
                      "comparison": result["comparison"] is not None, "trainedModelUsed": False}))


if __name__ == "__main__":
    main()
