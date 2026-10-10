"""Verified local publication snapshot for two registered practice cases.

Every immutable upload body is checked before writes. Historical reports keep
their original runtime/trace, with separate current presentation URLs. No CDK,
model, job table or arbitrary-input adapter is invoked by this module.
"""
import copy
from dataclasses import dataclass
import hashlib
import json
import math
import mimetypes
from pathlib import Path
import re
from urllib.parse import urlsplit
from serve import SOURCES, checked_file

WEB_FILES = ('index.html', 'app.js', 'styles.css', 'broadcast.css', 'atmosphere.js',
             'arcade.css', 'arcade.js', 'assets/grain.svg', 'assets/fonts/OFL.txt',
             'assets/fonts/fusion-pixel-12px-monospaced-zh_hans.otf.woff2')
FRAME_NAMES = {'flagg': ('00.2s', '09s', '15.5s', '16.5s', '17.0s', '21s'),
               'amen': ('00s', '15s', '16.0s', '17.5s', '18s', '21s')}
NOTICE = '10月7日已验收的真实历史成片，按原哈希重新发布；不是正式账号新推理或正式评分结果。'
SECRET_PATTERNS = (
    re.compile(rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
    re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    re.compile(rb'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,})\b'),
    re.compile(rb'(?im)^\s*(?:export\s+)?(?:AWS_SECRET_ACCESS_KEY|AWS_SESSION_TOKEN|aws_secret_access_key|aws_session_token)\s*=\s*["\x27]?[A-Za-z0-9+/]{20,}'))


class PublicationError(ValueError):
    pass


@dataclass(frozen=True)
class Asset:
    key: str
    body: bytes
    content_type: str
    prerequisite: bool = False

    @property
    def sha256(self):
        return hashlib.sha256(self.body).hexdigest()


@dataclass(frozen=True)
class PublicationPlan:
    bucket: str
    website: str
    assets: tuple

    def summary(self):
        return {'bucket': self.bucket, 'website': self.website + '/product/',
                'historicalRepublish': True, 'newInference': False, 'courtLabPublished': False,
                'objects': [{'key': a.key, 'bytes': len(a.body), 'sha256': a.sha256,
                             'prerequisite': a.prerequisite} for a in self.assets]}


def _read(root, relative):
    file = checked_file(root, relative)
    if file is None:
        raise PublicationError(f'Missing or unsafe publication file: {relative}')
    body = file.read_bytes()
    if not body:
        raise PublicationError(f'Empty publication file: {relative}')
    return body


def _private_check(body, label):
    if any(p.search(body) for p in SECRET_PATTERNS):
        raise PublicationError(f'Possible secret in publication text: {label}')


def _json(root, relative):
    body = _read(root, relative)
    _private_check(body, relative)
    try:
        result = json.loads(body)
    except (ValueError, UnicodeError) as error:
        raise PublicationError(f'Invalid publication JSON: {relative}') from error
    if not isinstance(result, dict):
        raise PublicationError(f'Publication JSON must be an object: {relative}')
    return result


def _json_asset(key, value, prerequisite=False):
    body = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode() + b'\n'
    _private_check(body, key)
    return Asset(key, body, 'application/json', prerequisite)


def _sha(body, expected, label):
    if not isinstance(expected, str) or not re.fullmatch(r'[a-f0-9]{64}', expected) or hashlib.sha256(body).hexdigest() != expected:
        raise PublicationError(f'SHA-256 mismatch: {label}')


def _number(value, label):
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise PublicationError(f'Invalid numeric metadata: {label}') from error
    if isinstance(value, bool) or not math.isfinite(result) or result <= 0:
        raise PublicationError(f'Invalid numeric metadata: {label}')
    return result


def _mp4(body, expected, size, label):
    _sha(body, expected, label)
    if len(body) != int(_number(size, label + ' bytes')) or len(body) < 12 or body[4:8] != b'ftyp':
        raise PublicationError(f'Media size or MP4 header mismatch: {label}')


def _dimension(value, label):
    # AgentCore's input contract requires JSON integers, not integral floats.
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 8192:
        raise PublicationError(f'Invalid integer video dimension: {label}')
    return value


def build_plan(root, bucket, website):
    """Verify and freeze all required local assets; no S3 reads or local writes."""
    root = Path(root).resolve()
    host = urlsplit(website)
    if (host.scheme != 'https' or not host.hostname or not host.hostname.endswith('.cloudfront.net')
            or host.username or host.password or host.port or host.path not in ('', '/') or host.query or host.fragment):
        raise PublicationError('Publication website must be the current HTTPS CloudFront origin.')
    if not re.fullmatch(r'[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]', bucket):
        raise PublicationError('Invalid current publication bucket.')
    website = website.rstrip('/')
    document = _json(root, 'product/data/stories.json')
    stories = document.get('stories')
    if not isinstance(stories, list) or len(stories) != 2 or {s.get('id') for s in stories if isinstance(s, dict)} != set(SOURCES):
        raise PublicationError('Publication supports exactly the two registered practice stories.')
    metadata = _json(root, 'data/reference/train-video-metadata.json')
    provenance = _json(root, 'product/research/frame-provenance.json')
    indexed = {f.get('file'): f for f in provenance.get('frames', []) if isinstance(f, dict)}
    assets, manifest, published = [], {}, copy.deepcopy(document)
    frame_keys = set()
    for story in published['stories']:
        sample, job_id = story['id'], story.get('showcaseJobId')
        if story.get('sample') != sample or not isinstance(job_id, str) or not re.fullmatch(r'[a-f0-9]{32}', job_id):
            raise PublicationError(f'Invalid registered story identity: {sample}')
        relative = SOURCES[sample]
        source = _read(root, relative)
        probe = metadata.get(relative, {})
        stream = next((s for s in probe.get('streams', []) if s.get('codec_type') == 'video'), None)
        if not stream or stream.get('codec_name') != 'h264' or not any(s.get('codec_type') == 'audio' for s in probe.get('streams', [])):
            raise PublicationError(f'Registered source metadata missing video/audio: {sample}')
        _mp4(source, story.get('sourceVideoSha256'), probe.get('format', {}).get('size'), sample)
        duration = _number(probe.get('format', {}).get('duration'), sample + ' duration')
        if abs(duration - _number(story.get('durationSeconds'), sample + ' story duration')) > .05:
            raise PublicationError(f'Story/source duration mismatch: {sample}')
        source_key = f'samples/{sample}.mp4'
        assets.append(Asset(source_key, source, 'video/mp4', True))
        frames = []
        for suffix in FRAME_NAMES[sample]:
            filename = f'{sample}-{suffix}.jpg'
            relative = 'data/reference/frames/' + filename
            frame = indexed.get(relative, {})
            image = _read(root, relative)
            _sha(image, frame.get('sha256'), relative)
            seconds = float(suffix[:-1])
            if (frame.get('sample') != sample or frame.get('videoTime') != seconds or not 0 <= seconds < duration
                    or len(image) != frame.get('bytes') or not image.startswith(b'\xff\xd8') or not image.endswith(b'\xff\xd9')):
                raise PublicationError(f'Frame provenance or JPEG mismatch: {relative}')
            key = 'frames/' + filename
            frame_keys.add('/' + key)
            assets.append(Asset(key, image, 'image/jpeg', True))
            frames.append({'timestamp_ms': int(round(seconds * 1000)), 's3_uri': f's3://{bucket}/{key}', 'format': 'jpeg'})
        manifest[sample] = {'video': {'id': sample, 'name': Path(SOURCES[sample]).name,
            's3_uri': f's3://{bucket}/{source_key}', 'duration_ms': duration * 1000,
            'sha256': story['sourceVideoSha256'], 'width': _dimension(stream.get('width'), sample + ' width'),
            'height': _dimension(stream.get('height'), sample + ' height')}, 'frames': frames}
        report_relative = f'product/evidence/run-{job_id}.json'
        report = _json(root, report_relative)
        analysis = report.get('analysis', {})
        if (report.get('contentReview', {}).get('acceptedForShowcase') is not True or report.get('jobId') != job_id
                or report.get('sample') != sample or report.get('mode') != 'story'
                or analysis.get('protocol_version') != 'product-story-v1' or analysis.get('preservesSourceTimeline') is not True
                or analysis.get('runId') != job_id or analysis.get('sample') != sample):
            raise PublicationError(f'Historical render lacks matching accepted evidence: {sample}')
        output_hash = story.get('showcaseOutputSha256')
        if (report.get('outputSha256') != output_hash or analysis.get('outputVideo', {}).get('sha256') != output_hash
                or analysis.get('sourceVideo', {}).get('sha256') != story['sourceVideoSha256']
                or analysis.get('sourceVideo', {}).get('id') != sample):
            raise PublicationError(f'Historical source/output identity mismatch: {sample}')
        enhanced = _read(root, f'product/build/verified/{job_id}/enhanced.mp4')
        _mp4(enhanced, output_hash, report.get('bytes'), sample + ' enhanced')
        if (len(enhanced) != analysis['outputVideo'].get('bytes')
                or abs(_number(report.get('durationSeconds'), sample + ' enhanced duration') - duration) > .25
                or abs(_number(analysis['sourceVideo'].get('duration_ms'), sample + ' original timeline') / 1000 - duration) > .05
                or abs(_number(analysis['outputVideo'].get('durationMs'), sample + ' output timeline') / 1000 - duration) > .25):
            raise PublicationError(f'Historical media timeline/size mismatch: {sample}')
        base = website + f'/product/outputs/{job_id}'
        history = {'historical': True, 'newInference': False, 'kind': 'verified-historical-republication',
            'notice': NOTICE, 'originalJobId': job_id, 'originalVerifiedAt': report.get('verifiedAt'),
            'originalRuntimeArn': analysis.get('runtimeArn'), 'originalVideoUrl': report.get('videoUrl'),
            'originalAnalysisUrl': report.get('analysisUrl'), 'evidenceFile': report_relative,
            'currentVideoUrl': base + '/enhanced.mp4', 'currentAnalysisUrl': base + '/analysis.json'}
        if not history['originalVerifiedAt'] or not history['originalRuntimeArn']:
            raise PublicationError(f'Historical provenance is incomplete: {sample}')
        copied_analysis = copy.deepcopy(analysis)
        copied_analysis['publication'] = copy.deepcopy(history)
        assets.append(Asset(f'product/outputs/{job_id}/enhanced.mp4', enhanced, 'video/mp4', True))
        assets.append(_json_asset(f'product/outputs/{job_id}/analysis.json', copied_analysis, True))
        story.update(sourceVideo=website + '/' + source_key, enhancedVideo=history['currentVideoUrl'],
                     analysisUrl=history['currentAnalysisUrl'], publication=history)
    for story in published['stories']:
        references = [(story, 'poster')] + [(item, 'frameUrl') for item in story.get('evidence', []) if isinstance(item, dict)]
        for owner, field in references:
            value = owner.get(field)
            if isinstance(value, str) and value.startswith('/frames/'):
                if value not in frame_keys:
                    raise PublicationError(f'Unpublished curated frame reference: {value}')
                owner[field] = website + value
    published['publication'] = {'mode': 'verified-historical-republication', 'historical': True,
                                'newInference': False, 'notice': NOTICE}
    assets.extend([_json_asset('config/samples.json', manifest, True),
                   _json_asset('product/config/samples.json', manifest, True)])
    for name in WEB_FILES:
        body = _read(root, 'product/web/' + name)
        if not name.endswith('.woff2'):
            _private_check(body, 'product/web/' + name)
        assets.append(Asset('product/' + name, body, mimetypes.guess_type(name)[0] or 'application/octet-stream'))
    for name in ('event-bindings.json', 'video-anchors.json'):
        assets.append(_json_asset('product/data/' + name, _json(root, 'product/data/' + name)))
    # URLs are exposed only after their media/config dependencies.
    assets.append(_json_asset('product/data/stories.json', published))
    if len({a.key for a in assets}) != len(assets):
        raise PublicationError('Duplicate publication asset key.')
    return PublicationPlan(bucket, website, tuple(assets))


def publish_plan(plan, s3, expected_owner, web_only=False):
    """Apply a verified snapshot; web-only verifies all prerequisites before writes."""
    if not re.fullmatch(r'[0-9]{12}', expected_owner):
        raise PublicationError('Expected bucket owner must be the verified account.')
    if web_only:
        for asset in plan.assets:
            if not asset.prerequisite:
                continue
            try:
                head = s3.head_object(Bucket=plan.bucket, Key=asset.key, ExpectedBucketOwner=expected_owner)
                if head.get('ContentLength') != len(asset.body) or head.get('Metadata', {}).get('sha256') != asset.sha256:
                    raise PublicationError(f'Current publication prerequisite differs: {asset.key}')
                if asset.content_type == 'application/json':
                    response = s3.get_object(Bucket=plan.bucket, Key=asset.key, ExpectedBucketOwner=expected_owner)
                    if response['Body'].read(len(asset.body) + 1) != asset.body:
                        raise PublicationError(f'Current configuration/analysis differs: {asset.key}')
            except PublicationError:
                raise
            except Exception as error:
                raise PublicationError(f'Missing/unreadable publication prerequisite: {asset.key}; use full publication.') from error
    uploaded = []
    for asset in plan.assets:
        if web_only and asset.prerequisite:
            continue
        s3.put_object(Bucket=plan.bucket, Key=asset.key, Body=asset.body, ExpectedBucketOwner=expected_owner,
                      ContentLength=len(asset.body), ContentType=asset.content_type,
                      CacheControl='no-store' if asset.content_type == 'application/json' else 'no-cache',
                      Metadata={'sha256': asset.sha256})
        uploaded.append(asset.key)
    return uploaded
