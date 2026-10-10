"""Offline checks for the RL-SCOUT environment and verifiable reward (no torch, no network)."""
import unittest

import scout_env as env


def shot(**overrides):
    base = {"gameId": "0022500100", "gameDate": "2025-12-01", "playerId": "201142", "teamId": 1610612745,
            "eventId": 10, "shotDesc": "突破漂移跳投", "shotType": "2PT", "side": "right", "locX": 81.0,
            "locY": 58.0, "period": 3, "distanceFt": 12.3, "zone": "paint", "made": 1, "quality": 0.45,
            "focus": True, "h2h": False}
    base.update(overrides)
    return base


PROFILES = {"201142": {"AVGSHOTQUALITY": 0.433, "AVGSHOTQUALITY2PT": 0.474, "AVGSHOTQUALITY3PT": 0.351,
                       "FGPCTABOVEEXPECTED": 0.087, "AVGDEFENDERBALLDISTANCE": 31.8,
                       "AVGDEFENDERPRESSURESCORE": 0.865}}


class Geometry(unittest.TestCase):
    def test_known_official_samples(self):
        three = env.shot_geometry(69, 63, "right", True)
        self.assertAlmostEqual(three["distanceFt"], 24.7, delta=0.2)
        self.assertEqual(three["zone"], "above_break3")
        self.assertEqual(env.shot_geometry(93, 48, "right", False)["zone"], "restricted")
        self.assertEqual(env.shot_geometry(90, 94, "right", True)["zone"], "corner3")

    def test_left_and_right_are_mirrored(self):
        right = env.shot_geometry(76, 40, "right", False)
        left = env.shot_geometry(24, 40, "left", False)
        self.assertEqual(right, left)


class Split(unittest.TestCase):
    def test_head_to_head_and_practice_games_never_train(self):
        self.assertEqual(env.held_out(shot(h2h=True)), "h2h")
        self.assertEqual(env.held_out(shot(gameId="0022500491", h2h=False)), "h2h")
        self.assertEqual(env.held_out(shot(gameId="0022500701", h2h=False)), "h2h")

    def test_focus_games_train_at_any_date_and_league_tail_is_held_out(self):
        self.assertIsNone(env.held_out(shot(gameDate="2026-03-20", focus=True)))
        self.assertEqual(env.held_out(shot(gameDate="2026-03-20", focus=False)), "league")
        self.assertIsNone(env.held_out(shot(gameDate="2026-01-20", focus=False)))

    def test_references_use_training_split_only(self):
        rows = [shot(quality=0.4), shot(quality=0.6), shot(h2h=True, quality=0.99)]
        train, test = env.split(rows)
        refs = env.References(train, PROFILES)
        self.assertEqual(len(test), 1)
        self.assertEqual(refs.baseline_zone(rows[0]), 0.5)
        self.assertNotIn("0.99", refs.zone_reference(rows[0]))


class Observation(unittest.TestCase):
    def test_policy_never_sees_the_label_or_the_result(self):
        text = env.observation(shot(quality=0.437, made=1))
        self.assertNotIn("0.437", text)
        self.assertNotIn("命中", text)
        self.assertIn("突破漂移跳投", text)

    def test_tools_report_unavailable_data_honestly(self):
        refs = env.References([shot()], PROFILES)
        self.assertIn("不可用", refs.player_profile(shot(playerId="999")))
        self.assertIn("样本不足", refs.move_reference(shot()))
        self.assertIn("0.433", refs.player_profile(shot()))


class Actions(unittest.TestCase):
    def test_tool_requests(self):
        self.assertEqual(env.parse_action('{"tools": ["zone_reference", "zone_reference"]}'),
                         ("tools", ["zone_reference"], True))
        self.assertEqual(env.parse_action('好的 {"tools": ["move_reference", "player_profile"]}'),
                         ("tools", ["move_reference", "player_profile"], False))
        self.assertEqual(env.parse_action('{"tools": ["weather"]}')[0], "invalid")
        self.assertEqual(env.parse_action('{"tools": []}')[0], "invalid")

    def test_malformed_tool_lists_are_invalid_not_fatal(self):
        self.assertEqual(env.parse_action('{"tools": [{"name": "zone_reference"}]}'), ("invalid", None, True))
        self.assertEqual(env.parse_action('{"tools": ["zone_reference", {"x": 1}, 3]}'), ("tools", ["zone_reference"], True))
        self.assertEqual(env.parse_action('{"tools": [["zone_reference"]]}'), ("invalid", None, True))

    def test_answers_and_garbage(self):
        kind, payload, invalid = env.parse_action('{"quality": 0.42, "reason": "禁区两分"}')
        self.assertEqual((kind, payload["quality"], invalid), ("answer", 0.42, False))
        self.assertEqual(env.parse_action("我觉得大概四成")[0], "invalid")
        self.assertEqual(env.parse_action('{"quality": 0.4')[0], "invalid")


