"""Queue worker for the product story pipeline, preserving legacy readiness jobs."""

import json
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import uuid

import readiness_worker as legacy
from delivery_events import emit_metrics, emit_terminal_metric, error_code, publish_video_rendered

try:
    from story_contract import (STORIES_KEY, STORY_PROTOCOL, StoryValidationError, evidence_catalog,
                                frame_id, number, select_story, validate_plan, validate_story_source)
except ModuleNotFoundError:
    # Local source checkout; production packages copy this shared module to ZIP root.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
    from story_contract import (STORIES_KEY, STORY_PROTOCOL, StoryValidationError, evidence_catalog,
                                frame_id, number, select_story, validate_plan, validate_story_source)

STORY_SAMPLES_KEY = "product/config/samples.json"
OUTPUT_WIDTH, OUTPUT_HEIGHT = 1280, 900
from rl_integration import start_selection, collect_selection, narrative_input, analysis_fields
from rl_render import add_rl_filters


def validate_request(request, bucket):
    video, frames = request.get("video"), request.get("frames")
    if not isinstance(video, dict) or not isinstance(frames, list) or not 1 <= len(frames) <= 6:
        raise legacy.JobError("story sample requires video and 1 to 6 source frames")
    if not number(video.get("duration_ms")) or not 0 < video["duration_ms"] <= 600000:
        raise legacy.JobError("source duration is invalid")
    legacy.configured_key(video.get("s3_uri"), bucket)
    seen = set()
    for frame in frames:
        if not isinstance(frame, dict):
            raise legacy.JobError("frame must be an object")
        timestamp = frame.get("timestamp_ms")
        if not number(timestamp) or not 0 <= timestamp <= video["duration_ms"] or timestamp in seen:
            raise legacy.JobError("source frame timestamps must be unique and within the clip")
        if frame.get("format") not in ("jpeg", "png"):
            raise legacy.JobError("source frame must be jpeg or png")
        legacy.configured_key(frame.get("s3_uri"), bucket)
        seen.add(timestamp)


