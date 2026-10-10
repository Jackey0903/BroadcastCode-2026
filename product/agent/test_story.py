"""Offline contract/tool-loop tests. Fake clients do not certify cloud inference."""

import copy
import hashlib
import io
import json
import unittest
from contextlib import redirect_stdout

from main import ProductAgent
from readiness_agent import ModelOutputError
from story_agent import StoryAgent
from story_contract import (STORIES_KEY, StoryValidationError, allowed_court_locations, canonical_metrics, model_text,
                            validate_plan, validate_story_source)

BUCKET = "team02-product-test"
VIDEO = b"offline-original-video-fixture"
JPEG = b"\xff\xd8\xffoffline-image-fixture"
MODEL = "offline-model-double"


def fixture():
    url = "https://api.nba.cn/nba-web/api/web/inside/gpShot?gameId=game-test&playerId=player-test"
    identity = {"gameId": "game-test", "eventId": 666, "playerId": "player-test"}
    story = {"id": "flagg", "durationSeconds": 22,
             "sourceVideoSha256": hashlib.sha256(VIDEO).hexdigest(),
             "storyOptions": [{"id": "player", "label": "看出手"}, {"id": "data", "label": "看数据"}],
             "officialEvent": {**identity, "verified": True, "expectedFg": 0.51, "made": True},
             "shotMetric": {**identity, "id": "metric", "label": "预期投篮命中率", "rawValue": 0.51,
                            "unit": "ratio", "display": "51.0%", "evidenceId": "official-xfg", "sourceUrl": url},
             "evidence": [{**identity, "id": "official-xfg", "kind": "official", "value": 0.51,
                           "unit": "ratio", "sourceUrl": url, "body": "原始官方事件证据"}], "chapters": []}
    request = {"protocol_version": "team02-readiness-v1", "request_id": "job-1", "mode": "story",
               "video": {"id": "flagg", "name": "练习视频", "s3_uri": f"s3://{BUCKET}/samples/flagg.mp4",
                         "duration_ms": 22000, "sha256": hashlib.sha256(VIDEO).hexdigest(), "width": 1920, "height": 1080},
               "frames": [{"timestamp_ms": value, "s3_uri": f"s3://{BUCKET}/frames/{value}.jpg", "format": "jpeg"}
                          for value in (1000, 15000)], "story": story}
    plan = {"perspective": "player", "title": "看懂出手选择", "summary": "先观察持球位置，再把结果与出手条件分开看。",
            "chapters": [{"id": "setup", "start": 0, "end": 15, "title": "关注持球者", "caption": "看持球者与篮筐之间的空间。", "evidenceIds": ["frame-1000"]},
                         {"id": "shot", "start": 15, "end": 22, "title": "结果与机会", "caption": "进球结果与出手机会需要分开理解。", "evidenceIds": ["frame-15000", "official-xfg"]}]}
    return request, plan


class FakeS3:
    def __init__(self, request):
        self.request = request
        self.reads = []
        self.uploads = []
        self.objects = {}

    def get_object(self, **kwargs):
        key = kwargs["Key"]
        self.reads.append(key)
        if key == STORIES_KEY:
            value = json.dumps({"version": "test-v1", "stories": [self.request["story"]]}, ensure_ascii=False).encode()
        elif key in ("product/config/samples.json", "config/samples.json"):
            value = json.dumps({"flagg": {key: self.request[key] for key in ("video", "frames")}}).encode()
        elif key.endswith(".mp4"):
            value = VIDEO
        else:
            value = JPEG
        return {"Body": io.BytesIO(value)}

    def upload_file(self, filename, bucket, key, **kwargs):
        from pathlib import Path
        self.uploads.append((key, Path(filename).read_bytes()))

    def put_object(self, **kwargs):
        self.objects[kwargs["Key"]] = kwargs["Body"]


def tool_response(*calls):
    return {"output": {"message": {"role": "assistant", "content": [
        {"toolUse": {"toolUseId": identifier, "name": name, "input": args}} for identifier, name, args in calls]}},
        "usage": {"inputTokens": 100, "outputTokens": 100, "totalTokens": 200}, "stopReason": "tool_use"}


