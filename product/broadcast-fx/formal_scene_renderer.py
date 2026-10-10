"""Reuse the asset library's camera-to-board animation with formal-source anchors.

The board is an editorial layout. It neither reconstructs court coordinates nor
uses the legacy clip's players, tracking, event values or media.
"""
from pathlib import Path
import json
import sys

import cv2
import numpy as np

from broadcast_fx import legacy as fx, tactics

HERE = Path(__file__).resolve().parent
ANNOTATIONS = HERE / "formal/data/annotations.json"
ROOT = HERE.parents[1]


def board_position(image):
    """Approximate composition for a schematic, never a measured court point."""
    x, y = image
    return np.array([660 + (x - 400) / 1100 * 600,
                     260 + (y - 350) / 700 * 555], dtype=float)


def render_scene(name, local_frame, count=210, workdir=None, scene_override=None, presentation_english=False):
    workdir = Path(workdir or ROOT / "product/build/formal-video")
    raw = json.loads(ANNOTATIONS.read_text())
    scene = dict(scene_override or raw["scenes"][name])
    if presentation_english:
        from presentation_court import refine_scene
        scene = refine_scene(name, scene)
    base = cv2.imread(str(workdir / f"frames/f{scene['frame']:04d}.jpg"))
    if base is None:
        raise FileNotFoundError("Missing source-bound formal frame")
    t, duration = local_frame / fx.FPS, count / fx.FPS
    morph = fx.ease_in_out((t - 1.15) / .85)
    release = fx.ease_in_out((t - (duration - .32)) / .32)
    morph *= 1 - release
    alpha = (1 - release) * min(1, .65 + t * 3)
    layer = fx.Layers(fx.grade(base, sat=1 - .55 * morph,
                             gain=1 - (.18 + .70 * morph) * (1 - release),
                             vig=.35 * morph))
    if morph > .001:
        for points, width in tactics.court_geometry():
            tactics.draw_path(layer, tactics.board_points(points), fx.CHALK,
                              1, .28 * morph * alpha, width, arrow=False)
        target = tactics.board_points([[5.25, 25]])[0]
        fx.ellipse(layer.glow, target, (25, 25), fx.scale_c(fx.ORANGE, morph * .6), 1, 10)
    for path_index, path in enumerate(scene["arrows"]):
        original = np.asarray(path["points"], dtype=float)
        board = (tactics.board_points(scene['boardArrows'][path_index]) if presentation_english else
                 np.array([board_position(point) for point in original]))
        points = original * (1 - morph) + board * morph
        color = fx.FLAME if path["kind"] == "offense" else tactics.RED
        tactics.draw_path(layer, points, color, fx.ease_in_out((t - .45) / .95),
                          alpha * (.95 if path["kind"] == "offense" else .65),
                          width=5, dashed=path["kind"] == "defense")
    for index, player in enumerate(scene["players"]):
        original = np.asarray(player["image"], dtype=float)
        board = (tactics.board_points([player['boardCourt']])[0] if presentation_english else
                 board_position(player["image"]))
        position = original * (1 - morph) + board * morph
        color = fx.FLAME if player["id"] == "D00" else fx.CYAN if player["team"] == "offense" else tactics.RED
        tactics.draw_marker(layer, position, color, player.get("number"), t,
                            alpha * fx.ease_out((t - .1 - index * .025) / .32),
                            active=player["id"] in ("D00", "D7"),
                            perspective=1 - morph,
                            body_only=player["anchorKind"] == "body-only")
    scene.update({"badge": "01 / DRIVE" if name == "T1" else "03 / RESET" if name == "T2" else "02 / SECOND CHANCE",
                  "steps": [("DRIVE", "持球切入"), ("PRESSURE", "防守向球侧收紧"), ("REBOUND", "争取第二次机会")] if name == "T1" else [("SCREEN", "7号形成掩护位置"), ("RESET", "00号向中路横移"), ("STEP BACK", "后撤步三分出手")],
                  "aside": ["先看持球人的位置", "再看队友与防守", "最后看出手空间"]})
    if scene_override:
        for key in ("steps", "aside", "badge"):
            if key in scene_override:
                scene[key] = scene_override[key]
    if presentation_english:
        from presentation_labels import draw_tactic_labels
        draw_tactic_labels(layer, scene, name, t, morph, alpha)
    else:
        tactics._title_and_notes(layer, scene, t, morph, alpha)
    return layer.compose(.65)


if __name__ == "__main__":
    destination = ROOT / "product/build/formal-video/asset-previews"
    destination.mkdir(exist_ok=True)
    for name in ("T1", "T2"):
        for frame in (55, 145):
            cv2.imwrite(str(destination / f"{name}-{frame}.jpg"), render_scene(name, frame))
    print(destination)
