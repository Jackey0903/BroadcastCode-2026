#!/usr/bin/env python3
"""Produce a local PPT movie using original MOSS English commentator voices.

No AWS calls or publication. New outputs never overwrite the submitted movie.
MOSS API synthesis is remote; all fitting, mixing and media export is local.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'product/agent'))
from moss_tts import MODELS, MossError, MossTTS

SOURCE_SHA = 'f2c0fb6aa1ec10bd78ea9e6724190b7f03bf48f21af2f743c694bbdb49254c91'
VISUAL_SHA = 'fa0e6805cb0f64fafcbb816e8e5d0d08a2543246a701975197beec409db24e6b'
DURATION = 55.055


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def command(args):
    try:
        subprocess.run(args, check=True, stdout=subprocess.DEVNULL,
                       stderr=subprocess.PIPE, timeout=240)
    except subprocess.CalledProcessError as error:
        raise ValueError(error.stderr.decode(errors='replace')[-1500:]) from None


def probe(path):
    return json.loads(subprocess.check_output(['ffprobe', '-v', 'error',
        '-show_streams', '-show_format', '-of', 'json', str(path)], timeout=30))


def validate(plan):
    if (plan.get('schema') != 'gamebuddy-moss-dialogue-v1'
            or plan.get('sourceSha256') != SOURCE_SHA
            or plan.get('visualSha256') != VISUAL_SHA
            or plan.get('durationSeconds') != DURATION
            or plan.get('language') != 'English'
            or set(plan.get('roles', {})) != {'A', 'B'}):
        raise ValueError('English dialogue must bind to the formal 55-second edit')
    facts = plan.get('facts', {})
    if (facts.get('eventId') != 273 or facts.get('gameId') != '0022500356'
            or facts.get('expectedFg') != .3 or facts.get('officialTrackingAvailable') is not False):
        raise ValueError('Formal basketball facts changed')
    allowed = {'formal-frame-review', 'formal-final-shot', 'pbp-270', 'pbp-272', 'pbp-273'}
    previous, ids, roles = 0, set(), set()
    for cue in plan.get('cues', []):
        a, b = cue['start'], cue['end']
        if (not all(isinstance(x, (int, float)) and not isinstance(x, bool)
                    and math.isfinite(x) for x in (a, b))
                or a < previous or not a < b <= DURATION
                or not re.fullmatch('[a-z-]{1,31}', cue['id']) or cue['id'] in ids
                or cue['role'] not in plan['roles'] or not 1 <= len(cue['text']) <= 180
                or not cue['evidenceIds'] or not set(cue['evidenceIds']) <= allowed):
            raise ValueError('Invalid source-bound English cue')
        if a < 30.79 and ('formal-final-shot' in cue['evidenceIds']
                or re.search(r'\b(bank|glass|percent|made|ties|forty.three)\b', cue['text'], re.I)):
            raise ValueError('Result narrated before the visible basket')
        if re.search(r'\b(free.throw|four.point|assist|automatic.track|guaranteed)\b', cue['text'], re.I):
            raise ValueError('Unsupported formal-video claim')
        previous = b; ids.add(cue['id']); roles.add(cue['role'])
    if not 2 <= len(ids) <= 20 or roles != {'A', 'B'}:
        raise ValueError('Bounded two-host dialogue is required')
    return plan


def load_key(file):
    key = os.environ.get('MOSS_API_KEY')
    if not key and file.is_file():
        values = dict(line.split('=', 1) for line in file.read_text().splitlines()
                      if '=' in line and not line.lstrip().startswith('#'))
        key = values.get('MOSS_API_KEY', '').strip().strip('\"\'')
    if not key:
        raise MossError('Save MOSS_API_KEY in the ignored local .env.moss file')
    return key


def fit_cue(provider, voices, cue, directory, preferred):
    available = cue['end'] - cue['start'] - .08
    attempts = []
    # TTSD preserves the two designed cast identities. Flash additionally
    # provides a native duration hint for unusually tight output windows.
    models = [preferred] + ([] if preferred == 'moss-tts-1.5-flash'
                            else ['moss-tts-1.5-flash'])
    for model in models:
        identity = json.dumps([model, cue['text'], voices[cue['role']], available], sort_keys=True)
        cache_id = hashlib.sha256(identity.encode()).hexdigest()[:24]
        raw = directory / f'{cache_id}.wav'; receipt_file = raw.with_suffix('.json')
        cached = raw.is_file() and receipt_file.is_file()
        if cached:
            receipt = json.loads(receipt_file.read_text())
            if sha(raw) != receipt['audioSha256']:
                raise ValueError('MOSS speech cache hash mismatch')
        else:
            audio, receipt = provider.synthesize(cue['text'], cue['role'], voices,
                                                model=model, duration=available)
            raw.write_bytes(audio)
            receipt_file.write_text(json.dumps(receipt, ensure_ascii=False, indent=2))
        trimmed = directory / f'{cache_id}-trimmed.wav'
        # Remove generated outer silence, keeping the actual utterance intact.
        trim = ('silenceremove=start_periods=1:start_duration=0.04:start_threshold=-50dB:'
                'start_silence=0.06,areverse,'
                'silenceremove=start_periods=1:start_duration=0.04:start_threshold=-50dB:'
                'start_silence=0.10,areverse')
        command(['ffmpeg', '-y', '-v', 'error', '-i', str(raw), '-af', trim,
                 '-ar', '48000', '-ac', '2', str(trimmed)])
        raw_seconds = float(probe(raw)['format']['duration'])
        speech_seconds = float(probe(trimmed)['format']['duration'])
        tempo = max(1.0, speech_seconds / available)
        attempts.append({'model': model, 'rawSeconds': raw_seconds,
                         'trimmedSeconds': speech_seconds, 'tempo': tempo})
        if tempo > 1.30:
            continue
        fitted = directory / f"cue-{cue['id']}.wav"
        command(['ffmpeg', '-y', '-v', 'error', '-i', str(trimmed), '-af',
            f'atempo={tempo:.8f},loudnorm=I=-17:TP=-1.5:LRA=8,aresample=48000',
            '-ar', '48000', '-ac', '2', str(fitted)])
        fitted_seconds = float(probe(fitted)['format']['duration'])
        if not .15 <= fitted_seconds <= available + .025:
            raise ValueError('Fitted MOSS cue crossed the editing boundary')
        record = {**cue, **receipt, 'cacheHit': cached, 'rawDurationSeconds': raw_seconds,
                  'fittedDurationSeconds': fitted_seconds, 'tempo': tempo, 'attempts': attempts}
        print(json.dumps({'cue': cue['id'], 'model': model,
                          'seconds': round(fitted_seconds, 3), 'tempo': round(tempo, 3)}), flush=True)
        return fitted, record
    raise ValueError(f"Cue {cue['id']} is too long; revise its text rather than truncate words")


def subtitle_time(seconds):
    ms = round(seconds * 1000)
    return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'


def render(plan, directory, key, preferred, *, sample=False):
    validate(plan)
    visual = (ROOT / plan['visualPath']).resolve()
    if not visual.is_relative_to(ROOT / 'product/build'):
        raise ValueError('Visual master must be a local registered build asset')
    if sha(visual) != VISUAL_SHA:
        raise ValueError('Locked visual input hash differs')
    master = json.loads(visual.with_suffix('.manifest.json').read_text())
    if (master.get('sourceSha256') != SOURCE_SHA or master.get('presentationClean') is not True
            or master.get('frameCount') != 3300 or master.get('durationSeconds') != DURATION):
        raise ValueError('Clean PPT master does not match the formal edit')
    provider = MossTTS(key, directory)
    voices = provider.voices(plan['roles'])
    cues = [cue for cue in plan['cues'] if not sample or cue['id'] in ('make', 'second-chance')]
    with ThreadPoolExecutor(max_workers=2) as pool:
        clips = list(pool.map(lambda cue: fit_cue(provider, voices, cue, directory, preferred), cues))
    if sample:
        return {'sampleOnly': True, 'clips': [str(path) for path, _ in clips]}
    speech = directory / 'dialogue-en.wav'
    inputs, filters = [], []
    for index, (path, cue) in enumerate(clips):
        inputs += ['-i', str(path)]
        filters.append(f'[{index}:a]adelay={round(cue["start"]*1000)}:all=1[a{index}]')
    labels = ''.join(f'[a{i}]' for i in range(len(clips)))
    filters.append(f'{labels}amix=inputs={len(clips)}:normalize=0,apad,atrim=duration={DURATION}[speech]')
    command(['ffmpeg', '-y', '-v', 'error', *inputs, '-filter_complex', ';'.join(filters),
             '-map', '[speech]', '-ar', '48000', '-ac', '2', str(speech)])
    for lang, field in [('en', 'text'), ('zh', 'subtitleZh')]:
        (directory / f'commentary.{lang}.srt').write_text('\n\n'.join(
            f'{i+1}\n{subtitle_time(c["start"])} --> {subtitle_time(c["end"])}\n{c[field]}'
            for i, c in enumerate(cues)) + '\n')
    output = ROOT / 'product/build/ppt-demo-20261011/GameBuddy-PPT-55s-MOSS-English.mp4'
    # Attenuate centered broadcast speech before ducking. This is a stereo mix
    # technique, not source separation or a claim of isolated crowd stems.
    mix = ('[0:a]pan=stereo|c0=0.55*c0-0.45*c1|c1=0.55*c1-0.45*c0,'
           'highpass=f=70,lowpass=f=10000,volume=0.7[background];'
           '[1:a]asplit=2[voice][control];'
           '[background][control]sidechaincompress=threshold=0.012:ratio=10:'
           'attack=8:release=240[ducked];'
           '[ducked][voice]amix=inputs=2:normalize=0:duration=first,'
           'alimiter=limit=0.94:level=false[mix]')
    command(['ffmpeg', '-y', '-v', 'error', '-i', str(visual), '-i', str(speech),
        '-filter_complex', mix, '-map', '0:v:0', '-map', '[mix]', '-c:v', 'copy',
        '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2',
        '-metadata:s:a:0', 'title=English two-host commentary',
        '-metadata:s:a:0', 'language=eng', '-metadata', 'title=GameBuddy · Second Chance',
        '-t', str(DURATION), '-movflags', '+faststart', str(output)])
    measured = probe(output)
    video = next(s for s in measured['streams'] if s['codec_type'] == 'video')
    audio = next(s for s in measured['streams'] if s['codec_type'] == 'audio')
    if (int(video['nb_frames']) != 3300 or video['width'] != 1920 or video['height'] != 1080
            or abs(float(video['duration']) - DURATION) > .02 or audio['codec_name'] != 'aac'):
        raise ValueError('PPT movie changed the fixed timeline or output format')
    command(['ffmpeg', '-v', 'error', '-i', str(output), '-map', '0', '-f', 'null', '-'])
    receipt = {'schema': 'gamebuddy-moss-local-commentary-v1',
        'createdAt': datetime.now(timezone.utc).isoformat(), 'output': str(output.relative_to(ROOT)),
        'sourceSha256': SOURCE_SHA, 'visualSha256': VISUAL_SHA, 'outputSha256': sha(output),
        'sizeBytes': output.stat().st_size, 'durationSeconds': DURATION, 'frameCount': 3300,
        'probe': measured, 'fullDecodePassed': True, 'published': False,
        'humanVoiceReviewPassed': False, 'pptPlaybackTested': False,
        'agentCoreInvokedThisRun': False, 'rlInvokedThisRun': False,
        'remoteProvider': 'MOSS official API', 'localStages': ['fitting', 'mixing', 'video_export'],
        'voiceDesign': 'Original voices from text descriptions; no real commentator references',
        'planSha256': hashlib.sha256(json.dumps(plan, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
        'planHashBasis': 'canonical JSON with sorted keys',
        'speechSha256': sha(speech), 'cues': [record for _, record in clips],
        'declaration': plan['declaration'], 'declarationLocation': 'project documentation, outside video',
        'presentationClean': True, 'presentationEnglish': bool(master.get('presentationEnglish')),
        'videoCodecCopiedFromVisualMaster': True,
        'mix': 'centered broadcast speech attenuated, sidechain ducked; no isolated crowd claim'}
    output.with_suffix('.manifest.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2))
    (ROOT / 'product/evidence/formal-moss-english-20261011.json').write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'output': str(output), 'seconds': DURATION,
                      'sha256': receipt['outputSha256'], 'fullDecodePassed': True}), flush=True)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--key-file', type=Path, default=ROOT / '.env.moss')
    parser.add_argument('--plan', type=Path, default=ROOT / 'product/data/formal-dialogue-en.json')
    parser.add_argument('--model', choices=MODELS, default='moss-tts-1.5-flash')
    parser.add_argument('--sample', action='store_true')
    parser.add_argument('--workdir', type=Path, default=ROOT / 'product/build/moss')
    args = parser.parse_args()
    render(json.loads(args.plan.read_text()), args.workdir,
           load_key(args.key_file), args.model, sample=args.sample)


if __name__ == '__main__':
    main()
