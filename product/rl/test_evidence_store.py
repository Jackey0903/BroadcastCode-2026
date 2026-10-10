import copy
import unittest

import evidence_store as es


class EvidenceStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = es.build_store()

    def test_flagg_three_layers_and_event_are_separate(self):
        b = es.build_bundle(self.store, "1642843", "0022500701", 666)
        self.assertTrue(b["threeLayersAvailable"])
        self.assertFalse(b["trainedModelUsed"])
        self.assertEqual(b["event"]["xfg"], .51)
        by_metric = {r["metric"]: r for r in b["records"]}
        self.assertEqual(by_metric["PTS"]["value"], 34)
        self.assertEqual(by_metric["EFG_PCT"]["value"], .54)
        self.assertAlmostEqual(by_metric["TS_PCT"]["value"], 34 / (2 * (25 + .44 * 10)))
        self.assertEqual(by_metric["EFG_PCT"]["grain"], "player-game")
        self.assertEqual(by_metric["OFF_BALL_PERIM_GRAV"]["grain"], "player-season")

    def test_wrong_event_cannot_substitute_another_players_fact(self):
        with self.assertRaises(ValueError):
            es.build_bundle(self.store, "1642843", "0022500491", 396)

    def test_missing_gravity_is_not_zero(self):
        result = es.query(self.store, "1629655", ["gravity"])
        self.assertEqual(result["records"], [])
        self.assertEqual(result["missing"][0]["reasonCode"], "family_unavailable")

    def test_dnp_and_bad_source_minutes_do_not_create_efficiency(self):
        records = self.store["records"]
        dnp = {(r["playerId"], r["gameId"]) for r in records if r.get("participation") != "played" and r["family"] == "basic"}
        self.assertTrue(dnp)
        self.assertFalse(any((r["playerId"], r["gameId"]) in dnp for r in records if r["family"] == "advanced"))
        self.assertTrue(any(r["reasonCode"] == "source_duration_not_standard_mm_ss" for r in self.store["unavailable"]))

    def test_modified_values_fail_content_verification(self):
        altered = copy.deepcopy(self.store)
        altered["records"][0]["value"] = 10000
        with self.assertRaises(ValueError):
            es.validate_store(altered)


if __name__ == "__main__":
    unittest.main()
