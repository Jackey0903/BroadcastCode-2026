"""Optional managed speech and scene hints after independent delivery verification."""
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
from xml.sax.saxutils import escape

import handler as delivery

MAX_TEXT = 120
MAX_AUDIO_BYTES = 2 * 1024 * 1024
DECLARATION = "AI语音解读 · Amazon Polly"
SCENE_SCOPE = "Scene labels only; not player identity, tracking or basketball accuracy certification"
VERSION = "native-media-v2"
SPEECH_RATE = "140%"


def narration_text(plan):
    captions = [chapter.get("caption") for chapter in plan.get("chapters", [])]
    delivery.require(captions and all(isinstance(text, str) and text.strip() for text in captions),
                     "missing_captions", "Validated chapter captions are required")
    text = "。".join(caption.strip().rstrip("。") for caption in captions) + "。"
    metrics = plan.get("metrics", [])
    metric = metrics[0] if metrics else None
    if metric is not None:
        text += "官方出手机会参考，xFG为" + metric["display"] + "。"
    delivery.require(len(text) <= MAX_TEXT, "narration_too_long", "Speech exceeds the 120-character reading budget")
    return text, metric


def narration_segments(plan, duration):
    """Copy approved short phrases into source-time windows, never early cues."""
    chapters = plan.get("chapters", [])
    delivery.require(isinstance(chapters, list) and chapters, "missing_captions", "Validated chapters are required")
    metric = plan.get("metrics", [None])[0] if plan.get("metrics") else None
    reveal = metric.get("revealAt", 0) if metric else None
    if metric:
        delivery.require(delivery.number(reveal) and 0 <= reveal < duration,
                         "invalid_speech_timing", "Metric reveal must remain within the source timeline")
    segments = []
    for index, chapter in enumerate(chapters):
        start, end = chapter.get("start"), chapter.get("end")
        caption = chapter.get("caption")
        delivery.require(delivery.number(start) and delivery.number(end) and 0 <= start < end <= duration + .25
            and isinstance(caption, str) and caption.strip(), "invalid_speech_timing", "Chapter speech needs verified time bounds")
        # Plan bounds refer to source PTS; encoded output can differ by <=250 ms.
        # Bound the available window, then measure speech against it; never cut audio.
        end = min(end, duration)
        delivery.require(start < end, "invalid_speech_timing", "Speech must begin before the output ends")
        # The final results/data stage can have only seconds available. Prefer a
        # separate late metric cue rather than overlapping result and metric.
        if metric and index == len(chapters) - 1 and start <= reveal < end:
            continue
        first_sentence = re.split(r"[。！？；]", caption.strip(), maxsplit=1)[0]
        first_clause = first_sentence.split("，", 1)[0]
        phrase = first_clause if len(first_clause) >= 4 else first_sentence
        delivery.require(0 < len(phrase) <= MAX_TEXT, "narration_too_long", "Approved speech phrase is too long")
        segments.append({"kind": "chapter", "chapterIndex": index, "start": start, "end": end, "text": phrase + "。"})
    if metric:
        segments.append({"kind": "official_metric", "start": reveal, "end": duration,
                         "text": "官方机会参考，" + metric["display"] + "。"})
    segments.sort(key=lambda segment: segment["start"])
    for index, segment in enumerate(segments[:-1]):
        segment["end"] = min(segment["end"], segments[index + 1]["start"])
        delivery.require(segment["start"] < segment["end"], "invalid_speech_timing", "Speech cue windows overlap")
    delivery.require(sum(len(item["text"]) for item in segments) <= MAX_TEXT,
                     "narration_too_long", "Speech exceeds the total 120-character budget")
    return segments, metric


def compose_audio(clips, output, duration, budget):
    """Place already duration-checked clips on silence without cutting speech."""
    command = [os.environ.get("FFMPEG_PATH", "/opt/bin/ffmpeg"), "-v", "error", "-xerror", "-nostdin", "-y",
               "-f", "lavfi", "-t", str(duration), "-i", "anullsrc=channel_layout=stereo:sample_rate=24000"]
    filters, labels = [], ["[0:a]"]
    for index, (path, segment) in enumerate(clips, 1):
        command.extend(["-i", str(path)])
        label = f"speech{index}"
        delay = round(segment['start'] * 1000)
        # The audited Layer uses FFmpeg 4.1: no adelay all or amix normalize.
        # Stereo plus silent padding keeps every mixer input live to the end,
        # so legacy normalization is constant and volume can restore it exactly.
        filters.append(f"[{index}:a]aformat=channel_layouts=stereo,adelay={delay}|{delay},"
                       f"apad=pad_len={math.ceil(duration * 24000)}[{label}]")
        labels.append(f"[{label}]")
    filters.append("".join(labels) + f"amix=inputs={len(labels)}:duration=first:dropout_transition=0,volume={len(labels)}[timeline]")
    command.extend(["-filter_complex", ";".join(filters), "-map", "[timeline]", "-c:a", "libmp3lame",
                    "-b:a", "128k", str(output)])
    subprocess.run(command, capture_output=True, check=True, timeout=budget.seconds(20))


