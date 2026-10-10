"""Scoped, source-preserving RL cards for the editorial video's top band.

This module prepares FFmpeg filters, not a media-success receipt. The worker may
mark them used only after its actual render succeeds; independent review must
still inspect the resulting MP4. Every number comes from the validated bridge.
"""

import math

from story_contract import canonical_rl_evidence, validate_rl_narrative


DEPTH_TITLES = {
    "gravity": "无球外线引力",
    "leverage": "创造机会影响力",
    "shotdifficulty": "赛季平均出手机会质量",
}
LIVE_FLAGS = ("available", "trainedModelUsed", "selectionVerified",
              "lineageVerified", "actualRL", "modelInvokedThisRequest")


def _enable(start, end):
    return f"gte(t,{start:.6f})*lt(t,{end:.6f})"


def _narrative_lines(value):
    """Preserve the entire validated prose while fitting the 648px header lane."""
    # 34 CJK characters at 17px are narrower than the available 648px. Three
    # lines cover the contract's 100-character cap without touching the video.
    return [value[index:index + 34] for index in range(0, len(value), 34)]


def add_rl_filters(filters, label, result):
    """Append real-live RL cards and return an honest filter-preparation receipt.

    ``label`` is render_story's text-file callback. All boxes and labels stay in
    x=28..890, y=4..68; the original 720px image and right-hand xFG are untouched.
    Historical/replay/static/failure payloads add no filter and no RL badge.
    Malformed *live* payloads fail closed through the shared typed contract.
    """
    receipt = {"schema": "rl-burn-preparation-v1", "prepared": False,
               "burnedIntoVideo": False, "narrativeUsed": False,
               "evidenceIds": [], "sourceRefs": [], "periodRefs": [],
               "stagedWindows": [], "narrativeIncluded": False}
    payload = result.get("rlEvidence")
    scout = payload.get("scout", {}) if isinstance(payload, dict) else {}
    if (not isinstance(scout, dict) or scout.get("invocationMode") != "live"
            or any(scout.get(flag) is not True for flag in LIVE_FLAGS)):
        receipt["reason"] = "no_verified_live_model_selection_for_this_request"
        return receipt

    facts = canonical_rl_evidence(payload, {"officialEvent": result.get("officialEvent", {})})
    narrative = validate_rl_narrative(result.get("plan", {}), facts)
    duration_ms = result.get("video", {}).get("duration_ms")
    if (not isinstance(duration_ms, (int, float)) or isinstance(duration_ms, bool)
            or not math.isfinite(duration_ms) or duration_ms < 6000):
        raise ValueError("RL cards require a finite source duration of at least six seconds")
    duration = duration_ms / 1000
    narrative_start = duration - min(4.0, duration * 0.3)
    interval = narrative_start / 3
    enabled = _enable(0, duration)

    # Replace only the pre-existing left header title. The official xFG starts
    # at x=912, while this lane ends at x=890 and y=68, above the source picture.
    filters.append(f"drawbox=x=28:y=4:w=862:h=64:color=0x07080b:t=fill:enable='{enabled}'")
    filters.append(f"drawbox=x=217:y=10:w=2:h=51:color=0xf4541f:t=fill:enable='{enabled}'")
    label("rl-brand", "GameBuddy", 28, 6, 14, "0xf2f0ea", enabled)
    label("rl-badge", "RL 数据球探", 28, 24, 18, "0xf4541f", enabled)
    label("rl-model", "AWS SageMaker · 3B", 28, 49, 11, "0x8d93a3", enabled)

    rows = facts["evidence"]
    for index, row in enumerate(rows):
        start, end = index * interval, (index + 1) * interval
        window = _enable(start, end)
        period = facts["periods"][row["periodRef"]]
        if row["family"] == "basic":
            title = "全场得分  " + row["display"] + " 分"
            scope = "本场赛后统计 · NBA 官方基础数据"
        elif row["family"] == "advanced":
            title = "全场 eFG  " + row["display"]
            scope = "本场赛后统计 · 由官方计数计算"
        else:
            title = DEPTH_TITLES[row["family"]] + "  " + row["display"]
            season = period["season"].replace("-", "–")
            scope = season + "赛季 · 深度背景，非本回合实测"
        label(f"rl-card-{index}", title, 242, 9, 24, "0xf2f0ea", window)
        label(f"rl-scope-{index}", scope, 242, 43, 13, "0x8d93a3", window)
        receipt["stagedWindows"].append({
            "kind": "evidence", "start": round(start, 6), "end": round(end, 6),
            "evidenceId": row["evidenceId"], "sourceRef": row["sourceRef"],
            "periodRef": row["periodRef"], "display": row["display"],
            "title": title, "scopeLabel": scope, "grain": row["grain"],
        })

    lines = _narrative_lines(narrative)
    narrative_window = _enable(narrative_start, duration)
    for index, line in enumerate(lines):
        label(f"rl-narrative-{index}", line, 242, 7 + index * 19,
              17, "0xf2f0ea", narrative_window)
    receipt.update({
        "prepared": True, "narrativeIncluded": True, "narrativeText": narrative,
        "narrativeLines": lines, "contextOnly": True,
        "evidenceIds": [row["evidenceId"] for row in rows],
        "sourceRefs": list(facts["sources"]), "periodRefs": list(facts["periods"]),
        "headerBounds": {"x": 28, "y": 4, "width": 862, "height": 64},
        "successScope": "Filters prepared; actual MP4 rendering and visual acceptance are separate",
    })
    receipt["stagedWindows"].append({
        "kind": "model_narrative", "start": round(narrative_start, 6),
        "end": round(duration, 6), "evidenceIds": receipt["evidenceIds"],
        "text": narrative,
    })
    return receipt
