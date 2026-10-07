"""SQS -> real AgentCore observation -> complete captioned MP4 readiness worker."""

import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
import textwrap
import time
from urllib.parse import urlsplit
import uuid

PROTOCOL = "team02-readiness-v1"
MAX_INPUT_BYTES = 256 * 1024 * 1024


class JobError(ValueError):
    pass


def validate_message(message):
    if not isinstance(message, dict):
        raise JobError("message must be an object")
    job_id, sample = message.get("jobId"), message.get("sample")
    if not isinstance(job_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", job_id):
        raise JobError("invalid jobId")
    if sample not in ("flagg", "amen"):
        raise JobError("sample must be flagg or amen")
    return job_id, sample


def configured_key(uri, bucket):
    if not isinstance(uri, str):
        raise JobError("missing source S3 URI")
    parsed = urlsplit(uri)
    if parsed.scheme != "s3" or parsed.netloc != bucket or not parsed.path.lstrip("/") or parsed.query or parsed.fragment:
        raise JobError("source must be in the configured readiness bucket")
    return parsed.path.lstrip("/")


def read_json_object(s3, bucket, key, limit=1024 * 1024):
    body = s3.get_object(Bucket=bucket, Key=key)["Body"]
    try:
        raw = body.read(limit + 1)
    finally:
        body.close()
    if len(raw) > limit:
        raise JobError("JSON input exceeds size limit")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise JobError("JSON input must be an object")
    return value


def download_video(s3, bucket, key, target):
    body = s3.get_object(Bucket=bucket, Key=key)["Body"]
    digest, total = hashlib.sha256(), 0
    try:
        with target.open("wb") as output:
            while True:
                chunk = body.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_INPUT_BYTES:
                    raise JobError("source video exceeds 256 MiB readiness limit")
                digest.update(chunk)
                output.write(chunk)
    finally:
        body.close()
    if total == 0:
        raise JobError("source video is empty")
    return digest.hexdigest()


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_agent_result(result, request):
    if (not isinstance(result, dict) or result.get("status") != "completed"
            or result.get("protocol_version") != PROTOCOL or result.get("request_id") != request["request_id"]):
        raise JobError("AgentCore did not return a matching completed result")
    if result.get("video", {}).get("id") != request["video"]["id"]:
        raise JobError("AgentCore result is for a different video")
    for key, maximum in (("observation", 180), ("subtitle", 40)):
        value = result.get(key)
        if not isinstance(value, str) or not value.strip() or len(value) > maximum or any(ord(c) < 32 for c in value):
            raise JobError(f"invalid AgentCore {key}")
    times = result.get("source_frame_times_ms")
    permitted = {frame["timestamp_ms"] for frame in request["frames"]}
    if (not isinstance(times, list) or not 1 <= len(times) <= 6
            or any(not isinstance(t, (int, float)) or isinstance(t, bool) or not math.isfinite(t) or t not in permitted for t in times)
            or len(set(times)) != len(times)):
        raise JobError("AgentCore cited an unavailable source frame")
    if result.get("inference_source") != "bedrock_converse" or not result.get("model_id"):
        raise JobError("AgentCore result lacks real model-call provenance")
    return result


def budget(context, ceiling, reserve=20):
    remaining = context.get_remaining_time_in_millis() / 1000 if context else 300
    allowed = min(ceiling, int(remaining - reserve))
    if allowed < 1:
        raise JobError("insufficient worker time remaining")
    return allowed


def render_video(source, output, subtitle_file, context=None):
    ffmpeg = os.environ.get("FFMPEG_PATH", "/opt/bin/ffmpeg")
    font = os.environ.get("FONT_PATH", "/opt/fonts/NotoSansCJKsc-Regular.otf")
    if not Path(ffmpeg).is_file() or not Path(font).is_file():
        raise JobError("FFmpeg or CJK font is missing from the tools layer")
    # Only trusted local paths are interpolated; text itself is read from a file.
    filtergraph = (
        "scale=1280:720:force_original_aspect_ratio=decrease,"
        "pad=1280:720:(ow-iw)/2:(oh-ih)/2,fps=30,"
        "drawbox=x=36:y=24:w=iw-72:h=90:color=black@0.65:t=fill,"
        f"drawtext=fontfile={font}:textfile={subtitle_file}:expansion=none:"
        "fontcolor=white:fontsize=28:line_spacing=8:x=(w-text_w)/2:y=38"
    )
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", str(source),
        "-map", "0:v:0", "-map", "0:a?", "-vf", filtergraph,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-pix_fmt", "yuv420p",
        "-threads", "2", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(output),
    ]
    process = subprocess.run(command, capture_output=True, timeout=budget(context, 180), check=False)
    if process.returncode != 0:
        # FFmpeg is a deterministic local tool; keep a bounded diagnostic, never a success substitute.
        print(json.dumps({"event": "ffmpeg_failed", "stderr": process.stderr.decode("utf-8", "replace")[-2000:]}), flush=True)
        raise JobError("FFmpeg failed to produce the enhanced video")
    if not output.is_file() or output.stat().st_size == 0:
        raise JobError("FFmpeg produced no output")


