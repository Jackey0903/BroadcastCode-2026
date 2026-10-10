"""Offline checks of the editorial extension's consequential timing guarantees."""
import unittest
from pathlib import Path
import tempfile
import wave
from unittest.mock import patch

import numpy as np

from broadcast_fx.audio import build_audio, splice_audio, tactical_sfx
from broadcast_fx.timeline import (
    FPS, FRAME_COUNT, LEGACY_FRAME_COUNT, TIMELINE, audio_insertions, frame_sample, locate_frame,
)


class TimelineTests(unittest.TestCase):
    def test_original_frames_survive_in_order(self):
        original = []
        for frame in range(FRAME_COUNT):
            segment, offset = locate_frame(frame)
            if segment.legacy_start is not None:
                original.append(segment.legacy_start + offset)
        self.assertEqual(original, list(range(LEGACY_FRAME_COUNT)))

    def test_live_source_has_no_skipped_or_repeated_frames(self):
        live = [6 + segment.local_start + offset for segment in TIMELINE if segment.name == "live"
                for offset in range(segment.count)]
        self.assertEqual(live, list(range(6, 1116)))
        for segment in TIMELINE:
            if segment.held_source_frame is not None:
                previous, offset = locate_frame(segment.start - 1)
                self.assertEqual(previous.name, "live")
                self.assertEqual(6 + previous.local_start + offset, segment.held_source_frame)
                following, offset = locate_frame(segment.end)
                self.assertEqual(6 + following.local_start + offset, segment.held_source_frame + 1)

    def test_timeline_is_contiguous_and_about_45_seconds(self):
        self.assertEqual(TIMELINE[0].start, 0)
        for left, right in zip(TIMELINE, TIMELINE[1:]):
            self.assertEqual(left.end, right.start)
        self.assertEqual(FRAME_COUNT, 2701)
        self.assertTrue(45 <= FRAME_COUNT / FPS < 45.1)
        with self.assertRaises(ValueError):
            locate_frame(-1)
        with self.assertRaises(ValueError):
            locate_frame(FRAME_COUNT)

    def test_audio_insertions_resume_without_drift(self):
        # A changing known signal catches off-by-one slicing and accidental time shifts.
        count = frame_sample(LEGACY_FRAME_COUNT)
        values = np.arange(count, dtype=np.float32) / count * .2
        original = np.column_stack((values, -values))
        result, metadata = splice_audio(original)
        self.assertEqual(len(result), frame_sample(FRAME_COUNT))
        self.assertEqual(metadata["sampleCount"], len(result))
        inserted = 0
        for insertion in audio_insertions():
            boundary = frame_sample(insertion["legacyFrame"])
            new_start = frame_sample(insertion["outputFrame"])
            added = frame_sample(insertion["outputFrame"] + insertion["frameCount"]) - new_start
            self.assertEqual(boundary + inserted, new_start)
            # 1000 samples clear the deliberate 480-sample edge fades.
            np.testing.assert_array_equal(result[new_start - 1000], original[boundary - 1000])
            np.testing.assert_array_equal(result[new_start + added + 1000], original[boundary + 1000])
            inserted += added
        self.assertEqual(len(result) - len(original), inserted)

    def test_sound_effect_is_finite_quiet_and_faded(self):
        effect = tactical_sfx(frame_sample(220))
        self.assertTrue(np.isfinite(effect).all())
        self.assertLess(float(np.abs(effect).max()), .25)
        self.assertGreater(float(np.abs(effect).max()), .01)
        np.testing.assert_array_equal(effect[0], [0, 0])
        np.testing.assert_array_equal(effect[-1], [0, 0])

    def test_truncated_original_audio_fails_instead_of_filling_silence(self):
        with self.assertRaises(ValueError):
            splice_audio(np.zeros((frame_sample(LEGACY_FRAME_COUNT) - 100, 2), np.float32))

    def test_fresh_workspace_can_find_its_packaged_audio_generator(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            source = work / "source.mp4"

            def generator(command, check):
                # The actual executable must exist, irrespective of its package layout.
                self.assertTrue(Path(command[1]).is_file())
                self.assertTrue(check)
                self.assertEqual(Path(command[2]), work)
                self.assertEqual(Path(command[3]), source)
                with wave.open(str(work / "out/audio.wav"), "wb") as stream:
                    stream.setnchannels(2)
                    stream.setsampwidth(2)
                    stream.setframerate(48000)
                    stream.writeframes(bytes(frame_sample(LEGACY_FRAME_COUNT) * 4))

            with patch("broadcast_fx.audio.subprocess.run", side_effect=generator) as called:
                result = build_audio(work, source, work / "final.wav")
            called.assert_called_once()
            self.assertEqual(result["sampleCount"], frame_sample(FRAME_COUNT))
            self.assertTrue((work / "final.wav").is_file())


if __name__ == "__main__":
    unittest.main()
