"""Conservative, offline binding of reviewed clip anchors to official NBA shots.

This verifies a supplied editorial annotation; it does not identify players, read
scoreboards, or locate release frames automatically. NBA China eventId joins to
NBA.com actionNumber, NEVER actionId. No dependencies or network access.
"""
import math
import re


class InvalidEvidence(ValueError):
    pass


def _int(value, name):
    if isinstance(value, bool) or not re.fullmatch(r"\d+", str(value)):
        raise InvalidEvidence(f"{name}: missing or invalid integer")
    return int(value)


def clock_seconds(value):
    """Parse the NBA.com ISO duration clock, without guessing missing clocks."""
    match = re.fullmatch(r"PT(\d+)M(\d+(?:\.\d+)?)S", str(value))
    if not match or float(match[2]) >= 60:
        raise InvalidEvidence("clock: missing or invalid NBA clock")
    return int(match[1]) * 60 + float(match[2])


def _score(value, name):
    if not isinstance(value, dict) or not {"home", "away"} <= value.keys():
        raise InvalidEvidence(f"{name}: both scores required")
    return {side: _int(value[side], f"{name}.{side}") for side in ("home", "away")}


def _row_score(row):
    return _score({"home": row.get("scoreHome"), "away": row.get("scoreAway")}, "PBP score")


