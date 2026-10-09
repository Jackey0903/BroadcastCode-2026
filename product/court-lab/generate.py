#!/usr/bin/env python3
"""Small, deliberately conservative, offline camera/cloth optical-flow experiment.

Uses existing OpenCV/Numpy only. This is not a detector, player identity system,
or official tracking data. Initial points/ROIs are AI-authored image annotations.
No downloads, cloud calls, or weight files. Run from any directory:
  python3 product/court-lab/generate.py --end 10

Outputs a JSON specimen, diagnostics, and ignored local diagnostic images/video.
The JSON preserves failures instead of filling ten plausible-looking trajectories.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "data/reference/train_video/train_video/训练_弗拉格2月1日.mp4"
EXPECTED_SHA = "9c3e4606d04e7f79e29a112952fcf069ebab202af207af500bfbc3338bc079ce"
BUILD = ROOT / "product/build/court-lab"
IMAGE_SIZE = (1280, 720)
SEED_T = 9.0
# AI checked the existing 1280x720 9s JPEG and magnified crops. These are the
# visible ground-plane paint-boundary corners, not rim/backboard points.
SEED_CORNERS = np.float32([[352, 332], [772, 350], [682, 465], [217, 438]])
COURT_CORNERS = np.float32([[0, 33], [19, 33], [19, 17], [0, 17]])
# Foot locations are approximate AI annotations, not expert-reviewed labels.
# D1's shoes are occluded by foreground spectators: do not invent a foot point.
PEOPLE = [
    {"id": "W1", "team": "white", "foot": [282, 501], "roi": [262, 358, 299, 421]},
    {"id": "W2", "team": "white", "foot": [491, 533], "roi": [478, 404, 516, 458]},
    {"id": "W3", "team": "white", "foot": [559, 319], "roi": [543, 224, 579, 273]},
    {"id": "W4", "team": "white", "foot": [790, 434], "roi": [775, 326, 810, 376]},
    {"id": "W5", "team": "white", "foot": [1004, 399], "roi": [990, 301, 1027, 351]},
    {"id": "D1", "team": "dark", "foot": None, "roi": [97, 424, 135, 492],
     "reason": "seed_feet_occluded_by_foreground_spectators"},
    {"id": "D2", "team": "dark", "foot": [447, 603], "roi": [414, 454, 461, 513]},
    {"id": "D3", "team": "dark", "foot": [624, 255], "roi": [609, 178, 632, 221]},
    {"id": "D4", "team": "dark", "foot": [862, 414], "roi": [862, 322, 893, 373]},
    {"id": "D5", "team": "dark", "foot": [1176, 421], "roi": [1142, 312, 1179, 352]},
]
LIMITS = {
    "flowSampleFps": 30, "outputSampleFps": 10,
    "forwardBackwardMaxPixels": 1.2, "minBodyFeatures": 6,
    "bodyMedianAbsoluteDeviationMaxPixels": 2.0,
    "bodyMotionMaxPixelsPerFrame": 14.0,
    "bodyPatchDifferenceMaxGray": 28.0,
    "courtSpeedMaxFtPerSecond": 45.0,
    "minGroundInliers": 25, "groundRansacMaxPixels": 1.7,
    "groundMedianReprojectionMaxPixels": 1.2,
}
# Conservative semantic veto after actual seed/mid/last overlay inspection by
# two AI agents. Numeric flow checks did not catch these foot/occlusion errors.
# These cutoffs apply only to this SHA-verified one-second specimen.
VISUAL_VETO = {
    "W2": (9.3, "visual_review_torso_offset_wrong_under_overlap"),
    "W4": (9.3, "visual_review_stance_change_invalidates_fixed_foot_offset"),
    "D2": (9.3, "visual_review_ground_contact_occluded_by_foreground_spectators"),
}


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def project(points, matrix):
    return cv2.perspectiveTransform(np.float32(points).reshape(-1, 1, 2), matrix).reshape(-1, 2)


def fb_flow(previous, current, points):
    if points is None or len(points) == 0:
        return np.empty((0, 2), np.float32), np.zeros(0, bool), np.zeros(0)
    source = np.float32(points).reshape(-1, 1, 2)
    target, good, _ = cv2.calcOpticalFlowPyrLK(
        previous, current, source, None, winSize=(21, 21), maxLevel=3,
        criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 25, 0.01))
    if target is None:
        return np.zeros((len(source), 2), np.float32), np.zeros(len(source), bool), np.full(len(source), np.inf)
    backward, valid, _ = cv2.calcOpticalFlowPyrLK(
        current, previous, target, None, winSize=(21, 21), maxLevel=3,
        criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 25, 0.01))
    if backward is None:
        return target.reshape(-1, 2), np.zeros(len(source), bool), np.full(len(source), np.inf)
    error = np.linalg.norm(backward.reshape(-1, 2) - source.reshape(-1, 2), axis=1)
    xy = target.reshape(-1, 2)
    mask = ((good[:, 0] == 1) & (valid[:, 0] == 1)
            & (error <= LIMITS["forwardBackwardMaxPixels"])
            & (xy[:, 0] >= 5) & (xy[:, 0] < 1275)
            & (xy[:, 1] >= 5) & (xy[:, 1] < 715))
    return xy, mask, error


def patch_difference(previous, current, before, after):
    diffs = []
    for a, b in zip(before, after):
        p = cv2.getRectSubPix(previous, (7, 7), tuple(map(float, a)))
        q = cv2.getRectSubPix(current, (7, 7), tuple(map(float, b)))
        diffs.append(float(np.mean(np.abs(p.astype(float) - q.astype(float)))))
    return float(np.median(diffs)) if diffs else None


def finite_json(value):
    # Diagnostics can contain missing/infinite residuals; keep strict JSON.
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not np.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: finite_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [finite_json(item) for item in value]
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--end", type=float, default=10.0, help="Short-window end, 9 < end <= 12")
    args = parser.parse_args()
    if not SEED_T < args.end <= 12:
        raise SystemExit("End must be between 9 and 12 seconds")
    actual_sha = sha256(SOURCE)
    if actual_sha != EXPECTED_SHA:
        raise SystemExit("Source SHA-256 differs; annotations are invalid for this file")
    BUILD.mkdir(parents=True, exist_ok=True)
    capture = cv2.VideoCapture(str(SOURCE))
    capture.set(cv2.CAP_PROP_POS_MSEC, SEED_T * 1000)
    ok, seed = capture.read()
    if not ok:
        raise SystemExit("Could not decode seed frame")
    seed_actual_t = float(capture.get(cv2.CAP_PROP_POS_MSEC)) / 1000
    seed = cv2.resize(seed, IMAGE_SIZE, interpolation=cv2.INTER_AREA)
    previous = cv2.cvtColor(seed, cv2.COLOR_BGR2GRAY)
    initial_h = cv2.getPerspectiveTransform(SEED_CORNERS, COURT_CORNERS)
    # Deliberately masked ground features: floor polygon, away from scoreboard,
    # plus broad person exclusions. No court-line neural model is being used.
    ground_mask = np.zeros((720, 1280), np.uint8)
    cv2.fillConvexPoly(ground_mask, np.int32([[250, 275], [1200, 300], [1245, 545], [215, 545], [185, 440]]), 255)
    for person in PEOPLE:
        x1, y1, x2, y2 = person["roi"]
        foot = person.get("foot")
        bottom = int(foot[1] + 25) if foot else 610
        cv2.rectangle(ground_mask, (x1 - 35, y1 - 65), (x2 + 40, bottom), 0, -1)
    # Three referees are not players, but must also be excluded from floor flow.
    for rectangle in [(255, 215, 330, 375), (650, 450, 715, 625), (1140, 180, 1245, 335)]:
        x1, y1, x2, y2 = rectangle
        cv2.rectangle(ground_mask, (x1, y1), (x2, y2), 0, -1)
    ground_points = cv2.goodFeaturesToTrack(previous, 420, 0.01, 7, mask=ground_mask)
    if ground_points is None or len(ground_points) < LIMITS["minGroundInliers"]:
        raise SystemExit("Insufficient initial ground features")
    ground_points = ground_points.reshape(-1, 2)
    ground_reference = ground_points.copy()
    ground_seed_count = len(ground_points)
    hsv = cv2.cvtColor(seed, cv2.COLOR_BGR2HSV)
    tracks, running = [], []
    initial_rows = []
    for person in PEOPLE:
        x1, y1, x2, y2 = person["roi"]
        clothing_mask = np.zeros((720, 1280), np.uint8)
        clothing_mask[y1:y2, x1:x2] = 255
        # Keep clothing features inside manually chosen upper-body rectangles.
        if person["team"] == "dark":
            clothing_mask[(hsv[:, :, 2] > 175)] = 0
        else:
            clothing_mask[(hsv[:, :, 1] > 85) | (hsv[:, :, 2] < 100)] = 0
        body = cv2.goodFeaturesToTrack(previous, 70, 0.005, 2, mask=clothing_mask)
        body = body.reshape(-1, 2) if body is not None else np.empty((0, 2), np.float32)
        foot = np.float32(person["foot"]) if person.get("foot") else None
        xy = project([foot], initial_h)[0] if foot is not None else None
        state = {"person": person, "features": body, "foot": foot, "xy": xy,
                 "failure": person.get("reason"), "stoppedAt": None}
        if foot is not None and len(body) < LIMITS["minBodyFeatures"]:
            state["failure"] = "insufficient_initial_clothing_features"
        point = {"t": seed_actual_t, "x": round(float(xy[0]), 3) if xy is not None else None,
                 "y": round(float(xy[1]), 3) if xy is not None else None,
                 "status": "estimated" if xy is not None else "occluded",
                 "segment": "flagg-wide-1", "reviewed": False}
        if foot is not None:
            point["image"] = foot.tolist()
        if state["failure"]:
            point["reason"] = state["failure"]
            if person.get("foot") and len(body) < LIMITS["minBodyFeatures"]:
                point.update({"x": None, "y": None, "status": "occluded"})
                point.pop("image", None)
        tracks.append({"id": person["id"], "team": person["team"], "label": person["id"],
                       "identityStatus": "anonymous", "points": [point]})
        running.append(state)
        initial_rows.append({**person, "clothingFeatures": len(body), "projectedFt": xy.tolist() if xy is not None else None})

    cv2.imwrite(str(BUILD / "ground-mask.png"), ground_mask)
    writer = cv2.VideoWriter(str(BUILD / "diagnostic.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), 30, IMAGE_SIZE)
    frames = []
    last_flow_t = seed_actual_t
    next_flow_t = seed_actual_t + 1 / 30
    next_output_t = seed_actual_t + 0.1
    current_to_seed = np.eye(3)
    ground_failed = False
    overlay = seed.copy()
    cv2.polylines(overlay, [np.int32(SEED_CORNERS)], True, (0, 170, 255), 2)
    for point in ground_points:
        cv2.circle(overlay, tuple(np.int32(point)), 2, (150, 150, 80), -1)
    for state in running:
        person = state["person"]
        x1, y1, x2, y2 = person["roi"]
        color = (65, 155, 255) if person["team"] == "dark" else (255, 210, 85)
        cv2.rectangle(overlay, (x1, y1), (x2, y2), color, 1)
        if state["foot"] is not None:
            p = tuple(np.int32(state["foot"]))
            cv2.circle(overlay, p, 5, color, 2)
            cv2.putText(overlay, person["id"], (p[0] + 5, p[1] - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
    cv2.putText(overlay, "AI MANUAL SEED / NOT OFFICIAL TRACKING / D1 FEET OCCLUDED", (18, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
    cv2.imwrite(str(BUILD / "seed-overlay.jpg"), overlay)
    writer.write(overlay)
    last_time = seed_actual_t
    while True:
        ok, image = capture.read()
        if not ok:
            break
        actual_t = float(capture.get(cv2.CAP_PROP_POS_MSEC)) / 1000
        if actual_t + 1e-7 < next_flow_t:
            continue
        if actual_t > args.end + 0.025:
            break
        next_flow_t += 1 / 30
        t = round(actual_t, 6)
        last_time = t
        image = cv2.resize(image, IMAGE_SIZE, interpolation=cv2.INTER_AREA)
        current = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        duration = t - last_flow_t
        record = {"t": t, "ground": {}, "players": []}
        ground_next, ground_valid, ground_fb = fb_flow(previous, current, ground_points)
        if not ground_failed:
            matched = ground_next[ground_valid]
            reference = ground_reference[ground_valid]
            if len(matched) >= LIMITS["minGroundInliers"]:
                matrix, inliers = cv2.findHomography(matched, reference, cv2.RANSAC,
                                                   LIMITS["groundRansacMaxPixels"])
                selected = inliers[:, 0] == 1 if inliers is not None else np.zeros(len(matched), bool)
                residual = (float(np.median(np.linalg.norm(project(matched[selected], matrix) - reference[selected], axis=1)))
                            if matrix is not None and selected.sum() else None)
                accepted = bool(matrix is not None and selected.sum() >= LIMITS["minGroundInliers"]
                                and residual <= LIMITS["groundMedianReprojectionMaxPixels"])
                record["ground"] = {"validFeatures": len(matched), "inliers": int(selected.sum()),
                                     "medianReprojectionPixels": residual, "accepted": accepted}
                if accepted:
                    current_to_seed = matrix
                    ground_points, ground_reference = matched[selected], reference[selected]
                else:
                    ground_failed = True
            else:
                ground_failed = True
                record["ground"] = {"validFeatures": len(matched), "accepted": False,
                                     "reason": "insufficient_ground_features"}
        else:
            record["ground"] = {"accepted": False, "reason": "ground_calibration_already_lost"}

        for state in running:
            person = state["person"]
            detail = {"id": person["id"]}
            if state["failure"]:
                detail.update({"accepted": False, "reason": state["failure"]})
                record["players"].append(detail)
                continue
            previous_body = state["features"]
            body, valid, backward_error = fb_flow(previous, current, previous_body)
            source_body, good_body = previous_body[valid], body[valid]
            failure = "ground_calibration_lost" if ground_failed else None
            detail.update({"validFeatures": len(good_body),
                           "medianForwardBackwardPixels": float(np.median(backward_error[valid])) if valid.any() else None})
            if len(good_body) < LIMITS["minBodyFeatures"]:
                failure = failure or "too_few_clothing_features"
            if failure is None:
                displacements = good_body - source_body
                motion = np.median(displacements, axis=0)
                residuals = np.linalg.norm(displacements - motion, axis=1)
                inliers = residuals <= LIMITS["bodyMedianAbsoluteDeviationMaxPixels"]
                detail["motionInliers"] = int(inliers.sum())
                if inliers.sum() < LIMITS["minBodyFeatures"]:
                    failure = "inconsistent_clothing_motion"
                else:
                    motion = np.median(displacements[inliers], axis=0)
                    difference = patch_difference(previous, current, source_body[inliers], good_body[inliers])
                    candidate_foot = state["foot"] + motion
                    candidate_xy = project([candidate_foot], initial_h @ current_to_seed)[0]
                    speed = float(np.linalg.norm(candidate_xy - state["xy"]) / max(duration, 1e-6))
                    detail.update({"motionPixels": motion.tolist(), "patchDifferenceGray": difference,
                                   "estimatedSpeedFtPerSecond": speed, "candidateCourtFt": candidate_xy.tolist()})
                    if np.linalg.norm(motion) > LIMITS["bodyMotionMaxPixelsPerFrame"]:
                        failure = "implausible_image_motion"
                    elif difference > LIMITS["bodyPatchDifferenceMaxGray"]:
                        failure = "clothing_appearance_changed"
                    elif speed > LIMITS["courtSpeedMaxFtPerSecond"]:
                        failure = "implausible_projected_speed"
                    elif not (0 <= candidate_foot[0] < 1280 and 0 <= candidate_foot[1] < 625):
                        failure = "image_position_left_usable_view"
                    elif not (0 <= candidate_xy[0] <= 47 and 0 <= candidate_xy[1] <= 50):
                        failure = "projected_position_outside_half_court"
                    else:
                        state["features"] = good_body[inliers]
                        state["foot"] = candidate_foot
                        state["xy"] = candidate_xy
            if failure:
                state["failure"], state["stoppedAt"] = failure, t
            detail["accepted"] = failure is None
            if failure:
                detail["reason"] = failure
            record["players"].append(detail)
        frames.append(record)

        overlay = image.copy()
        if not ground_failed:
            corners = project(SEED_CORNERS, np.linalg.inv(current_to_seed))
            cv2.polylines(overlay, [np.int32(corners)], True, (0, 170, 255), 2)
        for state in running:
            if state["failure"] or state["foot"] is None:
                continue
            p = tuple(np.int32(state["foot"]))
            color = (65, 155, 255) if state["person"]["team"] == "dark" else (255, 210, 85)
            cv2.circle(overlay, p, 6, color, 2)
            cv2.putText(overlay, state["person"]["id"], (p[0] + 5, p[1] - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
        active = sum(not state["failure"] for state in running)
        cv2.putText(overlay, f"CLOTH-FLOW EXPERIMENT {t:.3f}s / {active}/10 estimates / NO VERIFIED TRACKS", (18, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
        writer.write(overlay)
        if t + 1e-6 >= next_output_t:
            for track, state in zip(tracks, running):
                point = {"t": t, "x": None, "y": None,
                         "status": "occluded", "segment": "flagg-wide-1", "reviewed": False}
                if not state["failure"]:
                    point.update({"x": round(float(state["xy"][0]), 3), "y": round(float(state["xy"][1]), 3),
                                  "image": [round(float(v), 3) for v in state["foot"]], "status": "estimated"})
                else:
                    point["reason"] = state["failure"]
                    if state["failure"] in ("image_position_left_usable_view", "projected_position_outside_half_court"):
                        point["status"] = "offscreen"
                track["points"].append(point)
            cv2.imwrite(str(BUILD / f"flow-{t:.3f}s.jpg"), overlay)
            next_output_t += 0.1
        previous, last_flow_t = current, t
    capture.release()
    writer.release()

    # Include the actual terminal PTS, even if it misses the regular 10fps grid.
    for track, state in zip(tracks, running):
        if track["points"][-1]["t"] < last_time:
            point = {"t": last_time, "x": None, "y": None, "status": "occluded",
                     "segment": "flagg-wide-1", "reviewed": False}
            if not state["failure"]:
                point.update({"x": round(float(state["xy"][0]), 3), "y": round(float(state["xy"][1]), 3),
                              "image": [round(float(v), 3) for v in state["foot"]], "status": "estimated"})
            else:
                point["reason"] = state["failure"]
                if state["failure"] in ("image_position_left_usable_view", "projected_position_outside_half_court"):
                    point["status"] = "offscreen"
            track["points"].append(point)
    # Preserve numerically accepted but semantically rejected candidates in the
    # diagnostic record. The visible specimen contains only the filtered points.
    raw_candidate_tracks = json.loads(json.dumps(finite_json(tracks)))
    for track in tracks:
        if track["id"] in VISUAL_VETO:
            start, reason = VISUAL_VETO[track["id"]]
            for point in track["points"]:
                if point["t"] >= start:
                    point.update({"x": None, "y": None, "status": "occluded", "reason": reason})
                    point.pop("image", None)

    warning = ("本地离线技术实验，AI 手工选择禁区角点、上半身区域和初始足点；"
               "后续点仅为衣物光流位移加固定足点偏移的估计。不是球员检测、身份识别、官方数据或已验证轨迹。"
               "遮挡、跳跃和身体姿态变化会使足点估计错误；残差筛选不能证明语义正确。失败后断轨，不插值补人。")
    data = {"schema": "court-lab-v1", "sample": "flagg", "sourceSha256": actual_sha,
            "sourceVideo": "/samples/flagg.mp4", "videoSize": list(IMAGE_SIZE),
            "court": {"length": 94, "width": 50, "unit": "ft", "origin": "left-baseline-near-sideline"},
            "window": [seed_actual_t, last_time], "provenance": {"method": "AI manual seed + experimental clothing LK + ground LK/RANSAC + semantic rejection",
                "warning": warning, "reviewed": False, "officialTracking": False,
                "initializationImage": "data/reference/frames/flagg-09s.jpg",
                "seedVideoTimeActual": seed_actual_t, "noInterpolation": True,
                "acceptedForShowcase": False, "validationStatus": "not_accepted_for_showcase",
                "manualSemanticVeto": {key: {"from": value[0], "reason": value[1]} for key, value in VISUAL_VETO.items()}}, "tracks": tracks}
    diagnostics = {"protocol": "court-lab-diagnostic-v1", "date": "2026-10-09",
                   "sourceSha256": actual_sha, "hashMatched": True, "opencvVersion": cv2.__version__,
                   "numpyVersion": np.__version__, "seedImageCorners": SEED_CORNERS.tolist(),
                   "seedCourtCornersFt": COURT_CORNERS.tolist(), "initialHomography": initial_h.tolist(),
                   "seedFitResidualCourtFt": np.linalg.norm(project(SEED_CORNERS, initial_h) - COURT_CORNERS, axis=1).tolist(),
                   "seedFitResidualMeaning": "Four fitted manual points; zero fitting residual is not independent calibration validation.",
                   "initialization": initial_rows, "thresholds": LIMITS,
                   "requestedWindow": [9, args.end], "actualDecodedWindow": [seed_actual_t, last_time],
                   "flowFrames": len(frames), "initialGroundFeatureCount": ground_seed_count,
                   "groundCalibrationLost": ground_failed,
                   "rawNumericStopReasons": [{"id": state["person"]["id"], "reason": state["failure"], "stoppedAt": state["stoppedAt"]} for state in running],
                   "stopReasons": [{"id": state["person"]["id"],
                                    "reason": VISUAL_VETO[state["person"]["id"]][1] if state["person"]["id"] in VISUAL_VETO else state["failure"],
                                    "stoppedAt": VISUAL_VETO[state["person"]["id"]][0] if state["person"]["id"] in VISUAL_VETO else state["stoppedAt"]}
                                   for state in running],
                   "acceptedAtEnd": sum(track["points"][-1]["status"] == "estimated" for track in tracks),
                   "numericallyAcceptedAtEnd": sum(not state["failure"] for state in running),
                   "viewerEstimatedAtEnd": sum(track["points"][-1]["status"] == "estimated" for track in tracks),
                   "acceptedForShowcase": False, "validationStatus": "not_accepted_for_showcase",
                   "manualSemanticVeto": data["provenance"]["manualSemanticVeto"],
                   "rawCandidateTracks": raw_candidate_tracks,
                   "visualDiagnosticReview": {"reviewer": "AI assistant", "expertReviewed": False,
                       "seedFeetOccluded": ["D1"],
                       "notes": ["Seed corner points were revised after actual magnified image inspection.",
                                 "W2 overlaps D2; W4 changes stance. Fixed torso-to-foot offsets produce visibly wrong foot points by the last frame. Both are conservatively vetoed from 9.3s.",
                                 "D2 foot-to-ground contact is obscured by foreground spectators by 9.326s; vetoed from 9.3s.",
                                 "Residual acceptance measures numerical consistency only. No identity or trajectory accuracy was measured.",
                                 "Ground features are limited to the floor and exclude manually marked players/referees; no court-line recognition was run."]},
                   "warning": warning, "frames": frames,
                   "diagnosticMedia": "product/build/court-lab/diagnostic.mp4",
                   "diagnosticMediaMeaning": "Raw numerically accepted candidates, including subsequent semantic rejections. Not the filtered viewer dataset.",
                   "filteredFinalImage": "product/build/court-lab/filtered-last-overlay.jpg"}
    # Never overwrite the later editor-authored schematic presentation dataset.
    (ROOT / "product/court-lab/flow-flagg.json").write_text(json.dumps(finite_json(data), ensure_ascii=False, indent=2) + "\n")
    (ROOT / "product/evidence/court-lab-diagnostic-20261009.json").write_text(json.dumps(finite_json(diagnostics), ensure_ascii=False, indent=2) + "\n")
    cv2.imwrite(str(BUILD / "last-overlay.jpg"), overlay)
    filtered = image.copy()
    if not ground_failed:
        cv2.polylines(filtered, [np.int32(project(SEED_CORNERS, np.linalg.inv(current_to_seed)))], True, (0, 170, 255), 2)
    for track in tracks:
        point = track["points"][-1]
        if point["status"] != "estimated":
            continue
        p = tuple(np.int32(point["image"]))
        color = (65, 155, 255) if track["team"] == "dark" else (255, 210, 85)
        cv2.circle(filtered, p, 6, color, 2)
        cv2.putText(filtered, track["id"], (p[0] + 5, p[1] - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
    cv2.putText(filtered, f"FILTERED {last_time:.3f}s / {diagnostics['viewerEstimatedAtEnd']}/10 unreviewed estimates / NOT ACCEPTED", (18, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
    cv2.imwrite(str(BUILD / "filtered-last-overlay.jpg"), filtered)
    print(json.dumps({"window": data["window"], "flowFrames": len(frames),
                      "acceptedAtEnd": diagnostics["acceptedAtEnd"], "stopReasons": diagnostics["stopReasons"],
                      "data": "product/court-lab/flow-flagg.json", "diagnosticMedia": str(BUILD / "diagnostic.mp4")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