class Reward(unittest.TestCase):
    CONTEXT = env.observation(shot()) + "\n区域参考：禁区·两分，联盟平均官方质量 0.465（训练样本 1085 次）"

    def test_perfect_grounded_answer(self):
        parts = env.reward({"quality": 0.45, "reason": "禁区均值0.465"}, 0.45, ["zone_reference"], False, self.CONTEXT)
        self.assertEqual((parts["calibration"], parts["format"], parts["grounded"]), (1.0, 1.0, 1.0))
        self.assertAlmostEqual(parts["total"], 1.0 - env.TOOL_COST, places=4)

    def test_calibration_is_linear_in_absolute_error_and_floored(self):
        near = env.reward({"quality": 0.55, "reason": "接近均值"}, 0.45, [], False, self.CONTEXT)
        far = env.reward({"quality": 0.95, "reason": "很好"}, 0.45, [], False, self.CONTEXT)
        self.assertAlmostEqual(near["calibration"], 1 - 0.1 / env.CALIBRATION_SCALE, places=6)
        self.assertAlmostEqual(far["calibration"], 0.0, places=9)

    def test_useful_extra_tool_can_pay_for_itself(self):
        one = env.reward({"quality": 0.36, "reason": "x"}, 0.45, ["zone_reference"], False, "")
        two = env.reward({"quality": 0.38, "reason": "x"}, 0.45, ["zone_reference", "player_profile"], False, "")
        self.assertGreater(two["total"], one["total"])

    def test_v2_pays_for_the_small_gain_of_a_second_reference(self):
        # The move table improves the zone-only estimate by ~0.005 MAE; v1 punished fetching it.
        def gain(version):
            env.use_reward(version)
            one = env.reward({"quality": 0.405, "reason": "x"}, 0.45, ["zone_reference"], False, "")
            two = env.reward({"quality": 0.41, "reason": "x"}, 0.45, ["zone_reference", "move_reference"], False, "")
            return two["total"] - one["total"]
        try:
            self.assertLess(gain("v1"), 0)
            self.assertGreater(gain("v2"), 0)
            self.assertEqual((env.REWARD_VERSION, env.TOOL_COST), ("v2", 0.002))
        finally:
            env.use_reward("v1")
        self.assertEqual((env.REWARD_VERSION, env.TOOL_COST, env.CALIBRATION_SCALE), ("v1", 0.01, 0.5))

    def test_invented_numbers_are_not_grounded(self):
        parts = env.reward({"quality": 0.45, "reason": "防守人距离3.2英尺"}, 0.45, [], False, self.CONTEXT)
        self.assertEqual(parts["grounded"], 0.0)
        own = env.reward({"quality": 0.45, "reason": "估计45%"}, 0.45, [], False, self.CONTEXT)
        self.assertEqual(own["grounded"], 1.0)

    def test_format_and_invalid_penalties(self):
        self.assertEqual(env.reward(None, 0.4, [], True, "")["total"], -env.INVALID_PENALTY)
        out_of_range = env.reward({"quality": 1.4, "reason": "x"}, 0.4, [], False, "")
        self.assertEqual((out_of_range["calibration"], out_of_range["format"], out_of_range["prediction"]), (0.0, 0.0, None))
        extra = env.reward({"quality": 0.4, "reason": "x", "note": "y"}, 0.4, [], False, "")
        self.assertEqual(extra["format"], 0.0)
        bad_tool = env.reward({"quality": 0.4, "reason": "x"}, 0.4, ["zone_reference"], True, "")
        self.assertLess(bad_tool["total"], env.reward({"quality": 0.4, "reason": "x"}, 0.4, ["zone_reference"], False, "")["total"])

    def test_summary(self):
        rows = [dict(env.reward({"quality": q, "reason": "x"}, 0.5, [], False, ""), quality=0.5) for q in (0.4, 0.7)]
        summary = env.summarize(rows)
        self.assertEqual((summary["episodes"], summary["answered"], summary["mae"]), (2, 2, 0.15))


