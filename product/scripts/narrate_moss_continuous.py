#!/usr/bin/env python3
"""Synthesize approved continuous dialogue, then optionally join its visual master.

MOSS synthesis is remote; trimming, timing, mixing and export are local. No AWS
resources, cloud publication, visual overlays or previous outputs are changed.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import urllib.error
import urllib.request

from narrate_moss import ROOT, SOURCE_SHA, DURATION, command, load_key, probe, sha
from moss_tts import API, MossError, MossTTS, NoRedirect

MODEL = 'moss-tts-1.5-flash'
RATE = 48000
FRAMES = 3300
DEFAULT_DIR = ROOT / 'product/build/moss-continuous-v2'


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def validate(plan):
    if (plan.get('schema') != 'gamebuddy-moss-dialogue-v2'
            or plan['sourceVideo']['sha256'] != SOURCE_SHA
            or plan.get('durationSeconds') != DURATION
            or plan.get('language') != 'English'
            or not plan['verification'].get('scriptUserApproved')
            or set(plan.get('casting', {})) != {'A', 'B'}):
        raise ValueError('An approved, source-bound two-host plan is required')
    if sha(ROOT / plan['sourceVideo']['path']) != SOURCE_SHA:
        raise ValueError('Formal source changed')
    previous = .08
    for cue in plan['cues']:
        if (abs(cue['start'] - previous) > .00001 or cue['end'] <= cue['start']
                or cue['speaker'] not in ('A', 'B')
                or not re.fullmatch(r'[a-z-]{1,40}', cue['id'])
                or not 1 <= len(cue['text']) <= 180
                or not set(cue['evidenceIds']) <= set(plan['evidence'])):
            raise ValueError('Non-contiguous or invalid narration cue')
        previous = cue['end']
    if abs(previous - 55) > .001:
        raise ValueError('Dialogue must cover the full approved window')
    for name in ('game-efg', 'season-gravity'):
        evidence = plan['evidence'][name]
        if sha(ROOT / evidence['path']) != evidence['sha256']:
            raise ValueError('Narrated numerical source changed')
    return plan


def speech_clip(provider, voices, cue, directory, next_speaker):
    gap = .025 if next_speaker == cue['speaker'] else .055
    available = cue['end'] - cue['start'] - gap
    payload_identity = [MODEL, voices[cue['speaker']], cue['text'], available]
    cache_id = hashlib.sha256(json.dumps(payload_identity).encode()).hexdigest()[:24]
    raw = directory / (cache_id + '.wav')
    cache = raw.with_suffix('.json')
    cached = raw.is_file() and cache.is_file()
    if cached:
        receipt = json.loads(cache.read_text())
        if sha(raw) != receipt['audioSha256']:
            raise ValueError('MOSS cache audio changed')
    else:
        audio, receipt = provider.synthesize(cue['text'], cue['speaker'], voices,
                                            model=MODEL, duration=available)
        raw.write_bytes(audio)
        save(cache, receipt)
    trimmed = directory / (cache_id + '-connected.wav')
    # Remove long generated silence while retaining consonant edges and breaths.
    trim = ('silenceremove=start_periods=1:start_duration=0.02:start_threshold=-50dB:'
            'start_silence=0.015,areverse,'
            'silenceremove=start_periods=1:start_duration=0.02:start_threshold=-50dB:'
            'start_silence=0.015,areverse,'
            'silenceremove=stop_periods=-1:stop_duration=0.14:'
            'stop_threshold=-42dB:stop_silence=0.045')
    command(['ffmpeg', '-y', '-v', 'error', '-i', str(raw), '-af', trim,
             '-ar', str(RATE), '-ac', '2', str(trimmed)])
    seconds = float(probe(trimmed)['format']['duration'])
    tempo = seconds / (available - .01)
    if not .65 <= tempo <= 1.30:
        raise ValueError(f'Unnatural tempo for {cue["id"]}: {tempo:.3f}; revise delivery')
    fitted = directory / ('cue-' + cue['id'] + '.wav')
    samples = round(available * RATE)
    target_level = -15.8 if cue['id'] == 'make' else -17.2
    # Both slowing and accelerating speech prevent silent padding of short cues.
    filters = (f'atempo={tempo:.9f},loudnorm=I={target_level}:TP=-1.5:LRA=8,'
               f'aresample={RATE},apad=whole_len={samples},atrim=end_sample={samples}')
    command(['ffmpeg', '-y', '-v', 'error', '-i', str(trimmed), '-af', filters,
             '-ar', str(RATE), '-ac', '2', str(fitted)])
    record = {**cue, **receipt, 'cacheHit': cached, 'rawSeconds': float(probe(raw)['format']['duration']),
              'connectedSeconds': seconds, 'tempo': tempo, 'handoffGapSeconds': gap,
              'fittedSeconds': samples / RATE, 'fittedSha256': sha(fitted)}
    print(json.dumps({'cue': cue['id'], 'seconds': round(samples / RATE, 3),
                      'tempo': round(tempo, 3), 'cacheHit': cached}), flush=True)
    return fitted, record


def silence_windows(path):
    result = subprocess.run(['ffmpeg', '-hide_banner', '-i', str(path),
        '-af', 'silencedetect=noise=-42dB:d=0.25', '-f', 'null', '-'],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, check=True)
    starts = re.findall(r'silence_start: ([0-9.]+)', result.stderr)
    ends = re.findall(r'silence_end: ([0-9.]+) \| silence_duration: ([0-9.]+)', result.stderr)
    return [{'start': float(a), 'end': float(b), 'duration': float(d)}
            for a, (b, d) in zip(starts, ends)]


def subtitle_time(seconds):
    ms = round(seconds * 1000)
    return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'


def generate(plan, directory, key):
    validate(plan)
    directory.mkdir(parents=True, exist_ok=True)
    print('Designing two contrasting, energetic original commentator voices.', flush=True)
    provider = MossTTS(key, directory)
    voices = provider.voices(plan['casting'])
    print('Both original voices are ready; synthesizing approved dialogue.', flush=True)
    cues = plan['cues']
    jobs = [(cue, cues[i + 1]['speaker'] if i + 1 < len(cues) else None)
            for i, cue in enumerate(cues)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        clips = list(pool.map(lambda job: speech_clip(provider, voices, job[0], directory, job[1]), jobs))
    speech = directory / 'GameBuddy-55s-English-Commentary-v2.wav'
    inputs, filters = [], []
    for i, (path, cue) in enumerate(clips):
        inputs += ['-i', str(path)]
        filters.append(f'[{i}:a]adelay={round(cue["start"] * RATE)}S:all=1[a{i}]')
    labels = ''.join(f'[a{i}]' for i in range(len(clips)))
    filters.append(f'{labels}amix=inputs={len(clips)}:normalize=0,'
        f'alimiter=limit=0.94:level=false:latency=true,apad,'
        f'atrim=end_sample={round(DURATION * RATE)}[speech]')
    command(['ffmpeg', '-y', '-v', 'error', *inputs, '-filter_complex', ';'.join(filters),
             '-map', '[speech]', '-ar', str(RATE), '-ac', '2', str(speech)])
    audition = directory / 'GameBuddy-55s-English-Commentary-v2.mp3'
    command(['ffmpeg', '-y', '-v', 'error', '-i', str(speech), '-c:a', 'libmp3lame',
             '-b:a', '192k', str(audition)])
    for lang, field in [('en', 'text'), ('zh', 'translationZh')]:
        (directory / f'commentary.{lang}.srt').write_text('\n\n'.join(
            f'{i+1}\n{subtitle_time(c["start"])} --> {subtitle_time(c["end"])}\n{c[field]}'
            for i, c in enumerate(cues)) + '\n')
    pauses = silence_windows(speech)
    receipt = {'schema': 'gamebuddy-moss-continuous-audio-v2',
        'createdAt': datetime.now(timezone.utc).isoformat(),
        'planSha256': hashlib.sha256(json.dumps(plan, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
        'scriptUserApproved': True, 'ttsGenerated': True, 'model': MODEL,
        'speechPath': str(speech.relative_to(ROOT)), 'speechSha256': sha(speech),
        'auditionPath': str(audition.relative_to(ROOT)), 'auditionSha256': sha(audition),
        'durationSeconds': float(probe(speech)['format']['duration']),
        'audioOnlyDeliveredBeforeVisualMerge': True,
        'pausesOver250msAtMinus42db': pauses,
        'cues': [record for _, record in clips], 'humanVoiceStyleApproved': False,
        'remoteProvider': 'MOSS official API', 'voiceReferencePerson': None,
        'localFitting': 'Outer and long internal silence shortened, both-direction tempo fitting; 25–55ms nominal handoffs',
        'awsInvoked': False, 'published': False}
    save(directory / 'audio-receipt.json', receipt)
    save(ROOT / 'product/evidence/formal-moss-continuous-audio-20261011.json', receipt)
    print(json.dumps({'audition': str(audition), 'speech': str(speech),
                      'duration': receipt['durationSeconds'], 'longPauses': pauses}), flush=True)
    return receipt


def latest_visual(plan):
    candidates = []
    for manifest in (ROOT / 'product/build/ppt-demo-20261011').glob('english-v*/GameBuddy-PPT-English-v*.manifest.json'):
        master = json.loads(manifest.read_text())
        if (master.get('sourceSha256') == SOURCE_SHA and master.get('presentationClean') is True
                and master.get('fullDecodePassed') is True and master.get('frameCount') == FRAMES
                and master.get('durationSeconds') == DURATION):
            video = manifest.with_name(manifest.name.removesuffix('.manifest.json') + '.mp4')
            if video.is_file():
                candidates.append((int(re.search(r'english-v(\d+)', str(manifest))[1]), video, master))
    if not candidates:
        raise ValueError('Latest verified clean visual master is unavailable')
    _, visual, master = max(candidates, key=lambda item: item[0])
    if sha(visual) != master['outputSha256']:
        raise ValueError('Visual hash does not match its completed manifest')
    return visual, master


def transcribe(directory, key, *, audio_path=None):
    """Check actual spoken content with one official English-capable ASR call."""
    speech = audio_path or directory / 'GameBuddy-55s-English-Commentary-v2.wav'
    audio_hash = sha(speech)
    target = directory / ('transcription-' + speech.stem + '.json' if audio_path else 'transcription.json')
    if target.is_file():
        result = json.loads(target.read_text())
        if result.get('speechSha256') == audio_hash:
            return result
    boundary = 'GameBuddyAudioBoundary20261011'
    body = bytearray()
    for name, value in [('model', 'moss-transcribe-diarize-pro'),
                        ('response_format', 'json'), ('diarize', 'true')]:
        body.extend((f'--{boundary}\r\nContent-Disposition: form-data; '
                     f'name="{name}"\r\n\r\n{value}\r\n').encode())
    body.extend((f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
                 'filename="commentary.wav"\r\nContent-Type: audio/wav\r\n\r\n').encode())
    body.extend(speech.read_bytes())
    body.extend(f'\r\n--{boundary}--\r\n'.encode())
    request = urllib.request.Request(API + '/v1/audio/transcriptions', data=bytes(body),
        headers={'Authorization': 'Bearer ' + key,
                 'Content-Type': 'multipart/form-data; boundary=' + boundary})
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=150) as response:
            result = json.loads(response.read(2 * 1024 * 1024))
    except urllib.error.HTTPError as error:
        raise MossError(f'MOSS transcription HTTP {error.code}') from None
    result.update(speechSha256=audio_hash, model='moss-transcribe-diarize-pro',
                  humanVoiceStyleApproval=False)
    save(target, result)
    print(json.dumps({'transcribedText': result.get('text'),
                      'segments': len(result.get('segments', []))}), flush=True)
    return result


def merge(plan, directory):
    validate(plan)
    receipt = json.loads((directory / 'audio-receipt.json').read_text())
    speech = ROOT / receipt['speechPath']
    if sha(speech) != receipt['speechSha256']:
        raise ValueError('Approved audio changed')
    if receipt['planSha256'] != hashlib.sha256(json.dumps(plan, sort_keys=True, ensure_ascii=False).encode()).hexdigest():
        raise ValueError('Narration plan changed after synthesis')
    visual, master = latest_visual(plan)
    output = ROOT / 'product/build/ppt-demo-20261011/GameBuddy-PPT-55s-MOSS-Continuous-v2.mp4'
    mix = ('[0:a]pan=stereo|c0=0.55*c0-0.45*c1|c1=0.55*c1-0.45*c0,'
        'highpass=f=70,lowpass=f=10000,volume=0.55[background];'
        '[1:a]asplit=2[voice][control];'
        '[background][control]sidechaincompress=threshold=0.012:ratio=10:'
        'attack=8:release=180[ducked];'
        '[ducked][voice]amix=inputs=2:normalize=0:duration=first,'
        'alimiter=limit=0.94:level=false:latency=true[mix]')
    command(['ffmpeg', '-y', '-v', 'error', '-i', str(visual), '-i', str(speech),
        '-filter_complex', mix, '-map', '0:v:0', '-map', '[mix]', '-c:v', 'copy',
        '-c:a', 'aac', '-b:a', '192k', '-ar', str(RATE), '-ac', '2',
        '-metadata:s:a:0', 'language=eng', '-metadata:s:a:0', 'title=English two-host commentary',
        '-t', str(DURATION), '-movflags', '+faststart', str(output)])
    measured = probe(output)
    video = next(s for s in measured['streams'] if s['codec_type'] == 'video')
    if (int(video['nb_frames']) != FRAMES or abs(float(video['duration']) - DURATION) > .02
            or video['width'] != 1920 or video['height'] != 1080):
        raise ValueError('Merged movie changed the visual timeline')
    command(['ffmpeg', '-v', 'error', '-i', str(output), '-map', '0', '-f', 'null', '-'])
    video_hashes = [subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(path),
        '-map', '0:v:0', '-c:v', 'copy', '-f', 'hash', '-hash', 'sha256', '-'],
        text=True).strip().split('=')[-1] for path in (visual, output)]
    if video_hashes[0] != video_hashes[1]:
        raise ValueError('Merged video stream differs from the clean visual master')
    record = {'schema': 'gamebuddy-moss-continuous-movie-v2',
        'createdAt': datetime.now(timezone.utc).isoformat(), 'output': str(output.relative_to(ROOT)),
        'outputSha256': sha(output), 'sizeBytes': output.stat().st_size,
        'visualPath': str(visual.relative_to(ROOT)), 'visualSha256': master['outputSha256'],
        'speechSha256': sha(speech), 'audioReceiptPath': str((directory / 'audio-receipt.json').relative_to(ROOT)),
        'durationSeconds': DURATION, 'frameCount': FRAMES, 'probe': measured,
        'fullDecodePassed': True, 'videoStreamCopied': True, 'addedVisualOverlays': False,
        'encodedVideoStreamSha256': video_hashes[0], 'videoStreamIdentityVerified': True,
        'humanVoiceStyleApproved': False, 'pptPlaybackTested': False,
        'awsInvoked': False, 'published': False,
        'backgroundMix': 'Centered original commentary attenuated and ducked; no isolated crowd claim'}
    save(output.with_suffix('.manifest.json'), record)
    save(ROOT / 'product/evidence/formal-moss-continuous-movie-20261011.json', record)
    print(json.dumps({'movie': str(output), 'visual': str(visual),
                      'seconds': DURATION, 'sha256': record['outputSha256']}), flush=True)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, default=ROOT / 'product/data/formal-dialogue-en-v2.json')
    parser.add_argument('--workdir', type=Path, default=DEFAULT_DIR)
    parser.add_argument('--key-file', type=Path, default=ROOT / '.env.moss')
    parser.add_argument('--merge-only', action='store_true')
    parser.add_argument('--transcribe-only', action='store_true')
    parser.add_argument('--transcribe-file', type=Path)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    if args.transcribe_only:
        transcribe(args.workdir, load_key(args.key_file), audio_path=args.transcribe_file)
    elif args.merge_only:
        merge(plan, args.workdir)
    else:
        generate(plan, args.workdir, load_key(args.key_file))


if __name__ == '__main__':
    main()
