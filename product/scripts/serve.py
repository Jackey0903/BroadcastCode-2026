#!/usr/bin/env python3
"""Loopback-only offline product preview. Never contacts AWS or starts a new job."""
import argparse
import copy
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import math
from fractions import Fraction
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit
from watch_assets import WATCH_PUBLIC_FILES, watch_history_record

ROOT = Path(__file__).resolve().parents[2]
SOURCES = {
    "flagg": "data/reference/train_video/train_video/训练_弗拉格2月1日.mp4",
    "amen": "data/reference/train_video/train_video/训练_阿门1月4日 .mp4",
}


def checked_file(root, relative):
    """Only regular files inside the repository; don't follow any symlink."""
    parts = Path(relative).parts
    if Path(relative).is_absolute() or ".." in parts:
        return None
    target = root
    for part in parts:
        target = target / part
        if target.is_symlink():
            return None
    return target if target.is_file() and target.resolve().is_relative_to(root) else None


def digest(path):
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(block)
    return sha.hexdigest()


def normalize_formal_timeline(manifest, source_duration, output_duration):
    """Validate complete output coverage, retaining freezes/replays explicitly."""
    raw = manifest.get("timeline")
    if raw is None and "segments" in manifest:
        fps = 60000 / 1001
        raw = [{"outputStart": segment["start"] / fps,
                "outputEnd": (segment["start"] + segment["count"]) / fps,
                "sourceStart": min(source_duration, segment["sourceStart"] / fps),
                "sourceEnd": min(source_duration, (segment["sourceStart"] + segment["count"] * segment["sourceRate"]) / fps),
                "kind": "play" if segment["name"] == "live" else "replay" if segment["name"].startswith("replay") else "rewind" if segment["name"] == "rewind" else "freeze"}
               for segment in manifest["segments"]]
    if raw is None:
        editorial = manifest["editorial"]
        fps = float(Fraction(manifest["output"]["fps"]))
        source_fps = float(Fraction(editorial.get("sourceIndexFps", manifest["output"]["fps"])))
        raw = []
        for segment in editorial["timeline"]:
            start = segment["outputStartFrame"] / fps
            end = (segment["outputStartFrame"] + segment["count"]) / fps
            source_start = segment["sourceStart"] / source_fps
            source_end = (segment["sourceStart"] + segment["count"] * segment["sourceStep"]) / source_fps
            raw.append({"outputStart": start, "outputEnd": end,
                        "sourceStart": min(source_duration, max(0, source_start)),
                        "sourceEnd": min(source_duration, max(0, source_end)),
                        "kind": segment.get("kind", "play"), "name": segment["name"]})
    if not isinstance(raw, list) or not raw:
        raise ValueError("Missing edit timeline")
    timeline, previous = [], 0
    for item in raw:
        values = [item[key] for key in ("outputStart", "outputEnd", "sourceStart", "sourceEnd")]
        if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in values):
            raise ValueError("Invalid timeline number")
        start, end, source_start, source_end = values
        if abs(start - previous) > .05 or end <= start or not 0 <= source_start <= source_duration or not 0 <= source_end <= source_duration:
            raise ValueError("Timeline is discontinuous or outside source")
        timeline.append({key: item[key] for key in ("outputStart", "outputEnd", "sourceStart", "sourceEnd", "kind")})
        previous = end
    if abs(previous - output_duration) > .1:
        raise ValueError("Timeline does not cover render")
    return timeline


