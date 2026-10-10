"""Register one supplied short clip locally; this is NOT the official evaluation IO.

No AWS calls are made. Measured media facts and supplied story evidence produce
the existing internal Agent/Worker input manifests and a local publication plan.
Nothing marks supplied basketball evidence as independently reviewed.
"""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT / 'agent'))
from readiness_agent import MAX_IMAGE_BYTES, PROTOCOL, ValidationError, validate_request
from story_contract import StoryValidationError, validate_story_source

REGISTRATION_PROTOCOL = 'team02-case-registration-v1'
MAX_VIDEO_BYTES = 256 * 1024 * 1024
# Conservative short-clip registration scope, not a throughput guarantee.
MAX_CLIP_SECONDS = 60
SAFE_ID = re.compile(r'[a-z0-9][a-z0-9_-]{0,59}\Z')


class RegistrationError(ValueError):
    pass


def _number(value, label):
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        raise RegistrationError(f'{label} must be a finite number')
    return value


def _json_bytes(value):
    try:
        return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    except (TypeError, ValueError) as error:
        raise RegistrationError('Metadata must be finite, JSON-serializable data') from error


def _sha_file(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _file(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise RegistrationError('Input must be an existing regular local file, not a symlink')
    return path.resolve()


def probe_video(path):
    """Use the host ffprobe; never fall back to the Lambda Linux media layer."""
    binary = shutil.which('ffprobe')
    if not binary:
        raise RegistrationError('Local ffprobe is required to measure the source clip')
    result = subprocess.run([binary, '-v', 'error', '-show_entries',
        'stream=codec_type,width,height:format=duration', '-of', 'json', str(path)],
        capture_output=True, timeout=30, check=False)
    if result.returncode:
        raise RegistrationError('Local ffprobe could not measure a playable video')
    try:
        data = json.loads(result.stdout)
        stream = next(row for row in data['streams'] if row.get('codec_type') == 'video')
        return {'durationSeconds': float(data['format']['duration']),
                'width': stream['width'], 'height': stream['height'],
                'hasAudio': any(row.get('codec_type') == 'audio' for row in data['streams'])}
    except (ValueError, KeyError, StopIteration, TypeError) as error:
        raise RegistrationError('Local ffprobe could not measure a playable video') from error


def extract_frame(video, requested_seconds, output):
    """Select a decoded frame and record its actual showinfo timestamp, not the request."""
    binary = shutil.which('ffmpeg')
    if not binary:
        raise RegistrationError('Local ffmpeg is required to extract actual source frames')
    filter_text = f'select=gte(t\\,{requested_seconds:.9f}),scale=min(1280\\,iw):-2,showinfo'
    result = subprocess.run([binary, '-nostdin', '-hide_banner', '-loglevel', 'info',
        '-i', str(video), '-vf', filter_text, '-frames:v', '1', '-fps_mode', 'vfr',
        '-q:v', '3', '-an', '-y', str(output)], capture_output=True, timeout=60, check=False)
    pts = re.search(r'\bn:\s*0\s+pts:\s*[-\d]+\s+pts_time:([\d.eE+-]+)',
                    result.stderr.decode('utf-8', 'replace'))
    if result.returncode or not output.is_file() or not pts:
        raise RegistrationError('Local ffmpeg could not extract and timestamp the requested frame')
    return {'timestampSeconds': float(pts.group(1)), 'timestampSource': 'ffmpeg_showinfo_video_timeline'}


def register_case(*, sample, bucket, video_path, story, frame_times, output_dir,
                  existing_manifest=None, existing_stories=None,
                  probe=probe_video, extractor=extract_frame):
    """Append a controlled case, atomically emitting a new local bundle only on success.

    probe/extractor are injectable for offline CI; test doubles do not certify
    real media. Existing registry records are copied and never edited in place.
    """
    if not isinstance(sample, str) or not SAFE_ID.fullmatch(sample):
        raise RegistrationError('sample requires a safe lowercase ID of at most 60 characters')
    if (not isinstance(bucket, str) or not re.fullmatch(r'[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]', bucket)
            or '..' in bucket):
        raise RegistrationError('bucket must be the explicit controlled destination bucket')
    manifest = copy.deepcopy(existing_manifest if existing_manifest is not None else {})
    document = copy.deepcopy(existing_stories if existing_stories is not None else
                             {'version': 'registered-cases-v1', 'stories': []})
    if (not isinstance(manifest, dict) or not isinstance(document, dict)
            or not isinstance(document.get('version'), (str, int)) or not isinstance(document.get('stories'), list)
            or any(not isinstance(row, dict) or not isinstance(row.get('id'), str) for row in document['stories'])):
        raise RegistrationError('Existing registry must contain a manifest object and versioned stories[]')
    ids = [row['id'] for row in document['stories']]
    if sample in manifest or sample in ids or len(ids) != len(set(ids)):
        raise RegistrationError('Case ID already exists or the base stories contain duplicates; no overwrite performed')
    if not isinstance(story, dict):
        raise RegistrationError('Supplied story metadata must be an object')
    if (not isinstance(frame_times, (list, tuple)) or not 1 <= len(frame_times) <= 6
            or len({_number(value, 'frame time') for value in frame_times}) != len(frame_times)):
        raise RegistrationError('Provide 1 to 6 distinct finite requested frame times')
    source = _file(video_path)
    if source.suffix.lower() != '.mp4' or not 12 <= source.stat().st_size <= MAX_VIDEO_BYTES:
        raise RegistrationError('Source must be a nonempty MP4 within the existing 256 MiB worker limit')
    with source.open('rb') as stream:
        if stream.read(12)[4:8] != b'ftyp':
            raise RegistrationError('Source does not have an MP4 container header')
    media = probe(source)
    duration = _number(media.get('durationSeconds'), 'measured duration')
    if not 0 < duration <= MAX_CLIP_SECONDS:
        raise RegistrationError('Registration currently supports measured short clips up to 60 seconds')
    for key in ('width', 'height'):
        if type(media.get(key)) is not int or not 1 <= media[key] <= 8192:
            raise RegistrationError('Measured video dimensions must be valid integers')
    if any(not 0 <= value < duration for value in frame_times):
        raise RegistrationError('Requested frame times must lie inside the measured source duration')
    source_sha = _sha_file(source)
    supplied = copy.deepcopy(story)
    if ('id' in supplied and supplied['id'] != sample
            or 'sourceVideoSha256' in supplied and supplied['sourceVideoSha256'] != source_sha
            or 'durationSeconds' in supplied and abs(_number(supplied['durationSeconds'], 'story duration') - duration) > .25):
        raise RegistrationError('Supplied story conflicts with measured source identity')
    supplied.update(id=sample, durationSeconds=duration, sourceVideoSha256=source_sha,
                    sourceVideo=f'/samples/{sample}.mp4')
    event = supplied.setdefault('officialEvent', {'verified': False})
    if not isinstance(event, dict) or type(event.get('verified')) is not bool:
        raise RegistrationError('officialEvent requires an explicit verified boolean when supplied')
    if not event['verified'] and supplied.get('shotMetric') is not None:
        raise RegistrationError('Unknown or unverified official metrics must be omitted')
    # Freeze and re-check supplied JSON before exposing it in any publication asset.
    supplied_body = _json_bytes(story)
    if re.search(rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----', supplied_body):
        raise RegistrationError('Supplied metadata may contain a credential; registration rejected')
    destination = Path(output_dir).absolute()
    if destination.exists() or destination.is_symlink():
        raise RegistrationError('Output directory already exists; no overwrite performed')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.case-register-', dir=destination.parent) as temp:
        staging = Path(temp)
        shutil.copyfile(source, staging / 'source.mp4')
        if _sha_file(staging / 'source.mp4') != source_sha:
            raise RegistrationError('Source changed during registration')
        assets = [{'key': f'samples/{sample}.mp4', 'file': 'source.mp4', 'sha256': source_sha,
                   'bytes': (staging / 'source.mp4').stat().st_size, 'contentType': 'video/mp4'}]
        frames, measured_frames = [], []
        for index, target in enumerate(sorted(frame_times)):
            name = f'frame-{index:02d}.jpg'
            output = staging / name
            measured = extractor(staging / 'source.mp4', target, output)
            timestamp = _number(measured.get('timestampSeconds'), 'actual frame timestamp')
            if not 0 <= timestamp < duration or timestamp + .000001 < target:
                raise RegistrationError('Actual frame timestamp is outside the source or precedes the requested time')
            image = _file(output).read_bytes()
            if not 4 <= len(image) <= MAX_IMAGE_BYTES or not image.startswith(b'\xff\xd8\xff') or not image.endswith(b'\xff\xd9'):
                raise RegistrationError('Extracted frame must be a bounded actual JPEG')
            key = f'frames/{sample}/{name}'
            frames.append({'timestamp_ms': timestamp * 1000, 's3_uri': f's3://{bucket}/{key}', 'format': 'jpeg'})
            record = {'key': key, 'file': name, 'sha256': hashlib.sha256(image).hexdigest(),
                      'bytes': len(image), 'contentType': 'image/jpeg'}
            assets.append(record)
            measured_frames.append({**record, 'requestedSeconds': target, 'actualSeconds': timestamp,
                                    'timestampSource': measured.get('timestampSource', 'provided_extractor_result')})
        video = {'id': sample, 'name': source.name, 's3_uri': f's3://{bucket}/samples/{sample}.mp4',
                 'duration_ms': duration * 1000, 'width': media['width'], 'height': media['height'], 'sha256': source_sha}
        request = {'protocol_version': PROTOCOL, 'request_id': 'registration-' + sample,
                   'video': video, 'frames': frames}
        try:
            validate_request(request, bucket)
            validate_story_source(supplied, request)
        except (ValidationError, StoryValidationError) as error:
            raise RegistrationError(str(error)) from error
        manifest[sample] = {'video': video, 'frames': frames}
        document['stories'].append(supplied)
        receipt = {'protocol': REGISTRATION_PROTOCOL, 'scope': 'internal_registration_not_official_evaluation_schema',
                   'sample': sample, 'bucket': bucket, 'source': video, 'frames': measured_frames,
                   'suppliedStorySha256': hashlib.sha256(supplied_body).hexdigest(),
                   'sourceHasAudio': media.get('hasAudio') is True,
                   'validation': 'existing_internal_input_and_story_contract_passed',
                   'contentReview': 'supplied_metadata_not_independently_reviewed',
                   'newInference': False, 'newRender': False, 'cloudPublished': False}
        documents = [('samples.json', manifest, ('config/samples.json', 'product/config/samples.json')),
                     ('stories.json', document, ('product/data/stories.json',)),
                     ('registration.json', receipt, (f'product/registrations/{sample}.json',))]
        for name, value, keys in documents:
            body = _json_bytes(value)
            (staging / name).write_bytes(body)
            for key in keys:
                assets.append({'key': key, 'file': name, 'sha256': hashlib.sha256(body).hexdigest(),
                               'bytes': len(body), 'contentType': 'application/json'})
        (staging / 'supplied-story.json').write_bytes(supplied_body)
        plan = {'protocol': REGISTRATION_PROTOCOL, 'scope': receipt['scope'], 'bucket': bucket,
                'sample': sample, 'bundleDirectory': str(destination), 'assets': assets,
                'newInference': False, 'newRender': False, 'cloudPublished': False,
                'publicationOrder': 'source_and_frames_before_manifest_and_stories'}
        (staging / 'publication-plan.json').write_bytes(_json_bytes(plan))
        staging.rename(destination)
    return {'receipt': receipt, 'manifest': manifest, 'stories': document, 'publicationPlan': plan}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sample', required=True)
    parser.add_argument('--bucket', required=True)
    parser.add_argument('--video', type=Path, required=True)
    parser.add_argument('--story', type=Path, required=True, help='Supplied case metadata in the existing internal story format')
    parser.add_argument('--frame-time', type=float, action='append', required=True, help='Requested video seconds; actual selected PTS is measured')
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, help='Current same-bucket input manifest, if any')
    parser.add_argument('--stories', type=Path, default=PRODUCT / 'data/stories.json', help='Snapshot of current stories; default preserves local stories')
    args = parser.parse_args(argv)
    try:
        read = lambda path: json.loads(_file(path).read_text())
        result = register_case(sample=args.sample, bucket=args.bucket, video_path=args.video,
            story=read(args.story), frame_times=args.frame_time, output_dir=args.output_dir,
            existing_manifest=read(args.manifest) if args.manifest else {}, existing_stories=read(args.stories))
    except (RegistrationError, OSError, ValueError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f'Registration failed: {error}\n')
    print(json.dumps({'sample': args.sample, 'bundle': str(args.output_dir),
                      'scope': result['receipt']['scope'], 'assets': len(result['publicationPlan']['assets']),
                      'cloudPublished': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
