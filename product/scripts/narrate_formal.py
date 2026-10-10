#!/usr/bin/env python3
"""Render hash-bound two-host speech on the locked 55-second formal edit.

Backend only. Key comes from DOUBAO_API_KEY or an ignored local .env.doubao.
The final main track ducks broadcast audio; a second track retains the original.
"""
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'product/agent'))
from doubao_tts import MODEL, RESOURCE, synthesize
from narration_agent import validate_dialogue


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(args):
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=180)


def probe(path):
    return json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams',
        '-show_format', '-of', 'json', str(path)], timeout=30))


def render(plan, directory, api_key):
    validate_dialogue({key: value for key, value in plan.items() if key != 'agentCore'})
    directory.mkdir(parents=True, exist_ok=True)
    visual = ROOT / 'product/build/formal-assets/GameBuddy-正式资产联调-v2-55秒.mp4'
    if sha(visual) != plan['visualSha256']:
        raise ValueError('Locked visual input hash differs')
    clips, receipts = [], []
    for cue in plan['cues']:
        instruction = plan['roles'][cue['role']]
        if cue['id'] == 'make':
            instruction += '命中瞬间，兴奋爆发，但不要尖叫，停顿短促。'
        cache_id = hashlib.sha256(json.dumps([cue['text'], cue['role'], instruction, MODEL],
                                            ensure_ascii=False).encode()).hexdigest()[:24]
        mp3 = directory / f'{cache_id}.mp3'
        metadata_path = mp3.with_suffix('.json')
        cached = mp3.exists() and metadata_path.exists()
        if cached:
            metadata = json.loads(metadata_path.read_text())
            if sha(mp3) != metadata['audioSha256']:
                raise ValueError('Cached speech hash mismatch')
        else:
            audio, metadata = synthesize(cue['text'], cue['role'], api_key,
                                        instruction=instruction, speech_rate=5 if cue['role'] == 'A' else 3)
            mp3.write_bytes(audio)
            metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2))
        seconds = float(probe(mp3)['format']['duration'])
        available = cue['end'] - cue['start'] - .06
        tempo = max(1.0, seconds / available)
        if tempo > 1.30:
            raise ValueError(f"Speech cue {cue['id']} exceeds timing budget: {seconds:.2f}s / {available:.2f}s")
        normalized = directory / f"cue-{cue['id']}.wav"
        command(['ffmpeg', '-y', '-v', 'error', '-i', str(mp3), '-af',
            f'atempo={tempo:.8f},loudnorm=I=-17:TP=-2:LRA=6,aresample=48000',
            '-ac', '2', str(normalized)])
        actual = float(probe(normalized)['format']['duration'])
        if actual > available + .025:
            raise ValueError('Fitted audio crossed cue boundary')
        clips.append((normalized, cue))
        receipts.append({**cue, **metadata, 'cacheHit': cached, 'rawDurationSeconds': seconds,
                         'fittedDurationSeconds': actual, 'tempo': tempo})
        print(json.dumps({'cue': cue['id'], 'seconds': round(actual, 3), 'tempo': round(tempo, 3)}), flush=True)
    speech = directory / 'dialogue.wav'
    inputs, filters = [], []
    for index, (path, cue) in enumerate(clips):
        inputs += ['-i', str(path)]
        filters.append(f'[{index}:a]adelay={round(cue["start"]*1000)}:all=1[a{index}]')
    labels = ''.join(f'[a{i}]' for i in range(len(clips)))
    filters.append(f'{labels}amix=inputs={len(clips)}:normalize=0,apad,atrim=duration={plan["durationSeconds"]}[speech]')
    command(['ffmpeg', '-y', '-v', 'error', *inputs, '-filter_complex', ';'.join(filters),
             '-map', '[speech]', '-ar', '48000', '-ac', '2', str(speech)])
    output = ROOT / 'product/build/formal-assets/GameBuddy-正式55秒-豆包双人解说.mp4'
    declaration = directory / 'declaration.txt'
    declaration.write_text(plan['declaration'])
    font = ROOT / 'readiness-lab/build/layer/fonts/NotoSansCJKsc-Regular.otf'
    if not font.is_file():
        candidates = list((ROOT / 'readiness-lab/build/layer').rglob('*.otf'))
        if not candidates:
            raise ValueError('Verified subtitle font missing')
        font = candidates[0]
    # The local media build intentionally has no drawtext filter. A small RGBA
    # declaration uses the same licensed font and is composited without retiming.
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new('RGBA', (1920,1080))
    draw = ImageDraw.Draw(image); typeface = ImageFont.truetype(str(font),22)
    box = draw.textbbox((0,0), plan['declaration'], font=typeface)
    width = box[2]-box[0]; x=(1920-width)//2
    draw.rounded_rectangle((x-12,18,x+width+12,59),radius=8,fill=(0,0,0,150))
    draw.text((x,23),plan['declaration'],font=typeface,fill=(255,255,255,218))
    declaration_png=directory/'declaration.png';image.save(declaration_png)
    mix = ('[1:a]asplit=2[voice][control];'
           '[0:a]volume=0.48[background];'
           '[background][control]sidechaincompress=threshold=0.015:ratio=12:attack=10:release=220[ducked];'
           '[ducked][voice]amix=inputs=2:normalize=0:duration=first,alimiter=limit=0.94:level=false[mix];'
           '[0:v][2:v]overlay=0:0:format=auto[v]')
    command(['ffmpeg', '-y', '-v', 'error', '-i', str(visual), '-i', str(speech),
        '-loop', '1', '-framerate', '60000/1001', '-i', str(declaration_png),
        '-filter_complex', mix, '-map', '[v]', '-map', '[mix]', '-map', '0:a:0',
        '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '22', '-pix_fmt', 'yuv420p',
        '-c:a:0', 'aac', '-b:a:0', '192k', '-c:a:1', 'copy',
        '-metadata:s:a:0', 'title=AI 双人解说 · 豆包语音', '-metadata:s:a:0', 'language=zho',
        '-metadata:s:a:1', 'title=原片广播与特效音', '-disposition:a:0', 'default',
        '-disposition:a:1', '0', '-t', str(plan['durationSeconds']), '-movflags', '+faststart', str(output)])
    measured = probe(output)
    video = next(item for item in measured['streams'] if item['codec_type'] == 'video')
    if (int(video['nb_frames']) != 3300 or video['width'] != 1920 or video['height'] != 1080
            or abs(float(video['duration']) - plan['durationSeconds']) > .02):
        raise ValueError('Narrated movie changed the locked visual timeline')
    command(['ffmpeg', '-v', 'error', '-i', str(output), '-map', '0', '-f', 'null', '-'])
    original = json.loads(visual.with_suffix('.manifest.json').read_text())
    result = copy.deepcopy(original)
    result.update(createdAt=datetime.now(timezone.utc).isoformat(), outputSha256=sha(output),
        sizeBytes=output.stat().st_size, probe=measured, fullDecodePassed=True,
        browserPlaybackPassed=False, visualBaseSha256=plan['visualSha256'], aiNarrationUsed=True,
        narration={'schema': plan['schema'], 'provider': 'doubao', 'apiVersion': 'v3', 'model': MODEL,
                   'resource': RESOURCE, 'declaration': plan['declaration'], 'dualHost': True,
                   'planSha256': hashlib.sha256(json.dumps(plan, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
                   'audioSha256': sha(speech), 'cues': receipts,
                   'agentCore': plan.get('agentCore', {'invoked': False}),
                   'mix': 'timed_two_hosts_with_sidechain_ducking_and_original_second_track'})
    result['audio'] = {'aiSpeech': True, 'originalBroadcastRetained': True, 'tracks': 2,
                       'durationSeconds': plan['durationSeconds'], 'speechSha256': sha(speech)}
    output.with_suffix('.manifest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    safe = {key: result[key] for key in ('createdAt','sourceSha256','outputSha256','sizeBytes',
        'durationSeconds','frameCount','fullDecodePassed','visualBaseSha256','aiNarrationUsed','narration')}
    (ROOT / 'product/evidence/formal-doubao-20261010.json').write_text(json.dumps(safe, ensure_ascii=False, indent=2))
    print(json.dumps({'output': str(output), 'sha256': result['outputSha256'], 'bytes': result['sizeBytes'],
                      'seconds': result['durationSeconds'], 'fullDecodePassed': True}), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, default=ROOT / 'product/data/formal-dialogue.json')
    args = parser.parse_args()
    key = os.environ.get('DOUBAO_API_KEY')
    if not key:
        file = ROOT / '.env.doubao'
        key = dict(line.split('=', 1) for line in file.read_text().splitlines() if '=' in line).get('DOUBAO_API_KEY')
    render(json.loads(args.plan.read_text()), ROOT / 'product/build/doubao', key)


if __name__ == '__main__':
    main()
