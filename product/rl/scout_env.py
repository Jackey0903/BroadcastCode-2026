"""RL-SCOUT environment: geometry, dataset split, tools, prompts and verifiable reward.

Pure Python (no torch) so the same definitions run locally, in CI and inside the
SageMaker training container. One episode = one official shot. The policy never sees the
official quality value or the make/miss result; the reward compares its estimate with the
official value after the episode ends.
"""
import hashlib
import json
import math
import re
import statistics

COURT_LENGTH_FT, COURT_WIDTH_FT, RIM_FROM_BASELINE_FT = 94.0, 50.0, 5.25
ZONES_ZH = {"restricted": "篮下", "paint": "禁区", "midrange": "中距离",
            "corner3": "底角三分", "above_break3": "弧顶/两翼三分"}
TYPE_ZH = {"2PT": "两分", "3PT": "三分"}
POINT_TOOLS = ("zone_reference", "move_reference", "player_profile")
INTERVAL_TOOLS = POINT_TOOLS + ("player_zone",)
# v4 uses only cross-fitted shot references, never full-season profiles.
JOINT_TOOLS = ("zone_reference", "move_reference", "player_zone", "situation_reference")
TOOLS = POINT_TOOLS
TEST_FROM = "2026-03-01"
PRACTICE_GAMES = ("0022500491", "0022500701")
FOCUS_TEAM_IDS = {1610612742, 1610612745}
MIN_MOVE_SAMPLES = 15
MIN_PLAYER_ZONE_SAMPLES = 8
BAND = (0.2, 0.8)  # central 60% interval of official quality
INTERVAL_ALPHA, INTERVAL_SCALE = 0.4, 1.5
# Reward v1 (10:58): v0 used a squared calibration term with scale 0.4 and 0.03 per tool, which made
# "call zone_reference only and copy its mean" optimal (extra tools gained < 0.01, cost 0.03) and the
# GRPO groups collapsed. v1 aligns calibration with the reported metric (absolute error) and lowers
# the tool cost so useful information is worth fetching.
# Reward v2 (11:20): on the training split, "zone_reference only" still scores 0.5997 under v1 while
# averaging zone and move references scores 0.5976 (the move table saves ~0.005 MAE = 0.008 reward,
# less than the 0.01 cost), and the v1 run collapsed onto zone-only by step 15. v2 keeps the v1
# calibration and lowers the tool cost to 0.002 so the combined estimate becomes optimal (0.6136).
# v3 added 60% intervals, but clipped interval rewards lose strict propriety.
# v4 uses an unclipped affine interval score and absolute error (conditional median).
# Earlier linear-blend results are baselines, not evidence of an information ceiling.
POINT_WEIGHTS = {"calibration": 0.75, "format": 0.15, "grounded": 0.10}
REWARD_PRESETS = {"v1": {"toolCost": 0.01, "calibrationScale": 0.5, "spec": "point"},
                  "v2": {"toolCost": 0.002, "calibrationScale": 0.5, "spec": "point"},
                  "v3": {"toolCost": 0.002, "calibrationScale": 0.5, "spec": "interval",
                         "weights": {"calibration": 0.45, "interval": 0.30, "format": 0.15, "grounded": 0.10}},
                  "v4": {"toolCost": 0.002, "calibrationScale": 0.5, "spec": "interval",
                         "weights": {"calibration": 0.45, "interval": 0.30, "format": 0.15, "grounded": 0.10}}}
REWARD_VERSION, SPEC = "v1", "point"
TOOL_COST, INVALID_PENALTY = 0.01, 0.2
WEIGHTS = dict(POINT_WEIGHTS)
CALIBRATION_SCALE = 0.5
MAX_REASON_CHARS = 80

