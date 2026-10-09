#!/usr/bin/env python3
"""Rebuild the editorial schematic from stored image annotations; no detector.

Only standard-library Python is required. The source video hash is verified.
This does not overwrite the failed optical-flow experiment or call any service.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def digest(path):
    sha = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            sha.update(block)
    return sha.hexdigest()


def image_to_court(point, matrix):
    px, py = point
    denominator = matrix[2][0] * px + matrix[2][1] * py + matrix[2][2]
    if abs(denominator) < 1e-10:
        raise ValueError("Image point maps to infinity")
    xy = [(row[0] * px + row[1] * py + row[2]) / denominator for row in matrix[:2]]
    if not all(math.isfinite(value) for value in xy):
        raise ValueError("Nonfinite projected coordinates")
    return [round(value, 3) for value in xy]


def main():
    annotations = json.loads((HERE / "flagg-annotations.json").read_text())
    source = ROOT / annotations["sourceLocalPath"]
    if digest(source) != annotations["sourceSha256"]:
        raise SystemExit("Source hash changed: stored image annotations are invalid")
    frames = annotations["frames"]
    if len(frames) != 7 or any(right["t"] <= left["t"] for left, right in zip(frames, frames[1:])):
        raise SystemExit("Expected seven increasing real-media-time keyframes")
    tracks = []
    for identity in annotations["identities"]:
        points = []
        for frame in frames:
            point = {"t": frame["t"], "x": None, "y": None,
                     "status": "occluded", "segment": frame["segment"], "reviewed": False}
            foot = frame["feet"][identity["id"]]
            if foot is not None:
                if not (0 <= foot[0] <= 1280 and 0 <= foot[1] <= 720):
                    raise ValueError("Foot coordinate outside source image")
                x, y = image_to_court(foot, frame["calibration"]["imageToCourt"])
                if not (0 <= x <= 94 and 0 <= y <= 50):
                    raise ValueError(f"{identity['id']} at {frame['t']} is outside the court; review the annotation, don't clamp")
                point.update({"x": x, "y": y, "image": foot, "status": "estimated"})
            else:
                point["reason"] = frame["unknownReasons"].get(identity["id"], "foot_not_clear")
            points.append(point)
        tracks.append({**identity, "points": points})
    data = {"schema": "court-lab-v1", "sample": annotations["sample"],
            "presentation": "schematic", "sourceSha256": annotations["sourceSha256"],
            "sourceVideo": annotations["sourceVideo"], "videoSize": annotations["videoSize"],
            "court": annotations["court"], "window": [frames[0]["t"], frames[-1]["t"]],
            "provenance": {"method": annotations["annotationMethod"],
                "warning": annotations["warning"], "reviewed": False,
                "officialTracking": False, "accuracyMeasured": False,
                "acceptedAsAutomaticTracking": False, "independentExpertReview": False,
                "annotations": "flagg-annotations.json", "generator": "generate_schematic.py",
                "interpolation": "linear schematic movement between edited visible anchors; never across unknown points",
                "rawFlowEvidence": "flow-flagg.json"}, "tracks": tracks}
    (HERE / "flagg.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    visible = [{"t": frame["t"], "visible": sum(track["points"][index]["status"] == "estimated" for track in tracks)}
               for index, frame in enumerate(frames)]
    valid = [point for track in tracks for point in track["points"] if point["status"] == "estimated"]
    print(json.dumps({"output": "product/court-lab/flagg.json", "window": data["window"],
        "visibleKeyframes": visible, "coordinateBoundsFt": {
            "x": [min(point["x"] for point in valid), max(point["x"] for point in valid)],
            "y": [min(point["y"] for point in valid), max(point["y"] for point in valid)]},
        "sourceHashMatched": True}, ensure_ascii=False))


if __name__ == "__main__":
    main()