class ScriptedBedrock:
    def __init__(self, plan=None, responses=None):
        self.calls = []
        self.responses = responses or [
            tool_response(("inspect", "inspect_frames", {"frame_ids": ["frame-1000", "frame-15000"]}),
                          ("read", "read_official_event", {})),
            tool_response(("validate", "validate_story", {"plan": plan})),
        ]

    def converse(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        return copy.deepcopy(self.responses[len(self.calls) - 1])


def execute(request=None, plan=None, responses=None):
    default_request, default_plan = fixture()
    request, plan = request or default_request, plan or default_plan
    s3, model = FakeS3(request), ScriptedBedrock(plan, responses)
    with redirect_stdout(io.StringIO()):
        result = StoryAgent(BUCKET, s3, model, MODEL).run(request)
    return result, s3, model


class StoryTests(unittest.TestCase):
    def test_real_tool_dispatch_uses_image_bytes_and_preserves_official_metric(self):
        request, _ = fixture()
        result, s3, model = execute()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(model.calls), 2)
        self.assertEqual(s3.reads, ["frames/1000.jpg", "frames/15000.jpg", STORIES_KEY])
        results = model.calls[1]["messages"][2]["content"]
        images = [block["image"]["source"]["bytes"] for item in results
                  for block in item["toolResult"]["content"] if "image" in block]
        self.assertEqual(images, [JPEG, JPEG])
        self.assertEqual([item["tool"] for item in result["trace"]], ["inspect_frames", "read_official_event", "validate_story"])
        self.assertEqual(result["plan"]["metrics"], canonical_metrics(request["story"]))
        self.assertIn("not an independent factual", result["validation"]["scope"])

    def test_invalid_numeric_claim_can_be_repaired_only_after_rejected_tool(self):
        _, plan = fixture()
        bad = copy.deepcopy(plan)
        bad["chapters"][1]["caption"] = "命中率高达99%"
        responses = ScriptedBedrock(plan).responses
        responses.insert(1, tool_response(("bad-validation", "validate_story", {"plan": bad})))
        result, _, model = execute(responses=responses)
        self.assertEqual(result["trace"][2]["status"], "rejected")
        self.assertEqual(result["trace"][3]["status"], "succeeded")
        self.assertEqual(len(model.calls), 3)
        self.assertNotIn("99", json.dumps(result["plan"]))

    def test_validation_cannot_pass_in_the_same_round_that_first_reads_sources(self):
        _, plan = fixture()
        responses = [tool_response(
            ("inspect", "inspect_frames", {"frame_ids": ["frame-1000", "frame-15000"]}),
            ("read", "read_official_event", {}),
            ("too-early", "validate_story", {"plan": plan})),
            tool_response(("after-receiving-sources", "validate_story", {"plan": plan}))]
        result, _, model = execute(responses=responses)
        self.assertEqual(result["trace"][2]["status"], "rejected")
        self.assertEqual(result["trace"][3]["status"], "succeeded")
        self.assertEqual(len(model.calls), 2)
        delivered = model.calls[1]["messages"][-1]["content"]
        self.assertTrue(any("image" in block for item in delivered for block in item["toolResult"]["content"]))

    def test_rejected_plan_gets_frame_and_caption_hints_in_one_model_revision(self):
        request, plan = fixture()
        bad = copy.deepcopy(plan)
        bad["chapters"][1].update(start=15, end=17, caption="持球者看向篮筐，防守人双臂举起，随后持球者完成出手。")
        bad["chapters"][1]["evidenceIds"] = ["invented-frame"]
        corrected = copy.deepcopy(bad)
        corrected["chapters"][1].update(caption="防守人双臂举起。", evidenceIds=["frame-15000", "official-xfg"])
        responses = [
            tool_response(("inspect", "inspect_frames", {"frame_ids": ["frame-1000", "frame-15000"]}), ("read", "read_official_event", {})),
            tool_response(("bad", "validate_story", {"plan": bad})),
            tool_response(("fixed", "validate_story", {"plan": corrected})),
        ]
        result, _, model = execute(request=request, responses=responses)
        feedback = result["trace"][-2]["result"]["repairHints"]
        self.assertEqual(feedback["mustCiteAtLeastOneActualFrame"], ["frame-1000", "frame-15000"])
        self.assertIn("official-xfg", feedback["allowedEvidenceIds"])
        self.assertEqual(feedback["captionLimits"][1], {"chapter": 1, "maxCaptionCharacters": 16})
        self.assertEqual(len(model.calls), 3)
        self.assertEqual(result["status"], "completed")

    def test_short_chapter_requires_readable_caption_without_changing_its_time(self):
        request, plan = fixture()
        plan["chapters"][1].update(start=15, end=17,
                                   caption="持球者看向篮筐，防守人双臂举起，随后持球者完成出手。")
        with self.assertRaisesRegex(StoryValidationError, "caption exceeds reading budget"):
            validate_plan(plan, request["story"], request)
        plan["chapters"][1]["caption"] = "防守人双臂举起。"
        normalized = validate_plan(plan, request["story"], request)
        self.assertEqual(normalized["chapters"][1]["start"], 15)
        self.assertEqual(normalized["chapters"][1]["end"], 17)

    def test_official_metric_reveal_cannot_be_invalid_or_after_video_ends(self):
        request, _ = fixture()
        for reveal in (-1, True, float("nan"), request["story"]["durationSeconds"]):
            story = copy.deepcopy(request["story"])
            story["shotMetric"]["revealAt"] = reveal
            with self.subTest(reveal=reveal), self.assertRaisesRegex(StoryValidationError, "revealAt"):
                canonical_metrics(story)
        story["shotMetric"]["revealAt"] = 18.5
        self.assertEqual(canonical_metrics(story)[0]["revealAt"], 18.5)

    def test_bad_references_times_unseen_frames_and_model_metrics_are_rejected(self):
        request, plan = fixture()
        cases = []
        bad = copy.deepcopy(plan); bad["chapters"][0]["evidenceIds"] = ["made-up"]; cases.append(bad)
        bad = copy.deepcopy(plan); bad["chapters"][1]["end"] = 23; cases.append(bad)
        bad = copy.deepcopy(plan); bad["chapters"][1]["start"] = 14; cases.append(bad)
        bad = copy.deepcopy(plan); bad["metrics"] = [{"display": "99%"}]; cases.append(bad)
        for bad in cases:
            with self.subTest(plan=bad), self.assertRaises(StoryValidationError):
                validate_plan(bad, request["story"], request)
        with self.assertRaises(StoryValidationError):
            validate_plan(plan, request["story"], request, {"frame-1000"})

    def test_chinese_probability_claims_and_future_frame_chapters_are_rejected(self):
        request, plan = fixture()
        for claim in ("命中率为零点九九，胜率为一半。", "这个选择的成功概率更高。", "他贡献了一半。", "完成动作需要零点五秒。"):
            bad = copy.deepcopy(plan); bad["chapters"][1]["caption"] = claim
            with self.subTest(claim=claim), self.assertRaises(StoryValidationError):
                validate_plan(bad, request["story"], request)
        bad = copy.deepcopy(plan)
        bad["chapters"][0].update(start=0, end=0.75, caption="防守人已经起跳。", evidenceIds=["frame-15000"])
        with self.assertRaisesRegex(StoryValidationError, "outside its time range"):
            validate_plan(bad, request["story"], request)

    def test_narrative_once_is_allowed_but_quantitative_assertions_still_explain_rejection(self):
        for phrase in ("这一次出手，先看防守姿态。", "每一次选择都应回到画面。", "一次突破中的观察重点。"):
            self.assertEqual(model_text(phrase, "caption", 42), phrase)
        for phrase, matched in (("第一次数清事件。", "一次"), ("连续两次出手。", "两次"), ("有两名防守者。", "两名")):
            with self.subTest(phrase=phrase), self.assertRaisesRegex(StoryValidationError, matched):
                model_text(phrase, "caption", 42)

    def test_sparse_frame_overclaims_are_rejected_in_every_generated_prose_field(self):
        request, plan = fixture()
        claims = [("节奏错位打开了出手空间", "打开了出手空间"), ("阿门仍握球未动", "未动"),
                  ("推进至弧顶附近", "弧顶附近"), ("骗飞防守人后出手", "骗飞"),
                  ("因此获得空当", "因此"), ("他仍持球等待", "等待")]
        for phrase, matched in claims:
            for field in ("title", "summary", "chapter.title", "chapter.caption", "chapter.focus"):
                bad = copy.deepcopy(plan)
                target, key = (bad["chapters"][1], field.split(".")[1]) if "." in field else (bad, field)
                target[key] = phrase
                with self.subTest(phrase=phrase, field=field), self.assertRaisesRegex(StoryValidationError, matched):
                    validate_plan(bad, request["story"], request)
        plan["summary"] = "防守人已起跳时，持球人仍持球；随后持球人起跳，防守人正在下落。"
        plan["chapters"][1]["caption"] = "防守人双臂打开，持球人正在起跳。"
        self.assertEqual(validate_plan(plan, request["story"], request)["summary"], plan["summary"])
        plan["summary"] = "阿门推进至弧顶附近，仍持球等待，节奏错位打开了出手空间。"
        with self.assertRaises(StoryValidationError) as caught:
            validate_plan(plan, request["story"], request)
        for unsupported in ("弧顶附近", "等待", "打开了出手空间"):
            self.assertIn(unsupported, str(caught.exception))

    def test_shot_clock_judgments_are_rejected_before_temporal_grounding_exists(self):
        request, plan = fixture()
        for phrase in ("进攻时钟紧张。", "时间所剩不多。", "读秒时起跳。", "shot clock urgency"):
            for field in ("title", "summary", "chapter.title", "chapter.caption", "chapter.focus"):
                bad = copy.deepcopy(plan)
                target, key = (bad["chapters"][0], field.split(".")[1]) if "." in field else (bad, field)
                target[key] = phrase
                with self.subTest(phrase=phrase, field=field), self.assertRaisesRegex(StoryValidationError, "shot-clock"):
                    validate_plan(bad, request["story"], request)
        plan["chapters"][0]["caption"] = "持球人准备推进。"
        self.assertEqual(validate_plan(plan, request["story"], request)["chapters"][0]["caption"], "持球人准备推进。")

    def test_court_location_sources_exclude_editorial_hints_and_keep_qualifiers(self):
        request, plan = fixture()
        story = request["story"]
        story["title"] = "弧顶观察"
        story["storyOptions"][0]["description"] = "弧顶附近的动作"
        story["chapters"] = [{"caption": "持球人走到弧顶附近。"}]
        story["officialEvent"].update(verified=False, description="持球人在弧顶附近。")
        self.assertEqual(allowed_court_locations(story), [])
        plan["summary"] = "持球人在弧顶附近。"
        with self.assertRaisesRegex(StoryValidationError, "弧顶附近"):
            validate_plan(plan, story, request)
        story["evidence"].append({"id": "checked-location", "kind": "observation",
                                   "body": "持球人已推进至禁区附近；先前在三分线外持球。"})
        self.assertEqual(allowed_court_locations(story), ["三分线外", "禁区附近"])
        plan["summary"] = "先前三分线外持球，随后推进至禁区附近。"
        self.assertEqual(validate_plan(plan, story, request)["summary"], plan["summary"])
        plan["summary"] = "持球人已进入禁区。"
        with self.assertRaisesRegex(StoryValidationError, "court location '禁区'"):
            validate_plan(plan, story, request)

    def test_tool_repair_returns_exact_overclaim_and_source_location_vocabulary(self):
        request, plan = fixture()
        bad = copy.deepcopy(plan); bad["chapters"][1]["caption"] = "防守人起跳，持球人未动。"
        responses = ScriptedBedrock(plan).responses
        responses.insert(1, tool_response(("overclaim", "validate_story", {"plan": bad})))
        result, _, model = execute(request=request, responses=responses)
        source = next(record for record in result["trace"] if record["tool"] == "read_official_event")
        self.assertEqual(source["result"]["allowedCourtLocations"], [])
        self.assertEqual(result["trace"][2]["status"], "rejected")
        error = model.calls[2]["messages"][-1]["content"][0]["toolResult"]["content"][0]["json"]["error"]
        self.assertIn("未动", error)
        self.assertIn("仍持球", error)
        self.assertEqual(result["trace"][3]["status"], "succeeded")

    def test_all_prose_errors_return_together_and_one_revised_plan_can_pass(self):
        _, plan = fixture()
        bad = copy.deepcopy(plan)
        bad["title"] = "从外线到出手"
        bad["summary"] = "深衣32号准备出手。"
        bad["chapters"][0]["caption"] = "深衣32号在内线外持球。"
        bad["chapters"][1]["caption"] = "命中率51%，见下方指标。"
        responses = ScriptedBedrock(plan).responses
        responses.insert(1, tool_response(("all-prose-errors", "validate_story", {"plan": bad})))
        result, _, model = execute(responses=responses)
        error = result["trace"][2]["result"]["error"]
        for phrase in ("title", "外线", "summary", "32号", "chapters[0](id='setup').caption",
                       "内线外", "chapters[1](id='shot').caption", "命中率", "51%", "下方指标"):
            self.assertIn(phrase, error)
        self.assertEqual(len(model.calls), 3)
        self.assertEqual(result["trace"][3]["status"], "succeeded")
        self.assertEqual(result["plan"]["metrics"][0]["display"], "51.0%")

    def test_layout_references_are_rejected_without_banning_player_positions(self):
        request, plan = fixture()
        for phrase in ("看下方面板的数据", "指标位于右上角", "出手机会质量见下方指标"):
            for field in ("summary", "caption", "focus"):
                bad = copy.deepcopy(plan)
                target = bad if field == "summary" else bad["chapters"][1]
                target[field] = phrase
                with self.subTest(phrase=phrase, field=field), self.assertRaisesRegex(StoryValidationError, "layout phrases"):
                    validate_plan(bad, request["story"], request)
        for phrase in ("防守人在持球人右侧", "防守人在右侧，官方数据另有记录", "官方出手数据见指标"):
            plan["chapters"][1]["caption"] = phrase
            self.assertEqual(validate_plan(plan, request["story"], request)["chapters"][1]["caption"], phrase)

    def test_invalid_text_type_does_not_hide_other_fields_numeric_problems(self):
        request, plan = fixture()
        plan["title"] = None
        plan["summary"] = "32号球员持球。"
        with self.assertRaises(StoryValidationError) as caught:
            validate_plan(plan, request["story"], request)
        self.assertIn("title must be nonempty text", str(caught.exception))
        self.assertIn("32号", str(caught.exception))

    def test_official_value_identity_and_source_mismatches_fail_closed(self):
        request, _ = fixture()
        for section, key, value in [("officialEvent", "expectedFg", 0.99), ("shotMetric", "gameId", "other-game"),
                                    ("shotMetric", "playerId", "other-player"), ("shotMetric", "eventId", 999),
                                    ("shotMetric", "sourceUrl", "https://nba.cn.evil.example/data")]:
            story = copy.deepcopy(request["story"]); story[section][key] = value
            with self.subTest(section=section, key=key), self.assertRaises(StoryValidationError):
                canonical_metrics(story)
        story = copy.deepcopy(request["story"]); story["evidence"][0]["value"] = 0.99
        with self.assertRaises(StoryValidationError):
            canonical_metrics(story)

    def test_unverified_metric_is_never_injected(self):
        request, plan = fixture()
        request["story"]["officialEvent"]["verified"] = False
        self.assertEqual(validate_plan(plan, request["story"], request)["metrics"], [])

    def test_story_video_binding_checks_duration_and_sha(self):
        request, _ = fixture()
        for key, value in [("durationSeconds", 19), ("sourceVideoSha256", "0" * 64)]:
            story = copy.deepcopy(request["story"]); story[key] = value
            with self.subTest(key=key), self.assertRaises(StoryValidationError):
                validate_story_source(story, request)

    def test_six_round_limit_does_not_return_fake_success(self):
        responses = [tool_response((f"bad-{i}", "invented_tool", {})) for i in range(6)]
        with self.assertRaises(ModelOutputError):
            execute(responses=responses)

    def test_model_token_budget_does_not_return_fake_success(self):
        _, plan = fixture()
        responses = ScriptedBedrock(plan).responses
        responses[0]["usage"]["totalTokens"] = 91000
        with self.assertRaisesRegex(ModelOutputError, "totalTokens=91000"):
            execute(responses=responses)

    def test_round_usage_and_rejected_plan_are_logged_without_image_bytes(self):
        request, plan = fixture()
        bad = copy.deepcopy(plan); bad["chapters"][1]["caption"] = "有两名防守者。"
        responses = ScriptedBedrock(plan).responses
        responses.insert(1, tool_response(("rejected-plan", "validate_story", {"plan": bad})))
        log = io.StringIO()
        with redirect_stdout(log):
            StoryAgent(BUCKET, FakeS3(request), ScriptedBedrock(responses=responses), MODEL).run(request)
        entries = [json.loads(line) for line in log.getvalue().splitlines()]
        rounds = [entry for entry in entries if entry["event"] == "story_model_round"]
        self.assertEqual(len(rounds), 3)
        self.assertEqual(rounds[-1]["cumulativeUsage"]["totalTokens"], 600)
        rejected = next(entry for entry in entries if entry.get("status") == "rejected")
        self.assertEqual(rejected["input"]["plan"], bad)
        self.assertIn("两名", rejected["result"]["error"])
        self.assertNotIn("offline-image-fixture", log.getvalue())

    def test_legacy_readiness_request_still_works(self):
        request, _ = fixture(); request.pop("mode"); request.pop("story")
        response = {"output": {"message": {"role": "assistant", "content": [{"text": json.dumps({
            "observation": "球员出现在球场画面中。", "subtitle": "观察球员位置", "source_frame_times_ms": [1000]})}]}}, "usage": {}}
        agent = ProductAgent(BUCKET, FakeS3(request), ScriptedBedrock(responses=[response]))
        result = agent.run(request)
        self.assertEqual(result["protocol_version"], "team02-readiness-v1")
        self.assertEqual(result["subtitle"], "观察球员位置")


if __name__ == "__main__":
    unittest.main()