SYSTEM_PROMPT = (
    "你是 NBA 球探。根据一次出手的信息，估计这类出手在 NBA 官方出手质量模型下的常见质量（0 到 1 之间）。\n"
    "作答前可以先调用工具获取参考数据（每调用一个工具有少量成本，只调用你需要的）："
    "zone_reference（该区域联盟平均官方质量）、move_reference（同类出手描述的平均官方质量）、"
    "player_profile（出手人赛季档案）。\n"
    "需要工具时只输出：{\"tools\": [\"工具名\", ...]}\n"
    "作答时只输出：{\"quality\": 0.xx, \"reason\": \"不超过60字，只引用给出的事实\"}\n"
    "不要输出任何其他文字。"
)
INTERVAL_PROMPT = (
    "你是 NBA 球探。根据一次出手的信息，估计这类出手在 NBA 官方出手质量模型下的常见质量（0 到 1 之间），"
    "并给出同类出手官方质量的中间 60% 区间（第 20 到第 80 百分位）。\n"
    "作答前可以先调用工具获取参考数据（每调用一个工具有少量成本，只调用你需要的）："
    "zone_reference（该区域联盟平均官方质量与区间）、move_reference（同类出手描述的平均官方质量与区间）、"
    "player_profile（出手人赛季档案）、player_zone（出手人在该区域的历史官方质量与区间）。\n"
    "需要工具时只输出：{\"tools\": [\"工具名\", ...]}\n"
    "作答时只输出：{\"quality\": 0.xx, \"low\": 0.xx, \"high\": 0.xx, \"reason\": \"不超过60字，只引用给出的事实\"}\n"
    "要求 low ≤ quality ≤ high。不要输出任何其他文字。"
)
JOINT_PROMPT = (
    "你是 NBA 球探。根据出手类型、区域与动作，估计同类出手官方质量的典型值（条件中位数）及中间60%区间。"
    "本次出手的官方质量和命中结果不可见；不要把估计说成官方值或命中预测。\n"
    "可先请求参考工具（每次调用有成本，仅调用需要的）："
    "situation_reference（所属数据范围内区域×两分/三分×动作的联合中位数、均值、20/80百分位与样本数；不足时回退区域），"
    "zone_reference（区域参考），move_reference（动作参考），player_zone（球员区域参考）。"
    "所有表只使用训练比赛，训练时还排除了本题所在的整场比赛分组；没有全赛季档案或逐帧防守数据。\n"
    '需要工具只输出：{"tools": ["工具名", ...]}\n'
    '作答只输出：{"quality": 0.xx, "low": 0.xx, "high": 0.xx, "reason": "简短说明参考依据"}\n'
    "要求0≤low≤quality≤high≤1，reason不超过60字；不要猜防守距离、球员引力或战术因果。"
)
PROMPTS = {"point": SYSTEM_PROMPT, "interval": INTERVAL_PROMPT}


def reference_fold(shot, folds=5):
    """Whole-game folds: a training episode never retrieves statistics containing its own game."""
    return int(hashlib.sha256(("rl-scout-dev-v4:" + str(shot["gameId"])).encode()).hexdigest()[:8], 16) % folds



def use_reward(version):
    """Switch the module-wide reward preset and the matching prompt/tool spec (training: --reward;
    runtime: the "policy" field of reference_tables.json). v1/v2 share the point spec verbatim."""
    global REWARD_VERSION, TOOL_COST, CALIBRATION_SCALE, WEIGHTS, SPEC, TOOLS, SYSTEM_PROMPT
    preset = REWARD_PRESETS[version]
    REWARD_VERSION, TOOL_COST, CALIBRATION_SCALE = version, preset["toolCost"], preset["calibrationScale"]
    WEIGHTS = dict(preset.get("weights", POINT_WEIGHTS))
    SPEC = preset["spec"]
    TOOLS = JOINT_TOOLS if version == "v4" else INTERVAL_TOOLS if SPEC == "interval" else POINT_TOOLS
    SYSTEM_PROMPT = JOINT_PROMPT if version == "v4" else PROMPTS[SPEC]


def band(values):
    ordered = sorted(values)
    pick = lambda p: ordered[min(len(ordered) - 1, int(p * len(ordered)))]
    return round(pick(BAND[0]), 3), round(pick(BAND[1]), 3)


def shot_geometry(loc_x, loc_y, side, three):
    """Official full-court percentage coordinates -> distance to the rim (ft) and zone."""
    x = float(loc_x) / 100 * COURT_LENGTH_FT
    y = float(loc_y) / 100 * COURT_WIDTH_FT
    from_baseline = COURT_LENGTH_FT - x if side == "right" else x
    dx, dy = from_baseline - RIM_FROM_BASELINE_FT, y - COURT_WIDTH_FT / 2
    distance = math.hypot(dx, dy)
    if three:
        zone = "corner3" if from_baseline <= 14 and abs(dy) >= 21 else "above_break3"
    elif distance <= 4:
        zone = "restricted"
    elif from_baseline <= 19 and abs(dy) <= 8:
        zone = "paint"
    else:
        zone = "midrange"
    return {"distanceFt": round(distance, 1), "zone": zone}


