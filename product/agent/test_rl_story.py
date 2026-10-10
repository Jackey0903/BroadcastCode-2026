"""Offline RL story boundary tests; fabricated receipts do not certify a model."""

import copy
import json
import unittest

from story_contract import StoryValidationError, canonical_rl_evidence, validate_plan, validation_record
from test_story import execute, fixture


def rl_fixture():
    request, plan = fixture()
    game, player = "game-test", "player-test"
    common = {"playerId": player, "sourceRef": "box", "periodRef": "game", "grain": "player-game", "gameId": game}
    rows = [
        {**common, "evidenceId": "pts", "family": "basic", "metric": "PTS", "label": "得分",
         "value": 34, "unit": "count", "display": "34", "claimType": "official_fact"},
        {**common, "evidenceId": "efg", "family": "advanced", "metric": "EFG_PCT", "label": "投篮效率",
         "value": .54, "unit": "fraction", "display": "54.00%", "claimType": "derived_arithmetic"},
        {**common, "evidenceId": "depth", "family": "gravity", "metric": "OFF_BALL_PERIM_GRAV",
         "label": "无球外线防守关注", "value": 6.217, "unit": "gravity_score", "display": "6.217",
         "claimType": "official_fact", "gameId": None, "grain": "player-season", "sourceRef": "depth", "periodRef": "season"},
    ]
    request["rlEvidence"] = {
        "scout": {"available": True, "trainedModelUsed": True, "selectionVerified": True, "lineageVerified": True,
                  "actualRL": True, "modelInvoked": True, "modelInvokedThisRequest": True,
                  "threeLayersCovered": True, "invocationMode": "live", "evidence": rows},
        "sources": {"box": {"url": "https://www.nba.com/game/box-score", "sha256": "a" * 64},
                    "depth": {"url": "https://api.nba.cn/season/gravity", "sha256": "b" * 64}},
        "periods": {"game": {"season": "2025-26", "range": "full_completed_game"},
                    "season": {"season": "2025-26", "range": "source_season_snapshot"}},
    }
    plan.update(rlEvidenceIds=["pts", "efg", "depth"],
                rlNarrative="本场得分与投篮效率补充比赛背景；赛季无球防守关注仅作背景，不能解释此回合的动作原因。")
    return request, plan


