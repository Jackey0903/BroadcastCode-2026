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


def draw_focus_card(image, segment, plan, fonts, source_image):
    focus = segment['magnifier']
    draw = ImageDraw.Draw(image)
    color = '#75d6e8'
    player = next(p for p in plan['players'] if p['id'] == focus['playerId'])
    cx, cy, radius = focus['center']
    box = focus['crop']
    # Enlarge pixels from the same source frame; keep their aspect ratio intact.
    crop = source_image.crop(box).convert('RGBA').resize((radius*2, radius*2), Image.Resampling.LANCZOS)
    crop_draw = ImageDraw.Draw(crop)
    scale = radius*2/(box[2]-box[0])
    target = focus['target']
    tx, ty = (target[0]-box[0])*scale, (target[1]-box[1])*scale
    crop_draw.ellipse((tx-25*scale, ty-58*scale, tx+25*scale, ty+58*scale),
                      outline=rgba(color), width=3)
    mask = Image.new('L', crop.size)
    ImageDraw.Draw(mask).ellipse((2, 2, radius*2-3, radius*2-3), fill=255)
    draw.ellipse((cx-radius-7, cy-radius-7, cx+radius+7, cy+radius+7), fill=(4, 14, 18, 235))
    image.paste(crop, (cx-radius, cy-radius), mask)
    draw.ellipse((cx-radius, cy-radius, cx+radius, cy+radius), outline=rgba(color), width=4)
    lx, ly = focus['card']
    draw.rounded_rectangle((lx, ly, lx+280, ly+116), radius=10, fill=(4, 17, 23, 240), outline=rgba(color), width=2)
    draw.text((lx+16, ly+10), f"#{player['jersey']}  {player['name']}", font=fonts['title'], fill=rgba(color))
    draw.text((lx+16, ly+47), f"身高 {player['height']}", font=fonts['body'], fill=(255, 255, 255, 255))
    draw.text((lx+16, ly+74), f"臂展 {player.get('wingspanDisplay', '约2.18米')}", font=fonts['body'], fill=(255, 255, 255, 255))
    draw.text((lx+16, ly+98), focus['sourceNote'], font=fonts['small'], fill=(165, 186, 193, 255))
    draw.text((cx-radius+12, cy-radius-26), '同帧局部放大', font=fonts['small'], fill=rgba(color))
    arrow(draw, focus['leader'], rgba(color, 225))
    for spot in focus['spots']:
        x, y, rx, ry = spot['ellipse']
        ink = spot['color']
        draw.ellipse((x-rx, y-ry, x+rx, y+ry), fill=rgba(ink, 38), outline=rgba(ink), width=3)
        if spot.get('label'):
            draw.text((x-rx, y+ry+5), spot['label'], font=fonts['label'], fill=rgba(ink), stroke_width=2, stroke_fill=(0, 0, 0, 230))
    bx, by = focus['ball']
    draw.ellipse((bx-13, by-13, bx+13, by+13), outline=(255, 226, 96, 255), width=3)
    draw.text((bx+18, by-13), '球', font=fonts['label'], fill=(255, 226, 96, 255), stroke_width=2, stroke_fill=(0, 0, 0, 230))


def make_overlay(segment, plan, story, font_path, source_time=None, source_image=None):
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
    if segment.get('magnifier') and source_image is not None:
        draw_focus_card(image, segment, plan, fonts, source_image)
    else:
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
            source_image = None
            if segment.get('magnifier'):
                frame_index = min(count-1, round(segment['start']*plan['fps']))
                source_image = Image.open(frames/f'frame-{frame_index:04d}.jpg').convert('RGB')
            make_overlay(segment, plan, story, font, source_image=source_image).save(overlay_dir/'static.png')
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