def validate_result(result, request):
    if (not isinstance(result, dict) or result.get("protocol_version") != STORY_PROTOCOL
            or result.get("request_id") != request["request_id"] or result.get("status") != "completed"
            or result.get("video", {}).get("id") != request["video"]["id"]
            or result.get("inference_source") != "bedrock_converse_tool_loop" or not result.get("model_id")):
        raise legacy.JobError("AgentCore did not return a matching completed story")
    trace = result.get("trace")
    if not isinstance(trace, list) or not 3 <= len(trace) <= 24:
        raise legacy.JobError("story result lacks a bounded real tool trace")
    successful = [step for step in trace if isinstance(step, dict) and step.get("status") == "succeeded"]
    if not {"inspect_frames", "read_official_event", "validate_story"}.issubset({step.get("tool") for step in successful}):
        raise legacy.JobError("required tool executions did not complete")
    validation_steps = [step for step in successful if step.get("tool") == "validate_story"]
    if len(validation_steps) != 1 or validation_steps[0] is not trace[-1]:
        raise legacy.JobError("story must end with exactly one successful validation")
    validation_step = validation_steps[0]
    validation_round = validation_step.get("round")
    if not isinstance(validation_round, int) or isinstance(validation_round, bool) or not 2 <= validation_round <= 6:
        raise legacy.JobError("validation must happen in a later model round")
    for index, step in enumerate(trace, 1):
        if not isinstance(step, dict) or step.get("step") != index or not isinstance(step.get("round"), int):
            raise legacy.JobError("malformed tool execution sequence")
        if step is not validation_step and step["round"] >= validation_round:
            raise legacy.JobError("source tools must return in a previous model round before validation")
    if not any(step.get("tool") == "read_official_event" and step["round"] < validation_round for step in successful):
        raise legacy.JobError("official data was not delivered to the model before validation")
    available = {frame_id(frame["timestamp_ms"]): frame for frame in request["frames"]}
    inspected = set()
    for step in successful:
        if step.get("requestId") != request["request_id"]:
            raise legacy.JobError("tool trace belongs to a different request")
        if step.get("tool") == "inspect_frames":
            for frame in step.get("result", {}).get("frames", []):
                identifier = frame.get("id")
                if (identifier not in available or frame.get("source") != available[identifier]["s3_uri"]
                        or frame.get("timestamp_ms") != available[identifier]["timestamp_ms"]
                        or not re.fullmatch(r"[a-f0-9]{64}", str(frame.get("sha256", "")))):
                    raise legacy.JobError("tool trace frame does not match source metadata")
                inspected.add(identifier)
    if len(inspected) < min(2, len(available)):
        raise legacy.JobError("insufficient actual inspected frame evidence")
    raw_plan = result.get("plan", {})
    plan_keys = ["perspective", "title", "summary", "chapters"]
    if request.get("rlEvidence"):
        plan_keys.extend(["rlEvidenceIds", "rlNarrative"])
    generated = {key: raw_plan.get(key) for key in plan_keys}
    if validation_step.get("input", {}).get("plan") != generated:
        raise legacy.JobError("render plan differs from the actual validated tool input")
    normalized = validate_plan(generated, request["story"], request, inspected)
    if raw_plan != normalized or result.get("officialEvent") != request["story"].get("officialEvent", {}):
        raise legacy.JobError("Agent altered copied official values or returned an unvalidated plan")
    check = result.get("validation", {})
    if check.get("passed") is not True or set(check.get("inspectedFrameIds", [])) != inspected:
        raise legacy.JobError("Agent validation receipt does not match actual tool evidence")
    expected_times = sorted(available[identifier]["timestamp_ms"] for identifier in inspected)
    if result.get("source_frame_times_ms") != expected_times:
        raise legacy.JobError("Agent cited frame times differ from its tool trace")
    return result


def inspect_media(path, context=None):
    process = subprocess.run([
        os.environ.get("FFPROBE_PATH", "/opt/bin/ffprobe"), "-v", "error", "-show_entries",
        "format=duration:stream=codec_type,width,height,codec_name", "-of", "json", str(path),
    ], capture_output=True, timeout=legacy.budget(context, 20), check=True)
    value = json.loads(process.stdout)
    video = next(stream for stream in value["streams"] if stream.get("codec_type") == "video")
    duration = round(float(value["format"]["duration"]) * 1000)
    if duration <= 0:
        raise legacy.JobError("media duration is invalid")
    return {"durationMs": duration, "width": video["width"], "height": video["height"],
            "audioStreams": sum(stream.get("codec_type") == "audio" for stream in value["streams"])}


