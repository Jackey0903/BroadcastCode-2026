#!/usr/bin/env python3
"""Fetch official NBA China shot-quality data for RL-SCOUT training.

Only public read endpoints are used; responses are cached under data/rl-raw/ (git-ignored)
and the processed dataset is written to product/rl/data/. No cloud resources are touched.

    python3 product/rl/harvest.py --games-per-date 2 --step-days 4
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
import hashlib
import json
from pathlib import Path
import sys
import time
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scout_env import shot_geometry  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "rl-raw"
OUT = Path(__file__).resolve().parent / "data"
BASE = "https://api.nba.cn/nba-web/api/web/inside"
SEASON = "2025-26"
PRACTICE_GAMES = {"0022500491": "2026-01-04", "0022500701": "2026-02-01"}
FOCUS_TEAMS = {1610612745, 1610612742}  # Houston Rockets, Dallas Mavericks
SEASON_START, SEASON_END = "2025-10-21", "2026-04-12"


OFFLINE = False
PAUSE = 0.2
DEADLINE = None
STREAK = [0]


class NotCached(Exception):
    pass


def fetch(url, pause=None):
    """GET with a local cache so reruns are reproducible and polite."""
    key = hashlib.sha1(url.encode()).hexdigest()
    cached = RAW / f"{key}.json"
    if cached.exists():
        return json.loads(cached.read_text())
    if OFFLINE or (DEADLINE and time.time() > DEADLINE):
        raise NotCached(url)
    if STREAK[0] >= 5:  # looks throttled: cool down before trying again
        time.sleep(120)
        STREAK[0] = 0
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (BroadcastCode Team02 research)"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                payload = json.load(response)
            STREAK[0] = 0
            break
        except Exception:  # network hiccup or throttling: back off, then give up on this URL
            if attempt == 3:
                STREAK[0] += 1
                raise NotCached(url)
            time.sleep(2 * 2 ** attempt)
    RAW.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps({"url": url, "payload": payload}, ensure_ascii=False))
    time.sleep(PAUSE if pause is None else pause)
    return {"url": url, "payload": payload}


def games_on(day):
    try:
        data = fetch(f"{BASE}/game?date={day}")["payload"].get("data") or {}
    except NotCached:
        return []
    return [g for g in data.get("games", []) if g.get("status") == 3]


def team_profiles(team_id):
    query = urllib.parse.urlencode({"season": SEASON, "seasonType": "Regular Season", "teamId": team_id})
    try:
        data = fetch(f"{BASE}/season/shotDifficulty?{query}")["payload"].get("data") or {}
    except NotCached:
        return []
    return data.get("shots") or []


def player_shots(game_id, player_id):
    try:
        data = fetch(f"{BASE}/gpShot?gameId={game_id}&playerId={player_id}")["payload"].get("data") or {}
    except NotCached:
        return None
    return data.get("shotList") or []


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2025-11-01")
    parser.add_argument("--end", default="2026-04-10")
    parser.add_argument("--step-days", type=int, default=4)
    parser.add_argument("--games-per-date", type=int, default=2)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--offline", action="store_true", help="Use cached responses only; skip anything missing.")
    parser.add_argument("--pause", type=float, default=0.2)
    parser.add_argument("--deadline", default=None, help="HH:MM Beijing time; stop fetching afterwards.")
    args = parser.parse_args()
    parser_deadline = args.deadline
    global OFFLINE, PAUSE, DEADLINE
    OFFLINE, PAUSE = args.offline, args.pause
    if parser_deadline:
        hh, mm = map(int, parser_deadline.split(":"))
        now = datetime.now(ZoneInfo("Asia/Shanghai"))
        DEADLINE = now.replace(hour=hh, minute=mm, second=0).timestamp()

    picked = {}
    day = date.fromisoformat(args.start)
    while day <= date.fromisoformat(args.end):
        for game in games_on(day.isoformat())[: args.games_per_date]:
            picked[game["gameId"]] = {**game, "date": day.isoformat()}
        day += timedelta(days=args.step_days)
    # Focus teams: every regular-season game involving them (the contest footage is HOU vs DAL).
    day = date.fromisoformat(SEASON_START)
    while day <= date.fromisoformat(SEASON_END):
        for game in games_on(day.isoformat()):
            if {game["homeTeamId"], game["awayTeamId"]} & FOCUS_TEAMS:
                picked[game["gameId"]] = {**game, "date": day.isoformat()}
        day += timedelta(days=1)
    for game_id, game_day in PRACTICE_GAMES.items():
        if game_id not in picked:
            match = [g for g in games_on(game_day) if g["gameId"] == game_id]
            if match:
                picked[game_id] = {**match[0], "date": game_day}
    print(f"games: {len(picked)}", flush=True)

    teams = sorted({g["homeTeamId"] for g in picked.values()} | {g["awayTeamId"] for g in picked.values()})
    profiles = {}
    for team_id in teams:
        for row in team_profiles(team_id):
            profiles[str(row["PLAYERID"])] = {k: row[k] for k in row if k.isupper()}
    print(f"teams: {len(teams)}  profiled players: {len(profiles)}", flush=True)
    by_team = {}
    for player_id, row in profiles.items():
        by_team.setdefault(row["TEAMID"], []).append(player_id)

    jobs = [(gid, pid) for gid, g in picked.items() for tid in (g["homeTeamId"], g["awayTeamId"])
            for pid in by_team.get(tid, [])]
    print(f"player-game requests: {len(jobs)}", flush=True)

    shots = []
    def work(job):
        game_id, player_id = job
        return job, player_shots(game_id, player_id)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        missing = 0
        for done, ((game_id, player_id), rows) in enumerate(pool.map(work, jobs), 1):
            game = picked[game_id]
            if rows is None:
                missing += 1
                continue
            for row in rows:
                try:
                    value = float(row["value"])
                    loc_x, loc_y = float(row["locX"]), float(row["locY"])
                except (TypeError, ValueError, KeyError):
                    continue
                if not 0 <= value <= 1 or row.get("side") not in ("left", "right"):
                    continue
                three = "3" in str(row.get("shotType", ""))
                geo = shot_geometry(loc_x, loc_y, row["side"], three)
                shots.append({
                    "gameId": game_id, "gameDate": game["date"], "playerId": str(player_id),
                    "teamId": profiles[str(player_id)]["TEAMID"], "eventId": row.get("eventId"),
                    "shotDesc": row.get("shotDesc") or "未知", "shotType": "3PT" if three else "2PT",
                    "side": row["side"], "locX": loc_x, "locY": loc_y, "period": row.get("period"),
                    "distanceFt": geo["distanceFt"], "zone": geo["zone"],
                    "made": int(row.get("success") or 0), "quality": round(value, 4),
                    "focus": bool({game["homeTeamId"], game["awayTeamId"]} & FOCUS_TEAMS),
                    "h2h": {game["homeTeamId"], game["awayTeamId"]} == FOCUS_TEAMS,
                })
            if done % 100 == 0:
                print(f"  {done}/{len(jobs)} requests, {len(shots)} shots", flush=True)

    OUT.mkdir(parents=True, exist_ok=True)
    shots.sort(key=lambda s: (s["gameDate"], s["gameId"], s["playerId"], s["eventId"] or 0))
    with (OUT / "shots.jsonl").open("w") as stream:
        for shot in shots:
            stream.write(json.dumps(shot, ensure_ascii=False) + "\n")
    (OUT / "profiles.json").write_text(json.dumps(profiles, ensure_ascii=False, indent=0))
    manifest = {
        "source": "NBA China official endpoints (api.nba.cn inside/game, season/shotDifficulty, gpShot)",
        "season": SEASON, "fetchedAt": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"),
        "games": len(picked), "teams": len(teams), "profiledPlayers": len(profiles), "shots": len(shots),
        "dateRange": [args.start, args.end], "stepDays": args.step_days, "gamesPerDate": args.games_per_date,
        "practiceGamesIncluded": [g for g in PRACTICE_GAMES if g in picked],
        "focusTeams": sorted(FOCUS_TEAMS), "focusGames": sum(1 for g in picked.values() if {g["homeTeamId"], g["awayTeamId"]} & FOCUS_TEAMS),
        "headToHeadGames": sorted(gid for gid, g in picked.items() if {g["homeTeamId"], g["awayTeamId"]} == FOCUS_TEAMS),
        "missingPlayerGames": missing, "offline": args.offline,
        "note": "Shots cover profiled (season shot-difficulty) players only; no game-level roster endpoint is available.",
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    print(json.dumps(manifest, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
