"""Formal-footage reuse of the original intro, outro, shot card and goal effects."""
from functools import lru_cache
from pathlib import Path
import json

import cv2
import numpy as np

from broadcast_fx import legacy as fx, tactics
from formal import render as base
from formal_scene_renderer import render_scene
from formal_v2_timeline import FPS, locate_frame

HERE = Path(__file__).resolve().parent
RATE = float(FPS)
WORK = None
INTRO = {'headline': 'DOWN 4', 'contextEn': '5:13 LEFT · 2ND QTR',
         'contextCn': '落后4分 · 二次进攻，争取下一拍', 'player': '#00  MAX CHRISTIE'}
OUTRO = {'nameEn': 'MAX CHRISTIE', 'nameCn': '克里斯蒂  ·  DAL #00', 'points': 3,
         'pointsLabel': '本球得分',
         'chips': [('xFG 30%', fx.ORANGE), ('25 FT · STEP BACK 3', fx.CHALK),
                   ('Q2 · 4:58', fx.FLAME), ('DAL 43 — 44 HOU', fx.GREEN)]}
PRESENTATION_INTRO = {'headline': 'DOWN BY 4', 'headlineSize': 220,
                      'contextEn': '5:13 LEFT · 2ND QTR', 'contextSubEn': 'SECOND CHANCE',
                      'player': '#00  MAX CHRISTIE'}
PRESENTATION_OUTRO = {'headline': 'DOWN BY 1', 'headlineSize': 220, 'closing': True,
                      'contextEn': 'DAL 43 — 44 HOU', 'contextColor': fx.GREEN,
                      'contextSubEn': 'STEP-BACK BANK THREE · OFFICIAL xFG 30%',
                      'player': '#00  MAX CHRISTIE'}


def init(workdir, presentation_english=False):
    global WORK
    WORK = Path(workdir)
    fx.PRESENTATION_ENGLISH = presentation_english
    fx.tag_cached.cache_clear()
    base.init(workdir)
    # Only short, source-bound ball anchors. A null breaks the arc entirely.
    fx.BALL = {}
    anchors = base.replay_data()['ballAnchors']
    for left, right in zip(anchors, anchors[1:]):
        if left['position'] is None or right['position'] is None or right['sourceSeconds'] - left['sourceSeconds'] > .31:
            continue
        first, last = left['frame'], right['frame']
        for frame in range(first, last + 1):
            q = (frame - first) / max(1, last - first)
            fx.BALL[frame] = list(np.array(left['position']) * (1 - q) + np.array(right['position']) * q)


@lru_cache(maxsize=1)
def second_chance_scene():
    observations = json.loads((HERE / 'data/formal-source-observations.json').read_text())
    held = observations['freezeFrames'][0]
    players = []
    for index, marker in enumerate(held['markers']):
        offense = index in (0, 2)
        number = '00' if index == 0 else '10' if index == 1 else '7'
        players.append({'id': 'D' + number if offense else 'R' + number,
                        'team': 'offense' if offense else 'defense', 'number': number,
                        'image': marker.get('footPoint') or marker['bodyCenter'],
                        'anchorKind': 'visible-foot' if marker.get('footPoint') else 'body-only'})
    return {'frame': 480, 'titleCn': '前场篮板，让回合继续', 'titleEn': 'SECOND CHANCE',
            'captionEn': 'Powell recovers the board. Christie resets on the right.',
            'captionCn': '鲍威尔抢回前场篮板，克里斯蒂在右侧重新组织。',
            'players': players,
            'arrows': [{'points': [[1410, 850], [1500, 810]], 'kind': 'defense'}],
            'badge': '02 / SECOND CHANCE',
            'steps': [('REBOUND', '鲍威尔前场篮板'), ('RECYCLE', '球回到右侧'), ('RESET', '继续寻找出手机会')],
            'aside': ['一次被封盖，不等于回合结束', '前场篮板保住球权', '防守仍在贴近持球人']}


def tag(layer, source_seconds, color, alpha=1):
    anchors = base.replay_data().get('anchors', [])
    for left, right in zip(anchors, anchors[1:]):
        a, b = left['sourceSeconds'], right['sourceSeconds']
        if a <= source_seconds <= b and b - a <= .31:
            ratio = (source_seconds - a) / (b - a)
            body = np.array(left['body']) * (1 - ratio) + np.array(right['body']) * ratio
            tactics.draw_marker(layer, body, color, None, source_seconds, alpha=alpha,
                                active=True, body_only=True)
            # The original floating card is reused; obscured feet stay unknown.
            card = fx.tag_cached('00', 'M. CHRISTIE', 'STEP-BACK THREE' if fx.PRESENTATION_ENGLISH else '后撤步三分', color)
            x = max(190, min(1730, float(body[0]) + 120))
            layer.paste(card, x, float(body[1]) - 225, alpha=alpha, scale=.85, anchor='c')
            return


