"""Deterministic story contract shared by AgentCore and the rendering worker.

This is our product protocol, never an organizer evaluation schema. Curated
practice-video associations remain explicitly distinct from automatic matching.
"""

import copy
import json
import math
import re
from urllib.parse import urlsplit

STORY_PROTOCOL = "product-story-v1"
MAX_CHAPTERS = 5
CAPTION_CHARACTERS_PER_SECOND = 8
STORIES_KEY = "product/data/stories.json"
# These are lexical guardrails for sparse-frame narration, not a substitute for
# basketball review. Ordinary posture words such as “双臂打开” remain allowed.
CAUSAL_INTENT = re.compile(
    r"骗飞|骗起|骗过|晃飞|晃起|假动作|假投|佯投|诱使|诱导|诱骗|迫使|刻意|故意|意图|意在|旨在|为了"
    r"|试图|企图|等待|等到|等着|伺机|导致|使得|从而|因此|得益于|归因于|牵制|调动防守"
    r"|吸引(?:了)?(?:防守|对手)|有意(?:地|制造|诱|让|使|等待|拖延|吸引|放慢|避开)"
    r"|(?:打开|制造|创造|拉开|赢得|形成|带来|腾出|换来|带出|留出|获得)[^，。；！？]{0,12}(?:空间|机会|空当|空档|空位)"
    r"|让[^，。；！？]{0,12}(?:起跳|失位|失衡|空间|空位|空当|机会)"
)
STATIC_ASSERTION = re.compile(r"未动|没动|不动|静止|没有移动|未曾移动|毫无动作|停在原地|站在原地|停住")
# Sparse chapters can span changing shot-clock states. Until a temporal clock
# contract exists, leave urgency judgments out of generated prose altogether.
CLOCK_ASSERTION = re.compile(r"进攻时钟|投篮时钟|读秒|所剩不多|时间紧迫|时间紧张|时间有限|时间所剩|shot\s*clock", re.I)
COURT_REGIONS = (
    "罚球线延长线", "合理冲撞区", "限制区", "油漆区", "三秒区", "三分线", "三分弧",
    "罚球线", "罚球弧", "罚球圈", "弧顶", "肘区", "肘部", "低位", "高位", "禁区", "篮下",
    "底角", "底线", "边线", "中线", "中圈", "中距离", "外线", "内线", "侧翼", "翼侧",
    "左翼", "右翼", "弱侧", "强侧", "前场", "后场",
)
COURT_LOCATION = re.compile(
    "(?:" + "|".join(map(re.escape, sorted(COURT_REGIONS, key=len, reverse=True)))
    + r")(?:附近|边缘|外侧|内侧|外沿|内沿|一带|外|内)?"
)
LAYOUT_DIRECTION = r"(?:右上(?:角|方)?|右下(?:角|方)?|左上(?:角|方)?|左下(?:角|方)?|上方|下方|上面|下面|顶部|底部|左侧|右侧)"
LAYOUT_TARGET = r"(?:指标|数据|数值|面板|图表|进度条|条形图)"
LAYOUT_REFERENCE = re.compile(
    LAYOUT_DIRECTION + r"[^，。；！？]{0,8}" + LAYOUT_TARGET
    + "|" + LAYOUT_TARGET + r"[^，。；！？]{0,8}" + LAYOUT_DIRECTION
)


class StoryValidationError(ValueError):
    pass


def caption_character_limit(start, end):
    """Conservative on-screen reading budget, including punctuation."""
    return max(4, min(42, math.floor((end - start) * CAPTION_CHARACTERS_PER_SECOND + 1e-6)))


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def text(value, label, maximum):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or any(ord(c) < 32 for c in value):
        raise StoryValidationError(f"{label} must be nonempty text, max {maximum} characters")
    return value.strip()