class IntervalScout(unittest.TestCase):
    """Reward v3: point estimate + central 60% interval scored by the (proper) interval score."""

    def setUp(self):
        env.use_reward("v3")

    def tearDown(self):
        env.use_reward("v1")

    def test_spec_switches_prompt_tools_and_weights(self):
        self.assertIn("player_zone", env.TOOLS)
        self.assertIn('"low"', env.SYSTEM_PROMPT)
        self.assertEqual(env.parse_action('{"tools": ["player_zone"]}'), ("tools", ["player_zone"], False))
        self.assertAlmostEqual(sum(env.WEIGHTS.values()), 1.0)
        env.use_reward("v2")
        self.assertNotIn("player_zone", env.TOOLS)
        self.assertEqual(env.parse_action('{"tools": ["player_zone"]}'), ("invalid", None, True))
        self.assertNotIn('"low"', env.SYSTEM_PROMPT)

    def test_interval_reward_and_ordering(self):
        good = env.reward({"quality": 0.45, "low": 0.40, "high": 0.50, "reason": "x"}, 0.47, [], False, "")
        self.assertEqual((good["format"], good["low"], good["high"]), (1.0, 0.4, 0.5))
        self.assertAlmostEqual(good["intervalScore"], 0.10, places=6)
        self.assertAlmostEqual(good["interval"], 1 - 0.10 / env.INTERVAL_SCALE, places=6)
        missed = env.reward({"quality": 0.45, "low": 0.40, "high": 0.50, "reason": "x"}, 0.60, [], False, "")
        self.assertAlmostEqual(missed["intervalScore"], 0.10 + (2 / 0.4) * 0.10, places=6)
        disordered = env.reward({"quality": 0.45, "low": 0.50, "high": 0.40, "reason": "x"}, 0.47, [], False, "")
        self.assertEqual((disordered["format"], disordered["interval"], disordered["low"]), (0.0, 0.0, None))
        self.assertGreater(disordered["calibration"], 0.9)  # the point estimate still counts
        point_only = env.reward({"quality": 0.45, "reason": "x"}, 0.47, [], False, "")
        self.assertLess(point_only["total"], good["total"])

    def test_interval_score_rewards_true_percentiles_over_wide_or_narrow(self):
        values = [i / 100 for i in range(20, 81)]  # uniform 0.20..0.80 → true q20 = 0.32, q80 = 0.68
        mean_score = lambda lo, hi: sum(env.interval_score(lo, hi, v) for v in values) / len(values)
        true = mean_score(0.32, 0.68)
        self.assertLess(true, mean_score(0.20, 0.80))  # too wide
        self.assertLess(true, mean_score(0.45, 0.55))  # too narrow
        self.assertLess(true, mean_score(0.40, 0.76))  # shifted

    def test_tools_report_bands_only_for_the_interval_spec(self):
        rows = [shot(quality=q / 100) for q in range(30, 70)]
        refs = env.References(rows, PROFILES)
        self.assertIn("中间 60% 区间", refs.run("zone_reference", shot()))
        self.assertIn("球员区域：该球员在禁区·两分的平均官方质量", refs.run("player_zone", shot()))
        self.assertIn("样本不足", refs.run("player_zone", shot(playerId="999")))
        again = env.References.from_tables(refs.to_tables())
        for name in env.TOOLS:
            self.assertEqual(refs.run(name, shot()), again.run(name, shot()))
        env.use_reward("v2")
        self.assertNotIn("区间", refs.run("zone_reference", shot()))

    def test_interval_numbers_are_grounded_and_summarised(self):
        parts = env.reward({"quality": 0.45, "low": 0.40, "high": 0.52, "reason": "区间0.40到0.52"}, 0.47, [], False, "")
        self.assertEqual(parts["grounded"], 1.0)
        rows = [dict(env.reward({"quality": 0.45, "low": 0.4, "high": 0.5, "reason": "x"}, y, [], False, ""), quality=y)
                for y in (0.45, 0.6)]
        summary = env.summarize(rows)
        self.assertEqual((summary["coverage"], summary["intervalRate"], summary["width"]), (0.5, 1.0, 0.1))


if __name__ == "__main__":
    unittest.main()
