"""Offline verified publication tests; tiny fixtures, no AWS or actual media."""
import copy
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'agent'))
from readiness_agent import PROTOCOL, validate_request
from publication import (FRAME_NAMES, WEB_FILES, PublicationError, build_plan, publish_plan)
from serve import SOURCES

OWNER = '555726205424'
BUCKET = 'new-formal-product-bucket'
WEBSITE = 'https://new-formal.cloudfront.net'


def sha(body):
    return hashlib.sha256(body).hexdigest()


class FakeS3:
    def __init__(self):
        self.objects, self.puts, self.reads = {}, [], []

    def put_object(self, **request):
        assert request['ExpectedBucketOwner'] == OWNER
        assert request['Bucket'] == BUCKET
        self.objects[request['Key']] = copy.deepcopy(request)
        self.puts.append(request['Key'])

    def head_object(self, **request):
        assert request['ExpectedBucketOwner'] == OWNER
        self.reads.append(request['Key'])
        stored = self.objects[request['Key']]
        return {'ContentLength': len(stored['Body']), 'Metadata': stored['Metadata']}

    def get_object(self, **request):
        assert request['ExpectedBucketOwner'] == OWNER
        self.reads.append(request['Key'])
        return {'Body': io.BytesIO(self.objects[request['Key']]['Body'])}


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.s3 = FakeS3()
        self.stories, self.reports, metadata, frames = [], {}, {}, []
        for number, (sample, relative) in enumerate(SOURCES.items()):
            original = b'\x00\x00\x00\x18ftypisom' + sample.encode() + b'-source-fixture'
            enhanced = b'\x00\x00\x00\x18ftypisom' + sample.encode() + b'-enhanced-fixture'
            job = ('a' if number == 0 else 'b') * 32
            self.write(relative, original)
            self.write(f'product/build/verified/{job}/enhanced.mp4', enhanced)
            metadata[relative] = {'streams': [{'codec_type': 'video', 'codec_name': 'h264', 'width': 1920, 'height': 1080},
                                             {'codec_type': 'audio'}],
                                  'format': {'duration': '22', 'size': str(len(original))}}
            evidence = []
            for suffix in FRAME_NAMES[sample]:
                name = f'{sample}-{suffix}.jpg'
                relative_image = 'data/reference/frames/' + name
                image = b'\xff\xd8' + name.encode() + b'\xff\xd9'
                self.write(relative_image, image)
                frames.append({'sample': sample, 'file': relative_image, 'sha256': sha(image),
                               'bytes': len(image), 'videoTime': float(suffix[:-1])})
                evidence.append({'id': name, 'frameUrl': '/frames/' + name, 'kind': 'edited'})
            self.stories.append({'id': sample, 'sample': sample, 'durationSeconds': 22,
                'sourceVideoSha256': sha(original), 'sourceVideo': f'/samples/{sample}.mp4',
                'showcaseJobId': job, 'showcaseOutputSha256': sha(enhanced),
                'enhancedVideo': f'https://old.cloudfront.net/product/outputs/{job}/enhanced.mp4',
                'analysisUrl': f'https://old.cloudfront.net/product/outputs/{job}/analysis.json',
                'poster': evidence[0]['frameUrl'], 'evidence': evidence,
                'officialEvent': {'expectedFg': .51}, 'chapters': [{'start': 15, 'end': 22}]})
            analysis = {'protocol_version': 'product-story-v1', 'runId': job, 'sample': sample,
                'preservesSourceTimeline': True, 'runtimeArn': 'arn:aws:bedrock-agentcore:us-east-1:962768510637:runtime/historical',
                'trace': [{'tool': 'read_official_event', 'result': {'expectedFg': .51}}],
                'sourceVideo': {'id': sample, 'sha256': sha(original), 'duration_ms': 22000},
                'outputVideo': {'sha256': sha(enhanced), 'bytes': len(enhanced), 'durationMs': 22000}}
            report = {'jobId': job, 'sample': sample, 'mode': 'story', 'outputSha256': sha(enhanced),
                'bytes': len(enhanced), 'durationSeconds': 22, 'analysis': analysis,
                'contentReview': {'acceptedForShowcase': True}, 'verifiedAt': '2026-10-07T12:04:29+00:00',
                'videoUrl': self.stories[-1]['enhancedVideo'], 'analysisUrl': self.stories[-1]['analysisUrl']}
            self.reports[sample] = report
            self.save(f'product/evidence/run-{job}.json', report)
        self.save('data/reference/train-video-metadata.json', metadata)
        self.save('product/research/frame-provenance.json', {'frames': frames})
        self.save('product/data/stories.json', {'stories': self.stories})
        for name in ('event-bindings.json', 'video-anchors.json'):
            self.save('product/data/' + name, {'scope': 'practice'})
        for name in WEB_FILES:
            self.write('product/web/' + name, b'public-static-fixture')

    def tearDown(self):
        self.temp.cleanup()

    def write(self, name, body):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)

    def save(self, name, value):
        self.write(name, json.dumps(value, ensure_ascii=False).encode())

    def plan(self):
        return build_plan(self.root, BUCKET, WEBSITE)

    def report_path(self, sample='amen'):
        return f"product/evidence/run-{self.reports[sample]['jobId']}.json"

    def test_full_initializes_empty_bucket_with_both_configs_and_every_url_dependency(self):
        plan = self.plan()
        uploaded = publish_plan(plan, self.s3, OWNER)
        self.assertFalse(self.s3.reads)  # No old bucket/config assumptions.
        self.assertEqual(uploaded[-1], 'product/data/stories.json')
        configs = [json.loads(self.s3.objects[key]['Body']) for key in ('config/samples.json', 'product/config/samples.json')]
        self.assertEqual(configs[0], configs[1])
        self.assertEqual(set(configs[0]), {'flagg', 'amen'})
        for sample, item in configs[0].items():
            self.assertEqual(item['video']['s3_uri'], f's3://{BUCKET}/samples/{sample}.mp4')
            self.assertEqual(len(item['frames']), 6)
            for frame in item['frames']:
                self.assertIn(frame['s3_uri'].split(BUCKET + '/', 1)[1], uploaded)
        self.assertFalse(any('court-lab' in key or key.startswith('api/jobs') for key in uploaded))

    def test_current_presentation_urls_and_history_markers_do_not_change_original_evidence(self):
        original = {name: (self.root / name).read_bytes() for name in ('product/data/stories.json', self.report_path())}
        assets = {a.key: a for a in self.plan().assets}
        document = json.loads(assets['product/data/stories.json'].body)
        self.assertTrue(document['publication']['historical'])
        for story in document['stories']:
            self.assertTrue(story['publication']['historical'])
            self.assertFalse(story['publication']['newInference'])
            self.assertTrue(story['enhancedVideo'].startswith(WEBSITE + '/product/outputs/'))
            self.assertTrue(story['sourceVideo'].startswith(WEBSITE + '/samples/'))
            self.assertTrue(story['poster'].startswith(WEBSITE + '/frames/'))
            self.assertEqual(story['officialEvent'], {'expectedFg': .51})
            self.assertEqual(story['chapters'], [{'start': 15, 'end': 22}])
            analysis = json.loads(assets[f"product/outputs/{story['showcaseJobId']}/analysis.json"].body)
            history = analysis.pop('publication')
            self.assertEqual(analysis, self.reports[story['id']]['analysis'])
            self.assertTrue(history['historical'])
            self.assertIn('old.cloudfront.net', history['originalVideoUrl'])
        self.assertTrue(all((self.root / name).read_bytes() == body for name, body in original.items()))

    def test_generated_configs_satisfy_actual_agent_input_contract(self):
        assets = {a.key: a for a in self.plan().assets}
        for sample, item in json.loads(assets['product/config/samples.json'].body).items():
            request = validate_request({'protocol_version': PROTOCOL, 'request_id': 'publication-' + sample,
                                        **item}, BUCKET)
            self.assertIsInstance(request['video']['width'], int)
            self.assertIsInstance(request['video']['height'], int)
            self.assertEqual(len(request['frames']), 6)
            self.assertEqual(request['video']['sha256'], item['video']['sha256'])

    def test_missing_second_original_fails_before_any_writes(self):
        (self.root / SOURCES['amen']).unlink()
        with self.assertRaisesRegex(PublicationError, 'Missing or unsafe'):
            self.plan()
        self.assertFalse(self.s3.puts)

    def test_missing_historical_output_evidence_or_dense_frame_fails_before_writes(self):
        for name in [f"product/build/verified/{self.reports['amen']['jobId']}/enhanced.mp4",
                     self.report_path(), 'data/reference/frames/amen-17.5s.jpg']:
            file = self.root / name
            body = file.read_bytes()
            file.unlink()
            with self.subTest(name=name), self.assertRaisesRegex(PublicationError, 'Missing or unsafe'):
                self.plan()
            self.assertFalse(self.s3.puts)
            file.write_bytes(body)

    def test_corrupt_source_enhanced_or_anchor_is_rejected(self):
        paths = [SOURCES['amen'], f"product/build/verified/{self.reports['amen']['jobId']}/enhanced.mp4",
                 'data/reference/frames/amen-17.5s.jpg']
        for name in paths:
            file = self.root / name
            body = file.read_bytes()
            with self.subTest(name=name):
                file.write_bytes(body + b'corrupt')
                with self.assertRaisesRegex(PublicationError, 'SHA-256'):
                    self.plan()
                file.write_bytes(body)
                self.assertFalse(self.s3.puts)

    def test_unaccepted_or_mismatched_historical_evidence_is_rejected(self):
        for field, value in [('contentReview', {'acceptedForShowcase': False}), ('sample', 'flagg'), ('outputSha256', '0' * 64)]:
            report = copy.deepcopy(self.reports['amen'])
            report[field] = value
            self.save(self.report_path(), report)
            with self.subTest(field=field), self.assertRaises(PublicationError):
                self.plan()
        self.assertFalse(self.s3.puts)

    def test_size_or_timeline_metadata_conflicts_are_rejected(self):
        for field, value in [('bytes', 999), ('durationSeconds', 25)]:
            report = copy.deepcopy(self.reports['amen'])
            report[field] = value
            self.save(self.report_path(), report)
            with self.subTest(field=field), self.assertRaises(PublicationError):
                self.plan()

    def test_symlink_in_original_or_frontend_never_enters_plan(self):
        for name in [SOURCES['amen'], 'product/web/app.js']:
            file = self.root / name
            body = file.read_bytes()
            target = self.root / 'innocent.txt'
            target.write_bytes(body)
            file.unlink(); file.symlink_to(target)
            with self.subTest(name=name), self.assertRaisesRegex(PublicationError, 'unsafe'):
                self.plan()
            file.unlink(); file.write_bytes(body)

    def test_only_allowed_static_assets_are_published_and_secret_content_is_rejected(self):
        self.write('product/web/.env', b'do-not-publish')
        self.write('product/web/unregistered.json', b'{"private":"do-not-publish"}')
        self.assertFalse(any('.env' in a.key or 'unregistered' in a.key for a in self.plan().assets))
        self.write('product/web/app.js', b'const access = "' + b'AK' + b'IA' + b'Z' * 16 + b'";')
        with self.assertRaisesRegex(PublicationError, 'secret'):
            self.plan()
        self.assertFalse(self.s3.puts)

    def test_web_only_missing_prerequisite_has_zero_writes(self):
        with self.assertRaisesRegex(PublicationError, 'prerequisite'):
            publish_plan(self.plan(), self.s3, OWNER, web_only=True)
        self.assertFalse(self.s3.puts)

    def test_partial_prerequisites_missing_second_config_or_analysis_have_zero_writes(self):
        plan = self.plan()
        publish_plan(plan, self.s3, OWNER)
        for key in ['product/config/samples.json', f"product/outputs/{self.reports['amen']['jobId']}/analysis.json"]:
            stored = self.s3.objects.pop(key)
            self.s3.puts.clear()
            with self.subTest(key=key), self.assertRaisesRegex(PublicationError, 'prerequisite'):
                publish_plan(plan, self.s3, OWNER, web_only=True)
            self.assertFalse(self.s3.puts)
            self.s3.objects[key] = stored

    def test_web_only_wrong_remote_hash_or_json_content_has_zero_writes(self):
        plan = self.plan()
        publish_plan(plan, self.s3, OWNER)
        for key, mutation in [('samples/amen.mp4', 'hash'), ('config/samples.json', 'body')]:
            original = copy.deepcopy(self.s3.objects[key])
            self.s3.puts.clear()
            if mutation == 'hash': self.s3.objects[key]['Metadata']['sha256'] = '0' * 64
            else:
                data = self.s3.objects[key]['Body']
                self.s3.objects[key]['Body'] = b'X' + data[1:]  # Same size/claimed digest, different JSON.
            with self.subTest(key=key), self.assertRaises(PublicationError):
                publish_plan(plan, self.s3, OWNER, web_only=True)
            self.assertFalse(self.s3.puts)
            self.s3.objects[key] = original

    def test_web_only_complete_prerequisites_updates_ui_without_rewriting_media(self):
        plan = self.plan()
        publish_plan(plan, self.s3, OWNER)
        self.s3.puts.clear()
        uploaded = publish_plan(plan, self.s3, OWNER, web_only=True)
        self.assertEqual(set(uploaded), {a.key for a in plan.assets if not a.prerequisite})
        self.assertIn('product/data/stories.json', uploaded)
        self.assertNotIn('config/samples.json', uploaded)

    def test_plan_freezes_verified_bodies_against_later_local_replacement(self):
        plan = self.plan()
        expected = next(a for a in plan.assets if a.key == 'samples/amen.mp4').body
        (self.root / SOURCES['amen']).write_bytes(b'changed-after-validation')
        publish_plan(plan, self.s3, OWNER)
        self.assertEqual(self.s3.objects['samples/amen.mp4']['Body'], expected)

    def test_unknown_curated_frame_reference_fails_before_writes(self):
        self.stories[1]['poster'] = '/frames/amen-unregistered.jpg'
        self.save('product/data/stories.json', {'stories': self.stories})
        with self.assertRaisesRegex(PublicationError, 'Unpublished curated frame'):
            self.plan()
        self.assertFalse(self.s3.puts)


if __name__ == '__main__':
    unittest.main()
