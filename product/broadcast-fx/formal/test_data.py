"""Reject stale event data and fabricated visibility in the formal edit.

These checks validate input evidence. They do not certify the rendered frames,
human basketball judgment, cloud deployment, or actual Agent execution.
"""
import hashlib
import json
from pathlib import Path
import re
import unittest

try:
    from . import timeline as tl
except ImportError:
    import timeline as tl


HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
ROOT = HERE.parents[2]


def load(name):
    return json.loads((DATA / name).read_text())


class FormalEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.official = load("official.json")
        cls.page = load("nba-page-christie.json")
        cls.gpshot = load("gpshot-christie.json")["data"]
        cls.annotations = load("annotations.json")

    def test_all_sources_bind_to_new_video_and_game(self):
        expected = "f2c0fb6aa1ec10bd78ea9e6724190b7f03bf48f21af2f743c694bbdb49254c91"
        self.assertEqual(tl.SOURCE_SHA256, expected)
        self.assertEqual(self.official["sourceVideo"]["sha256"], expected)
        self.assertEqual(self.annotations["sourceSha256"], expected)
        for game_id in (self.official["game"]["gameId"], self.page["game"]["gameId"],
                        self.gpshot["gameId"]):
            self.assertEqual(game_id, "0022500356")
        self.assertEqual(self.page["game"]["homeTeamId"], 1610612742)
        self.assertEqual(self.page["game"]["awayTeamId"], 1610612745)

    def test_local_video_hash_when_media_is_present(self):
        source = ROOT / "data" / "正式视频.mp4"
        if not source.exists():
            self.skipTest("Formal source media is intentionally excluded from Git")
        with source.open("rb") as stream:
            self.assertEqual(hashlib.file_digest(stream, "sha256").hexdigest(), tl.SOURCE_SHA256)

    def test_event_273_joins_by_action_number_and_player_not_action_id(self):
        event = self.official["eventId"]
        self.assertEqual(event, 273)
        rows = [a for a in self.page["playByPlay"]["actions"]
                if a["actionNumber"] == event and a["isFieldGoal"] == 1]
        shots = [s for s in self.gpshot["shotList"] if s["eventId"] == event]
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(shots), 1)
        row, shot = rows[0], shots[0]
        self.assertNotEqual(row["actionId"], event)
        self.assertEqual(row["personId"], 1631108)
        self.assertEqual(str(row["personId"]), shot["playerId"])
        self.assertEqual((row["period"], shot["period"]), (2, 2))
        self.assertEqual((row["shotValue"], row["shotResult"], shot["success"]), (3, "Made", 1))
        self.assertEqual(self.official["shot"]["rawPbp"], row)
        self.assertEqual(self.official["shot"]["rawGpShot"], shot)

    def test_thirty_percent_is_this_shots_value_not_a_summary(self):
        shot = next(s for s in self.gpshot["shotList"] if s["eventId"] == 273)
        self.assertEqual(shot["value"], .3)
        self.assertEqual(self.official["shot"]["xfg"], shot["value"])
        self.assertEqual(self.official["shot"]["xfgPercent"], shot["value"] * 100)
        self.assertNotEqual(shot["value"], self.gpshot["shotQuality"])
        self.assertNotEqual(shot["value"], self.gpshot["avgShotQuality"])
        first = next(s for s in self.gpshot["shotList"] if s["eventId"] == 270)
        self.assertNotEqual(shot["value"], first["value"])
        self.assertNotEqual(shot["value"], .51)

    def test_clip_score_does_not_include_offscreen_free_throw(self):
        score = self.official["score"]
        made = self.official["shot"]["rawPbp"]
        self.assertEqual(score["before"], {"HOU": 44, "DAL": 40})
        self.assertEqual(score["afterMadeThree"], {"HOU": 44, "DAL": 43})
        self.assertEqual(score["afterMadeThree"],
                         {"HOU": int(made["scoreAway"]), "DAL": int(made["scoreHome"])})
        self.assertFalse(score["laterFreeThrowVisibleInSource"])
        self.assertEqual(score["afterLaterFreeThrow"], {"HOU": 44, "DAL": 44})
        free_throw = next(a for a in self.official["chain"] if a["actionNumber"] == 276)
        self.assertEqual(free_throw["actionType"], "Free Throw")
        self.assertGreater(free_throw["actionNumber"], made["actionNumber"])

    def test_rebound_is_not_relabelled_as_an_assist(self):
        chain = self.official["chain"]
        rebound = next(a for a in chain if a["actionNumber"] == 272)
        self.assertEqual(rebound["personId"], 203939)
        self.assertEqual(rebound["actionType"], "Rebound")
        self.assertIn("Off:1", rebound["description"])
        self.assertFalse(self.official["shot"]["assist"]["credited"])
        self.assertNotIn("AST", self.official["shot"]["rawPbp"]["description"])
        block = next(a for a in chain if a["actionNumber"] == 270 and a["personId"] == 1631095)
        self.assertIn("BLOCK", block["description"])
        self.assertEqual(self.official["foul"]["eventId"], 274)

    def test_source_snapshots_still_match_recorded_hashes(self):
        for source in self.official["sources"]:
            with self.subTest(source=source["path"]):
                self.assertEqual(hashlib.sha256((DATA / source["path"]).read_bytes()).hexdigest(),
                                 source["sha256"])

    def test_nine_visible_players_do_not_include_referee_or_invent_tenth(self):
        for key, scene in self.annotations["scenes"].items():
            with self.subTest(scene=key):
                players = scene["players"]
                self.assertEqual(scene["visiblePlayerCount"], 9)
                self.assertEqual(len(players), 9)
                self.assertEqual(len({p["id"] for p in players}), 9)
                self.assertEqual(sum(p["team"] == "offense" for p in players), 4)
                self.assertEqual(sum(p["team"] == "defense" for p in players), 5)
                self.assertTrue(any(e["kind"] == "referee" for e in scene["excluded"]))
                self.assertTrue(all("referee" not in p["role"] for p in players))

    def test_hidden_feet_remain_null_and_body_anchors_stay_distinct(self):
        width, height = self.annotations["canvas"]
        for scene in self.annotations["scenes"].values():
            for player in scene["players"]:
                with self.subTest(scene=scene["key"], player=player["id"]):
                    self.assertFalse(player["humanExpertReviewed"])
                    self.assertIn("editorial", player["positionBasis"])
                    if player["anchorKind"] == "visible-foot":
                        self.assertIsNotNone(player["foot"])
                        self.assertEqual(player["image"], player["foot"])
                    else:
                        self.assertEqual(player["anchorKind"], "body-only")
                        self.assertIsNone(player["foot"])
                        self.assertEqual(player["image"], player["body"])
                    for point in (player["body"], player["foot"]):
                        if point is not None:
                            self.assertEqual(len(point), 2)
                            self.assertTrue(0 <= point[0] < width and 0 <= point[1] < height)

    def test_jersey_number_is_not_role_or_a_fabricated_unknown_number(self):
        known = {team: {p["jerseyNum"] for p in roster}
                 for team, roster in self.official["onscreenPlayerRoster"].items()}
        for scene in self.annotations["scenes"].values():
            for player in scene["players"]:
                with self.subTest(scene=scene["key"], player=player["id"]):
                    number, role = player["number"], player["role"]
                    self.assertIsInstance(role, str)
                    self.assertFalse(role.isdigit())
                    self.assertIsInstance(player["numberVisible"], bool)
                    if number is None:
                        self.assertFalse(player["numberVisible"])
                    else:
                        self.assertIsInstance(number, str)
                        self.assertRegex(number, re.compile(r"^\d{1,2}$"))
                        team = "DAL" if player["team"] == "offense" else "HOU"
                        self.assertIn(number, known[team])
                        self.assertNotEqual(number, role)

    def test_tactical_freezes_use_the_exact_annotated_source_frames(self):
        self.assertEqual(set(self.annotations["scenes"]), {"T1", "T2"})
        for key, scene in self.annotations["scenes"].items():
            segment = next(s for s in tl.SEGMENTS if s["name"] == key)
            with self.subTest(scene=key):
                self.assertEqual(segment["sourceRate"], 0)
                self.assertEqual(segment["sourceStart"], scene["frame"])
                self.assertAlmostEqual(scene["sourceSeconds"], scene["frame"] / float(tl.FPS))
                self.assertEqual(tl.source_frame_at(segment["start"]), scene["frame"])
                self.assertEqual(tl.source_frame_at(segment["start"] + segment["count"] - 1), scene["frame"])


if __name__ == "__main__":
    unittest.main()
