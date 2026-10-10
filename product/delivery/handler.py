"""Independent, bounded media/provenance receipt for a completed story job.

This Lambda is a Step Functions task, not a model endpoint or public URL fetcher.
It only reads server-selected objects in its configured bucket. Success does not
certify basketball interpretation, visual quality, or organizer evaluation.
"""

from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit

try:
    from story_contract import canonical_metrics, select_story, StoryValidationError
except ModuleNotFoundError:
    # The deployment ZIP copies this shared contract to its root.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
    from story_contract import canonical_metrics, select_story, StoryValidationError

VERSION = "delivery-verification-v1"
MAX_VIDEO_BYTES = 50 * 1024 * 1024
MAX_JSON_BYTES = 1024 * 1024
MAX_VIDEO_SECONDS = 60
MAX_ELAPSED_SECONDS = 110
SCOPE = "Media and source provenance checks; not human content or organizer scoring certification"
JOB_ID = re.compile(r"[0-9a-f]{32}")
SHA256 = re.compile(r"[0-9a-f]{64}")


class Rejected(Exception):
    """A non-transient delivery contract rejection with safe diagnostics."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Config:
    bucket: str
    runtime: str
    model: str
    host: str

    @classmethod
    def from_environment(cls):
        host = os.environ["CLOUDFRONT_HOST"].removeprefix("https://").rstrip("/")
        if not re.fullmatch(r"[a-z0-9.-]+", host):
            raise Rejected("invalid_configuration", "CloudFront hostname is invalid")
        return cls(os.environ["BUCKET"], os.environ["RUNTIME_ARN"],
                   os.environ.get("MODEL_ID", "global.anthropic.claude-sonnet-4-6"), host)


class Budget:
    def __init__(self, context=None):
        self.started = time.monotonic()
        self.context = context

    def seconds(self, ceiling):
        remaining = MAX_ELAPSED_SECONDS - (time.monotonic() - self.started)
        if self.context is not None:
            remaining = min(remaining, self.context.get_remaining_time_in_millis() / 1000 - 5)
        if remaining < 1:
            raise Rejected("verification_timeout", "Delivery verification time budget exhausted")
        return min(ceiling, remaining)


def plain(value):
    """Normalize DynamoDB Decimal values for comparison with the JSON artifact."""
    return json.loads(json.dumps(value, allow_nan=False,
        default=lambda item: float(item) if isinstance(item, Decimal) else _unsupported(item)))


def _unsupported(value):
    raise TypeError(f"Unsupported receipt type: {type(value).__name__}")


def fingerprint(value):
    return hashlib.sha256(json.dumps(plain(value), ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def require(condition, code, message):
    if not condition:
        raise Rejected(code, message)


def parse_job_id(event):
    require(isinstance(event, dict) and bool(event) and set(event) <= {"jobId", "runId"},
            "invalid_input", "Input must contain only jobId or runId")
    identifiers = [event[key] for key in ("jobId", "runId") if key in event]
    require(all(isinstance(value, str) and JOB_ID.fullmatch(value) for value in identifiers)
            and len(set(identifiers)) == 1, "invalid_input", "Job ID must be a matching 32-character lowercase hex ID")
    return identifiers[0]


def same_bucket_key(uri, config):
    require(isinstance(uri, str), "invalid_source", "Source must reference a registered S3 object")
    parsed = urlsplit(uri)
    key = parsed.path.removeprefix("/")
    require(parsed.scheme == "s3" and parsed.netloc == config.bucket and key
            and not parsed.query and not parsed.fragment and not any(part in ("", ".", "..") for part in key.split("/")),
            "invalid_source", "Source must remain in the configured bucket")
    return key


def read_json(s3, config, key, budget):
    budget.seconds(1)
    response = s3.get_object(Bucket=config.bucket, Key=key)
    body = response["Body"]
    try:
        require(response.get("ContentLength", 0) <= MAX_JSON_BYTES,
                "artifact_too_large", "JSON artifact exceeds delivery limit")
        raw = body.read(MAX_JSON_BYTES + 1)
    finally:
        body.close()
    budget.seconds(1)
    require(0 < len(raw) <= MAX_JSON_BYTES, "invalid_json", "JSON artifact is empty or oversized")
    value = json.loads(raw, parse_constant=lambda token: _reject_nonfinite(token))
    require(isinstance(value, dict), "invalid_json", "JSON artifact must be an object")
    return value, hashlib.sha256(raw).hexdigest(), response


def _reject_nonfinite(token):
    raise Rejected("invalid_json", "JSON artifact contains a non-finite number")


def validate_job(job, job_id, config):
    require(isinstance(job, dict) and job.get("id") == job_id and job.get("jobId") == job_id
            and job.get("runId") == job_id, "job_identity_mismatch", "Stored job identity differs from request")
    require(job.get("status") == "completed" and job.get("mode") == "story",
            "job_not_completed", "Only completed story jobs can be verified")
    analysis = job.get("analysis")
    require(isinstance(analysis, dict), "missing_analysis", "Completed job lacks analysis")
    prefix = f"product/outputs/{job_id}"
    video_url = f"https://{config.host}/{prefix}/enhanced.mp4"
    analysis_url = f"https://{config.host}/{prefix}/analysis.json"
    require(job.get("videoPath") == prefix + "/enhanced.mp4"
            and job.get("videoUrl") == video_url and job.get("analysisUrl") == analysis_url,
            "invalid_output_path", "Stored output paths differ from the fixed delivery paths")
    require(analysis.get("protocol_version") == "product-story-v1" and analysis.get("runId") == job_id
            and analysis.get("mode") == "story" and analysis.get("sample") == job.get("sample"),
            "analysis_identity_mismatch", "Analysis does not belong to the selected story job")
    require(analysis.get("runtimeArn") == config.runtime and job.get("runtimeArn") == config.runtime
            and analysis.get("modelId") == config.model
            and analysis.get("inferenceSource") == "bedrock_converse_tool_loop",
            "inference_identity_mismatch", "Analysis runtime or model differs from deployment")
    usage = analysis.get("usage", {})
    require(number(usage.get("inputTokens")) and usage["inputTokens"] > 0
            and number(usage.get("outputTokens")) and usage["outputTokens"] > 0,
            "missing_inference_usage", "Analysis lacks actual model token usage")
    require(analysis.get("validation", {}).get("passed") is True
            and analysis.get("preservesSourceTimeline") is True and job.get("preservesSourceTimeline") is True,
            "unvalidated_analysis", "Analysis lacks the validated source-preserving contract")
    video = analysis.get("outputVideo", {})
    require(isinstance(video, dict) and isinstance(video.get("sha256"), str)
            and SHA256.fullmatch(video["sha256"]) and video["sha256"] == job.get("outputSha256")
            and video.get("url") == video_url and analysis.get("videoUrl") == video_url
            and analysis.get("videoPath") == job["videoPath"] and analysis.get("analysisUrl") == analysis_url,
            "output_metadata_mismatch", "Output metadata differs from the completed task")
    require(number(video.get("bytes")) and 0 < video["bytes"] <= MAX_VIDEO_BYTES
            and video["bytes"] == int(video["bytes"]), "artifact_too_large", "Output must fit the 50 MiB delivery limit")
    require(number(video.get("durationMs")) and 0 < video["durationMs"] <= MAX_VIDEO_SECONDS * 1000 + 250
            and video["durationMs"] == job.get("outputDurationMs"),
            "duration_mismatch", "Completed output exceeds one minute or has inconsistent duration")
    return analysis, prefix


def validate_sources(analysis, registry, stories, config):
    sample = analysis["sample"]
    registered = registry.get(sample, {}).get("video")
    source = analysis.get("sourceVideo")
    require(isinstance(registered, dict) and isinstance(source, dict) and source.get("id") == sample,
            "unregistered_source", "Analysis source is absent from the registered inputs")
    same_bucket_key(source.get("s3_uri"), config)
    for key in ("id", "s3_uri", "duration_ms", "width", "height", "name", "sha256"):
        require(key in registered and registered[key] == source.get(key),
                "source_mismatch", f"Analysis source {key} differs from registered media")
    require(isinstance(source.get("sha256"), str) and SHA256.fullmatch(source["sha256"])
            and number(source.get("duration_ms")) and 0 < source["duration_ms"] <= MAX_VIDEO_SECONDS * 1000,
            "invalid_source", "Source requires a SHA-256 and at most one-minute duration")
    story = select_story(stories, sample)
    require(story.get("sourceVideoSha256") == source["sha256"]
            and story.get("officialEvent") == analysis.get("officialEvent")
            and analysis.get("plan", {}).get("metrics") == canonical_metrics(story),
            "official_data_mismatch", "Official event or typed metric differs from the registered evidence")
    require(abs(story.get("durationSeconds", -1000) * 1000 - source["duration_ms"]) <= 250,
            "source_mismatch", "Story and source timelines differ")
    manifest = analysis.get("source", {})
    require(isinstance(manifest, dict)
            and same_bucket_key(manifest.get("manifest"), config) == "product/data/stories.json"
            and isinstance(manifest.get("sha256"), str) and SHA256.fullmatch(manifest["sha256"]),
            "invalid_source", "Analysis lacks its original same-bucket story manifest identity")
    # The current story document also contains mutable showcase links. Its whole
    # file hash can change after publication; selected event and metric values
    # above are compared exactly instead of pretending that hash is immutable.


def object_identity(response):
    return {"etag": response.get("ETag", ""), "versionId": response.get("VersionId", ""),
            "bytes": response.get("ContentLength", -1),
            "lastModified": str(response.get("LastModified", ""))}


def cached_receipt(job, analysis, s3, config, prefix, budget):
    receipt = job.get("deliveryVerification", {})
    if not isinstance(receipt, dict) or receipt.get("verified") is not True or receipt.get("version") != VERSION:
        return None
    if receipt.get("analysisFingerprint") != fingerprint(analysis) or receipt.get("outputSha256") != job["outputSha256"]:
        return None
    for field, suffix in (("videoObject", "enhanced.mp4"), ("analysisObject", "analysis.json")):
        budget.seconds(1)
        current = object_identity(s3.head_object(Bucket=config.bucket, Key=f"{prefix}/{suffix}"))
        if not current["etag"] or current != receipt.get(field):
            return None
    return {**receipt, "idempotent": True}


def download_output(s3, config, key, target, expected, budget):
    response = s3.get_object(Bucket=config.bucket, Key=key)
    body, digest, total, header = response["Body"], hashlib.sha256(), 0, b""
    try:
        require(response.get("ContentLength") == expected["bytes"]
                and 0 < response["ContentLength"] <= MAX_VIDEO_BYTES,
                "size_mismatch", "S3 output size differs from the persisted artifact")
        with target.open("wb") as output:
            while True:
                budget.seconds(1)
                chunk = body.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                require(total <= MAX_VIDEO_BYTES, "artifact_too_large", "Output exceeds 50 MiB while streaming")
                header = (header + chunk)[:32]
                digest.update(chunk)
                output.write(chunk)
    finally:
        body.close()
    require(total == expected["bytes"], "size_mismatch", "S3 output is incomplete")
    require(len(header) >= 16 and header[4:8] == b"ftyp"
            and 16 <= int.from_bytes(header[:4], "big") <= total,
            "invalid_mp4", "Output does not begin with a valid MP4 file-type box")
    require(digest.hexdigest() == expected["sha256"], "hash_mismatch", "Actual MP4 SHA-256 differs from the completed task")
    return object_identity(response)


def inspect_and_decode(path, budget):
    probe = subprocess.run([os.environ.get("FFPROBE_PATH", "/opt/bin/ffprobe"), "-v", "error",
        "-show_entries", "format=duration:stream=codec_type,width,height,codec_name", "-of", "json", str(path)],
        capture_output=True, check=True, timeout=budget.seconds(12))
    value = json.loads(probe.stdout)
    streams = value.get("streams", [])
    videos = [item for item in streams if item.get("codec_type") == "video"]
    require(len(videos) == 1, "invalid_media", "Output requires exactly one video stream")
    duration = float(value.get("format", {}).get("duration", "nan"))
    require(math.isfinite(duration) and 0 < duration <= MAX_VIDEO_SECONDS + 0.25,
            "invalid_media", "Decoded media duration exceeds one minute")
    video = videos[0]
    require(video.get("codec_name") == "h264" and (video.get("width"), video.get("height")) == (1280, 900),
            "invalid_media", "Output codec or dimensions differ from the delivery canvas")
    audio = [item for item in streams if item.get("codec_type") == "audio"]
    require(bool(audio) and all(item.get("codec_name") == "aac" for item in audio),
            "invalid_media", "Output requires the preserved AAC audio stream")
    # Full decode catches truncated/corrupt payloads that a header probe misses.
    # Local file only; no URL/protocol input and no additional inference.
    subprocess.run([os.environ.get("FFMPEG_PATH", "/opt/bin/ffmpeg"), "-v", "error", "-xerror", "-nostdin",
        "-threads", "2", "-i", str(path), "-map", "0:v:0", "-map", "0:a", "-f", "null", "-"],
        capture_output=True, check=True, timeout=budget.seconds(45))
    return {"durationMs": round(duration * 1000), "width": video["width"], "height": video["height"],
            "videoCodec": "h264", "audioStreams": len(audio), "audioCodec": "aac", "fullDecodeVerified": True}


def save_receipt(table, job_id, job, receipt):
    values = json.loads(json.dumps(receipt, ensure_ascii=False, allow_nan=False), parse_float=Decimal)
    snapshot = json.loads(json.dumps(job["analysis"], ensure_ascii=False, allow_nan=False), parse_float=Decimal)
    table.update_item(Key={"id": job_id}, UpdateExpression="SET #delivery = :receipt",
        ConditionExpression="attribute_exists(#id) AND #status = :completed AND #mode = :story AND #hash = :hash AND #analysis = :analysis",
        ExpressionAttributeNames={"#delivery": "deliveryVerification", "#id": "id", "#status": "status",
                                  "#mode": "mode", "#hash": "outputSha256", "#analysis": "analysis"},
        ExpressionAttributeValues={":receipt": values, ":completed": "completed", ":story": "story",
                                   ":hash": job["outputSha256"], ":analysis": snapshot})


def verify_delivery(event, s3, table, config, context=None, inspector=inspect_and_decode):
    """Purely bounded delivery task; injected clients make real edges testable."""
    budget, job_id, job = Budget(context), None, None
    eligible = False
    try:
        job_id = parse_job_id(event)
        item = table.get_item(Key={"id": job_id}, ConsistentRead=True).get("Item")
        require(item is not None, "job_not_found", "No stored task matches this job ID")
        job = plain(item)
        analysis, prefix = validate_job(job, job_id, config)
        eligible = True
        # Verify current registered event/metrics even on idempotent calls.
        registry, _, _ = read_json(s3, config, "product/config/samples.json", budget)
        stories, _, _ = read_json(s3, config, "product/data/stories.json", budget)
        validate_sources(analysis, registry, stories, config)
        cached = cached_receipt(job, analysis, s3, config, prefix, budget)
        if cached:
            return cached
        artifact, analysis_sha, analysis_response = read_json(s3, config, prefix + "/analysis.json", budget)
        # Publication attaches a receipt wrapper to the immutable analysis. It
        # cannot replace any original field, including source/runtime/plan/hash.
        facts = {key: value for key, value in artifact.items() if key != "publication"}
        require(facts == analysis and ("publication" not in artifact or isinstance(artifact["publication"], dict)),
                "analysis_mismatch", "S3 analysis facts differ from the persisted completed task")
        with tempfile.TemporaryDirectory(prefix="delivery-", dir="/tmp") as directory:
            path = Path(directory) / "enhanced.mp4"
            identity = download_output(s3, config, prefix + "/enhanced.mp4", path, analysis["outputVideo"], budget)
            media = inspector(path, budget)
        expected = analysis["outputVideo"]
        require(media["width"] == expected["width"] and media["height"] == expected["height"]
                and media["audioStreams"] == expected["audioStreams"]
                and abs(media["durationMs"] - expected["durationMs"]) <= 250
                and abs(media["durationMs"] - analysis["sourceVideo"]["duration_ms"]) <= 250,
                "media_mismatch", "Actual media differs from persisted dimensions, audio, or timeline")
        receipt = {"verified": True, "status": "verified", "version": VERSION, "jobId": job_id,
            "verifiedAt": int(time.time()), "elapsedSeconds": round(time.monotonic() - budget.started, 3),
            "outputSha256": expected["sha256"], "analysisSha256": analysis_sha,
            "analysisFingerprint": fingerprint(analysis), "sourceSha256": analysis["sourceVideo"]["sha256"],
            "runtimeArn": config.runtime, "modelId": config.model, "videoUrl": job["videoUrl"],
            "videoObject": identity, "analysisObject": object_identity(analysis_response),
            "media": media, "scope": SCOPE, "idempotent": False}
        save_receipt(table, job_id, job, receipt)
        return receipt
    except Exception as error:
        aws_code = getattr(error, "response", {}).get("Error", {}).get("Code")
        if isinstance(error, (Rejected, StoryValidationError, ValueError, TypeError, KeyError, AttributeError)):
            code = error.code if isinstance(error, Rejected) else "invalid_artifact"
            retryable = False
            message = str(error)[:240] if isinstance(error, (Rejected, StoryValidationError)) else "Artifact structure is invalid"
        elif isinstance(error, (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError)):
            code, retryable, message = "media_check_failed", False, "Media probe or full decode could not complete"
        else:
            code, retryable, message = "storage_unavailable", True, "Delivery storage is unavailable; retry verification"
            if aws_code in ("NoSuchKey", "404", "NotFound"):
                code, retryable, message = "artifact_not_found", False, "A required same-bucket artifact is absent"
            elif aws_code == "ConditionalCheckFailedException":
                code, retryable, message = "job_changed", True, "Task changed during verification; reread and retry"
        receipt = {"verified": False, "status": "unavailable" if retryable else "rejected", "version": VERSION,
            "jobId": job_id, "code": code, "message": message, "retryable": retryable, "scope": SCOPE}
        # Never create jobs or change processing status. Write an independent
        # rejection only after checking a real completed task and its identity.
        if eligible and not retryable:
            try:
                save_receipt(table, job_id, job, {**receipt, "verifiedAt": int(time.time())})
            except Exception:
                print(json.dumps({"event": "delivery_rejection_receipt_not_saved", "jobId": job_id}))
        print(json.dumps({"event": "delivery_verification_rejected", "jobId": job_id, "code": code,
                          "retryable": retryable, "errorType": type(error).__name__}))
        return receipt


def handler(event, context):
    # Configure clients lazily so import does not request credentials/network.
    import boto3
    from botocore.config import Config as SDKConfig

    sdk_config = SDKConfig(connect_timeout=5, read_timeout=10, retries={"max_attempts": 1})
    s3 = boto3.client("s3", config=sdk_config)
    table = boto3.resource("dynamodb", config=sdk_config).Table(os.environ["TABLE"])
    return verify_delivery(event, s3, table, Config.from_environment(), context)