def probe_audio(path, budget):
    result = subprocess.run([os.environ.get("FFPROBE_PATH", "/opt/bin/ffprobe"), "-v", "error",
        "-show_entries", "format=duration:stream=codec_type,codec_name", "-of", "json", str(path)],
        capture_output=True, check=True, timeout=budget.seconds(12))
    value = json.loads(result.stdout)
    duration = float(value.get("format", {}).get("duration", "nan"))
    delivery.require(math.isfinite(duration) and duration > 0 and len(value.get("streams", [])) == 1
        and value["streams"][0].get("codec_type") == "audio"
        and value["streams"][0].get("codec_name") == "mp3", "invalid_speech", "Polly output is not a bounded MP3")
    return duration


def mix_video(source, audio, output, budget):
    font = os.environ.get("FONT_PATH", "/opt/fonts/NotoSansCJKsc-Regular.otf")
    delivery.require(Path(font).is_file(), "missing_font", "Permanent speech declaration requires the CJK font")
    declaration = output.parent / "ai-speech.txt"
    declaration.write_text(DECLARATION, encoding="utf-8")
    filters = (f"[0:v:0]drawtext=fontfile={font}:textfile={declaration}:expansion=none:"
               "fontcolor=0xaeb4c0:fontsize=12:x=28:y=51[declared];"
               "[0:a:0]volume=0.22[ambient];"
               "[ambient][1:a:0]amix=inputs=2:duration=first:dropout_transition=0,volume=2[mixed]")
    # The first/default track is speech with quiet ambient sound. Every original
    # AAC track is copied separately; no -shortest, time cut, or speech truncation.
    subprocess.run([os.environ.get("FFMPEG_PATH", "/opt/bin/ffmpeg"), "-v", "error", "-xerror",
        "-nostdin", "-y", "-i", str(source), "-i", str(audio), "-filter_complex", filters,
        "-map", "[declared]", "-map", "[mixed]", "-map", "0:a", "-c:v", "libx264",
        "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", "-threads", "2",
        "-c:a", "copy", "-c:a:0", "aac", "-b:a:0", "128k",
        "-metadata:s:a:0", "title=AI speech and original ambience",
        "-metadata:s:a:1", "title=Original audio", "-disposition:a:0", "default",
        "-disposition:a:1", "0", "-movflags", "+faststart", str(output)],
        capture_output=True, check=True, timeout=budget.seconds(60))


def scene_hints(registry, sample, config, rekognition):
    try:
        frames = registry[sample].get("frames", [])
        delivery.require(bool(frames), "missing_registered_frame", "Scene hints require a registered input frame")
        key = delivery.same_bucket_key(frames[0].get("s3_uri"), config)
        result = rekognition.detect_labels(Image={"S3Object": {"Bucket": config.bucket, "Name": key}},
                                           MaxLabels=8, MinConfidence=70)
        return {"available": True, "frame": frames[0]["s3_uri"], "labels": result.get("Labels", []),
                "scope": SCENE_SCOPE, "service": "Amazon Rekognition"}
    except Exception as error:
        return {"available": False, "errorType": type(error).__name__, "scope": SCENE_SCOPE,
                "service": "Amazon Rekognition"}


def put_artifact(s3, config, key, body, content_type, immutable=True):
    digest = hashlib.sha256(body).hexdigest()
    s3.put_object(Bucket=config.bucket, Key=key, Body=body, ContentType=content_type,
        ContentLength=len(body), ChecksumSHA256=base64.b64encode(bytes.fromhex(digest)).decode(),
        Metadata={"sha256": digest}, ServerSideEncryption="AES256",
        CacheControl="public, max-age=31536000, immutable" if immutable else "no-store")
    return digest