def load_shots(path):
    with open(path, encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def select_universe(shots, universe="all"):
    if universe == "all":
        return list(shots)
    if universe != "two-teams":
        raise ValueError("universe must be all or two-teams")
    # Stored teamId comes from the official season roster/profile snapshot, not an as-of roster.
    return [shot for shot in shots if shot.get("teamId") in FOCUS_TEAM_IDS]


def held_out(shot):
    """Which test set a shot belongs to, or None for training.

    h2h: every Rockets-Mavericks game (the contest footage comes from this matchup, so the
    exact shots must never be memorised). league: later games without either focus team.
    Non-h2h games of the focus teams stay in training at any date to maximise focus data.
    """
    if shot.get("h2h") or shot["gameId"] in PRACTICE_GAMES:
        return "h2h"
    if not shot.get("focus") and shot["gameDate"] >= TEST_FROM:
        return "league"
    return None


def split(shots):
    train = [s for s in shots if held_out(s) is None]
    test = [s for s in shots if held_out(s) is not None]
    return train, test


def test_sets(shots):
    sets = {"h2h": [], "league": []}
    for shot in shots:
        name = held_out(shot)
        if name:
            sets[name].append(shot)
    return sets


class References:
    """Tool back-ends. Built from the training split only, so test labels never leak."""

    def __init__(self, train, profiles, universe="all"):
        self.universe = universe
        self.scope_label = "两队训练" if universe == "two-teams" else "联盟"
        self.zone, self.move, self.profiles = {}, {}, profiles
        self.zone_band, self.move_band, self.player_zone = {}, {}, {}
        self.situation, self.zone_median = {}, {}
        groups = {}
        for shot in train:
            groups.setdefault(("zone", shot["zone"], shot["shotType"]), []).append(shot["quality"])
            groups.setdefault(("move", shot["shotDesc"]), []).append(shot["quality"])
            groups.setdefault(("player", str(shot["playerId"]), shot["zone"], shot["shotType"]), []).append(shot["quality"])
            groups.setdefault(("situation", shot["zone"], shot["shotType"], shot["shotDesc"]), []).append(shot["quality"])
        for key, values in groups.items():
            summary = (round(statistics.fmean(values), 3), len(values))
            if key[0] == "zone":
                self.zone[key[1:]], self.zone_band[key[1:]] = summary, band(values)
                self.zone_median[key[1:]] = round(statistics.median(values), 3)
            elif key[0] == "move":
                self.move[key[1]], self.move_band[key[1]] = summary, band(values)
            elif key[0] == "situation":
                self.situation[key[1:]] = summary + (round(statistics.median(values), 3),) + band(values)
            else:
                self.player_zone[key[1:]] = summary + band(values)
        self.global_mean = round(statistics.fmean(s["quality"] for s in train), 3) if train else 0.45

    def to_tables(self):
        """Serialisable tool back-ends for runtime (no training rows needed)."""
        return {"universe": self.universe, "globalMean": self.global_mean,
                "zone": [[zone, kind, mean, count] for (zone, kind), (mean, count) in sorted(self.zone.items())],
                "move": [[desc, mean, count] for desc, (mean, count) in sorted(self.move.items())],
                "profiles": {} if REWARD_VERSION == "v4" else self.profiles,
                "zoneMedian": [[zone, kind, value] for (zone, kind), value in sorted(self.zone_median.items())],
                "situation": [[zone, kind, desc, *row] for (zone, kind, desc), row in sorted(self.situation.items())],
                "zoneBand": [[zone, kind, low, high] for (zone, kind), (low, high) in sorted(self.zone_band.items())],
                "moveBand": [[desc, low, high] for desc, (low, high) in sorted(self.move_band.items())],
                "playerZone": [[pid, zone, kind, *row] for (pid, zone, kind), row in sorted(self.player_zone.items())]}

    @classmethod
    def from_tables(cls, tables):
        refs = cls([], tables.get("profiles", {}), tables.get("universe", "all"))
        refs.global_mean = tables["globalMean"]
        refs.zone = {(zone, kind): (mean, count) for zone, kind, mean, count in tables["zone"]}
        refs.move = {desc: (mean, count) for desc, mean, count in tables["move"]}
        refs.zone_band = {(zone, kind): (low, high) for zone, kind, low, high in tables.get("zoneBand", [])}
        refs.move_band = {desc: (low, high) for desc, low, high in tables.get("moveBand", [])}
        refs.player_zone = {(pid, zone, kind): tuple(row) for pid, zone, kind, *row in tables.get("playerZone", [])}
        refs.zone_median = {(zone, kind): value for zone, kind, value in tables.get("zoneMedian", [])}
        refs.situation = {(zone, kind, desc): tuple(row) for zone, kind, desc, *row in tables.get("situation", [])}
        return refs

    def situation_values(self, shot):
        row = self.situation.get((shot["zone"], shot["shotType"], shot["shotDesc"]))
        if row and row[1] >= MIN_MOVE_SAMPLES:
            return row, "联合参考"
        key = (shot["zone"], shot["shotType"])
        mean, count = self.zone.get(key, (self.global_mean, 0))
        low, high = self.zone_band.get(key, (0.0, 1.0))
        median = self.zone_median.get(key, mean)
        return (mean, count, median, low, high), "联合样本不足，回退区域"

    def situation_reference(self, shot):
        (mean, count, median, low, high), source = self.situation_values(shot)
        return (f"{source}：{ZONES_ZH[shot['zone']]}·{TYPE_ZH[shot['shotType']]}·{shot['shotDesc']}，"
                f"典型质量（中位数）{median:.3f}，均值{mean:.3f}，中间60%区间{low:.3f}–{high:.3f}，"
                f"训练样本{count}次；非本次出手的官方值")

    def _band_text(self, values):
        return f"，中间 60% 区间 {values[0]:.3f}–{values[1]:.3f}" if SPEC == "interval" and values else ""

    def zone_reference(self, shot):
        mean, count = self.zone.get((shot["zone"], shot["shotType"]), (self.global_mean, 0))
        extra = self._band_text(self.zone_band.get((shot["zone"], shot["shotType"])))
        return (f"区域参考：{ZONES_ZH[shot['zone']]}·{TYPE_ZH[shot['shotType']]}，"
                f"{self.scope_label}平均官方质量 {mean:.3f}（训练样本 {count} 次{extra}）")

    def move_reference(self, shot):
        mean, count = self.move.get(shot["shotDesc"], (None, 0))
        if mean is None or count < MIN_MOVE_SAMPLES:
            return f"动作参考：{shot['shotDesc']} 样本不足（{count} 次）"
        extra = self._band_text(self.move_band.get(shot["shotDesc"]))
        return f"动作参考：{shot['shotDesc']}，平均官方质量 {mean:.3f}（样本 {count} 次{extra}）"

    def player_zone_reference(self, shot):
        place = f"{ZONES_ZH[shot['zone']]}·{TYPE_ZH[shot['shotType']]}"
        row = self.player_zone.get((str(shot["playerId"]), shot["zone"], shot["shotType"]))
        if not row or row[1] < MIN_PLAYER_ZONE_SAMPLES:
            return f"球员区域：该球员在{place}的训练样本不足（{row[1] if row else 0} 次）"
        mean, count, low, high = row
        return (f"球员区域：该球员在{place}的平均官方质量 {mean:.3f}"
                f"（训练样本 {count} 次，中间 60% 区间 {low:.3f}–{high:.3f}）")

    def player_profile(self, shot):
        row = self.profiles.get(str(shot["playerId"]))
        if not row:
            return "球员档案：不可用"
        return (f"球员档案：赛季平均出手质量 {row['AVGSHOTQUALITY']:.3f}"
                f"（两分 {row['AVGSHOTQUALITY2PT']:.3f}，三分 {row['AVGSHOTQUALITY3PT']:.3f}），"
                f"命中率高出期望 {row['FGPCTABOVEEXPECTED']:+.3f}，"
                f"平均防守人与球距离 {row['AVGDEFENDERBALLDISTANCE']:.1f}，"
                f"防守压力分 {row['AVGDEFENDERPRESSURESCORE']:.3f}")

    def run(self, name, shot):
        return self.player_zone_reference(shot) if name == "player_zone" else getattr(self, name)(shot)

    # Non-learned baselines for evaluation.
    def baseline_zone(self, shot):
        return self.zone.get((shot["zone"], shot["shotType"]), (self.global_mean, 0))[0]

    def baseline_combined(self, shot):
        zone = self.baseline_zone(shot)
        mean, count = self.move.get(shot["shotDesc"], (None, 0))
        return zone if mean is None or count < MIN_MOVE_SAMPLES else round((zone + mean) / 2, 3)


def observation(shot):
    """What the policy sees: no official value, no make/miss."""
    return (f"出手：{shot['shotDesc']}；{TYPE_ZH[shot['shotType']]}；{ZONES_ZH[shot['zone']]}，"
            f"距篮筐 {shot['distanceFt']} 英尺；第 {shot['period']} 节；出手人编号 {shot['playerId']}。")


def first_messages(shot):
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": observation(shot)}]


def parse_action(text):
    """Return ('tools', [names], invalid) | ('answer', {...}, invalid) | ('invalid', None, True)."""
    if not isinstance(text, str):
        return "invalid", None, True
    if REWARD_VERSION == "v4":
        try:
            strict = json.loads(text)
        except (ValueError, TypeError):
            return "invalid", None, True
        if not isinstance(strict, dict) or ("tools" in strict and set(strict) != {"tools"}):
            return "invalid", None, True
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return "invalid", None, True
    try:
        data = json.loads(text[start:end + 1])
    except (ValueError, TypeError):
        return "invalid", None, True
    if not isinstance(data, dict):
        return "invalid", None, True
    if "tools" in data:
        names = data["tools"] if isinstance(data["tools"], list) else []
        # Sampled policies sometimes emit objects ({"name": ...}) or numbers: never crash, count them invalid.
        valid = [n for n in dict.fromkeys(n for n in names if isinstance(n, str)) if n in TOOLS]
        invalid = not valid or len(valid) != len(names)
        return ("tools", valid, invalid) if valid else ("invalid", None, True)
    if "quality" in data:
        return "answer", data, False
    return "invalid", None, True


def tool_message(names, shot, references):
    return {"role": "user", "content": "工具结果：\n" + "\n".join(references.run(n, shot) for n in names)
            + "\n请作答，只输出 JSON。"}


_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def _number_forms(text):
    forms = set()
    for token in _NUMBER.findall(text):
        value = float(token)
        forms.update({round(value, 3), round(value * 100, 1), round(value / 100, 3)})
    return forms


def interval_score(low, high, value, alpha=INTERVAL_ALPHA):
    """Interval score for a central (1 - alpha) interval; lower is better, strictly proper."""
    return (high - low) + (2 / alpha) * max(0.0, low - value) + (2 / alpha) * max(0.0, value - high)


def _interval(answer, prediction):
    try:
        low, high = float(answer.get("low")), float(answer.get("high"))
    except (TypeError, ValueError):
        return None
    return (low, high) if prediction is not None and 0 <= low <= prediction <= high <= 1 else None


def valid_interval_answer(answer, invalid=False):
    if invalid or not isinstance(answer, dict) or set(answer) != {"quality", "low", "high", "reason"}:
        return False
    if any(isinstance(answer[k], bool) or not isinstance(answer[k], (int, float)) or not math.isfinite(answer[k])
           for k in ("quality", "low", "high")):
        return False
    return (_interval(answer, answer["quality"]) is not None and isinstance(answer["reason"], str)
            and 0 < len(answer["reason"].strip()) <= 60)


def reward(answer, quality, tools_used, invalid, context):
    """Verifiable reward. `context` is every string the policy was shown (state + tool results)."""
    parts = {"calibration": 0.0, "format": 0.0, "grounded": 0.0,
             "tools": len(tools_used), "invalid": bool(invalid), "prediction": None}
    if SPEC == "interval":
        parts.update({"interval": 0.0, "low": None, "high": None, "intervalScore": None})
    if REWARD_VERSION == "v4" and not valid_interval_answer(answer, invalid):
        parts["invalid"] = True
        parts["total"] = -2.0
        return parts
    if answer is None:
        parts["total"] = -INVALID_PENALTY
        return parts
    try:
        prediction = float(answer.get("quality"))
    except (TypeError, ValueError):
        prediction = None
    reason = answer.get("reason")
    keys = {"quality", "reason"}
    own = set()
    if prediction is not None and 0 <= prediction <= 1:
        parts["prediction"] = round(prediction, 4)
        parts["calibration"] = 1 - abs(prediction - quality) / CALIBRATION_SCALE
        if REWARD_VERSION != "v4":
            parts["calibration"] = max(0.0, parts["calibration"])
        shaped = True
        if SPEC == "interval":
            keys, span = keys | {"low", "high"}, _interval(answer, prediction)
            shaped = span is not None
            if span:
                score = interval_score(span[0], span[1], quality)
                parts.update({"low": round(span[0], 4), "high": round(span[1], 4), "intervalScore": round(score, 4),
                              "interval": (1 - score / INTERVAL_SCALE) if REWARD_VERSION == "v4" else max(0.0, 1 - score / INTERVAL_SCALE)})
                own = {round(v, 3) for v in span} | {round(v * 100, 1) for v in span}
        if shaped and isinstance(reason, str) and 0 < len(reason) <= MAX_REASON_CHARS and set(answer) <= keys:
            parts["format"] = 1.0
    if isinstance(reason, str) and reason and prediction is not None:
        allowed = _number_forms(context) | own | {round(prediction, 3), round(prediction * 100, 1)}
        claimed = [float(t) for t in _NUMBER.findall(reason)]
        parts["grounded"] = 1.0 if all(round(v, 3) in allowed or round(v, 1) in allowed for v in claimed) else 0.0
    total = sum(WEIGHTS[k] * parts[k] for k in WEIGHTS) - TOOL_COST * len(tools_used)
    if invalid:
        total -= INVALID_PENALTY
    parts["total"] = round(total, 4)
    return parts


def summarize(results):
    """Aggregate evaluation rows: each has prediction, quality, reward parts."""
    rows = [r for r in results if r.get("prediction") is not None]
    errors = [abs(r["prediction"] - r["quality"]) for r in rows]
    summary = {
        "allEpisodeMAE": round(statistics.fmean(abs(r["prediction"] - r["quality"])
            if r.get("prediction") is not None and r.get("format") == 1.0 and not r.get("invalid", False)
            else 1.0 for r in results), 4) if results else None,
        "validRate": round(statistics.fmean(r.get("prediction") is not None and r.get("format") == 1.0
            and not r.get("invalid", False) for r in results), 4) if results else None,
        "episodes": len(results),
        "answered": len(rows),
        "mae": round(statistics.fmean(errors), 4) if errors else None,
        "mse": round(statistics.fmean(e * e for e in errors), 4) if errors else None,
        "formatRate": round(statistics.fmean(r.get("format", 0) for r in results), 4) if results else None,
        "groundedRate": round(statistics.fmean(r.get("grounded", 0) for r in results), 4) if results else None,
        "toolsPerEpisode": round(statistics.fmean(r.get("tools", 0) for r in results), 3) if results else None,
        "meanReward": round(statistics.fmean(r.get("total", 0) for r in results), 4) if results else None,
    }
    spans = [r for r in rows if r.get("intervalScore") is not None]
    if any("intervalScore" in r for r in results):
        summary.update({
            "intervalRate": round(len(spans) / len(results), 4) if results else None,
            "intervalScore": round(statistics.fmean(r["intervalScore"] for r in spans), 4) if spans else None,
            "coverage": round(statistics.fmean(1.0 if r["low"] <= r["quality"] <= r["high"] else 0.0 for r in spans), 4) if spans else None,
            "width": round(statistics.fmean(r["high"] - r["low"] for r in spans), 4) if spans else None,
        })
    return summary


def shot_from_official(row, player_id):
    """Map an official gpShot record (as returned by api.nba.cn) to an RL-SCOUT shot."""
    three = "3" in str(row.get("shotType", ""))
    geo = shot_geometry(float(row["locX"]), float(row["locY"]), row["side"], three)
    return {"shotDesc": row.get("shotDesc") or "未知", "shotType": "3PT" if three else "2PT", "side": row["side"],
            "locX": float(row["locX"]), "locY": float(row["locY"]), "period": row.get("period"),
            "playerId": str(player_id), "distanceFt": geo["distanceFt"], "zone": geo["zone"]}


def render_qwen(messages):
    """Qwen2.5 chat format, identical to the token layout used in training."""
    text = "".join(f"<|im_start|>{m['role']}\n{m['content']}<|im_end|>\n" for m in messages)
    return text + "<|im_start|>assistant\n"
