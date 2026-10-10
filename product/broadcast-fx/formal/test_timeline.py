"""Semantic tests for source coverage, replay timing and new-source-only audio."""
import tempfile
from pathlib import Path
import unittest

import numpy as np

try:
    from . import timeline as tl
    from . import audio
except ImportError:
    import timeline as tl
    import audio


class FormalTimelineTests(unittest.TestCase):
    def test_original_live_frames_preserved_once_in_order(self):
        actual = []
        for segment in tl.SEGMENTS:
            if segment['name'] == 'live':
                actual.extend(range(round(segment['sourceStart']), round(segment['sourceStart']) + segment['count']))
        self.assertEqual(actual, list(range(1424)))
        self.assertEqual(tl.FRAME_COUNT, 2710)
        self.assertAlmostEqual(float(tl.DURATION), 45.21183333333333)

    def test_boundaries_have_one_owner_and_valid_source_mapping(self):
        for frame in range(tl.FRAME_COUNT):
            segment, local = tl.locate_frame(frame)
            self.assertGreaterEqual(local, 0)
            self.assertLess(local, segment['count'])
            self.assertGreaterEqual(tl.source_frame_at(frame), 0)
            self.assertLess(tl.source_frame_at(frame), 1424)
        for bad in (-1, 2710, 1.5):
            with self.assertRaises(ValueError):
                tl.locate_frame(bad)

    def test_replay_is_contiguous_around_frozen_instant(self):
        first = next(s for s in tl.SEGMENTS if s['name'] == 'replay1')
        second = next(s for s in tl.SEGMENTS if s['name'] == 'replay2')
        metric = next(s for s in tl.SEGMENTS if s['name'] == 'metric')
        self.assertAlmostEqual(first['sourceStart'] / float(tl.FPS), 12)
        self.assertAlmostEqual(first['sourceStart'] + first['count'] * .5, second['sourceStart'])
        self.assertEqual(metric['sourceStart'], second['sourceStart'])
        self.assertEqual(metric['sourceRate'], 0)
        self.assertAlmostEqual(second['sourceStart'] / float(tl.FPS), 13.55155)
        self.assertAlmostEqual((second['sourceStart'] + second['count'] * .5) / float(tl.FPS), 15.25325)

    def test_audio_live_source_samples_continue_across_insertions(self):
        source_length = tl.frame_sample(1424)
        ramp = np.linspace(-.2, .2, source_length, dtype=np.float32)
        original = np.stack((ramp, -ramp), axis=1)
        slow = np.full((300000, 2), .03, np.float32)
        mixed, metadata = audio.assemble_audio(original, slow)
        self.assertEqual(mixed.shape, (tl.frame_sample(2710), 2))
        self.assertTrue(np.isfinite(mixed).all())
        live = [s for s in metadata['segments'] if s['name'] == 'live']
        self.assertEqual([s['sourceSampleStart'] for s in live], [0, tl.frame_sample(241), tl.frame_sample(720)])
        self.assertEqual([s['sourceSampleEndExclusive'] for s in live], [tl.frame_sample(241), tl.frame_sample(720), source_length])
        for s in live:
            offset = 5000  # Well away from the boundary fades.
            np.testing.assert_allclose(mixed[s['outputSample'] + offset], original[s['sourceSampleStart'] + offset] * .9)
        records = metadata['segments']
        self.assertEqual(sum(s['sampleCount'] for s in records), len(mixed))
        for a, b in zip(records, records[1:]):
            self.assertEqual(a['outputSample'] + a['sampleCount'], b['outputSample'])

    def test_wrong_source_rejected_before_media_decoding(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'unrelated.mp4'
            source.write_bytes(b'not-the-formal-clip')
            target = Path(folder) / 'audio.wav'
            with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
                audio.build_audio(source, target)
            self.assertFalse(target.exists())

    def test_truncated_broadcast_audio_is_not_silently_padded(self):
        with self.assertRaisesRegex(ValueError, 'shorter'):
            audio.assemble_audio(np.zeros((100, 2), np.float32), np.zeros((300000, 2), np.float32))


if __name__ == '__main__':
    unittest.main()
