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


def annotation_frames(annotations):
    """Keep projected foot anchors and direct editorial court layouts distinct."""
    frames = list(annotations["frames"])
    early_file = annotations.get("earlyAnnotationFile")
    if early_file:
        early = json.loads((HERE / early_file).read_text())
        if early["sourceSha256"] != annotations["sourceSha256"]:
            raise ValueError("Early frame source hash mismatch")
        for frame in early["frames"]:
            frames.append({"requestedTime": frame["requestedTime"], "t": frame["actualTime"],
                "imagePath": frame["file"], "imageSha256": frame["imageSha256"],
                "segment": "flagg-wide-1", "players": frame["players"],
                "annotationSource": early_file, "coordinateMethod": frame["coordinateMethod"],
                "reviewed": False})
    frames.sort(key=lambda frame: frame["t"])
    if not frames or any(right["t"] <= left["t"] for left, right in zip(frames, frames[1:])):
        raise ValueError("Expected increasing real-media-time keyframes")
    return frames


def player_point(frame, identity):
    point = {"t": frame["t"], "x": None, "y": None, "image": None,
             "status": "occluded", "segment": frame["segment"], "reviewed": False}
    direct = frame.get("players", {}).get(identity)
    if direct is not None:
        point.update({key: direct[key] for key in ("x", "y", "status")})
        point["reason"] = direct.get("reason", frame.get("coordinateMethod", "editorial_court_layout"))
    else:
        foot = frame.get("feet", {}).get(identity)
        inferred = frame.get("inferredImageAnchors", {}).get(identity)
        anchor = foot if foot is not None else inferred
        if anchor is not None:
            if not (0 <= anchor[0] <= 1280 and 0 <= anchor[1] <= 720):
                raise ValueError("Image annotation outside source frame")
            x, y = image_to_court(anchor, frame["calibration"]["imageToCourt"])
            point.update({"x": x, "y": y,
                "image": foot if foot is not None else None,
                "status": "estimated" if foot is not None else "inferred"})
            if inferred is not None:
                point["reason"] = frame["inferenceReasons"][identity]
        else:
            point["reason"] = frame.get("unknownReasons", {}).get(identity, "foot_not_clear")
            point["status"] = frame.get("unknownStatuses", {}).get(identity, "occluded")
    if point["x"] is not None:
        if not all(math.isfinite(point[axis]) for axis in ("x", "y")):
            raise ValueError("Nonfinite editorial coordinate")
        if not (0 <= point["x"] <= 94 and 0 <= point["y"] <= 50):
            raise ValueError(f"{identity} at {frame['t']} is outside the court; review, do not clamp")
        if point["status"] == "inferred" and point["image"] is not None:
            raise ValueError("Inferred court layouts cannot be original-image overlays")
    elif point["y"] is not None or point["status"] not in ("occluded", "offscreen"):
        raise ValueError("Unknown points must have two null coordinates")
    return point


def main():
    annotations = json.loads((HERE / "flagg-annotations.json").read_text())
    source = ROOT / annotations["sourceLocalPath"]
    if digest(source) != annotations["sourceSha256"]:
        raise SystemExit("Source hash changed: stored image annotations are invalid")
    frames = annotation_frames(annotations)
    tracks = []
    for identity in annotations["identities"]:
        points = []
        for frame in frames:
            points.append(player_point(frame, identity["id"]))
        tracks.append({**identity, "points": points})
    data = {"schema": "court-lab-v1", "sample": annotations["sample"],
            "presentation": "schematic", "sourceSha256": annotations["sourceSha256"],
            "sourceVideo": annotations["sourceVideo"], "videoSize": annotations["videoSize"],
            "court": annotations["court"], "window": annotations.get("window", [frames[0]["t"], frames[-1]["t"]]),
            "provenance": {"method": annotations["annotationMethod"],
                "warning": annotations["warning"], "reviewed": False,
                "officialTracking": False, "accuracyMeasured": False,
                "acceptedAsAutomaticTracking": False, "independentExpertReview": False,
                "annotations": "flagg-annotations.json", "generator": "generate_schematic.py",
                "interpolation": "linear schematic movement between image-edited anchors up to 1.25s; unknown intervals preserve only the past snapshot, never a new observation",
                "earlyAnnotations": annotations.get("earlyAnnotationFile"),
                "sourceDurationSeconds": annotations.get("sourceDurationSeconds"),
                "rawFlowEvidence": "flow-flagg.json"}, "tracks": tracks}
    for key in ("schematic", "scenes", "possession", "ball"):
        if key in annotations:
            data[key] = annotations[key]
    possession_file = annotations.get("possessionAnnotationFile")
    if possession_file:
        possession = json.loads((HERE / possession_file).read_text())
        data["possession"] = possession["suggestedUiSegments"]
        data["provenance"]["possessionAnnotations"] = possession_file
        data["provenance"]["possessionBoundaryBasis"] = "source-frame editorial transition brackets; not exact automatic release or catch times"
    if annotations.get("ballDiagramPlans"):
        ball_points = []
        for plan in annotations["ballDiagramPlans"]:
            phases = [phase for phase in data["possession"] if phase["phase"] == plan["phase"]]
            if len(phases) != 1:
                raise ValueError("Expected one interval for each ball schematic plan")
            phase = phases[0]
            # Keep the final anchor inside this half-open phase. The next phase
            # gets its own starting anchor, so no path crosses possession changes.
            last = phase["end"] - 1e-6
            for t, position in ((phase["start"], plan["from"]), (last, plan["to"])):
                ball_points.append({"t": t, "x": position[0], "y": position[1],
                    "status": "inferred", "image": None, "segment": "flagg-wide-1",
                    "reviewed": False, "reason": plan["reason"]})
        data["ball"] = {"kind": "court-schematic", "points": sorted(ball_points, key=lambda point: point["t"]),
            "warning": "Edited plan-view shot/pass diagram, not measured airborne ball coordinates or a projected ball trajectory."}
    (HERE / "flagg.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    visible = [{"t": frame["t"],
                "estimated": sum(track["points"][index]["status"] == "estimated" for track in tracks),
                "inferred": sum(track["points"][index]["status"] == "inferred" for track in tracks)}
               for index, frame in enumerate(frames)]
    valid = [point for track in tracks for point in track["points"] if point["x"] is not None]
    print(json.dumps({"output": "product/court-lab/flagg.json", "window": data["window"],
        "visibleKeyframes": visible, "coordinateBoundsFt": {
            "x": [min(point["x"] for point in valid), max(point["x"] for point in valid)],
            "y": [min(point["y"] for point in valid), max(point["y"] for point in valid)]},
        "sourceHashMatched": True}, ensure_ascii=False))


if __name__ == "__main__":
    main()