def rim_at(source_seconds):
    anchors = base.replay_data()['rimAnchors']
    for left, right in zip(anchors, anchors[1:]):
        if left['sourceSeconds'] <= source_seconds <= right['sourceSeconds']:
            ratio = (source_seconds - left['sourceSeconds']) / (right['sourceSeconds'] - left['sourceSeconds'])
            return tuple(np.array(left['position']) * (1 - ratio) + np.array(right['position']) * ratio)
    return tuple(anchors[-1]['position'])


def basket_effect(layer, source_seconds, replay=False):
    rim = rim_at(source_seconds)
    net = base.replay_data()['events']['net']['sourceSeconds']
    frame = int(round(source_seconds * RATE))
    if frame in fx.BALL:
        length = 1
        while length < (26 if replay else 20) and frame - length in fx.BALL:
            length += 1
        fx.draw_ball_trail(layer, frame, fx.LED, fx.ORANGE, 1, length=length)
    fx.draw_burst(layer, source_seconds, net, rim, fx.GREEN, 1.6 if replay else .8, 1.15 if replay else 1)
    if net <= source_seconds <= net + .34:
        fx.ellipse(layer.glow, rim, (60, 22), fx.scale_c(fx.GREEN, 1.5 * (1 - (source_seconds - net) / .34)), 1, -1)
    fx.draw_popup(layer, source_seconds, net + .02, '+3', (rim[0] + 330, rim[1] + 10), fx.GREEN,
                  210, 1.3 if replay else 1.15, '三分命中', fx.CHALK)
    fx.draw_scorecard(layer, source_seconds, net + .24,
                      fx.window(source_seconds, net + .24, net + 1.24, .3, .15),
                      before=40, after=43, opponent=44)


def finish(image, source_seconds, freeze_time=None):
    net = base.replay_data()['events']['net']['sourceSeconds']
    if net <= source_seconds <= net + .1:
        image = cv2.addWeighted(image, 1, np.full_like(image, 255), .35 * (1 - (source_seconds - net) / .1), 0)
    image = fx.shake(image, source_seconds, net + .01, 16, .3)
    if freeze_time is not None:
        if freeze_time < .12:
            image = cv2.addWeighted(image, 1, np.full_like(image, 255), .45 * (1 - freeze_time / .12), 0)
        image = fx.shake(image, freeze_time, 0, 12, .25)
    return image