def inspect_video(path, context=None):
    command = [
        os.environ.get("FFPROBE_PATH", "/opt/bin/ffprobe"), "-v", "error", "-show_entries",
        "format=duration:stream=codec_type,width,height", "-of", "json", str(path),
    ]
    process = subprocess.run(command, capture_output=True, timeout=budget(context, 20), check=True)
    data = json.loads(process.stdout)
    duration_ms = round(float(data["format"]["duration"]) * 1000)
    stream = next(stream for stream in data["streams"] if stream.get("codec_type") == "video")
    if duration_ms <= 0:
        raise JobError("rendered video has invalid duration")
    return {"durationMs": duration_ms, "width": stream["width"], "height": stream["height"]}


def update_job(table, job_id, **fields):
    from decimal import Decimal

    # DynamoDB's high-level serializer rejects Python float values.
    values = json.loads(json.dumps({**fields, "updatedAt": int(time.time())}), parse_float=Decimal)
    keys = list(values)
    table.update_item(
        Key={"id": job_id},
        UpdateExpression="SET " + ", ".join(f"#k{i} = :v{i}" for i in range(len(keys))),
        ExpressionAttributeNames={f"#k{i}": key for i, key in enumerate(keys)},
        ExpressionAttributeValues={f":v{i}": values[key] for i, key in enumerate(keys)},
    )