def model_text_problems(value, label):
    """Collect every numeric/metric wording problem in one bounded text field."""
    # Numerals belong to copied source records, never model-authored prose.
    # “这一次出手 / 每一次选择” identifies the narrated instance; it does not
    # assert an event count. Do not exempt ordinals such as “第一次” or “两次”.
    # Named zones are checked against source text separately; their “三” is not
    # a score/count authored by the model.
    checked = re.sub(r"三分线|三分弧|三秒区", "", value)
    checked = re.sub(r"(?<![第零〇一二三四五六七八九十百千万两])(?:这|每|那)?一次", "", checked)
    numeric = sorted(set(re.findall(
        r"[0-9０-９]+(?:[.．][0-9０-９]+)?(?:号|分|秒|次|人|名|位|个|成|米|节|比|倍|[%％])?|[%％]"
        r"|[零〇一二三四五六七八九十百千万两]+(?:号|分|秒|次|人|名|位|个|成|米|节|比|倍)"
        r"|[零〇一二三四五六七八九十百千万两]+点[零〇一二三四五六七八九十百千万两]+|一半|半数|分之", checked)))
    problems = []
    if numeric:
        problems.append(f"{label}: numeric phrases {numeric!r} are not allowed; use a sourced player name or 持球人, never jersey numbers/counts")
    probability = sorted(set(re.findall(r"xfg|gravity|leverage|命中率|胜率|概率|成功率|百分|贡献|引力值|胜负影响率", value, re.I)))
    if probability:
        problems.append(f"{label}: probability/contribution phrases {probability!r} must be left to copied official metric labels")
    return problems


def model_text(value, label, maximum):
    value = text(value, label, maximum)
    problems = model_text_problems(value, label)
    if problems:
        raise StoryValidationError("; ".join(problems))
    return value


def allowed_court_locations(story):
    """Only source prose can authorize a named zone, never editorial suggestions.

    Keep location qualifiers: “禁区附近” alone cannot authorize “进入禁区”.
    This is an example-level vocabulary limit, not automatic spatial grounding.
    """
    bodies = [entry.get("body", "") for entry in story.get("evidence", [])
              if isinstance(entry, dict) and (entry.get("kind") == "observation"
                 or str(entry.get("kind", "")).lower().startswith("official"))]
    official = story.get("officialEvent", {})
    if isinstance(official, dict) and official.get("verified") is True:
        bodies.append(official.get("description", ""))
    return sorted({match.group(0) for body in bodies if isinstance(body, str)
                   for match in COURT_LOCATION.finditer(body)})


def grounded_model_text(value, label, maximum, allowed_locations):
    value = text(value, label, maximum)
    problems = model_text_problems(value, label)
    causal = sorted({match.group(0) for match in CAUSAL_INTENT.finditer(value)})
    if causal:
        problems.append(
            f"{label}: causal/intent phrases {causal!r} are unsupported by sparse frames; "
            "describe only visible order/posture, e.g. 防守人已起跳，持球人仍持球")
    static = sorted({match.group(0) for match in STATIC_ASSERTION.finditer(value)})
    if static:
        problems.append(
            f"{label}: static-motion phrases {static!r} cannot be established from sparse frames; "
            "use an observed posture such as 仍持球, without asserting no movement")
    clock = sorted({match.group(0) for match in CLOCK_ASSERTION.finditer(value)})
    if clock:
        problems.append(
            f"{label}: shot-clock phrases {clock!r} require time-aligned clock evidence; "
            "omit urgency judgments, especially in opening chapters; describe the sourced score or visible action")
    layout = sorted({match.group(0) for match in LAYOUT_REFERENCE.finditer(value)})
    if layout:
        problems.append(f"{label}: layout phrases {layout!r} must not guess rendered positions; use 官方出手数据见指标")
    for match in COURT_LOCATION.finditer(value):
        if match.group(0) not in allowed_locations:
            problems.append(
                f"{label}: court location {match.group(0)!r} is absent from approved source wording; "
                f"allowed phrases={sorted(allowed_locations)!r}; keep source qualifiers or omit the location")
    if problems:
        raise StoryValidationError("; ".join(problems))
    return value


