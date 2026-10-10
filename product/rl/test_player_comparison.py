import copy
import unittest

import evidence_store as es
import player_comparison as pc


class PlayerComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = es.load_store()

    def test_same_game_comparison_uses_percentage_points_and_keeps_sources(self):
        result = pc.compare_players(self.store, "1642843", "1641708", "0022500701")
        delta = next(r for r in result["comparisons"] if r["metric"] == "EFG_PCT")
        self.assertAlmostEqual(delta["difference"], 7.333333333333333)
        self.assertEqual(delta["differenceUnit"], "percentage_points")
        self.assertEqual(len(delta["evidenceIds"]), 2)
        profile = result["left"]
        ast = next(r for r in profile["derived"] if r["metric"] == "GAME_AST_TOV")
        gap = next(r for r in profile["derived"] if r["metric"] == "SEASON_FG_VS_EXPECTED_PP")
        self.assertEqual(ast["value"], 2.5)
        self.assertAlmostEqual(gap["value"], -1.3)
        self.assertFalse(result["trainedModelUsed"])
        self.assertFalse(result["matchupVerified"])

    def test_zero_turnovers_are_not_infinity_or_zero_ratio(self):
        profile = pc.build_player_profile(self.store, "1641708", "0022500701")
        ratio = next(r for r in profile["derived"] if r["metric"] == "GAME_AST_TOV")
        self.assertFalse(ratio["available"])
        self.assertIsNone(ratio["value"])
        self.assertEqual(ratio["reasonCode"], "zero_denominator")
        self.assertEqual([r["value"] for r in ratio["operands"]], [9, 0])

    def test_event_shooter_and_opponent_do_not_imply_defender_or_on_court(self):
        result = pc.build_story_context(self.store, "flagg", "1641708")
        self.assertEqual(result["event"]["eventId"], 666)
        self.assertFalse(result["defenderIdentity"]["verified"])
        self.assertIsNone(result["defenderIdentity"]["playerId"])
        self.assertTrue(all(p["team"] == "HOU" and not p["onCourtAtEventVerified"] for p in result["opponentChoices"]))
        with self.assertRaises(ValueError):
            pc.build_story_context(self.store, "flagg", "1642843")
        with self.assertRaises(ValueError):
            pc.build_story_context(self.store, "unknown")

    def test_dnp_missing_game_and_missing_depth_stay_unavailable(self):
        with self.assertRaises(ValueError):
            pc.build_player_profile(self.store, "201145", "0022500701")
        with self.assertRaises(ValueError):
            pc.build_player_profile(self.store, "1642843", "missing")
        profile = pc.build_player_profile(self.store, "203991", "0022500701")
        self.assertIn("AVGSHOTQUALITY", profile["missingMetrics"])
        self.assertEqual(profile["sections"]["seasonShooting"], [])

    def test_pressure_is_shooter_context_and_store_is_unchanged(self):
        original = copy.deepcopy(self.store)
        profile = pc.build_player_profile(self.store, "1642843", "0022500701")
        pressure = next(r for r in profile["facts"] if r["metric"] == "AVGDEFENDERPRESSURESCORE")
        self.assertIn(pressure["evidenceId"], profile["sections"]["seasonShooting"])
        self.assertNotIn(pressure["evidenceId"], profile["sections"]["seasonDefense"])
        self.assertEqual(self.store, original)

    def test_different_snapshot_is_not_compared_and_tampering_is_rejected(self):
        store = copy.deepcopy(self.store)
        row = next(r for r in store["records"] if r["playerId"] == "1641708" and r["metric"] == "DEF_LVG")
        row["source"]["sha256"] = "different_snapshot"
        row["evidenceId"] = es.record_id(row)
        store["contentSha256"] = es.sha({k: v for k, v in store.items() if k != "contentSha256"})
        result = pc.compare_players(store, "1642843", "1641708", "0022500701")
        self.assertFalse(any(r["metric"] == "DEF_LVG" for r in result["comparisons"]))
        self.assertIn({"metric": "DEF_LVG", "reasonCode": "incompatible_scope_or_source_snapshot"}, result["unavailable"])
        row["value"] = 100
        with self.assertRaises(ValueError):
            pc.build_player_profile(store, "1641708", "0022500701")


if __name__ == "__main__":
    unittest.main()
