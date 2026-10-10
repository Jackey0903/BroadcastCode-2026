#!/usr/bin/env python3
"""Collect four public HOU/DAL box scores and derive eFG/TS from official counts.

Default is an offline rebuild from saved factual snapshots. ``--fetch`` performs
one ordinary public-page GET per game, sequentially, with no retry/auth bypass.
Full HTML/editorial content is not persisted. Advanced values are explicitly
derived, not presented as fields returned by the NBA.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / "data" / "three_layer"
TEAMS = {1610612745: "HOU", 1610612742: "DAL"}
GAMES = {
    "0022500160": "dal-vs-hou",
    "0022500356": "hou-vs-dal",
    "0022500491": "hou-vs-dal",
    "0022500701": "dal-vs-hou",
}
FIELDS = {
    "PTS": "points", "FGM": "fieldGoalsMade", "FGA": "fieldGoalsAttempted",
    "FG3M": "threePointersMade", "FG3A": "threePointersAttempted",
    "FTM": "freeThrowsMade", "FTA": "freeThrowsAttempted", "MIN": "minutes",
    "AST": "assists", "REB": "reboundsTotal", "OREB": "reboundsOffensive",
    "DREB": "reboundsDefensive", "TOV": "turnovers", "STL": "steals",
    "BLK": "blocks", "PF": "foulsPersonal", "PLUS_MINUS": "plusMinusPoints",
}
FORMULAS = {
    "EFG_PCT": {"formula": "(FGM + 0.5 * FG3M) / FGA", "operands": ["FGM", "FG3M", "FGA"]},
    "TS_PCT": {"formula": "PTS / (2 * (FGA + 0.44 * FTA))", "operands": ["PTS", "FGA", "FTA"]},
}


def now():
    return datetime.now(timezone.utc).isoformat()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def fact_subset(game):
    """Retain only game identity and the two teams' official factual box scores."""
    if {game["homeTeamId"], game["awayTeamId"]} != set(TEAMS):
        raise ValueError("Only HOU/DAL head-to-head games are allowed")
    result = {key: game[key] for key in (
        "gameId", "gameCode", "gameStatus", "gameStatusText", "gameTimeUTC",
        "gameEt", "homeTeamId", "awayTeamId", "period",
    ) if key in game}
    for side in ("homeTeam", "awayTeam"):
        team = game[side]
        result[side] = {key: team[key] for key in (
            "teamId", "teamName", "teamTricode", "score", "statistics", "players",
        ) if key in team}
    return result


def fetch_game(game_id):
    url = f"https://www.nba.com/game/{GAMES[game_id]}-{game_id}/box-score"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read()
        match = re.search(r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>', body.decode(), re.S)
        if not match:
            raise ValueError("Public page did not contain __NEXT_DATA__")
        game = json.loads(match.group(1))["props"]["pageProps"]["game"]
        if game["gameId"] != game_id:
            raise ValueError("Returned game ID does not match request")
        return {
            "schema": "nba-public-boxscore-factual-subset-v1",
            "source": {
                "url": url, "retrievedAt": now(), "httpStatus": response.status,
                "htmlSha256": sha(body), "htmlBytes": len(body),
                "jsonPath": "__NEXT_DATA__.props.pageProps.game",
                "extraction": "Exact identity and two-team boxscore fields; HTML/editorial content omitted",
            },
            "game": fact_subset(game),
        }


def played_minutes(minutes):
    if not isinstance(minutes, str) or not re.fullmatch(r"\d+:\d{2}", minutes):
        return None
    minute, second = map(int, minutes.split(":"))
    return minute * 60 + second


def derive(basic, source, status):
    values, states, details = {}, {}, {}
    for metric, spec in FORMULAS.items():
        inputs = {key: basic.get(key) for key in spec["operands"]}
        value = None
        state = "unavailable"
        if status == "did_not_play":
            state = "did_not_play"
        elif all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in inputs.values()):
            if metric == "EFG_PCT":
                denom = inputs["FGA"]
                numerator = inputs["FGM"] + 0.5 * inputs["FG3M"]
            else:
                denom = 2 * (inputs["FGA"] + 0.44 * inputs["FTA"])
                numerator = inputs["PTS"]
            value = numerator / denom if denom > 0 else None
            state = "available" if denom > 0 else "zero_denominator"
        values[metric] = value
        states[metric] = state
        details[metric] = {
            "kind": "derived", "unit": "ratio", "formula": spec["formula"],
            "operands": inputs, "operandSource": source,
            "definitionSource": "https://www.nba.com/stats/help/faq" if metric == "EFG_PCT" else "https://www.nba.com/stats/help/glossary",
        }
    return values, states, details