def plan_prose(plan, allowed_locations):
    """Validate all generated fields together, so one model revision can fix all.

    Call after the plan/chapter field shapes are checked. No source IDs, chapter
    times or copied official records are treated as model-authored prose.
    """
    problems = []

    def check(value, path, maximum):
        try:
            return grounded_model_text(value, path, maximum, allowed_locations)
        except StoryValidationError as error:
            problems.append(str(error))

    result = {"title": check(plan["title"], "title", 24),
              "summary": check(plan["summary"], "summary", 140), "chapters": []}
    for index, chapter in enumerate(plan["chapters"]):
        label = f"chapters[{index}](id={str(chapter['id'])[:60]!r})"
        entry = {field: check(chapter[field], f"{label}.{field}", maximum)
                 for field, maximum in (("title", 20), ("caption", 42))}
        if "focus" in chapter:
            entry["focus"] = check(chapter["focus"], f"{label}.focus", 20)
        result["chapters"].append(entry)
    if problems:
        raise StoryValidationError("Fix ALL listed generated-text fields in one revised plan; do not repair only the first item:\n"
                                   + "\n".join(problems))
    return result


def frame_id(timestamp_ms):
    return "frame-" + format(timestamp_ms, ".12g")


def select_story(document, sample):
    if not isinstance(document, dict) or not isinstance(document.get("version"), (str, int)) or not isinstance(document.get("stories"), list):
        raise StoryValidationError("stories document must have version and stories[]")
    matches = [story for story in document["stories"] if isinstance(story, dict) and story.get("id") == sample]
    if len(matches) != 1:
        raise StoryValidationError("sample must select exactly one curated story")
    return copy.deepcopy(matches[0])


def evidence_catalog(story, frames):
    result = []
    seen = set()
    source_evidence = story.get("evidence", [])
    if not isinstance(source_evidence, list) or len(source_evidence) > 60:
        raise StoryValidationError("story evidence must contain at most 60 records")
    for item in source_evidence:
        if not isinstance(item, dict):
            raise StoryValidationError("evidence must be an object")
        identifier = text(item.get("id"), "evidence.id", 100)
        if identifier in seen or identifier.startswith("frame-"):
            raise StoryValidationError("duplicate or reserved evidence identifier")
        seen.add(identifier)
        result.append(copy.deepcopy(item))
    for frame in frames:
        identifier = frame_id(frame["timestamp_ms"])
        result.append({"id": identifier, "kind": "video_frame", "title": "本次实际输入帧",
                       "videoTime": frame["timestamp_ms"] / 1000, "timestampMs": frame["timestamp_ms"],
                       "sourceLabel": "原始视频抽帧", "s3_uri": frame["s3_uri"]})
    return result