def reuse_verified_artifacts(s3, config, prefix, analysis, job, budget):
    """Replays reuse only receipts and actual same-hash derivative bytes."""
    try:
        receipt, _, _ = delivery.read_json(s3, config, prefix + "/narration.json", budget)
    except Exception as error:
        if getattr(error, "response", {}).get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
            return None
        raise
    if receipt.get("available") is not True or receipt.get("version") != VERSION:
        return None
    delivery.require(receipt.get("version") == VERSION and receipt.get("jobId") == job["id"]
        and receipt.get("runtimeArn") == config.runtime and receipt.get("modelId") == config.model
        and receipt.get("originalOutputSha256") == job["outputSha256"]
        and receipt.get("analysisFingerprint") == delivery.fingerprint(analysis)
        and receipt.get("media", {}).get("fullDecodeVerified") is True,
        "cached_narration_mismatch", "Existing speech does not belong to this verified snapshot")
    for kind, name, maximum in (("audio", "narration.mp3", MAX_AUDIO_BYTES),
                                 ("video", "narrated.mp4", delivery.MAX_VIDEO_BYTES)):
        key, expected = prefix + "/" + name, receipt.get(kind + "Sha256")
        delivery.require(receipt.get(kind + "Url") == f"https://{config.host}/{key}"
            and isinstance(expected, str) and delivery.SHA256.fullmatch(expected),
            "cached_narration_mismatch", "Derivative URL or hash is invalid")
        head = s3.head_object(Bucket=config.bucket, Key=key)
        delivery.require(head.get("Metadata", {}).get("sha256") == expected
            and head.get("ContentLength") == receipt.get(kind + "Bytes")
            and 0 < head["ContentLength"] <= maximum,
            "cached_narration_mismatch", "Derivative S3 metadata differs from its receipt")
        response = s3.get_object(Bucket=config.bucket, Key=key)
        stream, digest, total = response["Body"], hashlib.sha256(), 0
        try:
            while chunk := stream.read(1024 * 1024):
                budget.seconds(1)
                total += len(chunk)
                delivery.require(total <= maximum, "artifact_too_large", "Cached derivative exceeds its limit")
                digest.update(chunk)
        finally:
            stream.close()
        delivery.require(total == head["ContentLength"] and digest.hexdigest() == expected,
                         "cached_narration_mismatch", "Actual derivative SHA-256 differs from its receipt")
    return {**receipt, "idempotent": True}


