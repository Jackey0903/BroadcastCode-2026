#!/usr/bin/env python3
"""Render the formal cut with the library's original camera-to-board scenes."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import multiprocessing
from pathlib import Path
import subprocess
import time

import cv2

from formal import render as base
from formal.audio import build_audio
from formal.timeline import FRAME_COUNT, DURATION, SEGMENTS, SOURCE_SHA256, locate_frame
from formal_scene_renderer import render_scene

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def chunk(job):
    workdir, output, start, end, variant, presentation_clean, presentation_english = job
    base.init(workdir)
    if variant == 'flagg55':
        import formal_v2_render as renderer
        renderer.init(workdir, presentation_english=presentation_english)
    base.fx.SHOW_PRODUCTION_NOTES = not presentation_clean
    cv2.setNumThreads(1)
    target = Path(output) / f'{start:04d}.mp4'
    command = ['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pixel_format', 'bgr24',
               '-video_size', '1920x1080', '-framerate', '60000/1001', '-i', 'pipe:0',
               '-an', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '19',
               '-pix_fmt', 'yuv420p', '-threads', '2', str(target)]
    encoder = subprocess.Popen(command, stdin=subprocess.PIPE)
    try:
        for frame in range(start, end):
            if variant == 'flagg55':
                image = renderer.render(frame)
            else:
                segment, local = locate_frame(frame)
                image = render_scene(segment['name'], local, segment['count'], workdir) if segment['name'] in ('T1', 'T2') else base.render(frame)
            encoder.stdin.write(image.tobytes())
        encoder.stdin.close()
        if encoder.wait():
            raise RuntimeError('Video encoding failed')
    except BaseException:
        encoder.kill()
        encoder.wait()
        raise
    return start


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / 'data/正式视频.mp4')
    parser.add_argument('--workdir', type=Path, default=ROOT / 'product/build/formal-video')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--variant', choices=['v1', 'flagg55'], default='flagg55')
    parser.add_argument('--workers', type=int, default=3)
    parser.add_argument('--presentation-clean', action='store_true',
                        help='Export a separate PPT visual master without production-note overlays or TTS')
    parser.add_argument('--presentation-english', action='store_true',
                        help='English-first PPT edition with refined tactical positions and dated matchup bug')
    args = parser.parse_args()
    if args.presentation_english:
        args.presentation_clean = True
    if args.presentation_clean and args.variant != 'flagg55':
        raise ValueError('The PPT visual master uses the locked 55-second timeline')
    if args.variant == 'flagg55':
        from formal_v2_timeline import FRAME_COUNT, DURATION, SEGMENTS
    else:
        from formal.timeline import FRAME_COUNT, DURATION, SEGMENTS
    if args.output is None:
        args.output = ROOT / ('product/build/ppt-demo-20261011/english-v3/GameBuddy-PPT-English-v3.mp4' if args.presentation_english else
                             'product/build/ppt-demo-20261011/GameBuddy-PPT-55秒-干净画面.mp4' if args.presentation_clean else
                             'product/build/formal-assets/GameBuddy-正式资产联调-v2-55秒.mp4' if args.variant == 'flagg55' else
                             'product/build/formal-assets/GameBuddy-正式资产联调-v1.mp4')
    if args.presentation_clean and args.output.resolve().is_relative_to(ROOT / 'product/build/formal-assets'):
        raise ValueError('Write the PPT edition outside the submitted formal-assets directory')
    if digest(args.source) != SOURCE_SHA256 or base.ANN['sourceSha256'] != SOURCE_SHA256 or base.OFFICIAL['sourceVideo']['sha256'] != SOURCE_SHA256:
        raise ValueError('Formal source identity mismatch')
    if not (args.workdir / 'frames/f1423.jpg').is_file() or not (args.workdir / 'slow/r0359.jpg').is_file():
        raise ValueError('Prepare the formal-source frames and slow replay first')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    suffix = '-english' if args.presentation_english else '-clean' if args.presentation_clean else ''
    chunks = args.output.parent / f'chunks-{args.variant}{suffix}'
    chunks.mkdir(exist_ok=True)
    started = time.monotonic()
    jobs = [(str(args.workdir.resolve()), str(chunks.resolve()), start, min(start + 120, FRAME_COUNT), args.variant, args.presentation_clean, args.presentation_english) for start in range(0, FRAME_COUNT, 120)]
    with ProcessPoolExecutor(max_workers=max(1, min(4, args.workers)), mp_context=multiprocessing.get_context('spawn')) as pool:
        for future in as_completed([pool.submit(chunk, job) for job in jobs]):
            print(f'Rendered formal asset chunk {future.result()}', flush=True)
    playlist = chunks / 'concat.txt'
    playlist.write_text(''.join(f"file '{job[2]:04d}.mp4'\n" for job in jobs))
    audio = build_audio(args.source, args.output.parent / f'formal-mix-{args.variant}.wav', SEGMENTS, FRAME_COUNT)
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', str(playlist),
                    '-i', audio['output'], '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy',
                    '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', str(args.output)], check=True)
    probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(args.output)]))
    video = next(stream for stream in probe['streams'] if stream['codec_type'] == 'video')
    if int(video['nb_frames']) != FRAME_COUNT or abs(float(video['duration']) - float(DURATION)) > .025:
        raise RuntimeError('Unexpected final frame count or duration')
    subprocess.run(['ffmpeg', '-v', 'error', '-i', str(args.output), '-map', '0:v:0', '-map', '0:a:0', '-f', 'null', '-'], check=True)
    receipt = {'schema': 'gamebuddy-formal-asset-edit-v1', 'createdAt': datetime.now(timezone.utc).isoformat(),
               'sourceSha256': SOURCE_SHA256, 'outputSha256': digest(args.output),
               'sizeBytes': args.output.stat().st_size, 'durationSeconds': float(DURATION),
               'frameCount': FRAME_COUNT, 'probe': probe, 'audio': audio, 'segments': SEGMENTS,
               'renderSeconds': round(time.monotonic() - started, 3), 'fullDecodePassed': True,
               'browserPlaybackPassed': False, 'editorial': True, 'agentCoreInvoked': False, 'rlInvoked': False,
               'assetLibrary': 'product/broadcast-fx/library.json', 'sourceAnnotations': 'product/broadcast-fx/formal/data/annotations.json',
               'variant': args.variant,
               'presentationClean': args.presentation_clean, 'aiNarrationUsed': False,
               'presentationEnglish': args.presentation_english,
               'presentationBookends': 'english-slide-v3' if args.presentation_english else None,
               'voiceoverPending': args.presentation_clean,
               'productionNotes': 'Visual effects use editorial keyframes/interpolation, not automatic tracking. No new model inference.',
               'reuse': ['Layers', 'draw_marker', 'draw_path', 'court_geometry', 'board_points', '_title_and_notes', 'draw_burst', 'render_intro', 'render_outro', 'draw_popup', 'draw_scorecard', 'draw_ball_trail', 'render_freeze'],
               'rendererHashes': {path.name: digest(path) for path in [Path(__file__), Path(__file__).with_name('formal_scene_renderer.py'), Path(base.__file__),
                                 Path(__file__).with_name('formal_v2_render.py'), Path(__file__).with_name('formal_v2_timeline.py'), Path(base.fx.__file__)]}}
    if args.presentation_english:
        from presentation_labels import game_label
        receipt['gameHeader'] = {'matchup': game_label()[0], 'dateTime': game_label()[1],
                                 'basis': 'formal/data/official.json gameTimeUTC; America/Chicago local time'}
        for name in ('presentation_labels.py', 'presentation_court.py', 'data/formal-presentation-court.json'):
            receipt['rendererHashes'][name] = digest(Path(__file__).parent / name)
    receipt_path = args.output.with_suffix('.manifest.json')
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'output': str(args.output), 'manifest': str(receipt_path), 'durationSeconds': float(DURATION)}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
