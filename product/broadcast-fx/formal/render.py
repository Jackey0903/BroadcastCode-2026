#!/usr/bin/env python3
"""Christie formal-source edit; generic primitives, independent evidence/timeline."""
from __future__ import annotations
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import time

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from broadcast_fx import legacy as fx, tactics
from formal.timeline import FPS, FRAME_COUNT, DURATION, SEGMENTS, SOURCE_SHA256, locate_frame, source_frame_at
from formal.audio import build_audio

W, H = 1920, 1080
RATE = float(FPS)
WD = None
ANN = json.loads((HERE / 'data/annotations.json').read_text())
OFFICIAL = json.loads((HERE / 'data/official.json').read_text())
RED = fx.hexc('ff5865')


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


CACHE_RECIPE = {'sourceSha256': SOURCE_SHA256, 'fps': '60000/1001',
                'sourceFrames': 1424, 'jpegQuality': 3, 'replayStartSeconds': 12,
                'replayFilter': 'minterpolate=fps=120000/1001:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1'}


def seal_cache(workdir):
    workdir = Path(workdir)
    files = list(sorted((workdir/'frames').glob('f*.jpg'))) + list(sorted((workdir/'slow').glob('r*.jpg')))
    data = {'recipe': CACHE_RECIPE, 'files': {str(p.relative_to(workdir)): sha(p) for p in files}}
    (workdir/'cache-manifest.json').write_text(json.dumps(data, indent=2))


def validate_cache(workdir):
    workdir = Path(workdir)
    data = json.loads((workdir/'cache-manifest.json').read_text())
    if data['recipe'] != CACHE_RECIPE:
        raise ValueError('Frame cache recipe/source mismatch; use a new workdir')
    required = [f'frames/f{i:04d}.jpg' for i in range(1424)] + [f'slow/r{i:04d}.jpg' for i in range(390)]
    for name in required:
        if name not in data['files'] or sha(workdir/name) != data['files'][name]:
            raise ValueError(f'Frame cache missing or altered: {name}')


def init(workdir):
    global WD
    WD = Path(workdir)
    cv2.setNumThreads(1)


@lru_cache(maxsize=10)
def source(i):
    path = WD / 'frames' / f'f{int(max(0, min(1423, i))):04d}.jpg'
    image = cv2.imread(str(path))
    if image is None:
        raise FileNotFoundError(path)
    return image


def txt(L, value, x, y, size=32, color=fx.CHALK, a=1, latin=False, anchor='lt', track=0):
    L.paste(fx.text_rgba(str(value), fx.DIN if latin else fx.CJK, size, color, track),
            x, y, alpha=a, anchor=anchor)


def panel(L, x, y, w, h, color=fx.ORANGE, a=1):
    fx.rect(L, x, y, x+w, y+h, fx.VOID, .88*a)
    fx.rect(L, x, y, x+5, y+h, color, a)
    fx.line(L.sharp, (x, y), (x+w, y), color, .55*a, 1)


def common(L, frame, label):
    fx.rect(L, 0, 0, W, 100, fx.VOID, .78)
    fx.rect(L, 0, 0, 8, 100, fx.ORANGE, 1)
    txt(L, 'GameBuddy', 55, 12, 48, latin=True, track=2)
    txt(L, '看懂关键一拍', 307, 30, 25, fx.LED)
    txt(L, label, W-58, 26, 30, fx.CHALK, latin=True, anchor='rt', track=2)
    fx.rect(L, 0, 1043, W, H, fx.VOID, .82)
    txt(L, '编辑解读 · 球员短时标注 / 非自动追踪', 58, 1045, 18, fx.MUTED)
    txt(L, 'NBA OFFICIAL DATA  /  0022500356 · 273', W-55, 1049, 19, fx.MUTED,
        latin=True, anchor='rt', track=1)
    fx.rect(L, 0, 1077, W*(frame+1)/FRAME_COUNT, 1080, fx.ORANGE, 1)