class Catalog:
    def __init__(self, root=ROOT):
        self.root = Path(root).resolve()
        self.files, self.jobs, self.issues = {}, {}, []
        self.watch_history = {"records": []}
        formal = checked_file(self.root, "product/data/formal-story.json")
        self.manifest = json.loads((formal or self.root / "product/data/stories.json").read_text())
        self.manifest["preview"] = {"mode": "offline", "historical": not bool(formal)}
        for name in ("index.html", "app.js", "styles.css", "broadcast.css", "atmosphere.js", "arcade.css", "arcade.js", "camp.html", "camp.css", "camp.js",
                     "assets/grain.svg", "assets/fonts/OFL.txt",
                     "assets/fonts/fusion-pixel-12px-monospaced-zh_hans.otf.woff2"):
            file = checked_file(self.root, f"product/web/{name}")
            if file:
                self.files[f"/product/{name}"] = file
        # Only the frontend's explicit runtime assets; never serve its dev docs,
        # test suites, Python preview or source-control/configuration files.
        for name in WATCH_PUBLIC_FILES:
            file = checked_file(self.root, f"product/watch/{name}")
            if file:
                self.files[f"/product/watch/{name}"] = file
        # RL-SCOUT training camp data, built from the real SageMaker run (product/rl/build_camp.py).
        camp = checked_file(self.root, "product/data/rl/training-camp.json")
        if camp:
            self.files["/product/data/rl/training-camp.json"] = camp
        # A local-only research workbench, separate from the contest product.
        # Explicit allowlist: never expose its generator, arbitrary imports or builds.
        for name in ("index.html", "lab.css", "lab.js", "viewer.js", "flagg.json"):
            file = checked_file(self.root, f"product/court-lab/{name}")
            if file:
                self.files[f"/product/court-lab/{name}"] = file
        for file in (self.root / "data/reference/frames").glob("*.jpg"):
            if re.fullmatch(r"(?:flagg|amen)-[0-9.]+s\.jpg", file.name):
                safe = checked_file(self.root, str(file.relative_to(self.root)))
                if safe:
                    self.files[f"/frames/{file.name}"] = safe
        for story in self.manifest["stories"]:
            if story["sample"] == "formal":
                self.prepare_formal(story)
                continue
            sample = story["sample"]
            source = checked_file(self.root, SOURCES[sample])
            if source and digest(source) == story["sourceVideoSha256"]:
                self.files[f"/samples/{sample}.mp4"] = source
            else:
                story["sourceVideo"] = None
                self.issues.append(f"{sample}: 原片缺失或哈希不符，请恢复本地媒体存档。")
            job_id = story["showcaseJobId"]
            if not re.fullmatch(r"[a-f0-9]{32}", job_id):
                raise ValueError("Invalid showcase job ID")
            report_file = checked_file(self.root, f"product/evidence/run-{job_id}.json")
            report = json.loads(report_file.read_text()) if report_file else {}
            media = checked_file(self.root, f"product/build/verified/{job_id}/enhanced.mp4")
            accepted = (report.get("contentReview", {}).get("acceptedForShowcase") is True
                        and report.get("jobId") == job_id and report.get("sample") == sample
                        and report.get("mode") == "story"
                        and report.get("analysis", {}).get("protocol_version") == "product-story-v1")
            matched = (media and report.get("outputSha256") == story["showcaseOutputSha256"]
                       and digest(media) == report["outputSha256"])
            if not accepted or not matched:
                story["enhancedVideo"] = story["analysisUrl"] = None
                self.issues.append(f"{sample}: 已验收成片缺失或核验失败，请恢复本地媒体存档。")
                continue
            self.watch_history["records"].append(watch_history_record(report))
            for field in ('scout', 'playerComparison', 'rlEvidenceSources', 'rlEvidencePeriods',
                          'rlVideoUse', 'rlAudit'):
                story.pop(field, None)
                if field in report['analysis']:
                    story[field] = copy.deepcopy(report['analysis'][field])
            local_base = f"/product/outputs/{job_id}"
            self.files[f"{local_base}/enhanced.mp4"] = media
            # Keep original analysis/provenance intact; only presentation URLs change.
            self.jobs[job_id] = {
                "jobId": job_id, "sample": sample, "mode": "story",
                "status": "completed", "stage": "completed",
                "videoUrl": f"{local_base}/enhanced.mp4",
                "analysisUrl": f"{local_base}/analysis.json",
                "outputSha256": report["outputSha256"],
                "elapsedSeconds": report["elapsedSeconds"],
                "preservesSourceTimeline": report["analysis"].get("preservesSourceTimeline", False),
                "analysis": report["analysis"],
                "preview": {"mode": "offline", "historical": True,
                            "verifiedAt": report["verifiedAt"],
                            "originalVideoUrl": report["videoUrl"],
                            "originalAnalysisUrl": report["analysisUrl"],
                            "notice": "已核验真实运行的留存结果；本地回看，没有发起新推理。"},
            }
            story["enhancedVideo"] = f"{local_base}/enhanced.mp4"
            story["analysisUrl"] = f"{local_base}/analysis.json"

    def prepare_formal(self, story):
        """Expose one hash-bound formal source and its separate editorial render.

        This path never creates a job, imports old AI acceptance, or uses paths
        supplied by the render manifest as a filesystem allowlist.
        """
        story["enhancedVideo"] = story["analysisUrl"] = None
        story["preview"] = {"mode": "offline", "historical": False}
        source = checked_file(self.root, "data/正式视频.mp4")
        if not source or digest(source) != story["sourceVideoSha256"]:
            story["sourceVideo"] = None
            self.issues.append("formal: 正式原片缺失或哈希不符。")
            return
        self.files["/product/media/formal/source.mp4"] = source
        output = checked_file(self.root, "product/build/formal-assets/GameBuddy-正式资产联调-v1.mp4")
        receipt = checked_file(self.root, "product/build/formal-assets/GameBuddy-正式资产联调-v1.manifest.json")
        if not output or not receipt:
            return
        try:
            manifest = json.loads(receipt.read_text())
            probe = manifest["probe"]
            stream = next(item for item in probe["streams"] if item["codec_type"] == "video")
            rendered = {"sha256": manifest["outputSha256"], "durationSeconds": manifest["durationSeconds"],
                        "width": stream["width"], "height": stream["height"]}
            if (manifest["sourceSha256"] != story["sourceVideoSha256"]
                    or digest(output) != rendered["sha256"]
                    or manifest.get("agentCoreInvoked") is not False
                    or manifest.get("rlInvoked") is not False
                    or manifest.get("editorial") is not True):
                raise ValueError("Render identity or mode does not match")
            duration = rendered.get("durationSeconds", rendered.get("duration"))
            if not isinstance(duration, (float, int)) or not 0 < duration < 60:
                raise ValueError("Editorial movie must be under one minute")
            timeline = normalize_formal_timeline(manifest, story["durationSeconds"], duration)
            if manifest.get("fullDecodePassed") is not True:
                raise ValueError("Render completion receipt not available")
            story["production"] = {
                "mode": "editorial", "status": "local-render-ready",
                "sourceSha256": story["sourceVideoSha256"],
                "outputSha256": rendered["sha256"], "durationSeconds": duration,
                "width": rendered.get("width"), "height": rendered.get("height"),
                "createdAt": manifest.get("createdAt"), "timeline": timeline,
                "agentCoreUsedForThisRender": False, "rlModelUsedForThisRender": False,
                "aiNarrationUsed": False, "preservesSourceTimeline": False,
                "manifestUrl": "/product/media/formal/manifest.json",
                "fullVideoAudioDecode": True,
            }
            story["enhancedVideo"] = "/product/media/formal/enhanced.mp4"
            self.files[story["enhancedVideo"]] = output
            # A sanitized production record is served below; local absolute paths
            # and arbitrary renderer fields are not published to the browser.
        except (KeyError, ValueError, TypeError, ZeroDivisionError, StopIteration):
            self.issues.append("formal: 编辑成片尚未满足来源、时间映射或完整导出契约。")

    def status(self):
        return {"status": "offline", "ready": False, "modes": [],
                "samples": [{"id": story["sample"], "available": False} for story in self.manifest["stories"]],
                "preview": {"mode": "offline", "historical": True, "issues": self.issues,
                            "notice": "本地预览：可回看素材与历史成片，暂不运行新的 Agent 任务。",
                            "jobs": [{"jobId": job["jobId"], "sample": job["sample"],
                                      "verifiedAt": job["preview"]["verifiedAt"]}
                                     for job in self.jobs.values()]}}


