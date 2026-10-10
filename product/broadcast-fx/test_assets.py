"""Guard the evidence boundaries most likely to be lost during asset reuse."""
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent


class EditorialAssetTests(unittest.TestCase):
    def test_preserved_assets_match_their_source_manifest(self):
        manifest = json.loads((ROOT / "data/manifest.json").read_text())
        for entry in manifest["files"]:
            content = (ROOT / "data" / entry["path"]).read_bytes()
            self.assertEqual(hashlib.sha256(content).hexdigest(), entry["sha256"], entry["path"])
        reviewed = json.loads((ROOT / "data/tactics_reviewed.json").read_text())
        self.assertEqual(reviewed["sourceSha256"], manifest["source"]["sha256"])

    def test_hidden_feet_are_never_presented_as_observed_contacts(self):
        scenes = json.loads((ROOT / "data/tactics_reviewed.json").read_text())["scenes"]
        for scene in scenes.values():
            self.assertEqual(len(scene["players"]), 10)
            for player in scene["players"]:
                self.assertFalse(player["humanExpertReviewed"])
                if player["anchorKind"] == "body-only":
                    self.assertIsNone(player["foot"])
                else:
                    self.assertEqual(player["foot"], player["image"])

    def test_official_shot_point_does_not_extend_editorial_movement(self):
        original = json.loads((ROOT / "data/tac/tactics.json").read_text())["T2"]
        active = json.loads((ROOT / "data/tactics_reviewed.json").read_text())["scenes"]["T2"]
        official = original["officialShot"]["court"]
        self.assertNotIn("officialShot", active)
        self.assertNotIn(official, active["paths"]["D32_drive"])
        self.assertNotIn("D3", [p["id"] for p in active["players"]])
        self.assertEqual(next(p for p in active["players"] if p["id"] == "D31")["number"], "31")


if __name__ == "__main__":
    unittest.main()
