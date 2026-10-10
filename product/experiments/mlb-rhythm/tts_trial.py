"""Local MiniMax trial. Credentials and generated assets never enter the UI.

Uses stdlib only. Inspect actual WAV duration before scheduling any narration.
No audio is truncated or accelerated to fit a scene. Captions are unit-level,
not vendor word alignment. Real requests are sequential and cached by payload.
"""
import argparse
import copy
import hashlib
import io
import json
import math
import os
import random
import sys
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

from serve import HERE, ROOT

BASES = {'https://api.minimax.io/v1', 'https://api.minimax.cn/v1'}
TRANSIENT = {1000, 1001, 1002, 1024, 1033, 1039, 1041, 2045}
OUT = ROOT / 'product/build/mlb-rhythm/flagg-voice'
FPS = 30


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def settings(env_file):
    local = {}
    if env_file and env_file.is_file():
        for line in env_file.read_text(encoding='utf-8-sig').splitlines():
            if line.strip() and not line.lstrip().startswith('#') and '=' in line:
                name, value = line.split('=', 1)
                local[name.strip()] = value.strip().strip('\"\'')
    key = os.environ.get('MINIMAX_API_KEY') or local.get('MINIMAX_API_KEY', '')
    base = (os.environ.get('MINIMAX_API_BASE') or local.get('MINIMAX_API_BASE') or 'https://api.minimax.io/v1').rstrip('/')
    if base == 'https://api.minimaxi.com/v1':
        base = 'https://api.minimax.cn/v1'  # Current official domestic endpoint; no credential-bearing redirect.
    if base not in BASES:
        raise ValueError('MINIMAX_API_BASE must be an official MiniMax /v1 endpoint.')
    if key in ('your-key', '你的密钥'):
        key = ''
    return key, base


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward Authorization to a redirect destination.


class ApiError(RuntimeError):
    pass


class MiniMax:
    def __init__(self, key, base, transport=None, sleep=time.sleep):
        if not key:
            raise ApiError('Missing MINIMAX_API_KEY. Configure the local env file first.')
        self.key, self.base = key, base
        self.transport = transport or self._request
        self.sleep = sleep

    def _request(self, endpoint, payload):
        request = urllib.request.Request(self.base + '/' + endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            headers={'Authorization': 'Bearer ' + self.key, 'Content-Type': 'application/json'}, method='POST')
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=90) as response:
            data = response.read(32 * 1024 * 1024 + 1)
        if len(data) > 32 * 1024 * 1024:
            raise ApiError('MiniMax response exceeded the local trial limit.')
        return json.loads(data)

    def call(self, endpoint, payload):
        for attempt in range(3):
            try:
                response = self.transport(endpoint, payload)
            except urllib.error.HTTPError as error:
                if error.code not in (429, 500, 502, 503, 504) or attempt == 2:
                    raise ApiError(f'MiniMax HTTP {error.code}; no response body logged.') from None
            except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
                if attempt == 2:
                    raise ApiError('MiniMax connection failed after three attempts.') from None
            else:
                code = response.get('base_resp', {}).get('status_code')
                if code == 0:
                    return response
                if code not in TRANSIENT or attempt == 2:
                    raise ApiError(f'MiniMax business error {code}; check account, voice ID and endpoint.')
            # A timed out request might still have been billed; no claim of idempotency.
            self.sleep(2 ** attempt + random.uniform(0, .5))
        raise ApiError('MiniMax request failed.')

    def voices(self):
        return self.call('get_voice', {'voice_type': 'system'}).get('system_voice', [])


def payload(text, plan, voice, language='Chinese', emotion=None, speed=None):
    result = {'model': plan['model'], 'text': text, 'stream': False,
            'language_boost': language, 'output_format': 'hex',
            'voice_setting': {'voice_id': voice, 'speed': speed or plan['speed'], 'vol': 1, 'pitch': 0},
            'audio_setting': {'sample_rate': 32000, 'format': 'wav', 'channel': 1}}
    if emotion:
        result['voice_setting']['emotion'] = emotion
    return result


def wav_duration(data):
    try:
        with wave.open(io.BytesIO(data), 'rb') as audio:
            if audio.getcomptype() != 'NONE' or audio.getnframes() <= 0:
                raise ValueError('Expected nonempty PCM WAV.')
            duration = audio.getnframes() / audio.getframerate()
    except (wave.Error, EOFError) as error:
        raise ValueError('MiniMax did not return a readable PCM WAV.') from error
    if not math.isfinite(duration) or not 0 < duration < 90:
        raise ValueError('WAV duration exceeds the local trial limit.')
    return duration