def canonical_metrics(story):
    """Copy a verified metric; no model is allowed to set its value or display."""
    official = story.get("officialEvent", {})
    metric = story.get("shotMetric")
    if not isinstance(official, dict) or official.get("verified") is not True or not metric:
        return []
    if not isinstance(metric, dict):
        raise StoryValidationError("shotMetric must be an object")
    required = {"id", "label", "rawValue", "unit", "display", "evidenceId", "sourceUrl"}
    if not required.issubset(metric):
        raise StoryValidationError("verified metric lacks required provenance fields")
    value, unit = metric["rawValue"], metric["unit"]
    if not number(value) or unit not in ("ratio", "percent"):
        raise StoryValidationError("metric must have a finite ratio or percent value")
    ratio = value if unit == "ratio" else value / 100
    if not 0 <= ratio <= 1:
        raise StoryValidationError("metric is outside the declared unit range")
    sources = [item for item in story.get("evidence", []) if item.get("id") == metric["evidenceId"]]
    if len(sources) != 1:
        raise StoryValidationError("metric source evidence is absent")
    source = sources[0]
    if not str(source.get("kind", "")).lower().startswith("official"):
        raise StoryValidationError("metric must cite official evidence")
    url = urlsplit(metric["sourceUrl"])
    host = url.hostname or ""
    if (url.scheme != "https" or url.username or url.password
            or not any(host == domain or host.endswith("." + domain) for domain in ("nba.com", "nba.cn"))
            or source.get("sourceUrl") != metric["sourceUrl"]):
        raise StoryValidationError("metric source URL must match its evidence on an official NBA host")
    expected_fg = official.get("expectedFg")
    if not number(expected_fg) or not 0 <= expected_fg <= 1 or abs(expected_fg - ratio) > 1e-9:
        raise StoryValidationError("metric differs from officialEvent.expectedFg")
    source_value = source.get("value")
    source_unit = source.get("unit")
    if not number(source_value) or source_unit not in ("ratio", "percent"):
        raise StoryValidationError("metric evidence lacks an explicitly typed numeric value")
    source_ratio = source_value if source_unit == "ratio" else source_value / 100
    if abs(source_ratio - ratio) > 1e-9:
        raise StoryValidationError("metric differs from its source evidence value")
    for key in ("gameId", "eventId", "playerId"):
        expected = official.get(key)
        if expected is None or any(str(entry.get(key)) != str(expected) for entry in (metric, source)):
            raise StoryValidationError(f"metric {key} does not match its official event identity")
    display = text(metric["display"], "metric.display", 32)
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)%", display)
    if not match or abs(float(match[1]) - ratio * 100) > 0.051:
        raise StoryValidationError("metric display does not match the source value")
    reveal = metric.get("revealAt", 0)
    duration = story.get("durationSeconds")
    if not number(reveal) or reveal < 0 or (number(duration) and reveal >= duration):
        raise StoryValidationError("metric revealAt must be within the source video")
    metric = copy.deepcopy(metric)
    metric["barRatio"] = ratio
    return [metric]


def validate_story_source(story, request):
    if not isinstance(story, dict) or story.get("id") != request["video"]["id"]:
        raise StoryValidationError("curated story and source video differ")
    duration = story.get("durationSeconds")
    if not number(duration) or abs(duration * 1000 - request["video"]["duration_ms"]) > 250:
        raise StoryValidationError("curated story duration differs from the source video")
    expected_sha = story.get("sourceVideoSha256")
    if expected_sha is not None and (not isinstance(expected_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha)
                                     or expected_sha != request["video"].get("sha256")):
        raise StoryValidationError("curated story SHA-256 differs from the source video")
    options = story.get("storyOptions")
    if not isinstance(options, list) or not 1 <= len(options) <= 6:
        raise StoryValidationError("storyOptions requires 1 to 6 selectable perspectives")
    option_ids = [text(option.get("id"), "storyOption.id", 60) for option in options if isinstance(option, dict)]
    if len(option_ids) != len(options) or len(set(option_ids)) != len(option_ids):
        raise StoryValidationError("story perspective IDs must be unique")
    evidence_catalog(story, request["frames"])
    canonical_metrics(story)
    return story


