"""Offline checks for the runtime RL-SCOUT client (fake model, no network)."""
import unittest

import scout_env as env
from scout_client import Scout
from test_scout_env import PROFILES, shot

OFFICIAL = {"shotDesc": "突破漂移跳投", "shotType": "2分投篮", "side": "right", "locX": "81", "locY": "58",
            "period": 3, "value": 0.445}


def tables():
    return env.References([shot(quality=0.4), shot(quality=0.6)], PROFILES).to_tables()


class Tables(unittest.TestCase):
    def test_round_trip_keeps_tool_outputs(self):
        refs = env.References([shot(quality=0.4), shot(quality=0.6)], PROFILES)
        again = env.References.from_tables(refs.to_tables())
        for name in env.TOOLS:
            self.assertEqual(refs.run(name, shot()), again.run(name, shot()))

    def test_official_row_mapping_and_prompt_layout(self):
        mapped = env.shot_from_official(OFFICIAL, 1641708)
        self.assertEqual((mapped["shotType"], mapped["zone"], mapped["playerId"]), ("2PT", "paint", "1641708"))
        text = env.render_qwen(env.first_messages(mapped))
        self.assertTrue(text.startswith("<|im_start|>system\n"))
        self.assertTrue(text.endswith("<|im_end|>\n<|im_start|>assistant\n"))
        self.assertNotIn("0.445", text)


class ScoutClient(unittest.TestCase):
    def test_tool_round_then_answer_and_delta(self):
        prompts = []
        replies = iter(['{"tools": ["zone_reference"]}', '{"quality": 0.55, "reason": "禁区均值0.500"}'])
        scout = Scout(lambda p: prompts.append(p) or next(replies), tables=tables(), model_name="test")
        result = scout.analyse(OFFICIAL, 1641708, official_quality=0.445)
        self.assertTrue(result["available"])
        self.assertEqual((result["typicalQuality"], result["toolsUsed"], result["difficultyDelta"], result["label"]),
                         (0.55, ["zone_reference"], -0.105, "tougher"))
        self.assertIn("区域参考", prompts[1])
        self.assertTrue(prompts[1].endswith("<|im_start|>assistant\n"))

    def test_direct_answer_without_official_value(self):
        scout = Scout(lambda p: '{"quality": 0.47, "reason": "常见"}', tables=tables())
        result = scout.analyse(OFFICIAL, 1641708)
        self.assertEqual(result["typicalQuality"], 0.47)
        self.assertNotIn("difficultyDelta", result)

    def test_interval_policy_uses_its_prompt_and_interval_label(self):
        data = dict(tables(), policy="v3")
        prompts = []
        replies = iter(['{"tools": ["zone_reference", "player_zone"]}',
                        '{"quality": 0.50, "low": 0.46, "high": 0.56, "reason": "禁区均值0.500"}'])
        try:
            scout = Scout(lambda p: prompts.append(p) or next(replies), tables=data, model_name="test-v3")
            result = scout.analyse(OFFICIAL, 1641708, official_quality=0.445)
        finally:
            env.use_reward("v1")
        self.assertIn('"low"', prompts[0])
        self.assertIn("球员区域", prompts[1])
        self.assertEqual((result["low"], result["high"], result["policy"]), (0.46, 0.56, "v3"))
        self.assertEqual((result["difficultyDelta"], result["label"]), (-0.055, "tougher"))  # below the interval

    def test_point_policy_ignores_interval_fields(self):
        scout = Scout(lambda p: '{"quality": 0.47, "low": 0.1, "high": 0.9, "reason": "常见"}', tables=tables())
        result = scout.analyse(OFFICIAL, 1641708, official_quality=0.445)
        env.use_reward("v1")
        self.assertNotIn("low", result)
        self.assertEqual((result["policy"], result["label"]), ("v2", "typical"))

    def test_failures_degrade_gracefully(self):
        def broken(_):
            raise TimeoutError("model cold start")
        self.assertEqual(Scout(broken, tables=tables()).analyse(OFFICIAL, 1)["available"], False)
        self.assertEqual(Scout(lambda p: "不知道", tables=tables()).analyse(OFFICIAL, 1)["available"], False)
        self.assertEqual(Scout(lambda p: '{"quality": 3}', tables=tables()).analyse(OFFICIAL, 1)["available"], False)


if __name__ == "__main__":
    unittest.main()
