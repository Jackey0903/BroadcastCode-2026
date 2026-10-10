"""Small regression set for reward correctness, leakage boundaries and runtime refusal."""
import json
import unittest

import scout_env as env
from scout_client import Scout
from test_scout_env import shot
from test_scout_client import OFFICIAL


class JointScoutTests(unittest.TestCase):
    def setUp(self):
        env.use_reward('v4')

    def tearDown(self):
        env.use_reward('v1')

    def test_joint_reference_keeps_interaction_and_roundtrips(self):
        rows = [shot(quality=.3, shotDesc='跳投') for _ in range(20)]
        rows += [shot(quality=.8, shotDesc='上篮') for _ in range(20)]
        refs = env.References(rows, {'secret': {'AVGSHOTQUALITY': .99}})
        self.assertEqual(refs.baseline_zone(shot()), .55)
        values, _ = refs.situation_values(shot(shotDesc='跳投'))
        self.assertEqual(values, (.3, 20, .3, .3, .3))
        self.assertIn('回退区域', refs.situation_values(shot())[1])
        tables = refs.to_tables()
        self.assertEqual(tables['profiles'], {})
        self.assertEqual(refs.situation_reference(shot(shotDesc='跳投')),
                         env.References.from_tables(tables).situation_reference(shot(shotDesc='跳投')))

    def test_two_team_universe_excludes_opponents_even_in_focus_games(self):
        rows = [shot(teamId=tid, focus=True) for tid in (1610612742, 1610612745, 1610612738)]
        self.assertEqual(len(env.select_universe(rows, 'two-teams')), 2)
        self.assertEqual(len(env.select_universe(rows, 'all')), 3)

    def test_crossfit_is_whole_game_and_hidden_targets_stay_hidden(self):
        a = shot(gameId='test-game', eventId=1, quality=.987)
        b = shot(gameId='test-game', eventId=2, quality=.123)
        self.assertEqual(env.reference_fold(a), env.reference_fold(b))
        self.assertNotIn('0.987', env.observation(a))
        self.assertEqual(env.parse_action('{"tools":["player_profile"]}')[0], 'invalid')
        self.assertIn('situation_reference', env.TOOLS)

    def test_affine_scores_do_not_saturate_and_invalid_is_worse(self):
        answer = {'quality': .1, 'low': .05, 'high': .15, 'reason': '联合参考'}
        near = env.reward(answer, .8, [], False, '')
        far = env.reward(answer, 1., [], False, '')
        self.assertLess(far['interval'], near['interval'])
        self.assertLess(far['calibration'], 0)
        self.assertLess(far['interval'], 0)
        self.assertLess(env.reward(None, 1., [], True, '')['total'], far['total'])
        for bad in [dict(answer, low=.2), dict(answer, quality=True), dict(answer, high=float('nan')),
                    dict(answer, extra='x'), dict(answer, reason='')]:
            self.assertEqual(env.reward(bad, .5, [], False, '')['total'], -2.)
        self.assertEqual(env.reward(answer, .1, ['unknown'], True, '')['total'], -2.)

    def test_missing_answers_do_not_improve_all_episode_error(self):
        good = dict(env.reward({'quality': .4, 'low': .3, 'high': .6, 'reason': '参考'}, .5, [], False, ''), quality=.5)
        missing = dict(env.reward(None, .5, [], True, ''), quality=.5)
        result = env.summarize([good, missing])
        self.assertEqual((result['mae'], result['allEpisodeMAE'], result['validRate']), (.1, .55, .5))
        self.assertEqual(env.parse_action('文字 {"tools":["zone_reference"]}')[0], 'invalid')

    def test_comparison_uses_requested_denominator(self):
        from compare_results import summarize_on, index
        a, b = ('g', 'p', '1'), ('g', 'p', '2')
        truth = {a: {'quality': .5}, b: {'quality': .8}}
        rows = {a: {'quality': .5, 'prediction': .4, 'format': 1., 'tools': ['zone_reference']}}
        result = summarize_on([a, b], rows, truth)
        self.assertEqual((result['episodes'], result['validRate'], result['allEpisodeMAE']), (2, .5, .55))
        rows[a]['quality'] = .3
        with self.assertRaises(ValueError):
            summarize_on([a], rows, truth)
        with self.assertRaises(ValueError):
            index([{'gameId': 'g', 'playerId': 'p', 'eventId': 1}] * 2)

    def test_runtime_requires_interval_and_preserves_its_own_policy(self):
        tables = dict(env.References([shot()], {}).to_tables(), policy='v4')
        scout = Scout(lambda _: '{"quality":0.4,"reason":"参考"}', tables=tables)
        self.assertFalse(scout.analyse(OFFICIAL, 1)['available'])
        replies = iter(['{"tools":["situation_reference"]}',
                        '{"quality":0.5,"low":0.4,"high":0.6,"reason":"联合参考"}'])
        scout = Scout(lambda _: next(replies), tables=tables)
        env.use_reward('v2')  # another client must not change this scout's protocol
        result = scout.analyse(OFFICIAL, 1, .445)
        self.assertTrue(result['available'])
        self.assertEqual((result['policy'], result['pointStatistic'], result['label']),
                         ('v4', 'conditional_median', 'typical'))


if __name__ == '__main__':
    unittest.main()
