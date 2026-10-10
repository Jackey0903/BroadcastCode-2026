"""Source-bound player cards for the retrospective PPT edit, never live metrics."""
from functools import lru_cache
import hashlib
import json
from pathlib import Path

from broadcast_fx import legacy as fx, tactics

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
STORE = ROOT / 'product/rl/data/evidence/store.json'
OFFICIAL = HERE / 'formal/data/official.json'


@lru_cache(maxsize=1)
def card_data():
    """Resolve exact evidence IDs and retain scope and original source receipts."""
    records = {r['evidenceId']: r for r in json.loads(STORE.read_text())['records']}
    official = json.loads(OFFICIAL.read_text())
    if official['game']['gameId'] != '0022500356' or official['eventId'] != 273:
        raise ValueError('Player cards require the verified Christie game and shot')

    def record(evidence_id, player, metric, grain, unit):
        r = records[evidence_id]
        if (r['playerId'], r['metric'], r['grain'], r['unit']) != (player, metric, grain, unit):
            raise ValueError('Player-card evidence identity or units changed')
        if grain == 'player-game' and r['gameId'] != official['game']['gameId']:
            raise ValueError('Player card belongs to another game')
        if grain == 'player-season' and r['period'] != {
                'season': '2025-26', 'seasonType': 'Regular Season', 'range': 'source_season_snapshot'}:
            raise ValueError('Player-card season scope changed')
        source = ROOT / r['source']['path']
        if hashlib.sha256(source.read_bytes()).hexdigest() != r['source']['sha256']:
            raise ValueError('Player-card raw source hash mismatch')
        return r

    gravity = record('e668e9dec6274', '1631108', 'OFF_BALL_PERIM_GRAV', 'player-season', 'gravity_score')
    on_ball_gravity = record('e87b46b0406bf', '1631108', 'ON_BALL_PERIM_GRAV', 'player-season', 'gravity_score')
    shot_quality = record('e6b7001720ade', '1631108', 'AVGSHOTQUALITY', 'player-season', 'fraction')
    three_quality = record('ed1b330db90a7', '1631108', 'AVGSHOTQUALITY3PT', 'player-season', 'fraction')
    defense = record('efb6f98be6489', '1631095', 'DEF_LVG', 'player-season', 'leverage_score')
    on_ball_defense = record('e5254c697db59', '1631095', 'ON_BALL_DEF_LVG', 'player-season', 'leverage_score')
    capela_defense = record('e8a63d3a4fdcc', '203991', 'DEF_LVG', 'player-season', 'leverage_score')
    capela_rebound = record('eb664ac7817e8', '203991', 'REB_LVG', 'player-season', 'leverage_score')
    rebound = record('ecf35983866ae', '203939', 'REB_LVG', 'player-season', 'leverage_score')
    creation = record('e6aa13262a6a5', '203939', 'CREATION_LVG', 'player-season', 'leverage_score')
    efficiency = record('e095ec00938d6', '1631108', 'EFG_PCT', 'player-game', 'fraction')
    counts = efficiency['derivation']['operands']
    if counts['FGA'] <= 0 or abs((counts['FGM'] + .5 * counts['FG3M']) / counts['FGA'] - efficiency['value']) > 1e-9:
        raise ValueError('Derived efficiency disagrees with the official counts')
    board_events = [r for r in official['chain'] if r['actionNumber'] == 272
                    and r['personId'] == 203939 and r['actionType'] == 'Rebound']
    if len(board_events) != 1 or board_events[0]['description'] != 'Powell REBOUND (Off:1 Def:0)':
        raise ValueError('The verified offensive-rebound event changed')
    shot = official['shot']
    if shot['rawGpShot']['playerId'] != '1631108' or shot['rawGpShot']['eventId'] != 273:
        raise ValueError('xFG card belongs to another player or attempt')

    def card(player, value, label, detail, scope, color, evidence, secondary=None):
        return dict(player=player, value=value, label=label, detail=detail,
                    scope=scope, color=color, evidence=evidence, secondaryEvidence=secondary)

    def defender(player, metrics):
        return {'player': player, 'role': 'HOU DEFENSE',
                'scope': '2025–26 SEASON SNAPSHOT · SOURCE SCORES',
                'metrics': [{'label': label, 'value': f"{evidence['value']:.2f}", 'evidence': evidence}
                            for label, evidence in metrics]}

    smith = defender('#10  JABARI SMITH JR.', [('DEF. LEVERAGE', defense),
                                              ('ON-BALL DEF. LEVERAGE', on_ball_defense)])

    return {
        'T1': [
            card('#00  MAX CHRISTIE', f"{gravity['value']:.3f}", 'OFF-BALL PERIM. GRAVITY',
                 f"ON-BALL: {on_ball_gravity['value']:.3f} · SCORE",
                 '2025–26 SNAPSHOT · GRAVITY SCORES', fx.FLAME, gravity, on_ball_gravity),
            card('#00  MAX CHRISTIE', f"{shot_quality['value'] * 100:.1f}%", 'AVG SHOT QUALITY',
                 f"3PT EXPECTED FG: {three_quality['value'] * 100:.1f}%",
                 '2025–26 SEASON SNAPSHOT', fx.FLAME, shot_quality, three_quality)],
        'T3': [
            card('#7  DWIGHT POWELL', str(len(board_events)), 'OFFENSIVE REBOUND',
                 'KEEPS THE POSSESSION ALIVE', 'THIS PLAY · Q2 5:03', fx.CYAN,
                 {'source': 'product/broadcast-fx/formal/data/official.json', 'event': board_events[0]}),
            card('#7  DWIGHT POWELL', f"{rebound['value']:.2f}", 'REBOUND LEVERAGE',
                 f"CREATION LEVERAGE: {creation['value']:.2f}",
                 '2025–26 SNAPSHOT · LEVERAGE SCORES', fx.CYAN, rebound, creation)],
        'T2': [
            card('#00  MAX CHRISTIE', f"{shot['rawGpShot']['value'] * 100:.0f}%", 'EXPECTED FG · xFG',
                 f"{shot['shotDistanceFeet']} FT · STEP-BACK THREE", 'THIS ATTEMPT · EVENT 273', fx.FLAME,
                 {'source': 'product/broadcast-fx/formal/data/official.json', 'shot': shot}),
            card('#00  MAX CHRISTIE', f"{efficiency['value'] * 100:.0f}%", 'EFFECTIVE FG · eFG',
                 f"{counts['FGM']}/{counts['FGA']} FG · {counts['FG3M']} MADE THREE", 'FINAL GAME · DERIVED EFFICIENCY', fx.CYAN, efficiency)],
        'defenseCards': {
            'T1': smith,
            'T2': smith,
            'T3': defender('#30  CLINT CAPELA', [('DEF. LEVERAGE', capela_defense),
                                               ('REBOUND LEVERAGE', capela_rebound)]),
        },
    }