def synthesize(client, request, cache):
    identity = {'apiBase': client.base, 'payload': request}
    cache_id = digest(json.dumps(identity, ensure_ascii=False, sort_keys=True).encode('utf-8'))
    audio_path, meta_path = cache / (cache_id + '.wav'), cache / (cache_id + '.json')
    if audio_path.is_file() and meta_path.is_file():
        audio, meta = audio_path.read_bytes(), read_json(meta_path)
        actual_duration = wav_duration(audio)
        if digest(audio) == meta.get('audioSha256') and meta.get('request') == identity:
            meta['durationSeconds'] = actual_duration
            return audio_path, meta, True
    response = client.call('t2a_v2', request)
    encoded = response.get('data', {}).get('audio')
    if not isinstance(encoded, str) or not encoded:
        raise ApiError('MiniMax returned success without audio.')
    try:
        audio = bytes.fromhex(encoded)
    except ValueError:
        raise ApiError('MiniMax returned malformed audio hex.') from None
    duration = wav_duration(audio)
    cache.mkdir(parents=True, exist_ok=True)
    temp = audio_path.with_suffix('.wav.tmp')
    temp.write_bytes(audio)
    temp.replace(audio_path)
    meta = {'provider': 'MiniMax', 'request': identity, 'traceId': response.get('trace_id'),
            'durationSeconds': duration, 'audioSha256': digest(audio), 'cacheId': cache_id}
    write_json(meta_path, meta)
    return audio_path, meta, False


def duration(segment):
    raw = segment['duration'] if segment['kind'] == 'hold' else (segment['end'] - segment['start']) / segment.get('rate', 1)
    return math.ceil(raw * FPS - 1e-8) / FPS


def validate_units(base, voice_plan):
    ids = [s['id'] for s in base['segments']]
    previous, used = -1, set()
    for unit in voice_plan['units']:
        indices = [ids.index(stage) for stage in unit['stages']]
        if not indices or indices != list(range(indices[0], indices[-1] + 1)) or indices[0] <= previous:
            raise ValueError('Voice groups must be ordered, contiguous and disjoint.')
        if unit['id'] in used or not unit['text'].strip():
            raise ValueError('Duplicate unit or empty narration.')
        used.add(unit['id'])
        previous = indices[-1]
        if unit.get('extendHold'):
            hold = next(s for s in base['segments'] if s['id'] == unit['extendHold'])
            if hold['kind'] != 'hold' or hold['id'] not in unit['stages'] or not 0 <= unit['maxExtraSeconds'] <= 3:
                raise ValueError('Only a hold within this group may be extended by at most three seconds.')


def schedule(base, voice_plan, recordings):
    validate_units(base, voice_plan)
    result = copy.deepcopy(base)
    result.update(version=base['version'] + '+minimax', hasVoice=True, hideNarration=True)
    segments = {s['id']: s for s in result['segments']}
    for unit, recording in zip(voice_plan['units'], recordings, strict=True):
        needed = recording['durationSeconds'] + .25  # Allow a small breath after each sentence.
        available = sum(duration(segments[stage]) for stage in unit['stages'])
        excess = max(0, needed - available)
        if excess:
            if not unit.get('extendHold') or excess > unit['maxExtraSeconds']:
                raise ValueError(f'{unit["id"]}: speech needs {needed:.2f}s, scene has {available:.2f}s. Shorten the text and regenerate; audio was not truncated.')
            segments[unit['extendHold']]['duration'] += math.ceil(excess * FPS) / FPS
    starts, elapsed = {}, 0
    for segment in result['segments']:
        starts[segment['id']] = elapsed
        elapsed += duration(segment)
    if elapsed > voice_plan['maxTotalSeconds']:
        raise ValueError('Voice story exceeds maximum duration. Shorten narration.')
    cues = []
    for unit, recording in zip(voice_plan['units'], recordings, strict=True):
        start = starts[unit['stages'][0]]
        cues.append({'id': unit['id'], 'stages': unit['stages'], 'text': unit['text'], 'caption': unit.get('caption', unit['text']),
                     'start': round(start, 6), 'end': round(start + recording['durationSeconds'], 6), **recording})
    result['voiceCues'] = cues
    result['voice'] = {'provider': 'MiniMax', 'model': voice_plan['model'],
                       'language': voice_plan.get('language', 'Chinese'),
                       'voiceId': recordings[0]['voiceId'], 'disclosure': 'AI生成语音解说',
                       'captionGranularity': 'narration unit, not word alignment',
                       'plannedDurationSeconds': elapsed}
    return result


