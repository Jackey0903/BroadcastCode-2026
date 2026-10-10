#!/usr/bin/env python3
"""Render the preserved GameBuddy cut with two frame-exact tactical inserts."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import multiprocessing
from pathlib import Path
import shutil
import subprocess
import tempfile

from broadcast_fx.timeline import DURATION, FPS, FRAME_COUNT, TIMELINE, locate_frame

_renderer = None
_tactics = None


def configure(workdir: str) -> None:
    global _renderer, _tactics
    import cv2
    from broadcast_fx import legacy, tactics
    cv2.setNumThreads(1)
    legacy.configure(workdir)
    tactics.configure(workdir)
    _renderer, _tactics = legacy, tactics


def render_frame(frame: int):
    segment, offset = locate_frame(frame)
    if segment.legacy_start is None:
        return _tactics.render_scene(segment.name, offset, segment.count)
    return _renderer.render(segment.name, segment.local_start + offset, segment.legacy_count)


def render_chunk(start: int, end: int, output: str) -> dict:
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
               "-f", "rawvideo", "-pixel_format", "bgr24", "-video_size", "1920x1080",
               "-framerate", str(FPS), "-i", "pipe:0", "-an", "-c:v", "libx264",
               "-preset", "veryfast", "-crf", "18", "-threads", "2", "-pix_fmt", "yuv420p",
               "-r", str(FPS), "-video_track_timescale", "60000", output]
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=errors)
        try:
            for index in range(start, end):
                image = render_frame(index)
                if image.shape != (1080, 1920, 3) or str(image.dtype) != "uint8":
                    raise ValueError(f"Invalid frame {index}: {image.shape}, {image.dtype}")
                process.stdin.write(image.tobytes())
            process.stdin.close()
            returncode = process.wait()
            if returncode:
                errors.seek(0)
                raise RuntimeError(f"FFmpeg failed for frames {start}:{end}: {errors.read().decode(errors='replace')}")
        except BaseException:
            if process.poll() is None:
                process.terminate()
                process.wait()
            errors.seek(0)
            details = errors.read().decode(errors="replace")
            if details:
                print(details, flush=True)
            raise
    return {"startFrame": start, "endFrameExclusive": end, "path": output}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def probe(path: Path) -> dict:
    result = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format",
                             "-of", "json", str(path)], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def verify_output(path: Path) -> dict:
    metadata = probe(path)
    video = next(stream for stream in metadata["streams"] if stream["codec_type"] == "video")
    audio = next(stream for stream in metadata["streams"] if stream["codec_type"] == "audio")
    if int(video.get("nb_frames", 0)) != FRAME_COUNT:
        raise ValueError(f"Encoded frame count differs: {video.get('nb_frames')}")
    if (video["width"], video["height"], video["pix_fmt"], video["avg_frame_rate"]) != (1920, 1080, "yuv420p", str(FPS)):
        raise ValueError("Unexpected video dimensions, pixel format, or frame rate")
    if audio["channels"] != 2 or int(audio["sample_rate"]) != 48000:
        raise ValueError("Expected stereo 48 kHz audio")
    if abs(float(video["duration"]) - float(DURATION)) > 1 / float(FPS):
        raise ValueError("Encoded video duration differs from timeline")
    if abs(float(audio["duration"]) - float(DURATION)) > .04:
        raise ValueError("Audio and video duration differ by more than 40 ms")
    # Actually decode the complete artifact, so a readable header is insufficient.
    subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-i", str(path),
                    "-map", "0:v:0", "-map", "0:a:0", "-f", "null", "-"], check=True)
    return {"frameCount": int(video["nb_frames"]), "videoDuration": float(video["duration"]),
            "audioDuration": float(audio["duration"]), "formatDuration": float(metadata["format"]["duration"]),
            "width": video["width"], "height": video["height"], "frameRate": video["avg_frame_rate"],
            "fullDecodePassed": True}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workdir", type=Path, required=True, help="Preserved frames/assets/out workspace")
    parser.add_argument("--source", type=Path, required=True, help="Original authorized source MP4")
    parser.add_argument("--output", type=Path, required=True, help="Final .mp4 path")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--preview", help="Comma-separated zero-based output frame indices; only writes JPEG previews")
    args = parser.parse_args()
    workdir, source, output = args.workdir.resolve(), args.source.resolve(), args.output.resolve()
    if not source.is_file():
        parser.error(f"Source video is missing: {source}")
    if not workdir.is_dir():
        parser.error(f"Work directory is missing: {workdir}")
    if output == source:
        parser.error("Output must differ from source")
    if output.suffix.lower() != ".mp4":
        parser.error("Output must have an .mp4 extension")
    if args.workers < 1:
        parser.error("--workers must be positive")
    asset_manifest = workdir / "asset-manifest.json"
    if not asset_manifest.is_file():
        parser.error("Missing asset-manifest.json; prepare this workdir with prepare.py first")
    source_hash = sha256(source)
    asset_data = json.loads(asset_manifest.read_text(encoding="utf-8"))
    if source_hash != asset_data["source"]["sha256"]:
        parser.error("Source differs from the clip bound to these editorial annotations")
    for executable in ("ffmpeg", "ffprobe"):
        if not shutil.which(executable):
            parser.error(f"{executable} is required")
    output.parent.mkdir(parents=True, exist_ok=True)
    if args.preview:
        import cv2
        configure(str(workdir))
        indices = [int(value.strip()) for value in args.preview.split(",")]
        previews = output.parent / f"{output.stem}-previews"
        previews.mkdir(parents=True, exist_ok=True)
        for index in indices:
            target = previews / f"frame-{index:04d}.jpg"
            if not cv2.imwrite(str(target), render_frame(index), [cv2.IMWRITE_JPEG_QUALITY, 94]):
                raise OSError(f"Could not write preview {target}")
            print(f"Preview {index}/{FRAME_COUNT}: {target}", flush=True)
        return
    from broadcast_fx.audio import build_audio
    audio_path = output.with_suffix(".wav")
    audio_metadata = build_audio(workdir, source, audio_path)
    with tempfile.TemporaryDirectory(prefix="gamebuddy-render-", dir=output.parent) as temporary:
        root = Path(temporary)
        ranges = [(start, min(start + 120, FRAME_COUNT)) for start in range(0, FRAME_COUNT, 120)]
        chunks = [root / f"chunk-{start:05d}.mp4" for start, _ in ranges]
        context = multiprocessing.get_context("spawn")
        with ProcessPoolExecutor(max_workers=args.workers, mp_context=context,
                                 initializer=configure, initargs=(str(workdir),)) as executor:
            jobs = [executor.submit(render_chunk, start, end, str(chunk))
                    for (start, end), chunk in zip(ranges, chunks)]
            completed = 0
            for future in as_completed(jobs):
                result = future.result()
                completed += result["endFrameExclusive"] - result["startFrame"]
                print(f"Rendered {completed}/{FRAME_COUNT} frames ({completed / FRAME_COUNT:.0%})", flush=True)
        concat = root / "concat.txt"
        # Only controlled simple chunk names enter the concat file, never user paths.
        concat.write_text("".join(f"file '{chunk.name}'\n" for chunk in chunks), encoding="utf-8")
        staged = root / "final.mp4"
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "1",
                        "-i", str(concat), "-i", str(audio_path), "-map", "0:v:0", "-map", "1:a:0",
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
                        "-video_track_timescale", "60000", "-movflags", "+faststart", str(staged)], check=True)
        verification = verify_output(staged)
        staged.replace(output)
    package = Path(__file__).resolve().parent
    code_paths = [Path(__file__).resolve(), *sorted((package / "broadcast_fx").glob("*.py"))]
    manifest = {
        "schema": "gamebuddy-editorial-video-v1", "product": "GameBuddy",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "frameCount": FRAME_COUNT, "frameRate": str(FPS), "durationSeconds": float(DURATION),
        "durationRational": str(DURATION), "segments": [segment.as_dict() for segment in TIMELINE],
        "inputs": {"source": {"path": str(source), "sha256": source_hash},
                   "assetManifest": {"path": str(asset_manifest), "sha256": sha256(asset_manifest)},
                   "legacyAudio": {"path": audio_metadata["legacyAudio"], "sha256": sha256(Path(audio_metadata["legacyAudio"]))}},
        "output": {"path": str(output), "sha256": sha256(output), "bytes": output.stat().st_size},
        "audio": audio_metadata, "verification": verification,
        "code": [{"path": str(path.relative_to(package)), "sha256": sha256(path)} for path in code_paths],
        "boundaries": {
            "production": "Local editorial cut assembled by AI coding assistants; manually specified timeline and labels",
            "agentInvoked": False, "cloudDeploymentPerformed": False,
            "tactics": "Editorial interpretation of visible source frames, not verified player intent or official tracking",
            "playerEffects": "Short frozen-frame visual highlights; no automatic identities or reconstructed trajectories",
            "audio": "Original broadcast audio and procedural SFX; no new AI voiceover",
            "acceptance": "Technical media validation; human basketball/editorial approval remains separate",
        },
    }
    manifest_path = output.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Finished {output}: {FRAME_COUNT} frames / {float(DURATION):.6f} s; manifest {manifest_path}", flush=True)


if __name__ == "__main__":
    main()