def draw_player_cards(layer, name, t, morph, alpha):
    """Reveal factual values intact: no tweened numbers or artificial rating bars."""
    for index, card in enumerate(card_data()[name]):
        entry = fx.ease_out((t - 1.62 - index * .10) / .35)
        a = alpha * morph * entry
        if a <= .003:
            continue
        x, y, width, height = 1385 + 16 * (1 - entry), 476 + index * 170, 490, 158
        color = card['color']
        fx.rect(layer, x, y, x + width, y + height, fx.VOID, .88 * a)
        fx.rect(layer, x, y, x + 4, y + height, color, a)
        fx.line(layer.sharp, (x + 15, y), (x + width, y), color, .38 * a, 1)
        layer.paste(fx.text_rgba(card['player'], fx.DIN, 27, fx.CHALK, 1), x + 18, y + 8, alpha=a)
        layer.paste(fx.text_rgba(card['value'], fx.DIN, 65, color), x + 18, y + 39, alpha=a)
        layer.paste(fx.text_rgba(card['label'], fx.DIN, 25, fx.CHALK), x + 172, y + 49, alpha=a)
        layer.paste(fx.text_rgba(card['detail'], fx.DIN, 19, fx.MUTED), x + 172, y + 81, alpha=a)
        layer.paste(fx.text_rgba(card['scope'], fx.DIN, 22, fx.CHALK, .4), x + 18, y + 125, alpha=a)


def draw_defense_card(layer, name, t, morph, alpha):
    """A defense profile, without implying a measured matchup or causal rating."""
    entry = fx.ease_out((t - 1.62) / .35)
    a = alpha * morph * entry
    if a <= .003:
        return
    card = card_data()['defenseCards'][name]
    x, y, width, height = 70 - 16 * (1 - entry), 697, 520, 145
    fx.rect(layer, x, y, x + width, y + height, fx.VOID, .9 * a)
    fx.rect(layer, x, y, x + 4, y + height, tactics.RED, a)
    fx.line(layer.sharp, (x + 16, y), (x + width, y), tactics.RED, .38 * a, 1)
    layer.paste(fx.text_rgba(card['player'], fx.DIN, 27, fx.CHALK, .6), x + 18, y + 7, alpha=a)
    layer.paste(fx.text_rgba(card['role'], fx.DIN, 21, tactics.RED), x + width - 17, y + 10, alpha=a, anchor='rt')
    for index, metric in enumerate(card['metrics']):
        xx = x + 18 + index * 248
        layer.paste(fx.text_rgba(metric['label'], fx.DIN, 22, fx.CHALK), xx, y + 39, alpha=a)
        layer.paste(fx.text_rgba(metric['value'], fx.DIN, 48, tactics.RED), xx, y + 61, alpha=a)
    layer.paste(fx.text_rgba(card['scope'], fx.DIN, 20, fx.CHALK, .15), x + 18, y + 116, alpha=a)