def particles(L, t, a=1):
    for j in range(28):
        x, y = (j*153.7+t*15)%W, (j*91.3-t*25)%H
        fx.line(L.sharp, (x, y), (x+5, y-10), fx.FLAME, .2*a, 2)


def intro(t):
    L = fx.Layers(fx.grade(source(1340), sat=.45, gain=.33, vig=.35))
    particles(L, t)
    k = fx.ease_out(t/.6)
    txt(L, 'SECOND CHANCE', 95-40*(1-k), 245, 154, fx.CHALK, k, True, track=3)
    txt(L, '封盖之后，再争一拍', 107, 450, 56, fx.LED, k)
    txt(L, 'MAX CHRISTIE  /  00', 110, 610, 66, fx.CHALK, k, True, track=3)
    txt(L, 'HOU @ DAL  /  SECOND QUARTER', 113, 711, 36, fx.MUTED, k, True, track=2)
    txt(L, '二次进攻  /  后撤步打板三分', 114, 785, 30, fx.CHALK, k)
    fx.ellipse(L.sharp, (1605, 602), (192, 192), fx.ORANGE, .8*k, 4, t*55, 280+t*55)
    txt(L, '00', 1600, 610, 292, fx.ORANGE, k, True, anchor='c')
    return L


def freeze(key, t, n):
    scene = ANN['scenes'][key]
    L = fx.Layers(fx.grade(source(scene['frame']), sat=.65, gain=.7, vig=.2))
    alpha = min(fx.ease_out(t/.32), fx.ease_out((n/RATE-t)/.22))
    color = fx.FLAME if key == 'T1' else fx.CYAN
    panel(L, 58, 149, 655, 305, color, alpha)
    txt(L, '01 / PAINT PRESSURE' if key == 'T1' else '02 / SCREEN & RESET', 86, 170, 32, color, alpha, True, track=2)
    txt(L, '切入禁区，防守收缩' if key == 'T1' else '借掩护，寻找出手空间', 83, 231, 43, fx.CHALK, alpha)
    rows = ['00号持球切入', '红衣防守向球侧收紧'] if key == 'T1' else ['7号在身旁形成掩护位置', '00号向中路横移，再后撤出手']
    for j, row in enumerate(rows):
        txt(L, row, 86, 316+j*49, 29, fx.CHALK, alpha)
    for j, player in enumerate(scene['players']):
        a = alpha*fx.ease_out((t-j*.035)/.3)
        col = color if player['team'] == 'offense' else RED
        tactics.draw_marker(L, player['image'], col, player['number'] or '', t,
                            alpha=a, active=player['id']=='D00',
                            body_only=player['foot'] is None)
    for arrow in scene['arrows']:
        col = color if arrow.get('kind') == 'offense' else RED
        tactics.draw_path(L, arrow['points'], col, fx.ease_out((t-.4)/.8), alpha*.9, 6,
                          dashed=arrow.get('kind')=='defense')
    # Small role labels avoid covering the original score graphic or the ball.
    panel(L, 1425, 153, 437, 186, color, alpha)
    txt(L, 'READ THE FLOOR', 1452, 174, 29, color, alpha, True, track=2)
    txt(L, 'DAL  /  进攻', 1452, 226, 27, color, alpha)
    txt(L, 'HOU  /  防守', 1452, 276, 27, RED, alpha)
    txt(L, '战术意图为画面解读', 64, 980, 25, fx.CHALK, alpha)
    return L


@lru_cache(maxsize=1)
def replay_data():
    path = HERE / 'data/replay_anchors.json'
    return json.loads(path.read_text()) if path.exists() else {}


def hero(L, source_seconds, t, a=1):
    # Independent short annotations, never old-source coordinates.
    data = replay_data()
    anchors = data.get('anchors', [])
    if not anchors:
        return
    for left, right in zip(anchors, anchors[1:]):
        lt, rt = left.get('sourceSeconds', -1), right.get('sourceSeconds', -1)
        if lt <= source_seconds <= rt and rt-lt <= .31:
            q = (source_seconds-lt)/max(rt-lt, 1e-6)
            p0, p1 = left.get('body'), right.get('body')
            if p0 is not None and p1 is not None:
                p = np.array(p0)*(1-q)+np.array(p1)*q
                tactics.draw_marker(L, p, fx.FLAME, '00', t, alpha=.85*a, active=True, body_only=True)
            return