def byte_range(value, size):
    """Parse a single HTTP byte range, including suffix/open-ended ranges."""
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", value)
    if not match or not any(match.groups()) or not size:
        raise ValueError("Invalid range")
    first, last = match.groups()
    if not first:
        count = int(last)
        if not count:
            raise ValueError("Empty suffix")
        return max(0, size - count), size - 1
    start, end = int(first), min(int(last), size - 1) if last else size - 1
    if start >= size or end < start:
        raise ValueError("Unsatisfiable range")
    return start, end


def handler_for(catalog):
    class Preview(BaseHTTPRequestHandler):
        def do_GET(self):
            self.read()

        def do_HEAD(self):
            self.read()

        def do_POST(self):
            path = urlsplit(self.path).path
            self.close_connection = True
            if path == "/api/jobs":
                self.json_response({"error": "offline_preview", "message":
                    "当前为本地历史回看，不能创建新的 Agent 任务。"}, 503)
            else:
                self.send_error(404)

        def json_response(self, data, status=200):
            payload = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(payload)

        def read(self):
            path = unquote(urlsplit(self.path).path)
            if ".." in Path(path).parts or "\0" in path or "\\" in path:
                self.send_error(404)
                return
            if path in ("/", "/product", "/product/court-lab", "/product/watch"):
                query = urlsplit(self.path).query
                destination = "/product/watch/" if path == "/product/watch" else "/product/court-lab/" if path == "/product/court-lab" else "/product/"
                self.send_response(301)
                self.send_header("Location", destination + ("?" + query if query else ""))
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if path == "/product/":
                path = "/product/index.html"
            if path == "/product/court-lab/":
                path = "/product/court-lab/index.html"
            if path == "/product/watch/":
                path = "/product/watch/index.html"
            if path == "/api/status":
                self.json_response(catalog.status())
                return
            if path in ("/product/data/stories.json", "/product/watch/data/stories.json"):
                self.json_response(catalog.manifest)
                return
            if path == "/product/media/formal/manifest.json":
                story = next((item for item in catalog.manifest["stories"] if item["sample"] == "formal"), None)
                if not story or not story.get("enhancedVideo"):
                    self.send_error(404)
                else:
                    self.json_response(story["production"])
                return
            if path == "/product/watch/data/history.json":
                self.json_response(catalog.watch_history)
                return
            if path.startswith("/api/jobs/"):
                job = catalog.jobs.get(path.removeprefix("/api/jobs/"))
                if job:
                    self.json_response(job)
                else:
                    self.json_response({"message": "本地没有这份已验收的历史记录。"}, 404)
                return
            match = re.fullmatch(r"/product/outputs/([a-f0-9]{32})/analysis\.json", path)
            if match and match[1] in catalog.jobs:
                self.json_response(catalog.jobs[match[1]]["analysis"])
                return
            file = catalog.files.get(path)
            # Recheck symlinks when opening, rather than trusting only startup state.
            if not file or checked_file(catalog.root, str(file.relative_to(catalog.root))) != file:
                self.send_error(404)
                return
            self.send_file(file)

        def send_file(self, file):
            size = file.stat().st_size
            start, end, status = 0, size - 1, 200
            # Range applies to GET; HEAD returns full representation headers.
            if self.command == "GET" and self.headers.get("Range"):
                try:
                    start, end = byte_range(self.headers["Range"], size)
                    status = 206
                except ValueError:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
            with file.open("rb") as stream:
                self.send_response(status)
                self.send_header("Content-Type", mimetypes.guess_type(file.name)[0] or "application/octet-stream")
                self.send_header("Content-Length", str(max(0, end - start + 1)))
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                if status == 206:
                    self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                self.end_headers()
                if self.command == "HEAD":
                    return
                stream.seek(start)
                remaining = end - start + 1
                try:
                    while remaining > 0:
                        block = stream.read(min(256 * 1024, remaining))
                        if not block:
                            break
                        self.wfile.write(block)
                        remaining -= len(block)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # Seeking or switching videos closes the prior request.

    return Preview


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=4173)
    args = parser.parse_args()
    catalog = Catalog()
    print(f"Offline preview: http://127.0.0.1:{args.port}/product/", flush=True)
    for issue in catalog.issues:
        print(issue, flush=True)
    ThreadingHTTPServer(("127.0.0.1", args.port), handler_for(catalog)).serve_forever()


if __name__ == "__main__":
    main()
