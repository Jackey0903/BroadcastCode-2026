"""Source-reviewed schematic positions for the separate PPT presentation edit.

These positions refine composition and relative spacing, not measured tracking.
The historical competition renderer and its original image anchors stay intact.
"""
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parent / "data/formal-presentation-court.json"


@lru_cache(maxsize=1)
def annotations():
    """Read the presentation-only layout and reject points outside safe bounds."""
    raw = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    depth, width = raw["courtSize"]
    margin = raw["markerSafeMargin"]
    for scene in raw["scenes"].values():
        for player in scene["players"].values():
            x, y = player["court"]
            if not (margin <= x <= depth - margin and margin <= y <= width - margin):
                raise ValueError("Presentation player marker crosses the court safety margin")
        for path in scene["arrows"]:
            if len(path) < 2:
                raise ValueError("Presentation arrow needs two positions")
            if any(not (0 <= x <= depth and 0 <= y <= width) for x, y in path):
                raise ValueError("Presentation direction arrow crosses the court")
    return raw


def refine_scene(name, scene):
    """Copy a scene and attach board-only points; preserve original image anchors.

    Consumers map ``player['boardCourt']`` and ``scene['boardArrows']`` through
    ``tactics.board_points``. Existing source-frame positions and body-only
    brackets are unchanged throughout the camera-to-board transition.
    """
    layout = annotations()["scenes"][name]
    if scene["frame"] != layout["frame"]:
        raise ValueError("Presentation court layout does not match the source frame")
    if {p["id"] for p in scene["players"]} != set(layout["players"]):
        raise ValueError("Presentation court layout does not match the visible players")
    if len(scene["arrows"]) != len(layout["arrows"]):
        raise ValueError("Presentation court layout does not match the direction arrows")
    refined = deepcopy(scene)
    for player in refined["players"]:
        reviewed = layout["players"][player["id"]]
        player["boardCourt"] = list(reviewed["court"])
        player["boardPositionBasis"] = reviewed["basis"]
    refined["boardArrows"] = deepcopy(layout["arrows"])
    refined["boardReview"] = layout["review"]
    return refined
