"""Guard formal-only source coverage, animation duration and missing ball arcs."""
import unittest
import numpy as np

from broadcast_fx import legacy
from formal import audio, timeline as previous
from formal_v2_timeline import SEGMENTS, FRAME_COUNT, DURATION, frame_sample, locate_frame
import formal_v2_render as renderer


class FormalV2Tests(unittest.TestCase):
    def test_full_source_preserved_once_and_edit_meets_requested_duration(self):
        live = []
        for segment in SEGMENTS:
            if segment['name'] == 'live':
                live.extend(range(round(segment['sourceStart']), round(segment['sourceStart']) + segment['count']))
        self.assertEqual(live, list(range(1424)))
        self.assertTrue(54.5 <= DURATION <= 55.5)
        self.assertEqual(FRAME_COUNT, 3300)
        self.assertEqual(previous.FRAME_COUNT, 2710)
        old = dict(legacy.SEGMENTS)
        for name in ('intro', 'outro'):
            self.assertEqual(next(s['count'] for s in SEGMENTS if s['name'] == name), old[name])
        for frame in range(FRAME_COUNT):
            segment, local = locate_frame(frame)
            self.assertGreaterEqual(segment['sourceStart'] + local * segment['sourceRate'], 0)
            self.assertLess(segment['sourceStart'] + local * segment['sourceRate'], 1424)

    def test_audio_covers_new_pauses_and_preserves_live_sample_continuity(self):
        source = np.zeros((frame_sample(1424), 2), np.float32)
        slow = np.zeros((frame_sample(390), 2), np.float32)
        mixed, record = audio.assemble_audio(source, slow, SEGMENTS, FRAME_COUNT)
        self.assertEqual(len(mixed), frame_sample(FRAME_COUNT))
        self.assertEqual(sum(s['sampleCount'] for s in record['segments']), len(mixed))
        live = [s for s in record['segments'] if s['name'] == 'live']
        self.assertEqual(live[0]['sourceSampleStart'], 0)
        self.assertEqual(live[-1]['sourceSampleEndExclusive'], frame_sample(1424))
        for left, right in zip(live, live[1:]):
            self.assertEqual(left['sourceSampleEndExclusive'], right['sourceSampleStart'])

    def test_formal_identity_does_not_borrow_legacy_points_or_hidden_ball_arc(self):
        renderer.init('product/build/formal-video')
        self.assertEqual(renderer.OUTRO['points'], renderer.base.OFFICIAL['shot']['points'])
        self.assertEqual(renderer.OUTRO['pointsLabel'], '本球得分')
        self.assertEqual(renderer.base.OFFICIAL['eventId'], 273)
        self.assertNotIn(854, legacy.BALL)  # Ball is out of frame at 14.25 s.
        self.assertIn(809, legacy.BALL)
        self.assertIn(869, legacy.BALL)
        scene = renderer.second_chance_scene()
        self.assertEqual(scene['frame'], 480)
        self.assertEqual(scene['players'][0]['anchorKind'], 'body-only')


if __name__ == '__main__':
    unittest.main()