def vtt_time(seconds):
    ms = round(seconds * 1000)
    hours, ms = divmod(ms, 3600000)
    minutes, ms = divmod(ms, 60000)
    sec, ms = divmod(ms, 1000)
    return f'{hours:02}:{minutes:02}:{sec:02}.{ms:03}'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['check', 'dry-run', 'list-voices', 'preview', 'auditions', 'full'])
    parser.add_argument('--env-file', type=Path, default=ROOT.parent / '.qa/minimax.env')
    parser.add_argument('--voice', help='An exact system voice ID verified by get_voice.')
    parser.add_argument('--plan', type=Path, default=HERE / 'voice-plan.json')
    args = parser.parse_args()
    key, api_base = settings(args.env_file)
    voice_plan, base = read_json(args.plan), read_json(HERE / 'story-plan.json')
    voice = args.voice or voice_plan['voiceId']
    validate_units(base, voice_plan)
    if args.action == 'check':
        print(json.dumps({'keyConfigured': bool(key), 'apiBase': api_base, 'model': voice_plan['model'], 'voiceId': voice}, ensure_ascii=False))
        return
    if args.action == 'dry-run':
        segments = {s['id']: s for s in base['segments']}
        print(json.dumps({'apiRequests': 0, 'voiceId': voice, 'units': [
            {'id': u['id'], 'text': u['text'], 'windowSeconds': sum(duration(segments[s]) for s in u['stages']),
             'maxExtraSeconds': u.get('maxExtraSeconds', 0)} for u in voice_plan['units']]}, ensure_ascii=False, indent=2))
        return
    client = MiniMax(key, api_base)
    voices = client.voices()
    if args.action == 'list-voices':
        print(json.dumps(voices, ensure_ascii=False, indent=2))
        return
    available_voices = {v['voice_id'] for v in voices}
    if args.action != 'auditions' and voice not in available_voices:
        raise ApiError('Selected system voice unavailable. Run list-voices and choose an exact ID using --voice.')
    OUT.mkdir(parents=True, exist_ok=True)
    lock = OUT / 'synthesis.lock'
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise ApiError('Another trial owns synthesis.lock. Wait for it to finish; inspect stale locks after a crash.') from None
    try:
        os.close(fd)
        if args.action == 'auditions':
            auditions = read_json(HERE / 'voice-auditions.json')
            samples = []
            for candidate in auditions['candidates']:
                if candidate['voiceId'] not in available_voices:
                    print(f'{candidate["id"]}: selected voice unavailable; skipped.', flush=True)
                    continue
                request = payload(auditions['texts'][candidate['language']], voice_plan, candidate['voiceId'], candidate['language'])
                path, meta, cached = synthesize(client, request, OUT / 'cache')
                target = OUT / f'audition-{candidate["id"]}.wav'
                target.write_bytes(path.read_bytes())
                sample = {**candidate, 'file': target.name, 'durationSeconds': meta['durationSeconds'],
                          'model': voice_plan['model'], 'audioSha256': meta['audioSha256'], 'traceId': meta['traceId'],
                          'text': request['text'], 'aiGenerated': True}
                write_json(target.with_suffix('.json'), sample)
                samples.append(sample)
                write_json(OUT / 'auditions.json', {'samples': samples, 'previousRadioHostRejected': True})
                print(json.dumps({'id': candidate['id'], 'voiceId': candidate['voiceId'], 'audio': str(target),
                                  'seconds': meta['durationSeconds'], 'cached': cached}, ensure_ascii=False), flush=True)
        elif args.action == 'preview':
            path, meta, cached = synthesize(client, payload(voice_plan['previewText'], voice_plan, voice, voice_plan.get('language', 'Chinese')), OUT / 'cache')
            (OUT / 'preview.wav').write_bytes(path.read_bytes())
            write_json(OUT / 'preview.json', {**meta, 'text': voice_plan['previewText'], 'voiceId': voice, 'aiGenerated': True})
            print(json.dumps({'preview': str(OUT / 'preview.wav'), 'seconds': meta['durationSeconds'], 'cached': cached}, ensure_ascii=False))
        else:
            recordings = []
            for unit in voice_plan['units']:
                request = payload(unit['text'], voice_plan, voice, voice_plan.get('language', 'Chinese'), unit.get('emotion'), unit.get('speed'))
                path, meta, cached = synthesize(client, request, OUT / 'cache')
                recordings.append({'audioFile': path.relative_to(ROOT).as_posix(), 'audioSha256': meta['audioSha256'],
                                   'durationSeconds': meta['durationSeconds'], 'voiceId': voice, 'traceId': meta['traceId'],
                                   'emotion': unit.get('emotion'), 'speed': request['voice_setting']['speed']})
                print(f'{unit["id"]}: {meta["durationSeconds"]:.2f}s, cache={cached}', flush=True)
                # Stop on the first overflow rather than paying for every subsequent line.
                partial = {**voice_plan, 'units': voice_plan['units'][:len(recordings)]}
                schedule(base, partial, recordings)
            result = schedule(base, voice_plan, recordings)
            captions = 'WEBVTT\n\n' + '\n\n'.join(f'{c["id"]}\n{vtt_time(c["start"])} --> {vtt_time(c["end"])}\n{c["caption"]}' for c in result['voiceCues']) + '\n'
            (OUT / 'captions-plan.vtt').write_text(captions, encoding='utf-8')
            write_json(OUT / 'story-plan-voice.json', result)
            print(json.dumps({'voicePlan': str(OUT / 'story-plan-voice.json'), 'seconds': result['voice']['plannedDurationSeconds'],
                              'next': 'Run render.py --voice with --ffmpeg and --font.'}, ensure_ascii=False))
    finally:
        lock.unlink(missing_ok=True)


if __name__ == '__main__':
    try:
        main()
    except (ApiError, ValueError, KeyError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