def render_story(source, output, result, context=None):
    """Burn a source-preserving 720px picture into a 1280x900 editorial canvas."""
    ffmpeg = os.environ.get("FFMPEG_PATH", "/opt/bin/ffmpeg")
    font = os.environ.get("FONT_PATH", "/opt/fonts/NotoSansCJKsc-Regular.otf")
    if not Path(ffmpeg).is_file() or not Path(font).is_file():
        raise legacy.JobError("FFmpeg or CJK font is missing")
    work = output.parent
    plan = result["plan"]
    filters = ["scale=1280:720:force_original_aspect_ratio=decrease",
               "pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=black", "fps=30",
               "pad=1280:900:0:76:color=0x07080b",
               "drawbox=x=28:y=69:w=72:h=3:color=0xf4541f:t=fill"]

    def label(name, value, x, y, size, color="0xf2f0ea", enable=None):
        path = work / (name + ".txt")
        path.write_text(value, encoding="utf-8")
        clause = f"drawtext=fontfile={font}:textfile={path}:expansion=none:fontcolor={color}:fontsize={size}:x={x}:y={y}"
        if enable is not None:
            clause += f":enable='{enable}'"
        filters.append(clause)

    label("title", "GameBuddy  /  " + plan["title"], 28, 21, 28)
    metrics = plan.get("metrics", [])
    if metrics:
        metric = metrics[0]
        metric_enable = f"gte(t,{metric.get('revealAt', 0):.6f})"
        label("metric", "本次出手 xFG  " + metric["display"], 912, 12, 22, "0xffffff", metric_enable)
        filters.extend([f"drawbox=x=912:y=44:w=280:h=6:color=0x323848:t=fill:enable='{metric_enable}'",
                        f"drawbox=x=912:y=44:w={max(1, round(280 * metric['barRatio']))}:h=6:color=0xf4541f:t=fill:enable='{metric_enable}'"])
        label("metric_source", "NBA官方 · 出手机会参考", 912, 55, 12, "0x8d93a3", metric_enable)
    else:
        label("metric_unavailable", "官方指标待核准", 958, 20, 21, "0x8d93a3")
    actual_frames = {item["id"] for item in result["evidence"] if item.get("kind") == "video_frame" and item["id"].startswith("frame-")}
    for index, chapter in enumerate(plan["chapters"]):
        enable = f"gte(t,{chapter['start']:.6f})*lt(t,{chapter['end']:.6f})"
        label(f"chapter-{index}", chapter["title"], 28, 806, 23, "0xf4541f", enable)
        label(f"caption-{index}", chapter["caption"], 28, 846, 25, "0xf2f0ea", enable)
        references = chapter["evidenceIds"]
        has_metric = any(metric["evidenceId"] in references for metric in metrics)
        has_frames = bool(actual_frames.intersection(references))
        source_label = "AI解读 · " + ("NBA官方数据 + 来源画面" if has_metric and has_frames else
                                       "NBA官方数据" if has_metric else "来源画面与策展证据")
        label(f"source-{index}", source_label, 820, 813, 14, "0x8d93a3", enable)
    rl_receipt = add_rl_filters(filters, label, result)
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", str(source),
               "-map", "0:v:0", "-map", "0:a?", "-vf", ",".join(filters),
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
               "-threads", "2", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(output)]
    process = subprocess.run(command, capture_output=True, timeout=legacy.budget(context, 130, reserve=25), check=False)
    if process.returncode or not output.is_file() or output.stat().st_size == 0:
        print(json.dumps({"event": "story_render_failed", "returnCode": process.returncode,
                          "stderr": process.stderr.decode("utf-8", "replace")[-2000:]}), flush=True)
        raise legacy.JobError("FFmpeg could not render the complete story")
    return rl_receipt


def record_render_delivery(job_id, table, events_client, bus_name):
    """Notify the independent verifier without invalidating a completed render."""
    receipt = publish_video_rendered(job_id, events_client, bus_name)
    if receipt["status"] != "disabled":
        try:
            legacy.update_job(table, job_id, deliveryEvent=receipt)
        except Exception as error:
            emit_metrics("delivery_event_receipt_not_persisted", {"DeliveryEventRecordFailed": 1}, job_id,
                         errorType=type(error).__name__, awsErrorCode=error_code(error))
    return receipt


