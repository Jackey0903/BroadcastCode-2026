"""Offline verified publication tests; tiny fixtures, no AWS or actual media."""
import base64
import copy
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'agent'))
from readiness_agent import PROTOCOL, validate_request
from publication import (CAMP_DATA, CAMP_FILES, FRAME_NAMES, WEB_FILES, PublicationError, build_plan, publish_plan)
from serve import SOURCES

OWNER = '555726205424'
BUCKET = 'new-formal-product-bucket'
WEBSITE = 'https://new-formal.cloudfront.net'
CURRENT_RUNTIME = 'arn:aws:bedrock-agentcore:us-east-1:555726205424:runtime/current-formal-runtime'


def sha(body):
    return hashlib.sha256(body).hexdigest()


class FakeS3Error(Exception):
    def __init__(self, code):
        self.response = {'Error': {'Code': code}}
        super().__init__(code)


class FakeS3:
    def __init__(self):
        self.objects, self.puts, self.reads, self.copies = {}, [], [], []

    def put_object(self, **request):
        assert request['ExpectedBucketOwner'] == OWNER
        assert request['Bucket'] == BUCKET
        assert request['ChecksumSHA256'] == base64.b64encode(hashlib.sha256(request['Body']).digest()).decode('ascii')
        self.objects[request['Key']] = copy.deepcopy(request)
        self.puts.append(request['Key'])

    def head_object(self, **request):
        assert request['ExpectedBucketOwner'] == OWNER
        assert request['Bucket'] == BUCKET
        self.reads.append(request['Key'])
        if request['Key'] not in self.objects:
            raise FakeS3Error('404')
        stored = self.objects[request['Key']]
        return {'ContentLength': len(stored['Body']), 'Metadata': stored['Metadata'],
                'CacheControl': stored.get('CacheControl'), 'ContentType': stored['ContentType'],
                'ETag': '"' + hashlib.md5(stored['Body']).hexdigest() + '"',
                'ServerSideEncryption': stored.get('ServerSideEncryption', 'AES256'),
                'ChecksumSHA256': base64.b64encode(hashlib.sha256(stored['Body']).digest()).decode('ascii')}

    def copy_object(self, **request):
        assert request['ExpectedBucketOwner'] == request['ExpectedSourceBucketOwner'] == OWNER
        assert request['CopySource'] == {'Bucket': BUCKET, 'Key': request['Key']}
        assert request['ChecksumAlgorithm'] == 'SHA256'
        assert request['MetadataDirective'] == 'REPLACE'
        previous = self.objects[request['Key']]
        etag = '"' + hashlib.md5(previous['Body']).hexdigest() + '"'
        if etag != request['CopySourceIfMatch']:
            raise FakeS3Error('PreconditionFailed')
        for field in ('ContentType', 'Metadata', 'CacheControl', 'ServerSideEncryption'):
            previous[field] = copy.deepcopy(request[field])
        self.copies.append(request['Key'])
        return {'CopyObjectResult': {'ChecksumSHA256':
            base64.b64encode(hashlib.sha256(previous['Body']).digest()).decode('ascii')}}

    def get_object(self, **request):
        assert request['ExpectedBucketOwner'] == OWNER
        assert request['Bucket'] == BUCKET
        self.reads.append(request['Key'])
        if request['Key'] not in self.objects:
            raise FakeS3Error('NoSuchKey')
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

    def camp_fixture(self):
        # Rendering-contract fixture only; no real training or scores claimed.
        data = {'job': 'synthetic-offline-job', 'model': 'synthetic-test-model', 'status': 'training',
                'data': {'source': 'synthetic offline fixture', 'shots': 1},
                'curve': [{'step': 1, 'mae': .2, 'meanReward': .4, 'toolsPerEpisode': 1}],
                'evalCurve': [], 'groups': [{'step': 1,
                    'shot': {'desc': 'fixture', 'zone': 'paint', 'type': '2PT', 'distanceFt': 3, 'official': .4},
                    'trajectories': [{'tools': ['zone_reference'], 'prediction': .5, 'reward': .4,
                                      'advantage': 0, 'say': 'fixture'}]}],
                'scoreboard': {'h2h': {'trained': None}, 'league': {'trained': None}},
                'calibration': {'base': [], 'trained': []}, 'honesty': ['synthetic fixture']}
        self.save(CAMP_DATA, data)
        for name in CAMP_FILES:
            self.write('product/web/' + name, b'public-camp-fixture')
        self.write('product/web/index.html', b'<nav><a href="./">WATCH</a><a class="nav-link" href="./camp.html"><b>CAMP</b></a></nav>')
        return data

    def test_unready_optional_camp_link_is_hidden_only_in_publication_copy(self):
        self.camp_fixture()
        (self.root / CAMP_DATA).unlink()
        original = (self.root / 'product/web/index.html').read_bytes()
        plan = self.plan()
        assets = {a.key: a for a in plan.assets}
        self.assertNotIn(b'camp.html', assets['product/index.html'].body)
        self.assertIn(b'WATCH', assets['product/index.html'].body)
        self.assertEqual((self.root / 'product/web/index.html').read_bytes(), original)
        self.assertFalse(any(a.key.startswith('product/camp.') for a in plan.assets))
        self.assertFalse(plan.summary()['trainingCamp']['published'])

    def test_ready_camp_publishes_exact_data_and_every_dependency_before_navigation(self):
        data = self.camp_fixture()
        plan = self.plan()
        assets = {a.key: a for a in plan.assets}
        self.assertEqual(json.loads(assets[CAMP_DATA].body), data)
        self.assertIn(b'./camp.html', assets['product/index.html'].body)
        keys = [a.key for a in plan.assets]
        for key in [CAMP_DATA] + ['product/' + name for name in CAMP_FILES]:
            self.assertLess(keys.index(key), keys.index('product/index.html'))
        self.assertEqual(plan.summary()['trainingCamp'], {'published': True,
            'dataValidation': 'structure-only', 'mainPipelineIntegration': False})

    def test_partial_real_run_contract_keeps_absent_comparisons_null(self):
        data = self.camp_fixture()
        data['groups'] = []
        data['curve'][0]['mae'] = None
        self.save(CAMP_DATA, data)
        assets = {a.key: a for a in self.plan().assets}
        result = json.loads(assets[CAMP_DATA].body)
        self.assertIsNone(result['scoreboard']['h2h']['trained'])
        self.assertIsNone(result['curve'][0]['mae'])
        self.assertEqual(result['groups'], [])

    def test_invalid_optional_camp_data_does_not_block_verified_main_video_pipeline(self):
        original = self.camp_fixture()
        cases = [dict(original, curve=[{'step': 1, 'mae': float('nan')}]),
                 dict(original, calibration={'base': [[1.1, .2]], 'trained': []}),
                 dict(original, groups=[{'step': 1, 'shot': {}, 'trajectories': []}]),
                 dict(original, status='assumed-success'), dict(original, honesty=[])]
        for data in cases:
            with self.subTest(data=data):
                self.save(CAMP_DATA, data)
                plan = self.plan()
                keys = [a.key for a in plan.assets]
                self.assertNotIn(CAMP_DATA, keys)
                self.assertIn('product/data/stories.json', keys)
                self.assertFalse(plan.camp_published)

    def test_missing_optional_camp_static_dependency_withholds_all_camp_links(self):
        self.camp_fixture()
        (self.root / 'product/web/camp.js').unlink()
        assets = {a.key: a for a in self.plan().assets}
        self.assertNotIn(CAMP_DATA, assets)
        self.assertNotIn('product/camp.html', assets)
        self.assertNotIn(b'camp.html', assets['product/index.html'].body)

    def test_optional_camp_credentials_are_never_frozen_for_publication(self):
        data = self.camp_fixture()
        data['secret'] = 'ASIA' + 'A' * 16
        self.save(CAMP_DATA, data)
        plan = self.plan()
        self.assertFalse(plan.camp_published)
        self.assertFalse(any(b'ASIA' + b'A' * 16 in a.body for a in plan.assets))

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

    def test_reuse_identical_snapshot_has_zero_puts(self):
        plan = self.plan()
        publish_plan(plan, self.s3, OWNER)
        self.s3.puts.clear()
        self.s3.reads.clear()
        uploaded = publish_plan(plan, self.s3, OWNER, reuse_unchanged=True)
        self.assertEqual(uploaded, [])
        self.assertEqual(self.s3.puts, [])
        # JSON requires head plus actual body; media is verified by head.
        for asset in plan.assets:
            expected_reads = 2 if asset.content_type == 'application/json' else 1
            self.assertEqual(self.s3.reads.count(asset.key), expected_reads)

    def test_republication_preserves_immutable_job_media_and_analysis(self):
        plan = self.plan()
        output_keys = [asset.key for asset in plan.assets if asset.key.startswith('product/outputs/')]
        publish_plan(plan, self.s3, OWNER)
        originals = {key: copy.deepcopy(self.s3.objects[key]) for key in output_keys}
        # Republishing the showcase used to overwrite Worker immutable headers
        # with no-cache (MP4) and no-store (analysis).
        publish_plan(plan, self.s3, OWNER)
        for key in output_keys:
            stored = self.s3.objects[key]
            self.assertEqual(stored['CacheControl'], 'public, max-age=31536000, immutable')
            self.assertEqual(stored['Body'], originals[key]['Body'])
            self.assertEqual(stored['Metadata'], originals[key]['Metadata'])
            self.assertEqual(stored['ChecksumSHA256'], originals[key]['ChecksumSHA256'])

    def test_changed_story_manifest_and_configs_never_receive_long_lived_cache(self):
        publish_plan(self.plan(), self.s3, OWNER)
        self.stories[0]['title'] = 'Updated editorial title'
        self.save('product/data/stories.json', {'stories': self.stories})
        self.s3.puts.clear()
        uploaded = publish_plan(self.plan(), self.s3, OWNER, reuse_unchanged=True)
        self.assertEqual(uploaded, ['product/data/stories.json'])
        self.assertEqual(json.loads(self.s3.objects[uploaded[0]]['Body'])['stories'][0]['title'],
                         'Updated editorial title')
        for key in ('product/data/stories.json', 'config/samples.json', 'product/config/samples.json'):
            self.assertEqual(self.s3.objects[key]['CacheControl'], 'no-store')
        self.assertEqual(self.s3.objects['samples/flagg.mp4']['CacheControl'], 'public, max-age=86400')
        self.assertEqual(self.s3.objects['frames/flagg-00.2s.jpg']['CacheControl'], 'public, max-age=86400')
        self.assertEqual(self.s3.objects['product/app.js']['CacheControl'],
                         'public, max-age=0, must-revalidate')

    def test_reuse_migrates_wrong_cache_policy_even_with_identical_body_and_hash(self):
        plan = self.plan()
        publish_plan(plan, self.s3, OWNER)
        media = f"product/outputs/{self.reports['flagg']['jobId']}/enhanced.mp4"
        analysis = f"product/outputs/{self.reports['flagg']['jobId']}/analysis.json"
        policies = {media: 'no-cache', analysis: 'no-store',
                    'product/data/stories.json': 'public, max-age=31536000, immutable'}
        original_bodies = {key: self.s3.objects[key]['Body'] for key in policies}
        for key, policy in policies.items():
            self.s3.objects[key]['CacheControl'] = policy
        self.s3.puts.clear()
        uploaded = publish_plan(plan, self.s3, OWNER, reuse_unchanged=True)
        self.assertEqual(set(uploaded), set(policies))
        self.assertEqual(set(self.s3.copies), set(policies))
        self.assertFalse(self.s3.puts)
        for key in policies:
            self.assertEqual(self.s3.objects[key]['Body'], original_bodies[key])
        self.assertEqual(self.s3.objects[media]['CacheControl'], 'public, max-age=31536000, immutable')
        self.assertEqual(self.s3.objects[analysis]['CacheControl'], 'public, max-age=31536000, immutable')
        self.assertEqual(self.s3.objects['product/data/stories.json']['CacheControl'], 'no-store')

    def test_cache_only_copy_requires_actual_service_checksum_not_claimed_metadata(self):
        plan = self.plan()
        publish_plan(plan, self.s3, OWNER)
        key = 'samples/amen.mp4'
        expected = self.s3.objects[key]['Body']
        self.s3.objects[key]['Body'] = expected[:-1] + b'X'
        self.s3.objects[key]['CacheControl'] = 'no-cache'
        self.s3.puts.clear()
        uploaded = publish_plan(plan, self.s3, OWNER, reuse_unchanged=True)
        self.assertEqual(uploaded, [key])
        self.assertEqual(self.s3.puts, [key])
        self.assertFalse(self.s3.copies)
        self.assertEqual(self.s3.objects[key]['Body'], expected)

    def test_cache_only_copy_is_etag_guarded_and_retains_source_encryption_and_metadata(self):
        plan = self.plan()
        publish_plan(plan, self.s3, OWNER)
        key = 'samples/amen.mp4'
        self.s3.objects[key]['CacheControl'] = 'no-cache'
        self.s3.objects[key]['Metadata']['retained-provenance'] = 'source-snapshot'
        self.s3.puts.clear()
        original_copy = self.s3.copy_object
        def changed_before_copy(**request):
            self.s3.objects[key]['Body'] += b'changed after preflight'
            return original_copy(**request)
        with patch.object(self.s3, 'copy_object', side_effect=changed_before_copy):
            with self.assertRaises(FakeS3Error):
                publish_plan(plan, self.s3, OWNER, reuse_unchanged=True)
        self.assertFalse(self.s3.copies or self.s3.puts)
        # A fresh stable snapshot preserves all existing source metadata/SSE.
        self.s3.objects[key]['Body'] = next(a.body for a in plan.assets if a.key == key)
        publish_plan(plan, self.s3, OWNER, reuse_unchanged=True)
        self.assertEqual(self.s3.copies, [key])
        self.assertEqual(self.s3.objects[key]['Metadata']['retained-provenance'], 'source-snapshot')
        self.assertEqual(self.s3.objects[key]['ServerSideEncryption'], 'AES256')

    def test_reuse_same_length_different_hash_uploads_only_changed_frozen_body(self):
        plan = self.plan()
        publish_plan(plan, self.s3, OWNER)
        self.s3.puts.clear()
        key = 'samples/amen.mp4'
        self.s3.objects[key]['Metadata']['sha256'] = '0' * 64
        expected = next(asset.body for asset in plan.assets if asset.key == key)
        (self.root / SOURCES['amen']).write_bytes(b'replaced-after-plan-was-frozen')
        progress = []
        uploaded = publish_plan(plan, self.s3, OWNER, reuse_unchanged=True,
                                progress=lambda key, size: progress.append((key, size)))
        self.assertEqual(uploaded, [key])
        self.assertEqual(self.s3.puts, [key])
        self.assertEqual(self.s3.objects[key]['Body'], expected)
        self.assertEqual(progress, [(key, len(expected))])

    def test_reuse_json_with_matching_head_but_different_bytes_is_rewritten(self):
        plan = self.plan()
        publish_plan(plan, self.s3, OWNER)
        self.s3.puts.clear()
        key = 'config/samples.json'
        original = self.s3.objects[key]['Body']
        self.s3.objects[key]['Body'] = b'X' + original[1:]
        uploaded = publish_plan(plan, self.s3, OWNER, reuse_unchanged=True)
        self.assertEqual(uploaded, [key])
        self.assertEqual(self.s3.objects[key]['Body'], original)

    def test_reuse_missing_object_uploads_only_that_asset(self):
        plan = self.plan()
        publish_plan(plan, self.s3, OWNER)
        key = 'samples/amen.mp4'
        self.s3.objects.pop(key)
        self.s3.puts.clear()
        uploaded = publish_plan(plan, self.s3, OWNER, reuse_unchanged=True)
        self.assertEqual(uploaded, [key])
        self.assertIn(key, self.s3.objects)

    def test_reuse_access_or_transport_error_stops_before_any_writes(self):
        plan = self.plan()
        publish_plan(plan, self.s3, OWNER)
        self.s3.puts.clear()
        # The first candidate is changed, but a later failed read prevents even
        # that already verified local body from being uploaded.
        self.s3.objects[plan.assets[0].key]['Metadata']['sha256'] = '0' * 64
        head = self.s3.head_object
        for error in (FakeS3Error('AccessDenied'), FakeS3Error('SlowDown'), OSError('offline transport failure')):
            def fail_late(**request):
                if request['Key'] == plan.assets[-1].key:
                    raise error
                return head(**request)
            with self.subTest(error=type(error).__name__), patch.object(self.s3, 'head_object', side_effect=fail_late):
                with self.assertRaisesRegex(PublicationError, 'Unreadable existing'):
                    publish_plan(plan, self.s3, OWNER, reuse_unchanged=True)
            self.assertEqual(self.s3.puts, [])

    def test_reuse_json_get_failure_is_not_treated_as_changed_content(self):
        plan = self.plan()
        publish_plan(plan, self.s3, OWNER)
        self.s3.puts.clear()
        with patch.object(self.s3, 'get_object', side_effect=FakeS3Error('AccessDenied')):
            with self.assertRaisesRegex(PublicationError, 'Unreadable existing'):
                publish_plan(plan, self.s3, OWNER, reuse_unchanged=True)
        self.assertEqual(self.s3.puts, [])

    def test_reuse_json_disappearing_after_head_is_uploaded_only_on_no_such_key(self):
        plan = self.plan()
        publish_plan(plan, self.s3, OWNER)
        self.s3.puts.clear()
        key = 'config/samples.json'
        get = self.s3.get_object

        def missing_json(**request):
            if request['Key'] == key:
                raise FakeS3Error('NoSuchKey')
            return get(**request)

        with patch.object(self.s3, 'get_object', side_effect=missing_json):
            uploaded = publish_plan(plan, self.s3, OWNER, reuse_unchanged=True)
        self.assertEqual(uploaded, [key])
        self.assertEqual(self.s3.puts, [key])

    def test_reuse_cannot_be_combined_with_web_only(self):
        with self.assertRaisesRegex(PublicationError, 'mutually exclusive'):
            publish_plan(self.plan(), self.s3, OWNER, web_only=True, reuse_unchanged=True)
        self.assertEqual(self.s3.reads, [])
        self.assertEqual(self.s3.puts, [])

    def test_matching_current_runtime_marks_formal_reports_current_without_changing_evidence(self):
        originals = {}
        for sample in SOURCES:
            report = copy.deepcopy(self.reports[sample])
            report['analysis']['runtimeArn'] = CURRENT_RUNTIME
            report['verifiedAt'] = '2026-10-10T05:00:00+00:00'
            self.save(self.report_path(sample), report)
            originals[sample] = copy.deepcopy(report)
        plan = build_plan(self.root, BUCKET, WEBSITE, current_runtime_arn=CURRENT_RUNTIME)
        assets = {asset.key: asset for asset in plan.assets}
        document = json.loads(assets['product/data/stories.json'].body)
        self.assertFalse(document['publication']['historical'])
        self.assertFalse(plan.summary()['historicalRepublish'])
        for story in document['stories']:
            self.assertFalse(story['publication']['historical'])
            self.assertFalse(story['publication']['newInference'])
            self.assertEqual(story['publication']['kind'], 'verified-current-publication')
            report = originals[story['id']]
            analysis_key = f"product/outputs/{story['showcaseJobId']}/analysis.json"
            analysis = json.loads(assets[analysis_key].body)
            provenance = analysis.pop('publication')
            self.assertEqual(analysis, report['analysis'])
            self.assertEqual(provenance['originalVerifiedAt'], report['verifiedAt'])
            self.assertEqual(provenance['originalRuntimeArn'], CURRENT_RUNTIME)
            self.assertEqual(json.loads((self.root / self.report_path(story['id'])).read_bytes()), report)

    def test_mixed_current_and_historical_sources_are_classified_per_story(self):
        report = copy.deepcopy(self.reports['flagg'])
        report['analysis']['runtimeArn'] = CURRENT_RUNTIME
        self.save(self.report_path('flagg'), report)
        plan = build_plan(self.root, BUCKET, WEBSITE, current_runtime_arn=CURRENT_RUNTIME)
        document = json.loads(next(asset.body for asset in plan.assets if asset.key == 'product/data/stories.json'))
        by_id = {story['id']: story['publication'] for story in document['stories']}
        self.assertFalse(by_id['flagg']['historical'])
        self.assertTrue(by_id['amen']['historical'])
        self.assertTrue(plan.summary()['historicalRepublish'])


    def install_watch_fixture(self):
        from watch_assets import WATCH_PUBLIC_FILES
        for name in WATCH_PUBLIC_FILES:
            self.write('product/watch/' + name, b'/* explicit test runtime asset */')
        self.save('product/watch/data/stories.json', {'stories': [{'sample': 'stale-fixture'}]})
        for name in ('preview.py', 'tests/config.test.js', 'dev/references/private.png', '.env'):
            self.write('product/watch/' + name, b'private-unpublished-fixture')

    def test_watch_uses_current_verified_catalog_and_original_report_facts(self):
        self.install_watch_fixture()
        plan = self.plan()
        assets = {asset.key: asset for asset in plan.assets}
        shared = json.loads(assets['product/data/stories.json'].body)
        watch = json.loads(assets['product/watch/data/stories.json'].body)
        self.assertEqual(shared, watch)
        records = json.loads(assets['product/watch/data/history.json'].body)['records']
        self.assertEqual({r['jobId'] for r in records}, {story['showcaseJobId'] for story in shared['stories']})
        for record in records:
            original = self.reports[record['sample']]
            self.assertEqual(record['analysis'], original['analysis'])
            self.assertEqual(record['verifiedAt'], original['verifiedAt'])
            self.assertEqual(record['contentReview'], original['contentReview'])
        for name in ('preview.py', 'tests/config.test.js', 'dev/references/private.png', '.env'):
            self.assertNotIn('product/watch/' + name, assets)
        self.assertEqual(assets['product/watch/data/history.json'].cache_control, 'no-store')

    def test_watch_missing_runtime_asset_aborts_before_upload(self):
        self.install_watch_fixture()
        (self.root / 'product/watch/glass/optics-model.js').unlink()
        with self.assertRaises(PublicationError):
            self.plan()
        self.assertFalse(self.s3.puts)

    def test_watch_credentials_in_runtime_asset_aborts_publication(self):
        self.install_watch_fixture()
        self.write('product/watch/app.js', b'const secret="' + b'AK' + b'IA' + b'Q' * 16 + b'";')
        with self.assertRaises(PublicationError):
            self.plan()
        self.assertFalse(self.s3.puts)


if __name__ == '__main__':
    unittest.main()
