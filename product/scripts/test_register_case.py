"""Internal case registration tests; synthetic media is not contest acceptance."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from register_case import RegistrationError, probe_video, register_case
from readiness_agent import PROTOCOL, validate_request
from story_contract import validate_story_source


class RegistrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.video = self.root / 'contest.mp4'
        self.video.write_bytes(b'\x00\x00\x00\x18ftypisom-source-fixture')
        self.story = {'storyOptions': [{'id': 'observed-play'}], 'evidence': [],
                      'officialEvent': {'verified': False}}
        self.base = {'version': 'base', 'stories': [{'id': 'existing', 'evidence': []}]}
        self.manifest = {'existing': {'video': {'id': 'existing'}}}

    def probe(self, path):
        return {'durationSeconds': 2.0, 'width': 1280, 'height': 720, 'hasAudio': True}

    def extract(self, source, target, output):
        output.write_bytes(b'\xff\xd8\xffsynthetic-frame\xff\xd9')
        return {'timestampSeconds': target + .1, 'timestampSource': 'synthetic_test_double'}

    def register(self, **changes):
        args = dict(sample='formal-01', bucket='formal-controlled-bucket', video_path=self.video,
            story=self.story, frame_times=[0, 1], output_dir=self.root / 'bundle',
            existing_manifest=self.manifest, existing_stories=self.base, probe=self.probe, extractor=self.extract)
        args.update(changes)
        return register_case(**args)

    def test_new_case_passes_existing_agent_contract_and_preserves_snapshot(self):
        before = copy.deepcopy((self.story, self.base, self.manifest))
        result = self.register()
        case = result['manifest']['formal-01']
        request = {'protocol_version': PROTOCOL, 'request_id': 'new-case', **case}
        validate_request(request, 'formal-controlled-bucket')
        validate_story_source(result['stories']['stories'][-1], request)
        self.assertEqual(case['frames'][0]['timestamp_ms'], 100)
        self.assertEqual(case['frames'][1]['timestamp_ms'], 1100)
        self.assertEqual((self.story, self.base, self.manifest), before)
        self.assertEqual(result['stories']['stories'][0], self.base['stories'][0])
        self.assertNotIn('shotMetric', result['stories']['stories'][-1])
        self.assertFalse(result['receipt']['newInference'])
        self.assertFalse(result['receipt']['cloudPublished'])

    def test_publication_plan_is_portable_hashed_and_needs_no_historical_output(self):
        result = self.register()
        bundle = self.root / 'bundle'
        plan = json.loads((bundle / 'publication-plan.json').read_text())
        keys = [asset['key'] for asset in plan['assets']]
        self.assertIn('config/samples.json', keys)
        self.assertIn('product/config/samples.json', keys)
        self.assertIn('product/data/stories.json', keys)
        self.assertFalse(any('outputs/' in key for key in keys))
        for asset in plan['assets']:
            body = (bundle / asset['file']).read_bytes()
            self.assertEqual(hashlib.sha256(body).hexdigest(), asset['sha256'])
            self.assertEqual(len(body), asset['bytes'])
        self.assertEqual((bundle / 'source.mp4').read_bytes(), self.video.read_bytes())
        self.assertEqual(result['receipt']['source']['sha256'], hashlib.sha256(self.video.read_bytes()).hexdigest())

    def test_unsafe_id_unknown_metric_and_source_conflicts_are_rejected(self):
        for changes in ({'sample': '../other'}, {'sample': '_budget'}, {'bucket': 'bad..bucket'},
                        {'story': {**self.story, 'shotMetric': {'rawValue': .5}}},
                        {'story': {**self.story, 'id': 'other'}},
                        {'story': {**self.story, 'sourceVideoSha256': 'a' * 64}},
                        {'story': {**self.story, 'durationSeconds': 8}},
                        {'story': {**self.story, 'officialEvent': {'verified': 'true'}}}):
            with self.subTest(changes=changes), self.assertRaises(RegistrationError):
                self.register(**changes)
        self.assertFalse((self.root / 'bundle').exists())

    def test_existing_case_or_destination_cannot_be_overwritten(self):
        with self.assertRaises(RegistrationError):
            self.register(sample='existing')
        result = self.register()
        original = (self.root / 'bundle' / 'registration.json').read_bytes()
        with self.assertRaises(RegistrationError):
            self.register()
        self.assertEqual((self.root / 'bundle' / 'registration.json').read_bytes(), original)
        self.assertEqual(result['manifest']['existing'], self.manifest['existing'])

    def test_requested_and_actual_times_images_and_short_clip_limits_are_checked(self):
        for times in ([0, 0], [], list(range(7)), [-1], [2], [float('nan')]):
            with self.subTest(times=times), self.assertRaises(RegistrationError):
                self.register(frame_times=times)
        for media in ({'durationSeconds': 61, 'width': 1280, 'height': 720},
                      {'durationSeconds': 2, 'width': 1280.0, 'height': 720}):
            with self.assertRaises(RegistrationError):
                self.register(probe=lambda path, media=media: media)
        def duplicate(source, target, output):
            output.write_bytes(b'\xff\xd8\xffsynthetic\xff\xd9')
            return {'timestampSeconds': 1.5}
        with self.assertRaises(RegistrationError):
            self.register(extractor=duplicate)
        def bad_image(source, target, output):
            output.write_bytes(b'not-a-jpeg')
            return {'timestampSeconds': target}
        with self.assertRaises(RegistrationError):
            self.register(extractor=bad_image)
        self.assertFalse((self.root / 'bundle').exists())

    def test_host_probe_errors_are_explicit_without_a_real_binary(self):
        with patch('register_case.shutil.which', return_value=None):
            with self.assertRaisesRegex(RegistrationError, 'Local ffprobe is required'):
                probe_video(self.video)
        # Even valid-looking JSON must not override a failed media probe.
        response = subprocess.CompletedProcess([], 1, stdout=b'{"streams":[],"format":{}}', stderr=b'bad media')
        with patch('register_case.shutil.which', return_value='/mock/ffprobe'), \
             patch('register_case.subprocess.run', return_value=response):
            with self.assertRaisesRegex(RegistrationError, 'could not measure'):
                probe_video(self.video)


if __name__ == '__main__':
    unittest.main()
