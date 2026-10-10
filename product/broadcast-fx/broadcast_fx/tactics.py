"""Reusable editorial basketball overlays and two source-anchored tactic scenes.

All player positions are editorial anchors visually reviewed by the assistant. Homographies are an
approximate graphic layout aid, not measured court coordinates or tracking.
The caller supplies a work directory to legacy.configure before rendering.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import cv2
import numpy as np

from . import legacy as fx

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "tactics_reviewed.json"
SCENES = {}
RED = (102, 98, 255)
MINT = (192, 245, 104)


def configure(workdir):
    """Load versioned editorial scene annotations; never infer hidden players."""
    global SCENES
    raw = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    SCENES = raw["scenes"]
    for scene in SCENES.values():
        h = np.asarray(scene["H"], np.float64)
        if h.shape != (3, 3) or not np.isfinite(h).all():
            raise ValueError("Invalid editorial projection")
        if len({p["id"] for p in scene["players"]}) != len(scene["players"]):
            raise ValueError("Duplicate player annotation")
        for p in scene["players"]:
            if p["anchorKind"] not in ("visible-foot", "body-only"):
                raise ValueError("Unknown anchor kind")
    return raw


def project_points(points, homography):
    """Project graphic points; callers must retain their editorial provenance."""
    pts = np.asarray(points, np.float64).reshape(-1, 2)
    h = np.asarray(homography, np.float64)
    v = np.c_[pts, np.ones(len(pts))] @ h.T
    if not np.isfinite(v).all() or np.any(np.abs(v[:, 2]) < 1e-7):
        raise ValueError("Projection crosses horizon")
    return v[:, :2] / v[:, 2, None]


def board_points(points):
    """Rotate a half-court diagram so the attacking basket sits at the top."""
    p = np.asarray(points, np.float64).reshape(-1, 2)
    return np.c_[650 + p[:, 1] * 12.4, 245 + p[:, 0] * 12.4]


def scene_project(scene, points, morph):
    a = project_points(points, scene["H"])
    b = board_points(points)
    return a * (1 - morph) + b * morph


def draw_path(layer, points, color, reveal=1.0, alpha=1.0, width=5,
              arrow=True, dashed=False):
    """Draw an animated vector path, optionally with a moving dashed stroke."""
    pts = np.asarray(points, np.float64)
    if len(pts) < 2 or reveal <= 0 or alpha <= 0:
        return
    lengths = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    total = float(lengths.sum())
    limit = total * fx.clamp(reveal)
    traversed = 0.0
    last_a = last_b = None
    for a, b, length in zip(pts[:-1], pts[1:], lengths):
        if length < 1e-5 or traversed >= limit:
            continue
        end = a + (b - a) * min(1, (limit - traversed) / length)
        if dashed:
            count = max(1, int(np.linalg.norm(end - a) / 20))
            for j in range(count):
                if j % 2 == 0:
                    aa = a + (end - a) * j / count
                    bb = a + (end - a) * min(j + .68, count) / count
                    fx.line(layer.sharp, aa, bb, color, alpha, width)
        else:
            fx.line(layer.sharp, a, end, color, alpha, width)
            fx.line(layer.glow, a, end, fx.scale_c(color, alpha * .65), 1, width * 2)
        last_a, last_b = a, end
        traversed += length
    if arrow and last_a is not None:
        d = last_b - last_a
        d = d / max(.01, float(np.linalg.norm(d)))
        side = np.array([-d[1], d[0]])
        for sign in (-1, 1):
            q = last_b - d * (22 + width) + side * sign * (12 + width * .4)
            fx.line(layer.sharp, q, last_b, color, alpha, width)


def draw_marker(layer, position, color, label, t, alpha=1, active=False,
                perspective=1, body_only=False):
    """A foot ring or a body bracket; hidden feet never receive invented rings."""
    x, y = map(float, position)
    pulse = 1 + .055 * math.sin(t * 6)
    r = ((42 if active else 28) * perspective + (27 if active else 19) * (1 - perspective)) * pulse
    ratio = .30 + .70 * (1 - perspective)
    if body_only and perspective > .92:
        # Brackets identify the visible body without claiming a floor contact.
        for sign in (-1, 1):
            xx = x + sign * 37
            fx.line(layer.sharp, (xx, y - 48), (xx, y + 36), color, .8 * alpha, 3)
            fx.line(layer.sharp, (xx, y - 48), (xx - sign * 13, y - 48), color, alpha, 3)
    else:
        fx.ellipse(layer.glow, (x, y), (r, r * ratio), fx.scale_c(color, .6 * alpha), 1, 8)
        if body_only and perspective < .92:
            for arc in range(0, 360, 45):
                fx.ellipse(layer.sharp, (x, y), (r, r * ratio), color, .8 * alpha, 2, arc, arc + 28)
        else:
            fx.ellipse(layer.sharp, (x, y), (r, r * ratio), color, .95 * alpha, 3)
        fx.ellipse(layer.sharp, (x, y), (r * .72, r * ratio * .72), color, .45 * alpha, 1)
        for a in range(0, 360, 90):
            fx.ellipse(layer.sharp, (x, y), (r * 1.20, r * ratio * 1.20),
                       fx.CHALK, .7 * alpha, 2, a + t * 65, a + t * 65 + 20)
    if label:
        yy = y - (62 if perspective > .5 else 2)
        size = 30 if perspective > .5 else 25
        text = fx.text_rgba(label, fx.DIN, size, fx.CHALK, 1)
        if perspective > .5:
            ww = text.shape[1] + 22
            fx.rect(layer, x - ww / 2, yy - 22, x + ww / 2, yy + 20,
                    fx.VOID, .84 * alpha)
        layer.paste(text, x, yy, alpha=alpha, anchor="c")


def court_geometry():
    a = np.linspace(0, 2 * math.pi, 60)
    paths = [([(0, 0), (47, 0), (47, 50), (0, 50), (0, 0)], 2),
             ([(0, 17), (19, 17), (19, 33), (0, 33)], 2),
             ([(4, 22), (4, 28)], 2),
             (np.c_[5.25 + .8 * np.cos(a), 25 + .8 * np.sin(a)], 2),
             (np.c_[19 + 6 * np.cos(a), 25 + 6 * np.sin(a)], 1)]
    theta = np.linspace(-1.185, 1.185, 90)
    arc = np.c_[5.25 + 23.75 * np.cos(theta), 25 + 23.75 * np.sin(theta)]
    paths.append((np.vstack(([[0, 3]], arc, [[0, 47]])), 2))
    return paths


def _tactic_vectors(layer, scene, morph, t, alpha):
    project = lambda p: scene_project(scene, p, morph)
    paths = scene["paths"]
    reveal = fx.ease_in_out((t - .65) / 1.2)
    if scene["key"] == "T1":
        route = project(paths["D32_drive"])
        draw_path(layer, route, fx.FLAME, reveal, alpha, 6)
        draw_path(layer, project(paths["D21_screen"]), fx.CYAN,
                  fx.ease_out((t - .40) / .85), alpha, 5)
        # Crossbar on the screener's final position denotes a screen, not contact.
        q = np.asarray(paths["D21_screen"][-1])
        screen = project([q + [-1.7, 0], q + [1.7, 0]])
        draw_path(layer, screen, fx.CYAN, reveal, alpha, 7, arrow=False)
        draw_path(layer, project(paths["W17_chase"]), RED,
                  reveal, alpha * .55, 3, dashed=True)
    else:
        route = project(paths["D32_drive"])
        # A broad fading lane is an editorial emphasis on the visible move.
        draw_path(layer, route, fx.FLAME, reveal, alpha * .28, 23, arrow=False)
        draw_path(layer, route, fx.LED, reveal, alpha, 6)
        for key in ("help_inner", "help_trailer"):
            draw_path(layer, project(paths[key]), RED, reveal,
                      alpha * .68, 4, dashed=True)


def _title_and_notes(layer, scene, t, morph, alpha):
    entry = fx.ease_out(t / .33)
    x = 70 - 25 * (1 - entry)
    fx.rect(layer, x, 55, x + 8, 178, fx.ORANGE, alpha)
    layer.paste(fx.text_rgba(scene["titleEn"], fx.DIN, 76, fx.CHALK, 3),
                x + 28, 48, alpha=alpha * entry)
    layer.paste(fx.text_rgba(scene["titleCn"], fx.CJK, 38, fx.CHALK),
                x + 30, 128, alpha=alpha * entry)
    layer.paste(fx.text_rgba("GameBuddy", fx.DINA, 44, fx.CHALK),
                1850, 57, alpha=alpha, anchor="rt")
    layer.paste(fx.text_rgba("COACH VIEW  /  " + scene["badge"], fx.DIN, 29, fx.CYAN, 2),
                1850, 114, alpha=alpha, anchor="rt")
    layer.paste(fx.text_rgba("编辑战术示意 · 非模型识别", fx.CJK, 23, fx.CHALK),
                1850, 160, alpha=.9 * alpha, anchor="rt")
    # Small team legend remains legible in both camera and board views.
    for xx, color, text in ((75, fx.CYAN, "DAL 进攻"), (265, RED, "HOU 防守")):
        fx.rect(layer, xx, 207, xx + 16, 223, color, alpha)
        layer.paste(fx.text_rgba(text, fx.CJK, 23, fx.CHALK), xx + 26, 196, alpha=alpha)
    if morph > .01:
        for j, (en, cn) in enumerate(scene["steps"]):
            yy = 340 + j * 124
            a = alpha * morph * fx.ease_out((t - 1.75 - .10 * j) / .4)
            layer.paste(fx.text_rgba(f"0{j+1}", fx.DIN, 64, fx.ORANGE), 90, yy, alpha=a)
            layer.paste(fx.text_rgba(en, fx.DIN, 36, fx.CHALK, 2), 164, yy + 3, alpha=a)
            layer.paste(fx.text_rgba(cn, fx.CJK, 25, fx.MUTED), 166, yy + 50, alpha=a)
        layer.paste(fx.text_rgba("READ THE FLOOR", fx.DIN, 36, fx.CYAN, 3), 1430, 376, alpha=alpha * morph)
        for j, row in enumerate(scene["aside"]):
            layer.paste(fx.text_rgba(row, fx.CJK, 27, fx.CHALK), 1430, 439 + j * 48,
                        alpha=alpha * morph)
        layer.paste(fx.text_rgba("示意站位 · 非精确坐标", fx.CJK, 21, fx.MUTED),
                    1430, 610, alpha=alpha * morph)
    # Opaque lower plate keeps the explanation separate from the score bug.
    a = alpha * fx.ease_out((t - .24) / .35)
    fx.rect(layer, 65, 856, 1855, 971, fx.VOID, .83 * a)
    fx.rect(layer, 65, 856, 72, 971, fx.ORANGE, a)
    layer.paste(fx.text_rgba(scene["captionEn"], fx.DIN, 33, fx.CYAN, 2), 99, 861, alpha=a)
    layer.paste(fx.text_rgba(scene["captionCn"], fx.CJK, 43, fx.CHALK), 98, 908, alpha=a)
    layer.paste(fx.text_rgba("人工关键帧 · 箭头为动作方向解读 · 原片足点与遮挡分别标注", fx.CJK, 21, fx.MUTED),
                960, 1016, alpha=alpha, anchor="c")
    fx.rect(layer, 70, 1040, 1850, 1043, (50, 53, 59), alpha)
    fx.rect(layer, 70, 1040, 70 + 1780 * fx.clamp(t / (220 / fx.FPS)), 1043, fx.ORANGE, alpha)


def render_scene(name, i, n):
    """Render one BGR frame of an editorial tactical pause (normally 220 frames)."""
    if not SCENES:
        raise RuntimeError("Call tactics.configure(workdir) first")
    scene = SCENES[name]
    t = i / fx.FPS
    duration = n / fx.FPS
    # Camera freeze -> schematic board -> dissolve back to the source frame.
    morph = fx.ease_in_out((t - 1.48) / .86)
    release = fx.ease_in_out((t - (duration - .32)) / .32)
    morph *= 1 - release
    alpha = (1 - release) * min(1, .65 + t * 3)
    base = fx.src_frame(scene["frame"])
    gain = 1 - (.18 + .70 * morph) * (1 - release)
    layer = fx.Layers(fx.grade(base, sat=1 - .55 * morph, gain=gain, vig=.35 * morph))
    if morph > .001:
        for points, width in court_geometry():
            pos = scene_project(scene, points, morph)
            draw_path(layer, pos, fx.CHALK, 1, .28 * morph * alpha, width, arrow=False)
        # The basket gets one orange target, keeping attack direction clear.
        target = scene_project(scene, [[5.25, 25]], morph)[0]
        fx.ellipse(layer.glow, target, (25, 25), fx.scale_c(fx.ORANGE, morph * .6), 1, 10)
    _tactic_vectors(layer, scene, morph, t, alpha)
    for j, player in enumerate(scene["players"]):
        p_image = np.asarray(player["image"])
        p_board = board_points([player["court"]])[0]
        pos = p_image * (1 - morph) + p_board * morph
        color = fx.CYAN if player["team"] == "offense" else RED
        if player["id"] == "D32":
            color = fx.FLAME
        a = alpha * fx.ease_out((t - .10 - j * .025) / .32)
        label = player.get("number")
        draw_marker(layer, pos, color, label, t, a,
                    active=player["id"] in ("D32", "D21"),
                    perspective=1 - morph, body_only=player["anchorKind"] == "body-only")
    # Text and plates sit above effects so feet near the bottom cannot paint
    # through explanatory captions or the source/disclosure line.
    overlay = fx.Layers(layer.compose(glow_gain=.75))
    _title_and_notes(overlay, scene, t, morph, alpha)
    image = overlay.compose(glow_gain=0)
    if t < .10:
        image = cv2.addWeighted(image, 1, np.full_like(image, 255), .10 * (1 - t / .10), 0)
    return image