def live(s, out_t):
    L = fx.Layers(source(round(s*RATE)))
    rows = [(.3, 3.5, '先看这次二次进攻', 'SECOND CHANCE'),
            (6.55, 7.95, '第一攻被封盖，回合还没有结束', 'STAY IN THE PLAY'),
            (8.0, 10.8, '鲍威尔抢下前场篮板，留住进攻机会', 'OFFENSIVE REBOUND'),
            (12.15, 13.4, '借掩护横移，后撤创造空间', 'CREATE SEPARATION'),
            (15.1, 17.6, '打板三分命中！', 'BANK IT IN  /  +3'),
            (19.0, 22.8, '独行侠追到 43–44', 'A ONE-POINT GAME')]
    for start, end, cn, en in rows:
        a = fx.window(s, start, end, .22, .22)
        if a:
            panel(L, 60, 144, 990, 126, fx.ORANGE, a)
            txt(L, en, 87, 156, 27, fx.LED, a, True, track=2)
            txt(L, cn, 85, 205, 35, fx.CHALK, a)
    if 12 <= s <= 13.7:
        hero(L, s, out_t)
    if 15.12 <= s <= 16.2:
        fx.draw_burst(L, s, 15.12, (1170, 280), fx.FLAME, dur=.8, big=.7)
        txt(L, '+3', 1600, 510, 178, fx.LED, fx.window(s,15.12,16.2,.12,.25), True, anchor='c')
    return L


def replay(index, t, source_seconds):
    image = cv2.imread(str(WD / 'slow' / f'r{index:04d}.jpg'))
    if image is None:
        raise FileNotFoundError(f'Missing slow replay frame {index}')
    L = fx.Layers(fx.grade(image, sat=.83, gain=.92, vig=.16))
    panel(L, 60, 147, 750, 135, fx.VIOLET)
    txt(L, 'THE SHOT  /  0.5x REPLAY', 87, 163, 31, fx.VIOLET, latin=True, track=2)
    txt(L, '横移 · 后撤 · 迎着干扰出手', 84, 216, 34)
    hero(L, source_seconds, t)
    return L


def metric(t):
    image = cv2.imread(str(WD / 'slow/r0186.jpg'))
    L = fx.Layers(fx.grade(image, sat=.55, gain=.66, vig=.16))
    a = fx.ease_out(t/.25)
    value = round(OFFICIAL['shot']['xfgPercent']*fx.ease_out(t/.72))
    panel(L, 1350, 164, 504, 659, fx.ORANGE, a)
    txt(L, 'OFFICIAL SHOT QUALITY', 1380, 191, 29, fx.LED, a, True, track=1)
    txt(L, 'xFG', 1380, 243, 73, fx.CHALK, a, True)
    txt(L, f'{value}%', 1601, 474, 208, fx.CHALK, a, True, anchor='c')
    fx.ellipse(L.sharp, (1601, 474), (170, 170), fx.MUTED, .35*a, 2)
    fx.ellipse(L.glow, (1601, 474), (170, 170), fx.ORANGE, .5*a, 8, -90, -90+360*value/100)
    fx.ellipse(L.sharp, (1601, 474), (170, 170), fx.FLAME, a, 6, -90, -90+360*value/100)
    txt(L, '官方预期命中率', 1601, 670, 31, fx.CHALK, a, anchor='c')
    txt(L, '25 FT  /  STEP BACK BANK 3', 1601, 737, 29, fx.LED, a, True, anchor='c')
    panel(L, 60, 157, 725, 146, fx.VIOLET, a)
    txt(L, '最后的出手窗口', 85, 176, 47, fx.CHALK, a)
    txt(L, '数据来自 NBA 官方本球记录', 88, 250, 27, fx.VIOLET, a)
    hero(L, 12+93/RATE, t, a)
    return L