def run_story_job(message, s3, table, agentcore, config, context=None, renderer=render_story,
                  inspector=inspect_media, events_client=None, rl_runner=None):
    job_id, sample = legacy.validate_message(message)
    bucket, runtime = config["bucket"], config["runtime"]
    host = config["host"].removeprefix("https://").rstrip("/")
    if not re.fullmatch(r"[A-Za-z0-9.-]+", host):
        raise legacy.JobError("invalid CloudFront hostname")
    previous_status = table.get_item(Key={"id": job_id}, ConsistentRead=True).get("Item", {}).get("status")
    if previous_status in ("completed", "failed"):
        return {"jobId": job_id, "status": previous_status, "idempotent": True}
    started, session_id = time.monotonic(), None
    try:
        legacy.update_job(table, job_id, status="processing", stage="loading_inputs", sample=sample, mode="story")
        samples = legacy.read_json_object(s3, bucket, STORY_SAMPLES_KEY)
        sample_data = samples.get(sample)
        if not isinstance(sample_data, dict):
            raise legacy.JobError("unknown story sample")
        document = legacy.read_json_object(s3, bucket, STORIES_KEY)
        story = select_story(document, sample)
        request = {"protocol_version": legacy.PROTOCOL, "request_id": job_id, "mode": "story", "sample": sample,
                   "video": sample_data.get("video"), "frames": sample_data.get("frames"), "story": story}
        validate_request(request, bucket)
        validate_story_source(story, request)
        # Start the real selector while source media downloads and is inspected.
        # The verified facts then enter the same AgentCore visual/narrative run.
        pending_rl = start_selection(sample, config.get("enableRL", False), rl_runner)
        with tempfile.TemporaryDirectory(prefix="story-", dir="/tmp") as directory:
            work = Path(directory)
            source, output = work / "input.mp4", work / "enhanced.mp4"
            source_sha = legacy.download_video(s3, bucket, legacy.configured_key(request["video"]["s3_uri"], bucket), source)
            if request["video"].get("sha256") and request["video"]["sha256"] != source_sha:
                raise legacy.JobError("source video SHA-256 differs from the registered sample")
            request["video"] = {**request["video"], "sha256": source_sha}
            validate_story_source(story, request)
            source_media = inspector(source, context)
            if abs(source_media["durationMs"] - request["video"]["duration_ms"]) > 250:
                raise legacy.JobError("actual source duration differs from registered metadata")
            rl_result = collect_selection(pending_rl, story)
            if rl_result:
                rl_input = narrative_input(rl_result['presentation'])
                if rl_input:
                    request['rlEvidence'] = rl_input
            session_id = str(uuid.uuid4())
            legacy.update_job(table, job_id, stage="analyzing", runtimeArn=runtime, runtimeSessionId=session_id)
            response = agentcore.invoke_agent_runtime(agentRuntimeArn=runtime, runtimeSessionId=session_id,
                qualifier="DEFAULT", contentType="application/json", accept="application/json",
                payload=json.dumps(request, ensure_ascii=False, allow_nan=False).encode())
            body = response["response"]
            try:
                raw = body.read(1024 * 1024 + 1)
            finally:
                body.close()
            if len(raw) > 1024 * 1024:
                raise legacy.JobError("AgentCore response exceeds the product limit")
            result = validate_result(json.loads(raw), request)
            if request.get('rlEvidence'):
                result['rlEvidence'] = request['rlEvidence']
            legacy.update_job(table, job_id, stage="rendering", agentRounds=max(step["round"] for step in result["trace"]))
            rl_receipt = renderer(source, output, result, context)
            media = inspector(output, context)
            if (media["width"], media["height"]) != (OUTPUT_WIDTH, OUTPUT_HEIGHT):
                raise legacy.JobError("story render dimensions differ from the safe-canvas contract")
            if abs(media["durationMs"] - request["video"]["duration_ms"]) > max(250, request["video"]["duration_ms"] * 0.01):
                raise legacy.JobError("story render did not preserve the full source duration")
            if source_media.get("audioStreams", 0) > 0 and media.get("audioStreams", 0) == 0:
                raise legacy.JobError("story render lost the source audio")
            output_sha = legacy.file_sha256(output)
            prefix = f"product/outputs/{job_id}"
            video_url, analysis_url = f"https://{host}/{prefix}/enhanced.mp4", f"https://{host}/{prefix}/analysis.json"
            evidence = evidence_catalog(story, request["frames"])
            for item in evidence:
                if item.get("s3_uri"):
                    item["frameUrl"] = f"https://{host}/" + legacy.configured_key(item["s3_uri"], bucket)
                    item["timeSeconds"] = item.get("videoTime")
                item.setdefault("description", item.get("body", item.get("title", "来源证据")))
            analysis = {
                "protocol_version": STORY_PROTOCOL, "runId": job_id, "sample": sample, "mode": "story",
                "summary": result["plan"]["summary"], "plan": result["plan"], "trace": result["trace"],
                "validation": result["validation"], "officialEvent": result["officialEvent"], "source": result["source"],
                "observations": [{"text": chapter["caption"], "timeSeconds": chapter["start"], "evidenceIds": chapter["evidenceIds"]}
                                 for chapter in result["plan"]["chapters"]],
                "source_frame_times_ms": result["source_frame_times_ms"], "preservesSourceTimeline": True,
                "evidence": evidence, "runtimeArn": runtime, "runtimeSessionId": session_id,
                "modelId": result["model_id"], "usage": result["usage"], "inferenceSource": result["inference_source"],
                "sourceVideo": request["video"],
                "outputVideo": {**media, "sha256": output_sha, "bytes": output.stat().st_size, "url": video_url},
                "renderContract": {"width": OUTPUT_WIDTH, "height": OUTPUT_HEIGHT,
                                   "sourcePicture": {"x": 0, "y": 76, "width": 1280, "height": 720},
                                   "overlaysOutsideSourcePicture": True, "originalAudioPreserved": True},
                "videoUrl": video_url, "videoPath": prefix + "/enhanced.mp4", "analysisUrl": analysis_url,
                "elapsedSeconds": round(time.monotonic() - started, 2),
                "scope": "product_story_protocol_not_organizer_evaluation_schema",
            }
            if rl_result:
                audit_key = prefix + '/rl-audit.json'
                audit_body = json.dumps(rl_result['audit'], ensure_ascii=False, allow_nan=False).encode()
                s3.put_object(Bucket=bucket, Key=audit_key, Body=audit_body,
                              ContentType='application/json; charset=utf-8',
                              CacheControl='public,max-age=31536000,immutable')
                analysis.update(analysis_fields(rl_result['presentation'], rl_receipt))
                analysis['rlAudit'] = {'path': audit_key, 'url': f'https://{host}/{audit_key}',
                    'sha256': hashlib.sha256(audit_body).hexdigest(), 'bytes': len(audit_body)}
            legacy.update_job(table, job_id, stage="publishing")
            s3.upload_file(str(output), bucket, prefix + "/enhanced.mp4",
                           ExtraArgs={"ContentType": "video/mp4", "CacheControl": "public,max-age=31536000,immutable"})
            s3.put_object(Bucket=bucket, Key=prefix + "/analysis.json", Body=json.dumps(analysis, ensure_ascii=False, allow_nan=False).encode(),
                          ContentType="application/json; charset=utf-8", CacheControl="public,max-age=31536000,immutable")
            legacy.update_job(table, job_id, status="completed", stage="completed", analysis=analysis,
                              videoUrl=video_url, videoPath=prefix + "/enhanced.mp4", analysisUrl=analysis_url,
                              outputSha256=output_sha, outputDurationMs=media["durationMs"],
                              preservesSourceTimeline=True, elapsedSeconds=analysis["elapsedSeconds"])
            emit_terminal_metric(job_id, "completed", elapsedSeconds=analysis["elapsedSeconds"])
            # Publishing happens after both objects and the completed job are durable.
            # This is a notification receipt, not a claim of independent verification.
            record_render_delivery(job_id, table, events_client, config.get("deliveryEventBus"))
            return {"jobId": job_id, "status": "completed", "videoUrl": video_url, "analysisUrl": analysis_url}
    except Exception as error:
        print(json.dumps({"event": "story_job_failed", "jobId": job_id, "type": type(error).__name__,
                          "awsErrorCode": getattr(error, "response", {}).get("Error", {}).get("Code")}), flush=True)
        message = str(error) if isinstance(error, (legacy.JobError, StoryValidationError)) else "故事生成失败，请查看运行记录后重试。"
        legacy.update_job(table, job_id, status="failed", stage="failed", error=message, errorType=type(error).__name__)
        emit_terminal_metric(job_id, "failed", errorType=type(error).__name__)
        return {"jobId": job_id, "status": "failed", "error": message}
    finally:
        if session_id:
            try:
                agentcore.stop_runtime_session(agentRuntimeArn=runtime, runtimeSessionId=session_id, qualifier="DEFAULT")
            except Exception as error:
                print(json.dumps({"event": "story_session_stop_failed", "jobId": job_id, "type": type(error).__name__}), flush=True)