def produce_native_media(event, s3, table, polly, rekognition, config, context=None,
                         audio_probe=probe_audio, mixer=mix_video, inspector=delivery.inspect_and_decode,
                         audio_composer=compose_audio):
    """Clients and local media functions are injected; no new model inference."""
    budget, eligible, phase = delivery.Budget(context), False, "provenance"
    result = {"available": False, "version": VERSION, "scene": {"available": False, "scope": SCENE_SCOPE}}
    try:
        job_id = delivery.parse_job_id(event)
        result["jobId"] = job_id
        job = delivery.plain(table.get_item(Key={"id": job_id}, ConsistentRead=True).get("Item"))
        analysis, prefix = delivery.validate_job(job, job_id, config)
        receipt = job.get("deliveryVerification", {})
        delivery.require(receipt.get("verified") is True and receipt.get("version") == delivery.VERSION
            and receipt.get("outputSha256") == job["outputSha256"]
            and receipt.get("analysisFingerprint") == delivery.fingerprint(analysis),
            "delivery_not_verified", "Independent delivery verification must pass first")
        result.update(originalVideoUrl=job["videoUrl"], originalOutputSha256=job["outputSha256"],
                      runtimeArn=config.runtime, modelId=config.model, declaration=DECLARATION,
                      analysisFingerprint=delivery.fingerprint(analysis))
        registry, _, _ = delivery.read_json(s3, config, "product/config/samples.json", budget)
        stories, _, _ = delivery.read_json(s3, config, "product/data/stories.json", budget)
        delivery.validate_sources(analysis, registry, stories, config)
        artifact, _, _ = delivery.read_json(s3, config, prefix + "/analysis.json", budget)
        delivery.require({key: value for key, value in artifact.items() if key != "publication"} == analysis,
                         "analysis_mismatch", "Stored analysis differs from the verified task")
        with tempfile.TemporaryDirectory(prefix="native-media-", dir="/tmp") as directory:
            source, audio, output = (Path(directory) / name for name in ("enhanced.mp4", "narration.mp3", "narrated.mp4"))
            delivery.download_output(s3, config, prefix + "/enhanced.mp4", source, analysis["outputVideo"], budget)
            cached = reuse_verified_artifacts(s3, config, prefix, analysis, job, budget)
            if cached:
                return cached
            eligible = True
            result["scene"] = scene_hints(registry, job["sample"], config, rekognition)
            original_seconds = min(analysis["sourceVideo"]["duration_ms"], analysis["outputVideo"]["durationMs"]) / 1000
            segments, metric = narration_segments(analysis["plan"], original_seconds)
            clips = []
            for index, segment in enumerate(segments):
                phase = "polly_segment_" + str(index)
                ssml = '<speak><prosody rate="' + SPEECH_RATE + '">' + escape(segment["text"]) + '</prosody></speak>'
                response = polly.synthesize_speech(Engine="standard", VoiceId="Zhiyu", TextType="ssml",
                                                  Text=ssml, OutputFormat="mp3", SampleRate="24000")
                stream = response["AudioStream"]
                try:
                    speech = stream.read(MAX_AUDIO_BYTES + 1)
                finally:
                    stream.close()
                delivery.require(0 < len(speech) <= MAX_AUDIO_BYTES, "invalid_speech", "Polly segment is empty or oversized")
                clip = Path(directory) / f"speech-{index}.mp3"
                clip.write_bytes(speech)
                phase = "probe_segment_" + str(index)
                clip_seconds = audio_probe(clip, budget)
                delivery.require(math.isfinite(clip_seconds) and 0 < clip_seconds <= segment["end"] - segment["start"],
                    "speech_exceeds_window", "Speech exceeds its approved source-time window; no truncation is allowed")
                segment["audioDurationSeconds"] = clip_seconds
                clips.append((clip, segment))
            phase = "compose_speech"
            audio_composer(clips, audio, original_seconds, budget)
            phase = "probe_composed_speech"
            duration = audio_probe(audio, budget)
            delivery.require(math.isfinite(duration) and 0 < duration <= original_seconds + .25,
                             "speech_exceeds_video", "Composed speech exceeds the complete timeline")
            speech = audio.read_bytes()
            delivery.require(0 < len(speech) <= MAX_AUDIO_BYTES, "invalid_speech", "Composed MP3 exceeds its delivery budget")
            phase = "mix_video"
            mixer(source, audio, output, budget)
            phase = "decode_narrated_video"
            media = inspector(output, budget)
            expected = analysis["outputVideo"]
            delivery.require(media.get("fullDecodeVerified") is True
                and abs(media["durationMs"] - expected["durationMs"]) <= 250
                and (media["width"], media["height"]) == (expected["width"], expected["height"])
                and media["audioStreams"] == expected["audioStreams"] + 1,
                "narrated_media_mismatch", "Narrated output must retain the complete timeline and original audio tracks")
            video = output.read_bytes()
            delivery.require(0 < len(video) <= delivery.MAX_VIDEO_BYTES, "artifact_too_large", "Narrated output exceeds 50 MiB")
            audio_sha = put_artifact(s3, config, prefix + "/narration.mp3", speech, "audio/mpeg")
            video_sha = put_artifact(s3, config, prefix + "/narrated.mp4", video, "video/mp4")
            result.update(available=True, text="".join(item["text"] for item in segments), segments=segments,
                officialMetric=metric, engine="standard", voice="Zhiyu",
                speechRate=SPEECH_RATE, audioDurationSeconds=duration, media=media, audioSha256=audio_sha,
                videoSha256=video_sha, audioBytes=len(speech), videoBytes=len(video),
                audioUrl=f"https://{config.host}/{prefix}/narration.mp3",
                videoUrl=f"https://{config.host}/{prefix}/narrated.mp4")
    except Exception as error:
        result.update(available=False, code=error.code if isinstance(error, delivery.Rejected) else "native_media_unavailable",
                      errorType=type(error).__name__, phase=phase)
        if isinstance(error, subprocess.CalledProcessError):
            result["mediaCommandExitCode"] = error.returncode
            stderr = error.stderr or b""
            diagnostic = stderr.decode("utf-8", errors="replace") if isinstance(stderr, bytes) else str(stderr)
            # Private logs contain only bounded local media diagnostics, never
            # request bodies, credentials, model prompts or SDK exceptions.
            print(json.dumps({"event":"native_media_command_failed", "jobId":result.get("jobId"),
                "phase":phase, "exitCode":error.returncode, "stderr":diagnostic[-1200:]}),flush=True)
    if eligible:
        result["createdAt"] = int(time.time())
        try:
            put_artifact(s3, config, prefix + "/narration.json",
                json.dumps(result, ensure_ascii=False, allow_nan=False).encode(), "application/json", immutable=False)
        except Exception as error:
            result.update(available=False, code="native_receipt_not_saved", errorType=type(error).__name__)
    return result


def handler(event, context):
    import boto3
    from botocore.config import Config as SDKConfig
    sdk = SDKConfig(connect_timeout=5, read_timeout=15, retries={"max_attempts": 1})
    clients = {name: boto3.client(name, config=sdk) for name in ("s3", "polly", "rekognition")}
    table = boto3.resource("dynamodb", config=sdk).Table(os.environ["TABLE"])
    return produce_native_media(event, clients["s3"], table, clients["polly"], clients["rekognition"],
                                delivery.Config.from_environment(), context)