def normalize(snapshot, path):
    game = snapshot["game"]
    if game["gameId"] not in GAMES:
        raise ValueError("Only the four explicitly scoped games are supported")
    fact_subset(game)
    file_sha = sha(path.read_bytes())
    records, teams = [], []
    for side in ("homeTeam", "awayTeam"):
        team = game[side]
        for index, player in [(None, team)] + list(enumerate(team["players"])):
            stats = player.get("statistics", {})
            basic = {key: stats.get(raw_key) for key, raw_key in FIELDS.items()}
            seconds = played_minutes(basic.get("MIN"))
            dnp = index is not None and (seconds == 0 or player.get("comment", "").startswith("DNP"))
            status = "did_not_play" if dnp else "played" if seconds is not None and seconds > 0 else "unknown"
            source = {
                "url": snapshot["source"]["url"], "sha256": file_sha,
                "path": path.relative_to(ROOT).as_posix(),
                "rowKey": f"game.{side}" + (f".players[{index}]" if index is not None else "") + ".statistics",
                "retrievedAt": snapshot["source"]["retrievedAt"],
                "htmlSha256": snapshot["source"]["htmlSha256"],
            }
            advanced, states, derived = derive(basic, source, status)
            record = {
                "gameId": game["gameId"], "teamId": team["teamId"],
                "teamAbbreviation": TEAMS[team["teamId"]],
                "playerId": str(player["personId"]) if index is not None else None,
                "playerName": " ".join(filter(None, [player.get("firstName"), player.get("familyName")])) if index is not None else None,
                "grain": "player-game" if index is not None else "team-game",
                "status": status, "comment": player.get("comment", ""),
                "period": {
                    "gameDate": game["gameEt"][:10], "gameDateBasis": "NBA gameEt Eastern date",
                    "gameTimeUTC": game["gameTimeUTC"], "season": "2025-26",
                    "seasonType": "Regular Season", "range": "full_completed_game",
                },
                "basic": basic, "basicKind": "official_returned",
                "advanced": advanced, "advancedKind": "derived",
                "advancedStatus": states, "derived": derived, "source": source,
                "allowedUses": ["postgame_fact_retrieval", "same_scope_comparison", "derived_metric_arithmetic"],
                "disallowedUses": ["same_game_pregame_or_pre_shot_prediction_feature", "season_aggregate_claim"],
            }
            (records if index is not None else teams).append(record)
    return records, teams


def validate(records, teams):
    for record in records + teams:
        assert record["teamId"] in TEAMS
        b = record["basic"]
        numeric = [b.get(k) for k in ("PTS", "FGM", "FG3M", "FTM")]
        if all(isinstance(x, (int, float)) for x in numeric):
            assert b["PTS"] == 2 * b["FGM"] + b["FG3M"] + b["FTM"], record
        for made, attempted in (("FGM", "FGA"), ("FG3M", "FG3A"), ("FTM", "FTA")):
            if b.get(made) is not None and b.get(attempted) is not None:
                assert 0 <= b[made] <= b[attempted]
        if record["status"] == "did_not_play":
            assert all(v is None for v in record["advanced"].values())
    for team in teams:
        players = [r for r in records if (r["gameId"], r["teamId"]) == (team["gameId"], team["teamId"])]
        for key in ("PTS", "FGM", "FGA", "FG3M", "FG3A", "FTM", "FTA"):
            assert sum(p["basic"].get(key) or 0 for p in players) == team["basic"][key], (team["gameId"], team["teamId"], key)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true", help="Fetch exactly the four authorized HOU/DAL public game pages")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    sources, records, teams = [], [], []
    for gid in GAMES:
        path = OUT / f"boxscore-{gid}.json"
        transitional = OUT / f"page-boxscore-{gid}.json"
        if args.fetch:
            snapshot = fetch_game(gid)
            path.write_bytes(encoded(snapshot))
            time.sleep(1)
        elif path.exists():
            snapshot = json.loads(path.read_bytes())
        elif transitional.exists():
            first = json.loads(transitional.read_bytes())
            snapshot = {"schema": "nba-public-boxscore-factual-subset-v1", "source": {**first["source"], "jsonPath": "__NEXT_DATA__.props.pageProps.game", "extraction": "Exact identity and two-team boxscore fields; HTML/editorial content omitted"}, "game": fact_subset(first["pageProps"]["game"])}
            path.write_bytes(encoded(snapshot))
        else:
            continue
        if transitional.exists():
            transitional.unlink()  # Delete only this collector's temporary overbroad page extraction.
        player_rows, team_rows = normalize(snapshot, path)
        records.extend(player_rows)
        teams.extend(team_rows)
        sources.append({**snapshot["source"], "path": path.relative_to(ROOT).as_posix(), "sha256": sha(path.read_bytes()), "gameId": gid})
    validate(records, teams)
    context = {
        "schema": "rl-scout-three-layer-basic-advanced-v1", "generatedAt": now(),
        "allowedTeams": {str(k): v for k, v in TEAMS.items()}, "sources": sources,
        "records": records, "teamRecords": teams,
        "formulas": FORMULAS,
        "scope": "Completed HOU/DAL game boxscores. Advanced values are derived eFG/TS, not NBA-returned advanced fields. NBA/AWS depth remains in ../depth/two-team-context.json with a different season snapshot grain.",
        "datePolicy": "gameDate uses NBA Eastern gameEt date; existing shot cache dates use the next UTC date for these games. Join on gameId, not date strings.",
    }
    (OUT / "context.json").write_bytes(encoded(context))
    summary = {
        "schema": "three-layer-source-audit-v2", "generatedAt": now(),
        "games": len(sources), "playerGameRows": len(records), "teamGameRows": len(teams),
        "uniquePlayers": len({r["playerId"] for r in records}),
        "playedRows": sum(r["status"] == "played" for r in records),
        "didNotPlayRows": sum(r["status"] == "did_not_play" for r in records),
        "metricsAvailable": {m: sum(r["advanced"][m] is not None for r in records) for m in FORMULAS},
        "sourcePaths": [s["path"] for s in sources], "contextPath": (OUT / "context.json").relative_to(ROOT).as_posix(),
        "validation": "Allowed team IDs; scoring identity; attempts >= makes; player counting sums match team totals; DNP efficiency null",
        "advancedOfficialReturned": [], "advancedDerived": list(FORMULAS),
        "notAvailable": ["official ORTG", "official DRTG", "official USG%", "official AST%", "official pace"],
        "notTrainingEvidence": True,
    }
    (HERE / "results" / "three-layer-source-audit-20261010.json").write_bytes(encoded(summary))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
