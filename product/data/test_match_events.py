"""Offline evidence-boundary tests against the two actual NBA source snapshots."""
import copy
import json
import unittest
from pathlib import Path
from match_events import bind_clip, clock_seconds, InvalidEvidence

HERE = Path(__file__).resolve().parent
SOURCES = HERE.parent / 'research/sources'
load = lambda p: json.loads(p.read_text())
ANCHORS = {a['sample']: a for a in load(HERE / 'video-anchors.json')['anchors']}


def fixture(sample):
    return (load(SOURCES / f'nba-page-{sample}.json'), load(SOURCES / f'gpshot-{sample}.json'), copy.deepcopy(ANCHORS[sample]))


def target(page, sample):
    number = 666 if sample == 'flagg' else 396
    return next(a for a in page['playByPlay']['actions'] if a['actionNumber'] == number and a['isFieldGoal'] == 1)


class RealEvidenceTests(unittest.TestCase):
    def test_both_real_bindings(self):
        for sample, event, action_id, expected in [('flagg',666,498,.51), ('amen',396,285,.445)]:
            with self.subTest(sample=sample):
                result = bind_clip(*fixture(sample))
                self.assertTrue(result['verified'], result)
                self.assertEqual(result['matched']['eventId'], event)
                self.assertEqual(result['matched']['actionId'], action_id)
                self.assertEqual(result['matched']['expectedFg'], expected)
                self.assertTrue(all(result['candidates'][0]['checks'].values()))

    def test_action_id_must_not_be_used_as_event_id(self):
        for sample in ('flagg','amen'):
            with self.subTest(sample=sample):
                page, shots, anchor = fixture(sample)
                row = target(page, sample)
                shot = next(s for s in shots['data']['shotList'] if s['eventId'] == row['actionNumber'])
                shot['eventId'] = row['actionId']
                self.assertFalse(bind_clip(page,shots,anchor)['verified'])

    def test_wrong_game_player_period_or_result_never_passes(self):
        for field, value in [('gameId','0022500000'),('playerId','1642843'),('period',4),('success',0),('shotType','3分投篮')]:
            with self.subTest(field=field):
                page, shots, anchor = fixture('amen')
                shot = next(s for s in shots['data']['shotList'] if s['eventId'] == 396)
                shot[field] = value
                self.assertFalse(bind_clip(page,shots,anchor)['verified'])

    def test_source_team_and_jersey_conflicts(self):
        for field, value in [('teamId',1610612742),('jerseyNumber','7')]:
            with self.subTest(field=field):
                page, shots, anchor = fixture('amen')
                anchor[field] = value
                self.assertFalse(bind_clip(page,shots,anchor)['verified'])

    def test_wrong_pbp_result_player_or_period(self):
        for field, value in [('shotResult','Missed'),('personId',1642843),('period',4),('shotValue',3)]:
            with self.subTest(field=field):
                page, shots, anchor = fixture('amen')
                target(page,'amen')[field] = value
                self.assertFalse(bind_clip(page,shots,anchor)['verified'])

    def test_score_delta_alone_is_not_enough(self):
        # Same +2 change, wrong absolute score: must disagree with official PBP.
        page, shots, anchor = fixture('flagg')
        anchor['scoreBefore']['away'] = 101
        anchor['scoreAfter']['away'] = 103
        self.assertFalse(bind_clip(page,shots,anchor)['verified'])

    def test_opponent_score_change_and_wrong_delta_rejected(self):
        for side in ('home','away'):
            with self.subTest(side=side):
                page, shots, anchor = fixture('flagg')
                anchor['scoreAfter'][side] += 1
                self.assertFalse(bind_clip(page,shots,anchor)['verified'])

    def test_previous_official_score_required(self):
        page, shots, anchor = fixture('amen')
        actions = page['playByPlay']['actions']
        index = actions.index(target(page,'amen'))
        for row in actions[:index]:
            row['scoreHome'] = row['scoreAway'] = ''
        self.assertFalse(bind_clip(page,shots,anchor)['verified'])

    def test_clock_window_must_include_event(self):
        page, shots, anchor = fixture('amen')
        anchor['clipClockStartSeconds'] = 440
        anchor['clipClockEndSeconds'] = 435
        self.assertFalse(bind_clip(page,shots,anchor)['verified'])

    def test_missing_anchor_fields_do_not_get_inferred(self):
        for field in ('scoreBefore','scoreAfter','clipClockStartSeconds','period','made','annotationMethod'):
            with self.subTest(field=field):
                page, shots, anchor = fixture('flagg')
                del anchor[field]
                self.assertFalse(bind_clip(page,shots,anchor)['verified'])

    def test_missing_source_fields_do_not_get_filled_from_other_source(self):
        for field in ('clock','actionNumber','shotResult','scoreHome','shotValue'):
            with self.subTest(field=field):
                page, shots, anchor = fixture('amen')
                del target(page,'amen')[field]
                self.assertFalse(bind_clip(page,shots,anchor)['verified'])

    def test_duplicate_pbp_or_shot_event_is_ambiguous(self):
        for source in ('pbp','shot'):
            with self.subTest(source=source):
                page, shots, anchor = fixture('amen')
                if source == 'pbp':
                    row = copy.deepcopy(target(page,'amen'))
                    row['teamId'] = 1610612742  # conflicting duplicate cannot be silently ignored
                    page['playByPlay']['actions'].append(row)
                else:
                    row = next(s for s in shots['data']['shotList'] if s['eventId'] == 396)
                    shots['data']['shotList'].append(copy.deepcopy(row))
                self.assertFalse(bind_clip(page,shots,anchor)['verified'])

    def test_missing_out_of_range_or_nonfinite_metric_rejected(self):
        for value in (None, -0.1, 1.01, float('nan'), float('inf'), '0.445', True):
            with self.subTest(value=value):
                page, shots, anchor = fixture('amen')
                next(s for s in shots['data']['shotList'] if s['eventId'] == 396)['value'] = value
                self.assertFalse(bind_clip(page,shots,anchor)['verified'])

    def test_pbp_block_row_sharing_action_number_is_not_a_shot_candidate(self):
        page, shots, anchor = fixture('flagg')
        # Actual source event 667 occurs in both a shot row and a block row.
        rows = [a for a in page['playByPlay']['actions'] if a['actionNumber'] == 667]
        self.assertGreaterEqual(len(rows),2)
        self.assertEqual(sum(a['isFieldGoal'] == 1 for a in rows),1)
        self.assertTrue(bind_clip(page,shots,anchor)['verified'])

    def test_clock_parser_rejects_missing_and_unrecognized(self):
        self.assertEqual(clock_seconds('PT07M25.00S'),445)
        for value in ('','7:25',None,'PT07M60S'):
            with self.subTest(value=value), self.assertRaises(InvalidEvidence):
                clock_seconds(value)

    def test_stories_preserve_metric_identity_and_valid_evidence_graph(self):
        for story in load(HERE/'stories.json')['stories']:
            with self.subTest(story=story['id']):
                evidence = {e['id']:e for e in story['evidence']}
                metric = story['shotMetric']; official = story['officialEvent']; metric_evidence = evidence[metric['evidenceId']]
                self.assertTrue(official['verified'])
                self.assertEqual(metric['rawValue'],official['expectedFg'])
                self.assertEqual(metric['rawValue'],metric_evidence['value'])
                self.assertEqual(metric['sourceUrl'],metric_evidence['sourceUrl'])
                for key in ('gameId','eventId','playerId'):
                    self.assertEqual(metric[key],official[key])
                    self.assertEqual(metric[key],metric_evidence[key])
                self.assertEqual(metric_evidence['kind'],'official')
                self.assertEqual(metric['unit'],'ratio')
                self.assertEqual(metric['display'],format(metric['rawValue'],'.1%'))
                choices = story['hook']['choices']
                self.assertEqual({c['id'] for c in choices},{o['id'] for o in story['storyOptions']})
                self.assertEqual(len({c['revealBody'] for c in choices}),len(choices))
                self.assertEqual(len({c['focusTime'] for c in choices}),len(choices))
                self.assertFalse(story['hook']['isQuiz'])
                for item in choices+story['chapters']:
                    self.assertLessEqual(set(item['evidenceIds']),evidence.keys())
                for item in story['evidence']:
                    self.assertTrue(0 <= item.get('videoTime',0) < story['durationSeconds'])


if __name__ == '__main__':
    unittest.main()