def run_job(message, s3, table, agentcore, config, context=None, **kwargs):
    if not isinstance(message, dict) or message.get("mode", "readiness") not in ("readiness", "story"):
        raise legacy.JobError("mode must be readiness or story")
    if message.get("mode") == "story":
        return run_story_job(message, s3, table, agentcore, config, context, **kwargs)
    kwargs.pop("events_client", None)
    return legacy.run_job(message, s3, table, agentcore, config, context, **kwargs)


def process_records(event, context, s3, table, agentcore, config, events_client=None):
    failures = []
    for record in event.get("Records", []):
        try:
            message = json.loads(record["body"])
            kwargs = {"events_client": events_client} if isinstance(message, dict) and message.get("mode") == "story" and events_client is not None else {}
            result = run_job(message, s3, table, agentcore, config, context, **kwargs)
            if isinstance(message, dict) and message.get("mode", "readiness") == "readiness" and not result.get("idempotent"):
                emit_terminal_metric(result.get("jobId"), result.get("status"))
            print(json.dumps({"event": "product_job_finished", **result}, ensure_ascii=False), flush=True)
        except Exception as error:
            print(json.dumps({"event": "invalid_product_job", "type": type(error).__name__}), flush=True)
            try:
                job_id, _ = legacy.validate_message(json.loads(record.get("body", "{}")))
            except (ValueError, TypeError):
                continue
            try:
                legacy.update_job(table, job_id, status="failed", stage="failed", error="任务参数或记录更新失败。", errorType=type(error).__name__)
                emit_terminal_metric(job_id, "failed", errorType=type(error).__name__)
            except Exception as persistence_error:
                print(json.dumps({"event": "product_terminal_status_not_persisted", "jobId": job_id,
                                  "type": type(persistence_error).__name__}), flush=True)
                message_id = record.get("messageId")
                if not isinstance(message_id, str) or not message_id:
                    raise legacy.JobError("valid SQS record is missing its messageId") from persistence_error
                failures.append({"itemIdentifier": message_id})
    return {"batchItemFailures": failures}


def handler(event, context):
    import boto3
    from botocore.config import Config

    config = {"bucket": os.environ["BUCKET"], "runtime": os.environ["RUNTIME_ARN"], "host": os.environ["CLOUDFRONT_HOST"],
              "deliveryEventBus": os.environ.get("DELIVERY_EVENT_BUS"),
              "enableRL": os.environ.get("ENABLE_RL_SCOUT") == '1'}
    s3 = boto3.client("s3", region_name="us-east-1")
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(os.environ.get("JOBS_TABLE") or os.environ["TABLE"])
    agentcore = boto3.client("bedrock-agentcore", region_name="us-east-1",
                             config=Config(connect_timeout=8, read_timeout=220, retries={"total_max_attempts": 1}))
    events_client = boto3.client("events", region_name="us-east-1",
        config=Config(connect_timeout=2, read_timeout=3, retries={"total_max_attempts": 1})) if config["deliveryEventBus"] else None
    return process_records(event, context, s3, table, agentcore, config, events_client=events_client)
