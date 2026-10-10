"""Source-reviewed floor-space highlights for the English presentation cut.

The camera polygons are assistant-drawn on two exact held source frames; the
board polygons are independently composed editorial areas. They show visible
floor worth watching, not a measured opening, a guaranteed passing lane, or
model segmentation/tracking. No distance, area or automatic calibration is
inferred. T1 is crowded and is deliberately left without an 'open space' patch.

Call ``draw_space`` after creating Layers and before court/player/UI graphics.
The camera patch fades away before the board patch appears. Existing timing is
unchanged and all highlights fade before the held image returns to live video.
"""
from functools import lru_cache

import cv2
import numpy as np

from broadcast_fx import legacy as fx, tactics

SOURCE_SHA256 = "f2c0fb6aa1ec10bd78ea9e6724190b7f03bf48f21af2f743c694bbdb49254c91"
SOURCE_FRAMES = {"T3": 480, "T2": 719}
CANVAS = (1080, 1920)
COLOR = (229, 218, 90)  # Restrained cyan, distinct from the attack direction.

# These small patches stay on visible floor and avoid bodies, shoes, the source
# score graphic and the presentation caption. Camera points are image pixels;
# board points use the existing editorial [depth, width] half-court convention.
SPACES = {
    "T3": {
        "camera": ((1190, 829), (1344, 816), (1341, 847), (1208, 854)),
        "board": ((8.8, 35.0), (10.0, 40.0), (15.6, 43.0), (15.2, 35.5)),
        "label": "RESET SPACE",
        "basis": "Visible floor between the interior support and the right-side reset. "
                 "The on-ball defender remains close; this is not an uncontested shot claim.",
    },
    "T2": {
        "camera": ((660, 778), (843, 762), (877, 847), (728, 844)),
        "board": ((21.5, 41.5), (27.0, 41.8), (31.5, 46.3), (22.0, 46.3)),
        "label": "SHIFTING SPACE",
        "basis": "Visible wood floor beyond the screen toward the middle. "
                 "An editorial viewing cue for the ball handler's change of direction, "
                 "not a reconstruction of space created or defender reach.",
    },
}


def _smooth(value):
    value = float(np.clip(value, 0, 1))
    return value * value * (3 - 2 * value)


@lru_cache(maxsize=4)
def _patch(name, view):
    points = np.asarray(SPACES[name][view], np.float64)
    if view == "board":
        points = tactics.board_points(points)
    x0, y0 = np.floor(points.min(axis=0) - 10).astype(int)
    x1, y1 = np.ceil(points.max(axis=0) + 11).astype(int)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(CANVAS[1], x1), min(CANVAS[0], y1)
    shape = (y1 - y0, x1 - x0)
    local = np.rint(points - (x0, y0)).astype(np.int32)
    mask = np.zeros(shape, np.uint8)
    cv2.fillPoly(mask, [local], 255, cv2.LINE_AA)
    fill = cv2.GaussianBlur(mask.astype(np.float32) / 255, (0, 0), 1.6)
    edge = np.zeros(shape, np.uint8)
    cv2.polylines(edge, [local], True, 255, 2, cv2.LINE_AA)
    edge = cv2.GaussianBlur(edge.astype(np.float32) / 255, (0, 0), .65)
    hatch = np.zeros(shape, np.uint8)
    # Sparse linework follows a shallow court-like slope on camera. It remains
    # entirely clipped to the polygon and does not imply a measured grid.
    stride = 18 if view == "camera" else 23
    rise = .18 if view == "camera" else .65
    for y in range(-shape[1], shape[0] + shape[1], stride):
        cv2.line(hatch, (0, y), (shape[1], int(y - shape[1] * rise)),
                 255, 1, cv2.LINE_AA)
    hatch = hatch.astype(np.float32) / 255 * fill
    glow = cv2.GaussianBlur(edge, (0, 0), 3.0)
    # Alpha remains low so court markings and texture remain readable.
    opacity = np.clip(fill * .15 + edge * .46 + hatch * .10, 0, .68)
    return x0, y0, x1, y1, opacity, glow


def draw_space(layer, name, t, morph, release):
    """Draw floor patches in-place; no new pause or source frame is introduced."""
    if name not in SPACES:
        return
    if layer.img.shape[:2] != CANVAS:
        raise ValueError("Floor-space graphics require the bound 1920x1080 source frame")
    release_alpha = 1 - _smooth(release)
    camera_alpha = _smooth((t - .16) / .30)
    camera_alpha *= 1 - _smooth((t - 1.08) / .56)
    camera_alpha *= (1 - _smooth(morph)) * release_alpha
    board_alpha = _smooth((morph - .67) / .30)
    board_alpha *= _smooth((t - 1.80) / .36) * release_alpha
    for view, alpha in (("camera", camera_alpha), ("board", board_alpha)):
        if alpha < .001:
            continue
        x0, y0, x1, y1, opacity, glow = _patch(name, view)
        a = opacity[..., None] * alpha
        roi = layer.img[y0:y1, x0:x1]
        color = np.asarray(COLOR, np.float32)
        roi[:] = roi * (1 - a) + color * a
        roi += glow[..., None] * color * (.12 * alpha)
    if board_alpha > .001:
        # Keep wording outside the schematic area so player markers stay clear.
        label = SPACES[name]["label"] + "  /  EDITORIAL"
        fx.line(layer.sharp, (685, 835), (725, 835), COLOR, board_alpha * .70, 2)
        layer.paste(fx.text_rgba(label, fx.DIN, 20, fx.CHALK, 1),
                    740, 823, alpha=.86 * board_alpha)