def validate_plan(plan, story, request, inspected_frame_ids=None):
    if not isinstance(plan, dict) or set(plan) != {"perspective", "title", "summary", "chapters"}:
        raise StoryValidationError("plan requires exactly perspective, title, summary, chapters")
    option_ids = {option["id"] for option in story["storyOptions"]}
    if plan["perspective"] not in option_ids:
        raise StoryValidationError("perspective must come from this story's choices")
    chapters = plan["chapters"]
    if not isinstance(chapters, list) or not 2 <= len(chapters) <= MAX_CHAPTERS:
        raise StoryValidationError("plan must contain 2 to 5 chapters")
    required = {"id", "start", "end", "title", "caption", "evidenceIds"}
    for chapter in chapters:
        if not isinstance(chapter, dict) or not required.issubset(chapter) or set(chapter) - required - {"focus"}:
            raise StoryValidationError("chapter contains missing or unsupported fields")
    prose = plan_prose(plan, set(allowed_court_locations(story)))
    result = {"perspective": plan["perspective"], "title": prose["title"],
              "summary": prose["summary"], "chapters": []}
    evidence_by_id = {entry["id"]: entry for entry in evidence_catalog(story, request["frames"])}
    evidence_ids = set(evidence_by_id)
    allowed_frames = {frame_id(frame["timestamp_ms"]) for frame in request["frames"]}
    inspected = allowed_frames if inspected_frame_ids is None else set(inspected_frame_ids)
    seen_ids, all_citations, previous_end = set(), set(), 0
    for index, chapter in enumerate(chapters):
        identifier = text(chapter["id"], "chapter.id", 60)
        if not re.fullmatch(r"[A-Za-z0-9_-]+", identifier) or identifier in seen_ids:
            raise StoryValidationError("chapter IDs must be unique simple identifiers")
        start, end = chapter["start"], chapter["end"]
        if not number(start) or not number(end) or not 0 <= start < end <= request["video"]["duration_ms"] / 1000:
            raise StoryValidationError("chapter time is outside the source video")
        if start < previous_end or end - start < 0.5:
            raise StoryValidationError("chapters must be ordered, nonoverlapping, and at least half a second")
        citations = chapter["evidenceIds"]
        if (not isinstance(citations, list) or not 1 <= len(citations) <= 6
                or any(not isinstance(item, str) or item not in evidence_ids for item in citations)
                or len(set(citations)) != len(citations)):
            raise StoryValidationError("chapter must cite 1 to 6 known unique evidence IDs")
        if any(item in allowed_frames and item not in inspected for item in citations):
            raise StoryValidationError("chapter cites an image that the inspect_frames tool did not return")
        for citation in citations:
            source = evidence_by_id[citation]
            timestamp = source.get("videoTime")
            if number(timestamp) and not str(source.get("kind", "")).lower().startswith("official"):
                if not start - 0.5 <= timestamp <= end + 0.5:
                    raise StoryValidationError("chapter image evidence is outside its time range; move the chapter or cite relevant frames")
        caption_limit = caption_character_limit(start, end)
        if len(prose["chapters"][index]["caption"]) > caption_limit:
            raise StoryValidationError(f"chapters[{index}].caption exceeds reading budget: shorten to {caption_limit} characters")
        entry = {"id": identifier, "start": start, "end": end,
                 "title": prose["chapters"][index]["title"],
                 "caption": prose["chapters"][index]["caption"],
                 "evidenceIds": list(citations)}
        if "focus" in chapter:
            entry["focus"] = prose["chapters"][index]["focus"]
        result["chapters"].append(entry)
        seen_ids.add(identifier)
        all_citations.update(citations)
        previous_end = end
    if not all_citations.intersection(inspected):
        raise StoryValidationError("the story must cite at least one image actually inspected")
    metrics = canonical_metrics(story)
    if metrics and not all(metric["evidenceId"] in all_citations for metric in metrics):
        raise StoryValidationError("verified official metric must be cited by a chapter")
    prose = " ".join([result["title"], result["summary"]] +
                     [chapter.get(field, "") for chapter in result["chapters"] for field in ("title", "caption", "focus")])
    if not metrics and re.search(r"xfg|命中率|引力|胜率|gravity|leverage", prose, re.I):
        raise StoryValidationError("unverified official metric claims cannot be rendered")
    result["metrics"] = metrics
    result["associationMethod"] = "curated_practice_video_mapping_not_automatic_event_matching"
    return result


def validation_record(plan, request, inspected_frame_ids):
    return {"passed": True, "protocol": STORY_PROTOCOL,
            "checks": ["known_evidence_ids", "cited_frames_actually_inspected", "source_time_bounds",
                       "nonoverlapping_chapters", "no_model_authored_numbers", "official_metrics_copied_verbatim",
                       "known_causal_static_phrases_rejected", "court_location_vocabulary_from_source_text",
                       "no_guessed_metric_layout_positions"],
            "chapterCount": len(plan["chapters"]), "sourceDurationMs": request["video"]["duration_ms"],
            "inspectedFrameIds": sorted(inspected_frame_ids),
            "scope": "Structural and provenance validation; not an independent factual or basketball-accuracy certification"}
