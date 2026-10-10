"""Offline guarantees for live RL cards, scope labels and rendering receipts."""

import copy
import json
from pathlib import Path
import sys
import unittest

PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT / "agent"))
from rl_render import add_rl_filters, _narrative_lines
from story_contract import StoryValidationError


def fixture():
    # Recorded service data are a deterministic test fixture, never billed or
    # represented by these tests as a new request or a successfully made movie.
    payload = json.loads((PRODUCT / "rl/results/product-integration/flagg-live-20261010.json").read_text())
    return {"video": {"duration_ms": 21548.118},
            "officialEvent": {"playerId": payload["playerId"], "gameId": payload["gameId"]},
            "rlEvidence": {key: copy.deepcopy(payload[key]) for key in ("scout", "sources", "periods")},
            "plan": {"rlEvidenceIds": [row["evidenceId"] for row in payload["scout"]["evidence"]],
                     "rlNarrative": "本场得分与效率呈现赛后表现，赛季无球外线引力仅作背景。"}}


class RLRenderTests(unittest.TestCase):
    def prepare(self, result=None):
        filters, labels = ["original_filter"], []

        def label(name, value, x, y, size, color, enable):
            labels.append({"name": name, "text": value, "x": x, "y": y,
                           "size": size, "color": color, "enable": enable})

        receipt = add_rl_filters(filters, label, fixture() if result is None else result)
        return receipt, filters, labels

    def test_cards_preserve_exact_values_and_statistics_scope(self):
        receipt, _, labels = self.prepare()
        text = {row["name"]: row["text"] for row in labels}
        self.assertEqual(text["rl-card-0"], "全场得分  34 分")
        self.assertEqual(text["rl-card-1"], "全场 eFG  54.00%")
        self.assertEqual(text["rl-card-2"], "无球外线引力  6.217")
        self.assertIn("赛后统计", text["rl-scope-0"])
        self.assertIn("由官方计数计算", text["rl-scope-1"])
        self.assertEqual(text["rl-scope-2"], "2025–26赛季 · 深度背景，非本回合实测")
        self.assertEqual(receipt["evidenceIds"], fixture()["plan"]["rlEvidenceIds"])
        self.assertEqual(len(receipt["sourceRefs"]), 2)
        self.assertEqual(len(receipt["periodRefs"]), 2)

    def test_movie_completion_is_not_claimed_by_prepared_filters(self):
        receipt, _, labels = self.prepare()
        self.assertTrue(receipt["prepared"])
        self.assertTrue(receipt["narrativeIncluded"])
        self.assertFalse(receipt["burnedIntoVideo"])
        self.assertFalse(receipt["narrativeUsed"])
        self.assertTrue(receipt["contextOnly"])
        self.assertEqual(receipt["narrativeText"], fixture()["plan"]["rlNarrative"])
        self.assertEqual("".join(row["text"] for row in labels if row["name"].startswith("rl-narrative-")),
                         fixture()["plan"]["rlNarrative"])

    def test_header_never_overlaps_source_picture_or_official_xfg(self):
        receipt, filters, labels = self.prepare()
        self.assertEqual(filters[0], "original_filter")
        bounds = receipt["headerBounds"]
        self.assertLess(bounds["x"] + bounds["width"], 912)
        self.assertLess(bounds["y"] + bounds["height"], 76)
        for row in labels:
            self.assertLessEqual(row["y"] + row["size"], 68)
            self.assertLess(row["x"], 890)
        self.assertEqual({row["text"] for row in labels if row["name"] in ("rl-brand", "rl-badge", "rl-model")},
                         {"GameBuddy", "RL 数据球探", "AWS SageMaker · 3B"})

    def test_stages_follow_original_clock_without_overlap_or_added_duration(self):
        receipt, _, _ = self.prepare()
        windows = receipt["stagedWindows"]
        self.assertEqual(windows[0]["start"], 0)
        self.assertEqual(windows[-1]["end"], 21.548118)
        for left, right in zip(windows, windows[1:]):
            self.assertEqual(left["end"], right["start"])
            self.assertGreater(left["end"], left["start"])
        self.assertAlmostEqual(windows[-1]["end"] - windows[-1]["start"], 4)

    def test_replay_unavailable_or_missing_live_flags_add_no_badge(self):
        cases = [{}, {"rlEvidence": {"scout": {"available": False}}}]
        for field, value in (("invocationMode", "recorded_live_replay"), ("actualRL", False),
                             ("lineageVerified", False), ("modelInvokedThisRequest", False)):
            case = fixture()
            case["rlEvidence"]["scout"][field] = value
            cases.append(case)
        for case in cases:
            with self.subTest(case=case.get("rlEvidence", {}).get("scout", {}).get("invocationMode")):
                receipt, filters, labels = self.prepare(case)
                self.assertFalse(receipt["prepared"])
                self.assertEqual(filters, ["original_filter"])
                self.assertEqual(labels, [])

    def test_live_identity_or_source_mismatch_fails_closed(self):
        for mutate in (lambda case: case["officialEvent"].update(playerId="other"),
                       lambda case: next(iter(case["rlEvidence"]["sources"].values())).update(sha256="invalid"),
                       lambda case: case["rlEvidence"]["scout"]["evidence"][2].update(grain="player-game")):
            case = fixture()
            mutate(case)
            with self.assertRaises(StoryValidationError):
                self.prepare(case)

    def test_narrative_requires_selected_evidence_and_explicit_background_scope(self):
        for mutate in (lambda case: case["plan"].update(rlEvidenceIds=["invented"]),
                       lambda case: case["plan"].update(rlNarrative="他本回合引力说明防守被吸引。")):
            case = fixture()
            mutate(case)
            with self.assertRaises(StoryValidationError):
                self.prepare(case)

    def test_invalid_or_too_short_source_duration_does_not_add_filters(self):
        for value in (None, True, float("nan"), -1, 5000):
            case = fixture()
            case["video"]["duration_ms"] = value
            with self.assertRaises(ValueError):
                self.prepare(case)

    def test_narrative_wrapping_keeps_all_original_text(self):
        original = "本" * 100
        lines = _narrative_lines(original)
        self.assertEqual("".join(lines), original)
        self.assertEqual([len(line) for line in lines], [34, 34, 32])


if __name__ == "__main__":
    unittest.main()