class RLStoryTests(unittest.TestCase):
    def test_three_layers_reach_actual_model_context_tool_result_and_accepted_plan(self):
        request, plan = rl_fixture()
        result, _, model = execute(request=request, plan=plan)
        first_context = json.loads(model.calls[0]["messages"][0]["content"][0]["text"])
        self.assertEqual(first_context["rlEvidence"]["evidence"], request["rlEvidence"]["scout"]["evidence"])
        read_result = model.calls[1]["messages"][-1]["content"][1]["toolResult"]["content"][0]["json"]
        self.assertEqual(read_result["rlEvidence"]["evidence"], result["plan"]["rlEvidence"])
        self.assertEqual(result["plan"]["rlNarrative"], plan["rlNarrative"])
        self.assertEqual(result["plan"]["metrics"][0]["rawValue"], .51)
        self.assertEqual(result["trace"][-1]["input"]["plan"]["rlEvidenceIds"], ["pts", "efg", "depth"])
        self.assertIn("rl_three_layers_cited", result["validation"]["checks"])
        required = model.calls[0]["toolConfig"]["tools"][-1]["toolSpec"]["inputSchema"]["json"]["properties"]["plan"]["required"]
        self.assertIn("rlNarrative", required)

    def test_count_efficiency_and_season_score_are_distinct_numeric_types(self):
        request, plan = rl_fixture()
        request["rlEvidence"]["scout"]["evidence"][1].update(value=1.2, display="120.00%")
        request["rlEvidence"]["scout"]["evidence"][2].update(value=-2.41, display="-2.41")
        accepted = validate_plan(plan, request["story"], request)
        self.assertEqual(accepted["rlEvidence"][1]["value"], 1.2)
        self.assertEqual(accepted["rlEvidence"][2]["value"], -2.41)
        self.assertEqual(accepted["metrics"][0]["barRatio"], .51)

    def test_each_invalid_live_receipt_flag_and_replay_is_rejected(self):
        request, _ = rl_fixture()
        for flag in ("trainedModelUsed", "selectionVerified", "lineageVerified", "actualRL", "modelInvoked", "modelInvokedThisRequest", "threeLayersCovered"):
            bad = copy.deepcopy(request["rlEvidence"]); bad["scout"][flag] = False
            with self.subTest(flag=flag), self.assertRaises(StoryValidationError):
                canonical_rl_evidence(bad, request["story"])
        bad = copy.deepcopy(request["rlEvidence"]); bad["scout"]["invocationMode"] = "recorded_live_replay"
        with self.assertRaises(StoryValidationError):
            canonical_rl_evidence(bad, request["story"])

    def test_wrong_identity_statistical_period_source_and_display_are_rejected(self):
        request, _ = rl_fixture()
        changes = [(0, "playerId", "other"), (0, "gameId", "other-game"),
                   (2, "gameId", "game-test"), (2, "grain", "shot-event"), (1, "display", "99%"),
                   (0, "value", True), (0, "value", 1.5), (1, "value", 1.6),
                   (2, "unit", "fraction"), (1, "claimType", "official_fact"), (1, "evidenceId", "pts")]
        for index, key, value in changes:
            bad = copy.deepcopy(request["rlEvidence"]); bad["scout"]["evidence"][index][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(StoryValidationError):
                canonical_rl_evidence(bad, request["story"])
        for table, key, field, value in [("sources", "box", "url", "https://example.com/stats"),
                                         ("sources", "box", "sha256", "invalid"),
                                         ("periods", "season", "range", "full_completed_game")]:
            bad = copy.deepcopy(request["rlEvidence"]); bad[table][key][field] = value
            with self.subTest(field=field), self.assertRaises(StoryValidationError):
                canonical_rl_evidence(bad, request["story"])

    def test_missing_selected_layers_and_unselected_metrics_are_rejected(self):
        request, _ = rl_fixture()
        for metric in ("TS_PCT", "UNKNOWN"):
            bad = copy.deepcopy(request["rlEvidence"]); bad["scout"]["evidence"][1]["metric"] = metric
            with self.subTest(metric=metric), self.assertRaises(StoryValidationError):
                canonical_rl_evidence(bad, request["story"])
        bad = copy.deepcopy(request["rlEvidence"]); bad["scout"]["evidence"].pop()
        with self.assertRaises(StoryValidationError):
            canonical_rl_evidence(bad, request["story"])

    def test_model_cannot_omit_a_layer_or_rewrite_numbers_and_scopes(self):
        request, plan = rl_fixture()
        narratives = ["本场得分34分与效率补充背景，赛季防守关注仅作背景。",
                      "本场得分与效率使得赛季防守关注增加，仅作背景。",
                      "本场得分与效率补充背景；当前防守关注仅作背景。",
                      "本场得分与效率补充背景；赛季防守关注证明空间。"]
        for narrative in narratives:
            bad = copy.deepcopy(plan); bad["rlNarrative"] = narrative
            with self.subTest(narrative=narrative), self.assertRaises(StoryValidationError):
                validate_plan(bad, request["story"], request)
        bad = copy.deepcopy(plan); bad["rlEvidenceIds"] = ["pts", "efg", "other"]
        with self.assertRaises(StoryValidationError):
            validate_plan(bad, request["story"], request)

    def test_legacy_story_remains_unchanged_and_failsoft_omits_rl(self):
        request, plan = fixture()
        result, _, model = execute(request=request, plan=plan)
        self.assertNotIn("rlEvidence", result["plan"])
        self.assertNotIn("rlNarrative", model.calls[0]["toolConfig"]["tools"][-1]["toolSpec"]["inputSchema"]["json"]["properties"]["plan"]["required"])
        request["rlEvidence"] = {"scout": {"available": False}}
        self.assertNotIn("rlEvidence", validate_plan(plan, request["story"], request))

    def test_all_three_supported_focus_metrics_require_correct_scoped_narrative(self):
        request, plan = rl_fixture()
        for family, metric, unit, value, display, words in [
            ("leverage", "CREATION_LVG", "leverage_score", 1.77, "1.77", "创造机会影响力"),
            ("shotdifficulty", "AVGSHOTQUALITY", "fraction", .481, "48.10%", "出手机会质量"),
        ]:
            test_request, test_plan = copy.deepcopy(request), copy.deepcopy(plan)
            test_request["rlEvidence"]["scout"]["evidence"][2].update(family=family, metric=metric, unit=unit, value=value, display=display)
            test_plan["rlNarrative"] = f"本场得分与投篮效率补充比赛背景；赛季{words}仅作背景，不能解释此回合动作。"
            with self.subTest(family=family):
                accepted = validate_plan(test_plan, test_request["story"], test_request)
                self.assertEqual(accepted["rlEvidence"][2]["metric"], metric)


if __name__ == "__main__":
    unittest.main()
