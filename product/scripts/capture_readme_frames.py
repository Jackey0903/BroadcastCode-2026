#!/usr/bin/env python3
"""Capture selected actual frames from the frozen 55-second formal movie.

The MP4 is an ignored local artifact. Only eight bounded JPEGs and their source
manifest enter the repository. FFmpeg decodes the movie; no renderer, inference
or image synthesis is used to create these illustrations.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'product/build/formal-assets/GameBuddy-正式资产联调-v2-55秒.mp4'
SOURCE_SHA256 = '0a93a488fa4f79e5a3ac87c68506ff447d461c30a59bec472ebbedd16edb4019'
DESTINATION = ROOT / 'docs/assets/readme-55s'
FRAMES = (
    ('intro.jpg', 110, '人物出场与回合背景'),
    ('drive.jpg', 470, '真实转播画面的持球与防守标记'),
    ('court.jpg', 610, '镜头转入俯视战术示意'),
    ('second-chance.jpg', 1110, '进攻篮板后的右侧重组'),
    ('screen-reset.jpg', 1610, '掩护、横移与后撤出手的分步解读'),
    ('basket.jpg', 1890, '三分命中与比分更新'),
    ('shot-quality.jpg', 2760, '出手时刻、官方点位与30% xFG'),
    ('recap.jpg', 3180, '本回合得分与官方数据收束'),
)


def main():
    with SOURCE.open('rb') as stream:
        actual_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
    if actual_hash != SOURCE_SHA256:
        raise ValueError('The local movie differs from the confirmed 55-second version.')
    ffmpeg, ffprobe = shutil.which('ffmpeg'), shutil.which('ffprobe')
    if not ffmpeg or not ffprobe:
        raise ValueError('FFmpeg and FFprobe are required for exact movie-frame extraction.')
    probe = json.loads(subprocess.check_output([
        ffprobe, '-v', 'error', '-select_streams', 'v:0',
        '-show_entries', 'stream=width,height,r_frame_rate,nb_frames:format=duration',
        '-of', 'json', str(SOURCE)], text=True))
    video = probe['streams'][0]
    if video['r_frame_rate'] != '60000/1001' or int(video['nb_frames']) != 3300:
        raise ValueError('Unexpected timing for the confirmed movie.')
    DESTINATION.mkdir(parents=True, exist_ok=True)
    select = '+'.join(f'eq(n\\,{frame})' for _, frame, _ in FRAMES)
    with tempfile.TemporaryDirectory(prefix='gamebuddy-readme-frames-') as temporary:
        subprocess.run([
            ffmpeg, '-hide_banner', '-loglevel', 'error', '-i', str(SOURCE),
            '-vf', f'select={select},scale=1280:720', '-fps_mode', 'vfr',
            '-q:v', '2', str(Path(temporary) / 'frame-%02d.jpg')], check=True)
        captures = []
        for index, (name, frame, purpose) in enumerate(FRAMES, 1):
            file = DESTINATION / name
            shutil.copyfile(Path(temporary) / f'frame-{index:02d}.jpg', file)
            captures.append({'path': str(file.relative_to(ROOT)), 'frameIndex': frame,
                             'outputSeconds': round(frame * 1001 / 60000, 6),
                             'purpose': purpose, 'width': 1280, 'height': 720,
                             'sha256': hashlib.sha256(file.read_bytes()).hexdigest(),
                             'bytes': file.stat().st_size})
    manifest = {'capturedAt': datetime.now(timezone.utc).isoformat(),
                'source': str(SOURCE.relative_to(ROOT)), 'sourceSha256': actual_hash,
                'durationSeconds': float(probe['format']['duration']),
                'frameRate': video['r_frame_rate'], 'frameCount': int(video['nb_frames']),
                'captures': captures,
                'scope': 'Decoded MP4 frames resized to 1280x720; output timestamps, original picture content and burned-in disclosures retained.'}
    (DESTINATION / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'destination': str(DESTINATION), 'capturedFrames': len(captures),
                      'sourceSha256': actual_hash}, ensure_ascii=False))


if __name__ == '__main__':
    main()
