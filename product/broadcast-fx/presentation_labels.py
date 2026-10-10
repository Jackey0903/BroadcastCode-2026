"""English-first typography for the separate presentation visual master."""
from datetime import datetime
from functools import lru_cache
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from broadcast_fx import legacy as fx, tactics

HERE = Path(__file__).resolve().parent


@lru_cache(maxsize=1)
def game_label():
    game = json.loads((HERE / 'formal/data/official.json').read_text())['game']
    tip = datetime.fromisoformat(game['gameTimeUTC'].replace('Z', '+00:00'))
    local = tip.astimezone(ZoneInfo('America/Chicago'))
    return (f"{game['awayTeam']} @ {game['homeTeam']}",
            f"{local.strftime('%b %d, %Y').upper()} | {local.strftime('%I:%M %p').lstrip('0')} CT")


def draw_game_header(layer, replay=False):
    """A dated broadcast-style matchup bug, without a synthetic game clock."""
    matchup, date = game_label()
    x, y, w = 70, 58, 460
    fx.rect(layer, x, y, x + w, y + 104, fx.VOID, .87)
    fx.rect(layer, x, y, x + 6, y + 52, tactics.RED, 1)
    fx.rect(layer, x, y + 52, x + 6, y + 104, fx.BLUE, 1)
    layer.paste(fx.text_rgba(matchup, fx.DINA, 34, fx.CHALK, 1), x + 22, y + 9)
    fx.line(layer.sharp, (x + 22, y + 54), (x + w - 22, y + 54), fx.MUTED, .35, 1)
    layer.paste(fx.text_rgba(date, fx.DINA, 20, fx.CHALK), x + 22, y + 65)
    if replay:
        layer.paste(fx.text_rgba('REPLAY · 0.5×', fx.DIN, 25, fx.VIOLET), x + w - 18, y + 17, anchor='rt')


COPY = {
    'T1': {
        'steps': [('DRIVE', '持球切入'), ('DRAW HELP', '吸引协防'), ('STAY IN THE PLAY', '争取第二次机会')],
        'aside': [('Christie attacks the lane', '克里斯蒂持球切入'),
                  ('Help closes around the ball', '协防向持球侧收紧'),
                  ('Watch the interior support', '关注篮下接应')],
    },
    'T3': {
        'steps': [('OFFENSIVE BOARD', '鲍威尔前场篮板'), ('RECYCLE', '球回到右侧'), ('RESET', '重新组织进攻')],
        'aside': [('Powell keeps it alive', '鲍威尔保住球权'),
                  ('Christie resets on the right', '克里斯蒂在右侧重组'),
                  ('The defense stays close', '防守继续贴近')],
    },
    'T2': {
        'steps': [('SCREEN', '鲍威尔形成掩护位置'), ('SHIFT INSIDE', '克里斯蒂向中路横移'), ('STEP BACK', '后撤步三分出手')],
        'aside': [('Powell offers the screen', '鲍威尔提供掩护'),
                  ('Christie moves to the middle', '克里斯蒂向中路移动'),
                  ('The defender follows', '防守人跟随持球方向')],
    },
}


def draw_tactic_labels(layer, scene, name, t, morph, alpha):
    entry = fx.ease_out(t / .33)
    x = 70 - 25 * (1 - entry)
    fx.rect(layer, x, 55, x + 7, 174, fx.ORANGE, alpha)
    layer.paste(fx.text_rgba(scene['titleEn'], fx.DIN, 76, fx.CHALK, 3), x + 28, 48, alpha=alpha * entry)
    layer.paste(fx.text_rgba(scene['titleCn'], fx.CJK, 25, fx.MUTED), x + 30, 134, alpha=alpha * entry)
    layer.paste(fx.text_rgba('GameBuddy', fx.DINA, 40, fx.CHALK), 1850, 57, alpha=alpha, anchor='rt')
    layer.paste(fx.text_rgba('PLAY BREAKDOWN  /  ' + scene['badge'], fx.DIN, 27, fx.CYAN, 1),
                1850, 111, alpha=alpha, anchor='rt')
    for xx, color, text in ((75, fx.CYAN, 'DAL OFFENSE'), (295, tactics.RED, 'HOU DEFENSE')):
        fx.rect(layer, xx, 207, xx + 14, 221, color, alpha)
        layer.paste(fx.text_rgba(text, fx.DIN, 27, fx.CHALK, 1), xx + 24, 195, alpha=alpha)
    if morph > .01:
        for j, (en, cn) in enumerate(COPY[name]['steps']):
            yy = 340 + j * 124
            a = alpha * morph * fx.ease_out((t - 1.75 - .10 * j) / .4)
            layer.paste(fx.text_rgba(f'0{j+1}', fx.DIN, 60, fx.ORANGE), 90, yy, alpha=a)
            layer.paste(fx.text_rgba(en, fx.DIN, 38, fx.CHALK, 1), 164, yy + 3, alpha=a)
            layer.paste(fx.text_rgba(cn, fx.CJK, 21, fx.MUTED), 166, yy + 52, alpha=a)
        layer.paste(fx.text_rgba('READ THE FLOOR', fx.DIN, 28, fx.CYAN, 2), 1405, 244, alpha=alpha * morph)
        for j, (en, cn) in enumerate(COPY[name]['aside']):
            yy = 285 + j * 59
            layer.paste(fx.text_rgba(en, fx.DIN, 27, fx.CHALK), 1405, yy, alpha=alpha * morph)
            layer.paste(fx.text_rgba(cn, fx.CJK, 17, fx.MUTED), 1407, yy + 31, alpha=alpha * morph)
        from presentation_stats import draw_player_cards, draw_defense_card
        draw_player_cards(layer, name, t, morph, alpha)
        draw_defense_card(layer, name, t, morph, alpha)
    a = alpha * fx.ease_out((t - .24) / .35)
    fx.rect(layer, 65, 856, 1855, 978, fx.VOID, .86 * a)
    fx.rect(layer, 65, 856, 72, 978, fx.ORANGE, a)
    layer.paste(fx.text_rgba(scene['captionEn'], fx.DIN, 46, fx.CHALK, 1), 99, 865, alpha=a)
    layer.paste(fx.text_rgba(scene['captionCn'], fx.CJK, 25, fx.MUTED), 101, 929, alpha=a)
    layer.paste(fx.text_rgba('SCHEMATIC POSITIONS · DIRECTIONAL ARROWS', fx.DIN, 22, fx.MUTED, 1),
                960, 1012, alpha=alpha, anchor='c')