def outro(t):
    L = fx.Layers(fx.grade(source(1370), sat=.3, gain=.24, vig=.3))
    k = fx.ease_out(t/.45)
    particles(L, t, .5)
    txt(L, 'ONE MORE CHANCE.', 99, 182, 115, fx.CHALK, k, True, track=3)
    txt(L, '把回合留住，把三分投进。', 109, 348, 55, fx.LED, k)
    txt(L, 'MAX CHRISTIE', 110, 481, 71, fx.CHALK, k, True, track=3)
    txt(L, '+3', 1640, 350, 260, fx.ORANGE, k, True, anchor='c')
    cards = [('01','首攻被封盖'),('02','前场篮板续命'),('03','后撤打板三分')]
    for j,(num,cn) in enumerate(cards):
        a = fx.ease_out((t-.2-j*.14)/.35)
        x = 110+j*570
        panel(L, x, 635, 533, 145, fx.ORANGE if j==2 else fx.CYAN, a)
        txt(L, num, x+25, 658, 50, fx.LED, a, True)
        txt(L, cn, x+97, 681, 35, fx.CHALK, a)
    txt(L, 'xFG 30%   /   25 FT   /   DAL 43–44 HOU', 112, 844, 41, fx.CHALK, k, True, track=2)
    txt(L, 'NBA 官方事件 273 · 本段三分后的比分', 115, 922, 25, fx.MUTED, k)
    return L


def render(frame):
    seg, local = locate_frame(frame)
    name, t = seg['name'], local/RATE
    sf = source_frame_at(frame)
    if name == 'intro':
        L = intro(t)
    elif name in ('T1','T2'):
        L = freeze(name,t,seg['count'])
    elif name == 'live':
        L = live(sf/RATE,frame/RATE)
    elif name == 'rewind':
        L = fx.Layers(fx.grade(source(round(sf)),sat=.15,gain=.45))
        txt(L, 'REWIND', 960, 500, 160, fx.VIOLET, latin=True, anchor='c', track=8)
        for yy in range(0,H,12):
            fx.line(L.sharp,(0,yy),(W,yy),fx.VIOLET,.08,2)
    elif name in ('replay1','replay2'):
        index = local+(186 if name=='replay2' else 0)
        L = replay(index,t,sf/RATE)
    elif name == 'metric':
        L = metric(t)
    else:
        L = outro(t)
    label = {'intro':'FORMAL EDIT / HOU @ DAL','T1':'TACTICAL PAUSE / 01','T2':'TACTICAL PAUSE / 02',
             'metric':'OFFICIAL xFG / EVENT 273','outro':'SECOND CHANCE / +3',
             'rewind':'REPLAY','replay1':'SLOW MOTION / 0.5x','replay2':'SLOW MOTION / 0.5x'}.get(name,'HOU @ DAL / MAX CHRISTIE')
    common(L,frame,label)
    image = L.compose()
    # Let the live-action cuts resume directly; fade only the editorial title/end.
    if name=='intro':
        image = (image*fx.ease_out(t/.22)).astype(np.uint8)
    if name=='outro':
        image = (image*fx.ease_out((seg['count']-1-local)/RATE/.55)).astype(np.uint8)
    return image


