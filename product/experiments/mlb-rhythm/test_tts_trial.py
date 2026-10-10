"""Offline regression checks. Generated fixture audio is not MiniMax speech."""
import io
import json
import tempfile
import unittest
import wave
from pathlib import Path

from tts_trial import ApiError, HERE, MiniMax, digest, duration, payload, read_json, schedule, settings, synthesize


def wav(seconds=1):
    stream = io.BytesIO()
    with wave.open(stream, 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(32000)
        audio.writeframes(b'\0\0' * round(32000 * seconds))
    return stream.getvalue()


class TrialTests(unittest.TestCase):
    def test_incomplete_json_retried_and_english_emotion_preserved(self):
        calls = []
        def interrupted(endpoint, request):
            calls.append(request)
            if len(calls) == 1:
                raise json.JSONDecodeError('fixture truncated response', '{', 1)
            return {'base_resp': {'status_code': 0}}
        plan = read_json(HERE / 'voice-plan-en.json')
        request = payload(plan['units'][0]['text'], plan, plan['voiceId'], 'English', 'surprised')
        client = MiniMax('test-only-key', 'https://api.minimax.cn/v1', interrupted, sleep=lambda _: None)
        client.call('t2a_v2', request)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[-1]['language_boost'], 'English')
        self.assertEqual(calls[-1]['voice_setting']['emotion'], 'surprised')

    def test_business_rate_limit_retried_but_auth_not_retried(self):
        calls = []
        def limited(endpoint, payload):
            calls.append(endpoint)
            return {'base_resp': {'status_code': 1002 if len(calls) == 1 else 0}}
        client = MiniMax('test-only-key', 'https://api.minimax.io/v1', limited, sleep=lambda _: None)
        self.assertEqual(client.call('t2a_v2', {})['base_resp']['status_code'], 0)
        self.assertEqual(len(calls), 2)
        calls.clear()
        def denied(endpoint, payload):
            calls.append(endpoint)
            return {'base_resp': {'status_code': 1004}}
        client.transport = denied
        with self.assertRaisesRegex(ApiError, '1004'):
            client.call('t2a_v2', {})
        self.assertEqual(len(calls), 1)

    def test_cache_skips_second_synthesis_and_recovers_corrupt_audio(self):
        calls, audio = [], wav()
        def transport(endpoint, payload):
            calls.append(endpoint)
            return {'base_resp': {'status_code': 0}, 'data': {'audio': audio.hex()}, 'trace_id': 'offline-fixture'}
        client = MiniMax('test-only-key', 'https://api.minimax.io/v1', transport)
        with tempfile.TemporaryDirectory() as folder:
            cache = Path(folder)
            path, meta, hit = synthesize(client, {'text': 'fixture'}, cache)
            self.assertFalse(hit)
            self.assertEqual(meta['durationSeconds'], 1)
            self.assertTrue(synthesize(client, {'text': 'fixture'}, cache)[2])
            self.assertEqual(len(calls), 1)
            self.assertNotIn('test-only-key', next(cache.glob('*.json')).read_text())
            # A valid WAV with a different hash must not masquerade as cached speech.
            path.write_bytes(wav(2))
            self.assertFalse(synthesize(client, {'text': 'fixture'}, cache)[2])
            self.assertEqual(len(calls), 2)

    def test_success_without_audio_fails_without_publishing(self):
        client = MiniMax('test-only-key', 'https://api.minimax.io/v1',
                         lambda *_: {'base_resp': {'status_code': 0}, 'data': {}})
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ApiError, 'without audio'):
                synthesize(client, {}, Path(folder))
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_hold_extension_retimes_every_following_cue(self):
        base = read_json(HERE / 'story-plan.json')
        plan = read_json(HERE / 'voice-plan.json')
        stages = {s['id']: s for s in base['segments']}
        records = [{'durationSeconds': sum(duration(stages[s]) for s in u['stages']) - .5,
                    'voiceId': plan['voiceId']} for u in plan['units']]
        original = schedule(base, plan, records)
        records[3]['durationSeconds'] += 1.5
        updated = schedule(base, plan, records)
        extension = updated['voice']['plannedDurationSeconds'] - original['voice']['plannedDurationSeconds']
        self.assertGreater(extension, 1.2)
        self.assertAlmostEqual(updated['voiceCues'][4]['start'] - original['voiceCues'][4]['start'], extension, places=5)
        self.assertEqual(base['segments'], read_json(HERE / 'story-plan.json')['segments'])

    def test_overflow_of_moving_scene_rejected(self):
        base, plan = read_json(HERE / 'story-plan.json'), read_json(HERE / 'voice-plan.json')
        records = [{'durationSeconds': 1, 'voiceId': plan['voiceId']} for _ in plan['units']]
        records[0]['durationSeconds'] = 5
        with self.assertRaisesRegex(ValueError, 'hook.*Shorten'):
            schedule(base, plan, records)

    def test_disjoint_groups_required(self):
        base, plan = read_json(HERE / 'story-plan.json'), read_json(HERE / 'voice-plan.json')
        plan['units'][1]['stages'] = ['hook']
        with self.assertRaisesRegex(ValueError, 'disjoint'):
            schedule(base, plan, [])


if __name__ == '__main__':
    unittest.main()
