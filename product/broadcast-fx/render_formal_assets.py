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
    workdir, output, start, end = job
    base.init(workdir)
    cv2.setNumThreads(1)
    target = Path(output) / f'{start:04d}.mp4'
    command = ['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pixel_format', 'bgr24',
               '-video_size', '1920x1080', '-framerate', '60000/1001', '-i', 'pipe:0',
               '-an', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '19',
               '-pix_fmt', 'yuv420p', '-threads', '2', str(target)]
    encoder = subprocess.Popen(command, stdin=subprocess.PIPE)
    try:
        for frame in range(start, end):
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
    parser.add_argument('--output', type=Path, default=ROOT / 'product/build/formal-assets/GameBuddy-正式资产联调-v1.mp4')
    parser.add_argument('--workers', type=int, default=3)
    args = parser.parse_args()
    if digest(args.source) != SOURCE_SHA256 or base.ANN['sourceSha256'] != SOURCE_SHA256 or base.OFFICIAL['sourceVideo']['sha256'] != SOURCE_SHA256:
        raise ValueError('Formal source identity mismatch')
    if not (args.workdir / 'frames/f1423.jpg').is_file() or not (args.workdir / 'slow/r0359.jpg').is_file():
        raise ValueError('Prepare the formal-source frames and slow replay first')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    chunks = args.output.parent / 'chunks'
    chunks.mkdir(exist_ok=True)
    started = time.monotonic()
    jobs = [(str(args.workdir.resolve()), str(chunks.resolve()), start, min(start + 120, FRAME_COUNT)) for start in range(0, FRAME_COUNT, 120)]
    with ProcessPoolExecutor(max_workers=max(1, min(4, args.workers)), mp_context=multiprocessing.get_context('spawn')) as pool:
        for future in as_completed([pool.submit(chunk, job) for job in jobs]):
            print(f'Rendered formal asset chunk {future.result()}', flush=True)
    playlist = chunks / 'concat.txt'
    playlist.write_text(''.join(f"file '{start:04d}.mp4'\n" for _, _, start, _ in jobs))
    audio = build_audio(args.source, args.output.parent / 'formal-mix.wav')
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
               'reuse': ['Layers', 'draw_marker', 'draw_path', 'court_geometry', 'board_points', '_title_and_notes', 'draw_burst'],
               'rendererHashes': {path.name: digest(path) for path in [Path(__file__), Path(__file__).with_name('formal_scene_renderer.py'), Path(base.__file__)]}}
    receipt_path = args.output.with_suffix('.manifest.json')
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'output': str(args.output), 'manifest': str(receipt_path), 'durationSeconds': float(DURATION)}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