def chunk(job):
    workdir,start,end = job
    init(workdir)
    path = WD/'chunks'/f'{start:04d}.mp4'
    cmd = ['ffmpeg','-v','error','-y','-f','rawvideo','-pixel_format','bgr24','-video_size','1920x1080',
           '-framerate','60000/1001','-i','pipe:0','-an','-c:v','libx264','-preset','veryfast',
           '-crf','18','-pix_fmt','yuv420p','-threads','2',str(path)]
    process = subprocess.Popen(cmd,stdin=subprocess.PIPE)
    try:
        for frame in range(start,end):
            process.stdin.write(render(frame).tobytes())
        process.stdin.close()
        if process.wait():
            raise RuntimeError('Encoder failed')
    except BaseException:
        process.kill()
        process.wait()
        raise
    return start,str(path)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--workdir',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--workers',type=int,default=3)
    p.add_argument('--preview',help='Comma-separated output frame numbers')
    args=p.parse_args()
    if sha(args.source)!=SOURCE_SHA256 or ANN['sourceSha256']!=SOURCE_SHA256:
        raise ValueError('Wrong source video or annotations')
    if OFFICIAL['sourceVideo']['sha256']!=SOURCE_SHA256:
        raise ValueError('Wrong official event binding')
    args.workdir.mkdir(parents=True,exist_ok=True)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    init(args.workdir.resolve())
    has_manifest = (WD/'cache-manifest.json').exists()
    if has_manifest:
        validate_cache(WD)
    if not has_manifest:
        (WD/'frames').mkdir(exist_ok=True)
        subprocess.run(['ffmpeg','-v','error','-y','-i',str(args.source),'-fps_mode','passthrough',
                        '-q:v','3','-start_number','0',str(WD/'frames/f%04d.jpg')],check=True)
    if not has_manifest:
        (WD/'slow').mkdir(exist_ok=True)
        subprocess.run(['ffmpeg','-v','error','-y','-ss','12','-i',str(args.source),'-t','3.25',
                        '-vf','minterpolate=fps=120000/1001:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1',
                        '-q:v','3','-start_number','0',str(WD/'slow/r%04d.jpg')],check=True)
        seal_cache(WD)
        validate_cache(WD)
    if args.preview:
        (WD/'previews').mkdir(exist_ok=True)
        for frame in map(int,args.preview.split(',')):
            cv2.imwrite(str(WD/'previews'/f'{frame:04d}.jpg'),render(frame))
        return
    (WD/'chunks').mkdir(exist_ok=True)
    started=time.time()
    jobs=[(str(WD),start,min(start+120,FRAME_COUNT)) for start in range(0,FRAME_COUNT,120)]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for future in as_completed([pool.submit(chunk,job) for job in jobs]):
            start,_=future.result()
            print(f'Rendered frames {start}–{min(start+119,FRAME_COUNT-1)}',flush=True)
    # Only controlled numeric filenames occur in this concat file.
    (WD/'concat.txt').write_text(''.join(f"file 'chunks/{start:04d}.mp4'\n" for _,start,_ in jobs))
    audio=build_audio(args.source,WD/'formal-mix.wav')
    subprocess.run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',str(WD/'concat.txt'),
                    '-i',str(WD/'formal-mix.wav'),'-map','0:v:0','-map','1:a:0','-c:v','copy',
                    '-c:a','aac','-b:a','192k','-movflags','+faststart',str(args.output)],check=True)
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(args.output)]))
    subprocess.run(['ffmpeg','-v','error','-i',str(args.output),'-f','null','-'],check=True)
    video=next(s for s in probe['streams'] if s['codec_type']=='video')
    if int(video['nb_frames'])!=FRAME_COUNT or abs(float(video['duration'])-float(DURATION))>.025:
        raise RuntimeError('Unexpected final duration/frame count')
    evidence={'sourceSha256':SOURCE_SHA256,'output':str(args.output.resolve()),'outputSha256':sha(args.output),
              'sizeBytes':args.output.stat().st_size,'frameCount':FRAME_COUNT,'durationSeconds':float(DURATION),
              'probe':probe,'audio':audio,'segments':SEGMENTS,'renderSeconds':time.time()-started,
              'fullDecodePassed':True,'browserPlaybackPassed':False,'editorial':True,'agentCoreInvoked':False,'rlInvoked':False}
    (WD/'render-evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2))
    print(json.dumps({'output':evidence['output'],'duration':float(DURATION),'sha256':evidence['outputSha256']},ensure_ascii=False),flush=True)


if __name__=='__main__':
    main()
