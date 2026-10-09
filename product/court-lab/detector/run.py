"""Isolated local YOLO11n/person detection probe; no product integration.

Official Ultralytics model / AGPL-3.0-or-Enterprise, source and SHA in the committed experiment record.
This uses general person boxes, not pose keypoints, player IDs, or trajectories.
No downloads are allowed during inference; only three source-video frames.
"""
import argparse
from pathlib import Path
import ast
import hashlib
import importlib.metadata
import json
import os
import platform
import socket
import time



def main(argv=None):
    parser = argparse.ArgumentParser(description="Local-only, three-frame YOLO11n diagnostic; no automatic downloads or product integration.")
    parser.add_argument("--run-local-probe", action="store_true", help="Explicitly run the three known source frames with the already verified local model")
    args = parser.parse_args(argv)
    if not args.run_local_probe:
        parser.error("use --run-local-probe for this independent local experiment")
    ROOT = Path(__file__).resolve().parents[3]
    BUILD = ROOT / "product/build/court-lab"
    BUILD.mkdir(parents=True, exist_ok=True)
    MODEL = BUILD / "detector-yolo11n.pt"
    EXPECTED_MODEL_SHA = "0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1"
    if not MODEL.is_file():
        raise RuntimeError("Official model is absent. Follow detector/README.md; no automatic download is allowed.")
    if hashlib.sha256(MODEL.read_bytes()).hexdigest() != EXPECTED_MODEL_SHA:
        raise RuntimeError("Model SHA-256 mismatch; refusing to load a different pickle/checkpoint")
    os.environ["YOLO_CONFIG_DIR"] = str(BUILD / "detector-config")
    os.environ["YOLO_AUTOINSTALL"] = "false"
    os.environ["YOLO_VERBOSE"] = "false"
    os.environ["OMP_NUM_THREADS"] = "4"
    os.environ["MPLCONFIGDIR"] = str(BUILD / "detector-matplotlib")
    for name, expected in {"ultralytics": "8.4.174", "torch": "2.9.1", "torchvision": "0.24.1"}.items():
        if importlib.metadata.version(name) != expected:
            raise RuntimeError(f"{name} must be {expected}; use the isolated locked environment")

    # All network downloads happened explicitly before invoking this probe.
    def deny_connection(*args, **kwargs):
        raise RuntimeError("Network disabled for the local detector probe")
    socket.socket.connect = deny_connection
    socket.create_connection = deny_connection

    import cv2
    import numpy as np
    import torch
    import ultralytics
    from ultralytics import YOLO, settings

    settings.update({"sync": False})
    torch.set_num_threads(4)
    SOURCE = ROOT / "data/reference/train_video/train_video/训练_弗拉格2月1日.mp4"
    EXPECTED = "9c3e4606d04e7f79e29a112952fcf069ebab202af207af500bfbc3338bc079ce"
    source_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    if source_hash != EXPECTED:
        raise RuntimeError("Source integrity mismatch")

    # Read the separate experiment's original 9s AI annotations without importing
    # or mutating its code. Association here is a diagnostic against those seeds,
    # not a trained identity recognizer or independently reviewed ground truth.
    tree = ast.parse((ROOT / "product/court-lab/generate.py").read_text())
    seeds = next(ast.literal_eval(n.value) for n in tree.body
                 if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "PEOPLE" for t in n.targets))

    model = YOLO(str(MODEL))
    capture = cv2.VideoCapture(str(SOURCE))
    fps = capture.get(cv2.CAP_PROP_FPS)
    if not capture.isOpened() or fps <= 0:
        capture.release()
        raise RuntimeError("Cannot open the expected source video")
    report = {
        "experiment": "three-real-frames-person-detection-only",
        "source": str(SOURCE.relative_to(ROOT)), "sourceSha256": source_hash,
        "sourceFps": fps, "sourceDimensions": [capture.get(cv2.CAP_PROP_FRAME_WIDTH), capture.get(cv2.CAP_PROP_FRAME_HEIGHT)],
        "model": "YOLO11n COCO person", "modelSha256": EXPECTED_MODEL_SHA,
        "modelMetadata": "product/evidence/court-detector-20261009.json",
        "library": {"ultralytics": ultralytics.__version__, "torch": torch.__version__,
                    "torchvision": importlib.metadata.version("torchvision"), "opencv": cv2.__version__, "numpy": np.__version__},
        "platform": platform.platform(), "python": platform.python_version(),
        "device": "cpu", "mpsAvailable": torch.backends.mps.is_available(),
        "parameters": {"imgsz": 1280, "conf": 0.25, "iou": 0.7, "classes": [0], "max_det": 300, "threads": 4},
        "provenanceLimits": ["COCO person class includes spectators, staff, referees and players", "Box bottom center is only a geometric proxy, not measured feet or pose", "9s seed comparison uses existing AI manual annotations, not expert ground truth", "No re-identification, tracking, ball detector, automatic court calibration or new training", "No inference network connections; original video remains local"],
        "frames": [],
    }
    for requested in [9.0, 9.5, 10.0]:
        frame_index = round(requested * fps)
        capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ok, raw = capture.read()
        if not ok:
            raise RuntimeError(f"Could not decode {requested}s")
        frame = cv2.resize(raw, (1280, 720))
        cv2.imwrite(str(BUILD / f"detector-source-{requested:.1f}s.jpg"), frame)
        started = time.monotonic()
        result = model.predict(frame, imgsz=1280, conf=0.25, iou=0.7,
                               classes=[0], max_det=300, device="cpu", verbose=False,
                               save=False, save_txt=False)[0]
        elapsed = time.monotonic() - started
        boxes = []
        for index, (xyxy, confidence) in enumerate(zip(result.boxes.xyxy.cpu().numpy(), result.boxes.conf.cpu().numpy())):
            x1,y1,x2,y2 = map(float, xyxy)
            boxes.append({"index": index, "class": "person", "confidence": float(confidence),
                          "xyxy": [x1,y1,x2,y2], "boxBottomCenterProxy": [(x1+x2)/2,y2]})
        associations = []
        if requested == 9.0:
            for seed in seeds:
                x1,y1,x2,y2 = seed["roi"]
                cx,cy = (x1+x2)/2,(y1+y2)/2
                candidates = [box for box in boxes if box["xyxy"][0] <= cx <= box["xyxy"][2] and box["xyxy"][1] <= cy <= box["xyxy"][3]]
                candidates.sort(key=lambda box: -box["confidence"])
                hit = candidates[0] if candidates else None
                associations.append({"seed": seed["id"], "seedFoot": seed["foot"],
                                     "matchedBox": hit["index"] if hit else None,
                                     "confidence": hit["confidence"] if hit else None,
                                     "proxyFootErrorPixels": float(np.linalg.norm(np.asarray(hit["boxBottomCenterProxy"])-seed["foot"])) if hit and seed["foot"] else None,
                                     "comparisonIsManualSeedDiagnostic": True})
        # Label every detection so visual review can remove spectators/referees.
        overlay = frame.copy()
        for box in boxes:
            x1,y1,x2,y2 = [round(v) for v in box["xyxy"]]
            color = (85,205,245)
            cv2.rectangle(overlay,(x1,y1),(x2,y2),color,1)
            cv2.circle(overlay,tuple(round(v) for v in box["boxBottomCenterProxy"]),3,color,-1)
            cv2.putText(overlay,f'{box["index"]}: {box["confidence"]:.2f}',(x1,max(13,y1-3)),cv2.FONT_HERSHEY_SIMPLEX,.35,color,1,cv2.LINE_AA)
        cv2.rectangle(overlay,(0,0),(1280,24),(10,10,10),-1)
        cv2.putText(overlay,f'LOCAL YOLO11n PERSON BOXES / {requested:.1f}s / NOT PLAYER TRACKING / CPU',(10,17),cv2.FONT_HERSHEY_SIMPLEX,.43,(255,255,255),1,cv2.LINE_AA)
        output = BUILD / f"detector-boxes-{requested:.1f}s.jpg"
        cv2.imwrite(str(output),overlay)
        record = {"requestedSeconds": requested, "frameIndex": frame_index,
                  "frameIndexSeconds": frame_index/fps, "decodePositionMsec": capture.get(cv2.CAP_PROP_POS_MSEC),
                  "elapsedSeconds": elapsed, "speed": result.speed, "personBoxes": boxes,
                  "personBoxCount": len(boxes), "original9sSeedAssociations": associations,
                  "diagnosticImage": str(output.relative_to(ROOT))}
        report["frames"].append(record)
        print(json.dumps({"seconds":requested,"personBoxes":len(boxes),"elapsed":elapsed,"associations":associations}),flush=True)
    capture.release()
    (BUILD / "detector-results.json").write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n")
    print("saved detector-results.json",flush=True)


if __name__ == "__main__":
    main()