def bind_clip(official_page, gp_shot, anchor):
    """Return verified only for one fully consistent event and its shot metric.

    Inputs are our factual NBA.com extraction, original gpShot response, and a
    reviewed clip anchor from video-anchors.json. Candidate and failed-check
    details are retained for audit. This internal format is not the contest API.
    """
    result = {"verified": False, "status": "unmatched", "candidates": [], "errors": []}
    try:
        required = {"gameId", "playerId", "teamId", "period", "jerseyNumber",
                    "clipClockStartSeconds", "clipClockEndSeconds", "scoreBefore",
                    "scoreAfter", "made", "shotValue", "annotationMethod"}
        missing = required - anchor.keys()
        if missing:
            raise InvalidEvidence("anchor missing: " + ", ".join(sorted(missing)))
        if not isinstance(anchor["gameId"], str) or not re.fullmatch(r"\d{10}", anchor["gameId"]):
            raise InvalidEvidence("gameId must retain its ten-digit string")
        if type(anchor["made"]) is not bool or not str(anchor["annotationMethod"]).strip():
            raise InvalidEvidence("explicit made boolean and annotationMethod required")
        player = _int(anchor["playerId"], "playerId")
        team = _int(anchor["teamId"], "teamId")
        period = _int(anchor["period"], "period")
        shot_value = _int(anchor["shotValue"], "shotValue")
        if period < 1 or shot_value not in (2, 3):
            raise InvalidEvidence("period or shotValue invalid")
        start, end = anchor["clipClockStartSeconds"], anchor["clipClockEndSeconds"]
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in (start, end)):
            raise InvalidEvidence("clip clock interval requires finite numbers")
        if not 0 <= end <= start <= (720 if period <= 4 else 300):
            raise InvalidEvidence("clip clock interval invalid")
        before, after = _score(anchor["scoreBefore"], "scoreBefore"), _score(anchor["scoreAfter"], "scoreAfter")
        game, pbp = official_page["game"], official_page["playByPlay"]
        data = gp_shot["data"]
        if gp_shot.get("code") != 0:
            raise InvalidEvidence("gpShot did not return success")
        if any(str(d.get("gameId")) != anchor["gameId"] for d in (game, pbp, data)):
            raise InvalidEvidence("gameId conflict across sources")
        if _int(data.get("playerId"), "gpShot playerId") != player or _int(data.get("teamId"), "gpShot teamId") != team:
            raise InvalidEvidence("gpShot player/team conflict")
        if team == _int(game.get("homeTeamId"), "homeTeamId"):
            side = "home"
        elif team == _int(game.get("awayTeamId"), "awayTeamId"):
            side = "away"
        else:
            raise InvalidEvidence("shooter's team is not in this game")
        roster = game.get(f"{side}TeamPlayers", [])
        roster_match = [r for r in roster if str(r.get("personId")) == str(player)]
        if len(roster_match) != 1 or str(roster_match[0].get("jerseyNum")) != str(anchor["jerseyNumber"]):
            raise InvalidEvidence("official roster and observed jersey conflict")
        other = "away" if side == "home" else "home"
        expected_delta = shot_value if anchor["made"] else 0
        if after[side] - before[side] != expected_delta or after[other] != before[other]:
            raise InvalidEvidence("observed score change does not match shooter and result")
        actions = pbp["actions"]
        shots = data["shotList"]
        if not isinstance(actions, list) or not isinstance(shots, list):
            raise InvalidEvidence("official event lists missing")
        for index, row in enumerate(actions):
            if row.get("isFieldGoal") != 1 or str(row.get("personId")) != str(player) or row.get("period") != period:
                continue
            try:
                event_clock = clock_seconds(row.get("clock"))
            except InvalidEvidence as exc:
                result["errors"].append(str(exc))
                continue
            if not end <= event_clock <= start:
                continue
            candidate = {"actionNumber": row.get("actionNumber"), "actionId": row.get("actionId"),
                         "clock": row.get("clock"), "checks": {}, "errors": []}
            result["candidates"].append(candidate)
            try:
                event_id = _int(row.get("actionNumber"), "actionNumber")
                candidate["checks"]["uniquePbpEvent"] = sum(1 for r in actions if r.get("isFieldGoal") == 1 and r.get("actionNumber") == event_id) == 1
                candidate["checks"]["team"] = _int(row.get("teamId"), "PBP teamId") == team
                candidate["checks"]["made"] = row.get("shotResult") == ("Made" if anchor["made"] else "Missed")
                candidate["checks"]["shotValue"] = _int(row.get("shotValue"), "PBP shotValue") == shot_value
                candidate["checks"]["scoreAfter"] = _row_score(row) == after
                # Walk backwards only to an explicitly recorded score snapshot.
                prior = next((r for r in reversed(actions[:index])
                              if r.get("scoreHome") not in (None, "") and r.get("scoreAway") not in (None, "")), None)
                candidate["checks"]["scoreBefore"] = prior is not None and _row_score(prior) == before
                joined = [s for s in shots if s.get("eventId") == event_id]
                candidate["checks"]["uniqueEventIdJoin"] = len(joined) == 1
                if len(joined) != 1:
                    raise InvalidEvidence("eventId must uniquely join actionNumber; actionId is not a join key")
                shot = joined[0]
                candidate["checks"]["shotGame"] = shot.get("gameId") == anchor["gameId"]
                candidate["checks"]["shotPlayer"] = str(shot.get("playerId")) == str(player)
                candidate["checks"]["shotPeriod"] = shot.get("period") == period
                candidate["checks"]["shotMade"] = type(shot.get("success")) is int and shot["success"] == int(anchor["made"])
                candidate["checks"]["shotType"] = shot.get("shotType") == f"{shot_value}分投篮"
                value = shot.get("value")
                candidate["checks"]["metricRange"] = type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1
                candidate["passed"] = all(candidate["checks"].values())
                if candidate["passed"]:
                    candidate["matched"] = {"eventId": event_id, "actionId": row.get("actionId"),
                        "gameId": anchor["gameId"], "playerId": str(player), "period": period,
                        "clock": row["clock"], "expectedFg": value, "made": anchor["made"],
                        "shotValue": shot_value, "description": row.get("description"),
                        "scoreBefore": before, "scoreAfter": after,
                        "officialShot": shot, "officialPlayByPlay": row}
            except (InvalidEvidence, KeyError, TypeError) as exc:
                candidate["passed"] = False
                candidate["errors"].append(str(exc))
        passed = [c for c in result["candidates"] if c.get("passed")]
        # An ill-formed clock could hide another candidate; fail closed.
        if len(passed) == 1 and not result["errors"]:
            result.update(verified=True, status="verified", matched=passed[0]["matched"])
        elif len(passed) > 1:
            result.update(status="conflict")
            result["errors"].append("multiple events satisfy the clip anchors")
        elif result["candidates"] or result["errors"]:
            result["status"] = "conflict"
    except (InvalidEvidence, KeyError, TypeError, AttributeError) as exc:
        result["status"] = "conflict"
        result["errors"].append(str(exc))
    return result