def render(frame):
    segment, local = locate_frame(frame)
    name, t = segment['name'], local / RATE
    source_frame = segment['sourceStart'] + local * segment['sourceRate']
    source_seconds = source_frame / RATE
    if name == 'intro':
        copy = PRESENTATION_INTRO if fx.PRESENTATION_ENGLISH else INTRO
        return fx.render_intro(local, segment['count'], base.source(6), copy)
    if name == 'outro':
        if fx.PRESENTATION_ENGLISH:
            return fx.render_intro(local, segment['count'], base.source(910), PRESENTATION_OUTRO)
        return fx.render_outro(local, segment['count'], base.source(910), OUTRO)
    if name in ('T1', 'T2', 'T3'):
        scene = second_chance_scene() if name == 'T3' else None
        return render_scene(name, local, segment['count'], WORK, scene_override=scene,
                            presentation_english=fx.PRESENTATION_ENGLISH)
    if name == 'rewind':
        image = base.source(round(source_frame)).astype(np.int16)
        b, g, r = cv2.split(image)
        image = cv2.merge([np.roll(b, -10, axis=1), g, np.roll(r, 10, axis=1)]).clip(0, 255).astype(np.uint8)
        image = fx.grade(image, sat=.55, gain=.9, tint=(fx.PURPLE, .25), vig=.5)
        image[::3] = (image[::3] * .7).astype(np.uint8)
        band = int((t * 900) % 1080)
        image[band:band + 40] = np.clip(image[band:band + 40].astype(np.int16) + 40, 0, 255)
        layer = fx.Layers(image)
        for k in range(2):
            x = 120 + k * 52
            cv2.fillPoly(layer.sharp, [np.array([[x + 50, 150], [x + 50, 214], [x, 182]], np.int32)], fx.CHALK + (255,), cv2.LINE_AA)
        layer.paste(fx.text_rgba('REPLAY', fx.PIX, 72, fx.CHALK), 250, 140)
        layer.paste(fx.text_rgba('慢镜头回放', fx.CJK, 25 if fx.PRESENTATION_ENGLISH else 44, fx.VIOLET), 128, 230)
        image = layer.compose()
        if local > segment['count'] - 8:
            k = (local - (segment['count'] - 8)) / 8
            image = cv2.addWeighted(image, 1 - .8 * k, np.full_like(image, 255), .8 * k, 0)
        return image
    replay = name.startswith('replay') or name == 'metric'
    if replay:
        index = 186 if name == 'metric' else local + (186 if name == 'replay2' else 0)
        image = cv2.imread(str(WORK / f'slow/r{index:04d}.jpg'))
        if image is None:
            raise FileNotFoundError('Missing formal-source slow frame')
        layer = fx.Layers(fx.grade(image, sat=.7 if name == 'metric' else .82,
                                  gain=.82 if name == 'metric' else 1,
                                  tint=(fx.PURPLE, .06), vig=.7 if name == 'metric' else .45))
    else:
        layer = fx.Layers(fx.grade(base.source(round(source_frame)), sat=1.08, vig=.25))
    tag(layer, source_seconds, fx.PURPLE if replay else fx.BLUE)
    basket_effect(layer, source_seconds, replay)
    if fx.PRESENTATION_ENGLISH:
        from presentation_labels import draw_game_header
        draw_game_header(layer, replay)
    else:
        fx.draw_game_tag(layer, 1, 'COACH' if replay else 'LIVE', 'REPLAY · 0.5×' if replay else 'HOU @ DAL · Q2')
    if name == 'metric':
        raw = base.OFFICIAL['shot']['rawGpShot']
        release_ball = fx.ball_at(source_frame)
        if release_ball is None:
            raise ValueError('Missing source-bound release anchor')
        fx.render_freeze(layer, t, segment['count'] / RATE,
                         shot={'ball': release_ball, 'xfg': base.OFFICIAL['shot']['xfg'],
                               'locX': raw['locX'], 'locY': raw['locY'], 'side': raw['side'],
                               'distance': '25 FT', 'eventId': 273,
                               'rows': [('25 FT', '出手距离 · 官方逐回合'), ('STEP BACK 3', '后撤步打板三分'), ('Q2 · 4:58', '第二节 · 官方事件时钟')]})
    elif replay:
        fx.draw_caption(layer, t, .1, segment['count'] / RATE - .05,
                        'REPLAY · STEP BACK THREE' if name == 'replay1' else 'OFFICIAL xFG 30%',
                        '横移、后撤，迎着举手干扰出手' if name == 'replay1' else '官方预期命中率30%，实际三分命中', fx.PURPLE)
    else:
        captions = [(.3, 4.7, 'POSSESSION START · DOWN 4', '独行侠落后4分，克里斯蒂持球切入'),
                    (5.65, 7.8, 'CONTEST · SECOND CHANCE', '首攻受到封盖，鲍威尔抢回前场篮板'),
                    (8, 10.8, 'RESET ON THE RIGHT', '球回到右侧，防守仍然贴近'),
                    (11, 13.4, 'SCREEN · SHIFT · STEP BACK', '借身旁掩护横移，再后撤到三分线外'),
                    (13.5, 15.1, 'THREE OVER THE CONTEST', '迎着举手干扰，后撤步三分出手'),
                    (15.15, 17, 'STEP BACK BANK THREE — GOOD!', '后撤步打板三分命中！')]
        for a, b, en, cn in captions:
            fx.draw_caption(layer, source_seconds, a, b, en, cn, fx.GREEN if a == 15.15 else fx.ORANGE)
        if 11.5 <= source_seconds <= 12.8:
            fx.draw_popup(layer, source_seconds, 11.5, 'SCREEN', (540, 525), fx.PURPLE, 150, 1, '掩护', fx.VIOLET)
        if 12.6 <= source_seconds <= 13.6:
            fx.draw_popup(layer, source_seconds, 12.6, 'STEP BACK', (340, 510), fx.FLAME, 110, 1, '后撤步', fx.LED)
    fx.draw_disclosure(layer, 1)
    return finish(layer.compose(), source_seconds, t if name == 'metric' else None)
