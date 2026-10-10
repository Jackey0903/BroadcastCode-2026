"""Render the shared possession story with frame-specific on-court annotations.

Only local source video and the verified official event are used. The annotated
ellipses are editorial highlights in image coordinates, not measured coverage.
Requires FFmpeg and Pillow; generated assets stay in product/build/.
"""
import argparse
import hashlib
import json
import math
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from serve import HERE, ROOT, source_file

OUTPUT_FPS = 30
OUTPUT_SIZE = (1280, 720)


def run(command, cwd):
    subprocess.run(command, cwd=cwd, check=True)


def file_hash(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def segment_duration(segment):
    if segment['kind'] == 'hold':
        return segment['duration']
    return (segment['end'] - segment['start']) / segment.get('rate', 1)


def wrap_text(draw, text, font, max_width):
    lines, line = [], ''
    for char in text:
        if line and draw.textlength(line + char, font=font) > max_width:
            lines.append(line)
            line = char
        else:
            line += char
    if line:
        lines.append(line)
    return lines


def rgba(color, alpha=255):
    color = color.lstrip('#')
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4)) + (alpha,)


def arrow(draw, coords, color):
    x1, y1, x2, y2 = coords
    draw.line(coords, fill=color, width=3)
    angle = math.atan2(y2 - y1, x2 - x1)
    points = [(x2, y2)]
    for offset in (-.48, .48):
        points.append((x2 - 13 * math.cos(angle + offset),
                       y2 - 13 * math.sin(angle + offset)))
    draw.polygon(points, fill=color)


def draw_annotation(draw, annotation, fonts):
    color = annotation.get('color', '#ff974f')
    x, y = annotation['x'], annotation['y']
    rx, ry = annotation.get('rx', 0), annotation.get('ry', 0)
    if rx > 0 and ry > 0:
        draw.ellipse((x-rx, y-ry, x+rx, y+ry),
                     fill=rgba(color, 23), outline=rgba(color, 240), width=3)
    if annotation.get('arrow'):
        arrow(draw, annotation['arrow'], rgba(color))
    if annotation.get('label'):
        lx, ly = annotation['lx'], annotation['ly']
        width = draw.textlength(annotation['label'], font=fonts['label']) + 22
        draw.rounded_rectangle((lx, ly, lx+width, ly+31), radius=7,
                               fill=(10, 17, 22, 222), outline=rgba(color, 160), width=1)
        draw.text((lx+11, ly+5), annotation['label'], font=fonts['label'], fill=rgba(color))


def focus_at(track, source_time):
    if not track or source_time < track[0]['t'] or source_time > track[-1]['t']:
        return None
    for left, right in zip(track, track[1:]):
        if left['t'] <= source_time <= right['t']:
            amount = (source_time-left['t']) / (right['t']-left['t'])
            return {key: left[key]+(right[key]-left[key])*amount for key in ('x', 'y', 'rx', 'ry')}
    return None


def make_overlay(segment, plan, story, font_path, source_time=None):
    image = Image.new('RGBA', (plan['width'], plan['height']))
    draw = ImageDraw.Draw(image)
    fonts = {name: ImageFont.truetype(str(font_path), size) for name, size in
             [('chapter', 15), ('title', 25), ('body', 18), ('label', 17), ('metric', 34), ('small', 13)]}
    chapter = segment['chapter']
    width = draw.textlength(chapter, font=fonts['chapter']) + 28
    draw.rounded_rectangle((22, 18, 22+width, 48), radius=8, fill=(10, 17, 22, 214))
    draw.text((36, 23), chapter, font=fonts['chapter'], fill=(255, 168, 99, 255))
    draw.text((23, 60), segment['title'], font=fonts['title'], fill=(255, 255, 255, 255),
              stroke_width=2, stroke_fill=(0, 0, 0, 185))
    lines = wrap_text(draw, segment['narration'], fonts['body'], 864)
    top = 469 - (len(lines)*25+16)
    draw.rounded_rectangle((28, top, 932, 469), radius=8, fill=(8, 16, 22, 205))
    for index, line in enumerate(lines):
        draw.text((46, top+7+index*25), line, font=fonts['body'], fill=(249, 248, 243, 255))
    for annotation in segment.get('annotations', []):
        draw_annotation(draw, annotation, fonts)
    if segment['id'] in ('drive', 'finish') and source_time is not None:
        focus = focus_at(plan.get('focusTrack'), source_time)
        if focus:
            draw_annotation(draw, {**focus, 'color': '#ff974f'}, fonts)
    if segment.get('metric'):
        draw.rounded_rectangle((735, 93, 931, 191), radius=12, fill=(8, 16, 22, 225))
        draw.text((753, 103), '本次出手 · 官方 xFG', font=fonts['small'], fill=(212, 219, 219, 255))
        draw.text((751, 125), story['shotMetric']['display'], font=fonts['metric'], fill=(255, 168, 99, 255))
        draw.text((753, 169), '出手机会的模型参考', font=fonts['small'], fill=(212, 219, 219, 255))
    return image.resize(OUTPUT_SIZE, Image.Resampling.LANCZOS)