def run_job(message, s3, table, agentcore, config, context=None, renderer=render_video, inspector=inspect_video):
    job_id, sample = validate_message(message)
    bucket, runtime = config["bucket"], config["runtime"]
    host = config["host"].removeprefix("https://").rstrip("/")
    if not re.fullmatch(r"[A-Za-z0-9.-]+", host):
        raise JobError("invalid CloudFront hostname")
    existing = table.get_item(Key={"id": job_id}, ConsistentRead=True).get("Item", {})
    if existing.get("status") in ("completed", "failed"):
        return {"jobId": job_id, "status": existing["status"], "idempotent": True}
    session_id = None
    started = time.monotonic()
    try:
        update_job(table, job_id, status="processing", stage="loading_inputs", sample=sample)
        samples = read_json_object(s3, bucket, "config/samples.json")
        entry = samples.get(sample)
        if not isinstance(entry, dict) or not isinstance(entry.get("video"), dict) or not isinstance(entry.get("frames"), list):
            raise JobError("sample manifest is missing video or frames")
        video = entry["video"]
        key = configured_key(video.get("s3_uri"), bucket)
        if not isinstance(video.get("duration_ms"), (int, float)) or not 0 < video["duration_ms"] <= 600000:
            raise JobError("invalid source video duration")
        if not 1 <= len(entry["frames"]) <= 6:
            raise JobError("sample requires 1 to 6 source frames")
        for frame in entry["frames"]:
            configured_key(frame.get("s3_uri"), bucket)
        with tempfile.TemporaryDirectory(prefix="readiness-", dir="/tmp") as workspace:
            work = Path(workspace)
            source, output = work / "input.mp4", work / "enhanced.mp4"
            source_sha = download_video(s3, bucket, key, source)
            if video.get("sha256") and source_sha != video["sha256"]:
                raise JobError("source video SHA-256 differs from the registered sample")
            request = {
                "protocol_version": PROTOCOL, "request_id": job_id,
                "video": {**video, "sha256": source_sha}, "frames": entry["frames"],
            }
            session_id = str(uuid.uuid4())
            update_job(table, job_id, stage="analyzing", runtimeArn=runtime, runtimeSessionId=session_id)
            response = agentcore.invoke_agent_runtime(
                agentRuntimeArn=runtime, runtimeSessionId=session_id, qualifier="DEFAULT",
                contentType="application/json", accept="application/json",
                payload=json.dumps(request, ensure_ascii=False, allow_nan=False).encode("utf-8"),
            )
            body = response["response"]
            try:
                raw = body.read(1024 * 1024 + 1)
            finally:
                body.close()
            if len(raw) > 1024 * 1024:
                raise JobError("AgentCore response exceeds readiness limit")
            agent_result = validate_agent_result(json.loads(raw), request)
            update_job(table, job_id, stage="rendering")
            subtitle_file = work / "subtitle.txt"
            evidence_seconds = ",".join(f"{timestamp / 1000:.3f}".rstrip("0").rstrip(".")
                                        for timestamp in agent_result["source_frame_times_ms"])
            caption = f"AI片段摘要 · 引用帧秒数：{evidence_seconds}\n" + "\n".join(textwrap.wrap(agent_result["subtitle"], width=40))
            subtitle_file.write_text(caption, encoding="utf-8")
            renderer(source, output, subtitle_file, context)
            media = inspector(output, context)
            if media["width"] != 1280 or media["height"] != 720:
                raise JobError("rendered video dimensions differ from 720p contract")
            if abs(media["durationMs"] - video["duration_ms"]) > max(250, video["duration_ms"] * 0.01):
                raise JobError("rendered duration does not preserve the complete source clip")
            output_sha = file_sha256(output)
            prefix = f"outputs/{job_id}"
            video_url = f"https://{host}/{prefix}/enhanced.mp4"
            analysis_url = f"https://{host}/{prefix}/analysis.json"
            source_times = agent_result["source_frame_times_ms"]
            analysis = {
                "protocol_version": PROTOCOL, "runId": job_id, "sample": sample,
                "summary": agent_result["observation"],
                "observations": [{"text": agent_result["observation"], "timeSeconds": source_times[0] / 1000,
                                  "timestampMs": source_times[0], "source_frame_times_ms": source_times}],
                "subtitle": agent_result["subtitle"], "source_frame_times_ms": source_times,
                "preservesSourceTimeline": True,
                "evidence": [{"timeSeconds": frame["timestamp_ms"] / 1000,
                              "description": "实际送入模型的来源帧",
                              "frameUrl": f"https://{host}/" + configured_key(frame["s3_uri"], bucket)}
                             for frame in entry["frames"]],
                "runtimeArn": runtime, "runtimeSessionId": session_id,
                "modelId": agent_result["model_id"], "usage": agent_result.get("usage", {}),
                "inferenceSource": agent_result["inference_source"],
                "sourceVideo": {**video, "sha256": source_sha},
                "outputVideo": {**media, "sha256": output_sha, "bytes": output.stat().st_size, "url": video_url},
                "videoUrl": video_url, "analysisUrl": analysis_url,
                "elapsedSeconds": round(time.monotonic() - started, 2),
                "scope": "team_readiness_test_not_official_evaluation_schema",
            }
            update_job(table, job_id, stage="publishing")
            s3.upload_file(str(output), bucket, prefix + "/enhanced.mp4", ExtraArgs={"ContentType": "video/mp4", "CacheControl": "public,max-age=31536000,immutable"})
            s3.put_object(Bucket=bucket, Key=prefix + "/analysis.json", Body=json.dumps(analysis, ensure_ascii=False, allow_nan=False).encode("utf-8"), ContentType="application/json; charset=utf-8", CacheControl="public,max-age=31536000,immutable")
            update_job(table, job_id, status="completed", stage="completed", videoUrl=video_url,
                       analysisUrl=analysis_url, analysis=analysis, outputSha256=output_sha,
                       outputDurationMs=media["durationMs"], elapsedSeconds=analysis["elapsedSeconds"],
                       preservesSourceTimeline=True, evidence=analysis["evidence"])
            return {"jobId": job_id, "status": "completed", "videoUrl": video_url, "analysisUrl": analysis_url}
    except Exception as error:
        aws_error = getattr(error, "response", {}).get("Error", {}).get("Code")
        message_text = str(error) if isinstance(error, JobError) else "处理失败，请查看运行日志后重试。"
        print(json.dumps({"event": "job_failed", "jobId": job_id, "type": type(error).__name__, "aws_error_code": aws_error}), flush=True)
        update_job(table, job_id, status="failed", stage="failed", error=message_text, errorType=type(error).__name__)
        return {"jobId": job_id, "status": "failed", "error": message_text}
    finally:
        if session_id:
            try:
                agentcore.stop_runtime_session(agentRuntimeArn=runtime, runtimeSessionId=session_id, qualifier="DEFAULT")
            except Exception as error:
                print(json.dumps({"event": "session_stop_failed", "jobId": job_id, "type": type(error).__name__}), flush=True)


def handler(event, context):
    import boto3
    from botocore.config import Config

    config = {"bucket": os.environ["BUCKET"], "runtime": os.environ["RUNTIME_ARN"], "host": os.environ["CLOUDFRONT_HOST"]}
    s3 = boto3.client("s3", region_name="us-east-1")
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(os.environ["TABLE"])
    agentcore = boto3.client("bedrock-agentcore", region_name="us-east-1",
                             config=Config(connect_timeout=10, read_timeout=140, retries={"total_max_attempts": 1}))
    for record in event.get("Records", []):
        try:
            message = json.loads(record["body"])
            result = run_job(message, s3, table, agentcore, config, context)
            print(json.dumps({"event": "job_finished", **result}, ensure_ascii=False), flush=True)
        except Exception as error:
            print(json.dumps({"event": "invalid_or_unrecorded_job", "messageId": record.get("messageId"), "type": type(error).__name__}), flush=True)
            # A recognizable job should still have an explicit failed status.
            try:
                candidate = json.loads(record.get("body", "{}"))
                job_id = candidate.get("jobId")
                if isinstance(job_id, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,80}", job_id):
                    update_job(table, job_id, status="failed", stage="failed", error="任务参数或记录更新失败，请检查后重试。", errorType=type(error).__name__)
            except Exception:
                pass
    # User-triggered retry only: do not automatically spend model calls on a failed job.
    return {"batchItemFailures": []}