def render(sample, ffmpeg, font):
    story = next(s for s in json.loads((ROOT/'product/data/stories.json').read_text(encoding='utf-8'))['stories'] if s['sample'] == sample)
    plan_path = HERE/'story-plan.json'
    plan = json.loads(plan_path.read_text(encoding='utf-8'))
    source = source_file(sample)
    if not source:
        raise ValueError('Restore the original practice video first.')
    source_hash = file_hash(source)
    if source_hash != story['sourceVideoSha256']:
        raise ValueError('Source hash mismatch.')
    if not story['officialEvent']['verified'] or story['shotMetric']['rawValue'] != story['officialEvent']['expectedFg']:
        raise ValueError('The corresponding official shot is not verified.')
    out = ROOT/f'product/build/mlb-rhythm/{sample}'
    frames = out/'frames'
    frames.mkdir(parents=True, exist_ok=True)
    common = [ffmpeg, '-hide_banner', '-loglevel', 'error', '-y']
    # Preserve decoded source frame order. Frame n corresponds to n/source_fps,
    # without synthesizing intermediate images for the frame-step controls.
    run(common + ['-i', str(source), '-map', '0:v:0', '-vf', f"scale={plan['width']}:{plan['height']}",
                  '-fps_mode', 'passthrough', '-q:v', '3', '-start_number', '0', str(frames/'frame-%04d.jpg')], out)
    count = len(list(frames.glob('frame-*.jpg')))
    if count != plan['sourceFrameCount']:
        raise ValueError(f'Source has {count} decoded frames; plan expects {plan["sourceFrameCount"]}.')
    print(f'Extracted {count} exact source frames.', flush=True)
    reverse = plan['reverseWindow']
    reverse_duration = (reverse['end']-reverse['start'])/reverse['rate']
    run(common + ['-ss', str(reverse['start']), '-t', str(reverse['end']-reverse['start']), '-i', str(source),
                  '-an', '-vf', f"reverse,setpts=(PTS-STARTPTS)/{reverse['rate']},scale=1280:720,setsar=1,fps={OUTPUT_FPS}",
                  '-t', str(reverse_duration), '-c:v', 'libx264', '-preset', 'fast', '-crf', '20',
                  '-pix_fmt', 'yuv420p', '-movflags', '+faststart', 'reverse.mp4'], out)
    files, time_map, elapsed, metric_at = [], [], 0, None
    for index, segment in enumerate(plan['segments']):
        duration = segment_duration(segment)
        kind = segment['kind']
        overlay_dir = out/f'overlay-{index:02d}'
        overlay_dir.mkdir(exist_ok=True)
        animated = segment['id'] in ('drive', 'finish')
        if animated:
            for frame in range(math.ceil(duration*OUTPUT_FPS)+1):
                source_time = segment['start']+frame/OUTPUT_FPS*segment.get('rate', 1)
                make_overlay(segment, plan, story, font, source_time).save(overlay_dir/f'{frame:04d}.png')
            overlay_input = ['-framerate', str(OUTPUT_FPS), '-i', str(overlay_dir/'%04d.png')]
        else:
            make_overlay(segment, plan, story, font).save(overlay_dir/'static.png')
            overlay_input = ['-loop', '1', '-framerate', str(OUTPUT_FPS), '-i', str(overlay_dir/'static.png')]
        command = common.copy()
        rate = segment.get('rate', 1)
        video_filter = f'scale=1280:720,setsar=1,fps={OUTPUT_FPS},format=yuv420p,setparams=range=limited:color_primaries=bt709:color_trc=bt709:colorspace=bt709'
        if kind == 'hold':
            frame_index = min(count-1, round(segment['start']*plan['fps']))
            command += ['-loop', '1', '-framerate', str(OUTPUT_FPS), '-i', str(frames/f'frame-{frame_index:04d}.jpg')]
        elif kind == 'reverse':
            command += ['-i', str(out/'reverse.mp4')]
        else:
            command += ['-ss', str(segment['start']), '-t', str(segment['end']-segment['start']), '-i', str(source)]
            video_filter = f'setpts=(PTS-STARTPTS)/{rate},' + video_filter
        command += overlay_input
        if kind == 'play':
            audio_map = '0:a:0'
        else:
            command += ['-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo']
            audio_map = '2:a:0'
        output = f'part-{index:02d}.mp4'
        filters = f'[0:v]{video_filter}[base];[base][1:v]overlay=0:0:shortest=1,format=yuv420p[v]'
        command += ['-filter_complex', filters, '-map', '[v]', '-map', audio_map, '-af', f'atempo={rate if kind == "play" else 1},aresample=48000',
                    '-t', str(duration), '-c:v', 'libx264', '-preset', 'fast', '-crf', '20', '-pix_fmt', 'yuv420p',
                    '-c:a', 'aac', '-b:a', '128k', '-ar', '48000', '-ac', '2', '-video_track_timescale', '90000', output]
        run(command, out)
        files.append(output)
        mapping = {'stage': segment['id'], 'kind': kind, 'outputStart': round(elapsed, 6), 'duration': duration,
                   'sourceStart': segment['start'], 'sourceEnd': segment.get('end', segment['start']), 'rate': rate,
                   'hasAnnotations': bool(segment.get('annotations')) or animated}
        if kind == 'hold':
            mapping['sourceFrameIndex'] = frame_index
            mapping['sourceFrameTimestamp'] = frame_index/plan['fps']
        time_map.append(mapping)
        if segment.get('metric') and metric_at is None:
            metric_at = elapsed
        elapsed += duration
        print(f'Rendered {index+1}/{len(plan["segments"])}: {segment["id"]}', flush=True)
    (out/'concat.txt').write_text(''.join(f"file '{file}'\n" for file in files), encoding='utf-8')
    run(common + ['-f', 'concat', '-safe', '0', '-i', 'concat.txt', '-c', 'copy', '-movflags', '+faststart', 'enhanced.mp4'], out)
    evidence = {'sample': sample, 'planVersion': plan['version'], 'planSha256': file_hash(plan_path),
                'sourceSha256': source_hash, 'outputSha256': file_hash(out/'enhanced.mp4'),
                'officialEvent': story['officialEvent'], 'metric': story['shotMetric'], 'sourceTimeMap': time_map,
                'metricAppearsAfterSeconds': metric_at, 'plannedDurationSeconds': elapsed,
                'sourceFrames': {'count': count, 'fps': plan['fps'], 'numbering': 'zero-based, decoded source frame order'},
                'reverseWindow': reverse, 'annotationBasis': plan['annotationBasis'], 'players': plan['players'],
                'difficulty': plan['difficulty'], 'newAgentInvocation': False, 'preservesSourceTimeline': False,
                'provenance': 'Local deterministic story edit. Full original possession is narrated chronologically after a hook and short reverse bridge.'}
    (out/'evidence.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'video': str(out/'enhanced.mp4'), 'reverse': str(out/'reverse.mp4'),
                      'sourceFrames': count, 'plannedDurationSeconds': elapsed}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--sample', choices=['flagg'], default='flagg')
    parser.add_argument('--ffmpeg', required=True)
    parser.add_argument('--font', required=True)
    args = parser.parse_args()
    render(args.sample, str(Path(args.ffmpeg).resolve()), Path(args.font).resolve())
