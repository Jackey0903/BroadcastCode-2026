"""Offline tests of real delivery boundaries, with no inference/network calls."""

import copy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import handler as delivery

JOB = "0123456789abcdef0123456789abcdef"
CONFIG = delivery.Config("delivery-test-bucket", "arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/test",
                         "global.anthropic.claude-sonnet-4-6", "example.cloudfront.net")
VIDEO = b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00isomiso2" + b"\x00\x00\x00\x10mdatpayload!"
PREFIX = f"product/outputs/{JOB}"


class MissingObject(Exception):
    response = {"Error": {"Code": "NoSuchKey"}}


class ChangedTask(Exception):
    response = {"Error": {"Code": "ConditionalCheckFailedException"}}


class FakeS3:
    def __init__(self, objects):
        self.objects = objects
        self.gets = []
        self.heads = []
        self.bodies = []

    def metadata(self, bucket, key):
        if bucket != CONFIG.bucket or key not in self.objects:
            raise MissingObject()
        value = self.objects[key]
        return {"ContentLength": len(value), "ETag": '"' + hashlib.md5(value).hexdigest() + '"',
                "LastModified": "2026-10-10 05:30:00+00:00"}

    def get_object(self, Bucket, Key):
        self.gets.append((Bucket, Key))
        response = self.metadata(Bucket, Key)
        body = io.BytesIO(self.objects[Key])
        self.bodies.append(body)
        return {**response, "Body": body}

    def head_object(self, Bucket, Key):
        self.heads.append((Bucket, Key))
        return self.metadata(Bucket, Key)


class FakeTable:
    def __init__(self, item):
        self.item = copy.deepcopy(item)
        self.updates = []

    def get_item(self, **kwargs):
        return {"Item": copy.deepcopy(self.item)} if self.item else {}

    def update_item(self, **kwargs):
        self.updates.append(kwargs)
        expected = kwargs["ExpressionAttributeValues"]
        if (self.item["status"] != expected[":completed"] or self.item["mode"] != expected[":story"]
                or self.item["outputSha256"] != expected[":hash"]
                or delivery.plain(self.item["analysis"]) != delivery.plain(expected[":analysis"])):
            raise ChangedTask()
        # Test records retain every original job field, as DynamoDB's SET does.
        self.item["deliveryVerification"] = copy.deepcopy(kwargs["ExpressionAttributeValues"][":receipt"])


def fixture():
    source = {"id": "flagg", "name": "practice.mp4", "duration_ms": 1000, "width": 1920, "height": 1080,
              "s3_uri": f"s3://{CONFIG.bucket}/samples/flagg.mp4", "sha256": "a" * 64}
    url = "https://api.nba.cn/shot?gameId=0022500701"
    identity = {"gameId": "0022500701", "eventId": 666, "playerId": "1642843"}
    official = {**identity, "verified": True, "expectedFg": 0.51, "made": True, "period": 4, "clock": "1:34"}
    metric = {**identity, "id": "xfg", "label": "xFG", "rawValue": 0.51, "unit": "ratio", "display": "51.0%",
              "evidenceId": "official-xfg", "sourceUrl": url, "revealAt": 0.5}
    story = {"id": "flagg", "sourceVideoSha256": source["sha256"], "durationSeconds": 1,
             "officialEvent": official, "shotMetric": metric,
             "evidence": [{**identity, "id": "official-xfg", "kind": "official_metric", "sourceUrl": url,
                           "value": 0.51, "unit": "ratio"}]}
    video_url = f"https://{CONFIG.host}/{PREFIX}/enhanced.mp4"
    analysis_url = f"https://{CONFIG.host}/{PREFIX}/analysis.json"
    analysis = {"protocol_version": "product-story-v1", "runId": JOB, "sample": "flagg", "mode": "story",
                "runtimeArn": CONFIG.runtime, "modelId": CONFIG.model,
                "inferenceSource": "bedrock_converse_tool_loop", "usage": {"inputTokens": 100, "outputTokens": 50},
                "validation": {"passed": True}, "preservesSourceTimeline": True,
                "videoUrl": video_url, "analysisUrl": analysis_url, "videoPath": f"{PREFIX}/enhanced.mp4",
                "sourceVideo": source, "officialEvent": official,
                "source": {"manifest": f"s3://{CONFIG.bucket}/product/data/stories.json", "sha256": "b" * 64},
                "plan": {"metrics": delivery.canonical_metrics(story)},
                "outputVideo": {"url": video_url, "sha256": hashlib.sha256(VIDEO).hexdigest(), "bytes": len(VIDEO),
                                "durationMs": 1024, "width": 1280, "height": 900, "audioStreams": 1}}
    job = {"id": JOB, "jobId": JOB, "runId": JOB, "status": "completed", "stage": "completed",
           "mode": "story", "sample": "flagg", "runtimeArn": CONFIG.runtime,
           "preservesSourceTimeline": True, "videoUrl": video_url, "analysisUrl": analysis_url,
           "videoPath": f"{PREFIX}/enhanced.mp4", "outputSha256": analysis["outputVideo"]["sha256"],
           "outputDurationMs": 1024, "analysis": analysis}
    objects = {f"{PREFIX}/enhanced.mp4": VIDEO, f"{PREFIX}/analysis.json": json.dumps(analysis).encode(),
               "product/config/samples.json": json.dumps({"flagg": {"video": source}}).encode(),
               "product/data/stories.json": json.dumps({"version": "delivery-test-v1", "stories": [story]}).encode()}
    return job, FakeS3(objects), FakeTable(job)


def media(path, budget):
    assert path.read_bytes() == VIDEO
    return {"durationMs": 1024, "width": 1280, "height": 900, "audioStreams": 1,
            "videoCodec": "h264", "audioCodec": "aac", "fullDecodeVerified": True}


class DeliveryBoundaries(unittest.TestCase):
    def verify(self, s3, table, event=None, inspector=media):
        return delivery.verify_delivery(event if event is not None else {"jobId": JOB}, s3, table,
                                        CONFIG, inspector=inspector)

    def test_completed_job_yields_independent_receipt_without_rewriting_analysis(self):
        original, s3, table = fixture()
        receipt = self.verify(s3, table)
        self.assertTrue(receipt["verified"])
        self.assertEqual(receipt["outputSha256"], original["outputSha256"])
        self.assertTrue(receipt["media"]["fullDecodeVerified"])
        self.assertEqual({key: table.item[key] for key in original}, original)
        self.assertEqual(len(table.updates), 1)
        self.assertTrue(all(body.closed for body in s3.bodies))

    def test_invalid_input_and_arbitrary_url_never_read_or_create_job(self):
        for event in ({}, None, [], {"jobId": "x"}, {"runId": "A" * 32},
                      {"jobId": JOB, "videoUrl": "https://attacker.example/video.mp4"},
                      {"jobId": JOB, "runId": "f" * 32}):
            with self.subTest(event=event):
                _, s3, table = fixture()
                result = delivery.verify_delivery(event, s3, table, CONFIG, inspector=media)
                self.assertFalse(result["verified"])
                self.assertEqual(result["code"], "invalid_input")
                self.assertFalse(s3.gets)
                self.assertFalse(table.updates)

    def test_missing_and_incomplete_jobs_do_not_create_failed_records(self):
        _, s3, table = fixture()
        table.item = None
        self.assertEqual(self.verify(s3, table)["code"], "job_not_found")
        self.assertFalse(table.updates)
        _, s3, table = fixture()
        table.item["status"] = "processing"
        self.assertEqual(self.verify(s3, table)["code"], "job_not_completed")
        self.assertEqual(table.item["status"], "processing")
        self.assertFalse(table.updates)

    def test_wrong_actual_hash_is_rejected_but_completed_status_is_preserved(self):
        _, s3, table = fixture()
        s3.objects[f"{PREFIX}/enhanced.mp4"] = VIDEO[:-1] + b"X"
        result = self.verify(s3, table)
        self.assertEqual(result["code"], "hash_mismatch")
        self.assertFalse(result["verified"])
        self.assertEqual(table.item["status"], "completed")
        self.assertFalse(table.item["deliveryVerification"]["verified"])

    def test_json_analysis_must_equal_persisted_analysis(self):
        _, s3, table = fixture()
        wrong = json.loads(s3.objects[f"{PREFIX}/analysis.json"])
        wrong["modelId"] = "pretend-model"
        s3.objects[f"{PREFIX}/analysis.json"] = json.dumps(wrong).encode()
        self.assertEqual(self.verify(s3, table)["code"], "analysis_mismatch")
        self.assertNotIn((CONFIG.bucket, f"{PREFIX}/enhanced.mp4"), s3.gets)

    def test_publication_wrapper_is_allowed_without_replacing_original_facts(self):
        _, s3, table = fixture()
        published = json.loads(s3.objects[f"{PREFIX}/analysis.json"])
        published["publication"] = {"kind": "verified-current-publication", "evidenceFile": "run-test.json"}
        s3.objects[f"{PREFIX}/analysis.json"] = json.dumps(published).encode()
        self.assertTrue(self.verify(s3, table)["verified"])
        published["officialEvent"]["expectedFg"] = 0.75
        s3.objects[f"{PREFIX}/analysis.json"] = json.dumps(published).encode()
        self.assertEqual(self.verify(s3, table)["code"], "analysis_mismatch")

    def test_cross_bucket_and_untrusted_output_paths_are_rejected(self):
        _, s3, table = fixture()
        table.item["analysis"]["sourceVideo"]["s3_uri"] = "s3://another-bucket/samples/flagg.mp4"
        self.assertEqual(self.verify(s3, table)["code"], "invalid_source")
        self.assertTrue(all(bucket == CONFIG.bucket for bucket, _ in s3.gets))
        _, s3, table = fixture()
        table.item["videoUrl"] = "https://attacker.example/enhanced.mp4"
        self.assertEqual(self.verify(s3, table)["code"], "invalid_output_path")
        self.assertFalse(s3.gets)

    def test_official_metric_cannot_be_substituted_with_season_percentage(self):
        _, s3, table = fixture()
        table.item["analysis"]["plan"]["metrics"][0]["rawValue"] = 0.75
        self.assertEqual(self.verify(s3, table)["code"], "official_data_mismatch")
        self.assertNotIn((CONFIG.bucket, f"{PREFIX}/enhanced.mp4"), s3.gets)

    def test_repeat_success_uses_stable_object_identity_and_skips_decoding(self):
        _, s3, table = fixture()
        first = self.verify(s3, table)
        initial_reads = len(s3.gets)
        with patch.object(delivery, "inspect_and_decode", side_effect=AssertionError("must not decode")):
            repeat = self.verify(s3, table, {"runId": JOB}, inspector=lambda *_: self.fail("decoded twice"))
        self.assertTrue(repeat["idempotent"])
        self.assertEqual(repeat["verifiedAt"], first["verifiedAt"])
        self.assertEqual(len(s3.gets) - initial_reads, 2)  # Current registry/evidence only.
        self.assertEqual(len(table.updates), 1)
        self.assertEqual(len(s3.heads), 2)

    def test_changed_output_invalidates_previous_success_receipt(self):
        _, s3, table = fixture()
        self.assertTrue(self.verify(s3, table)["verified"])
        s3.objects[f"{PREFIX}/enhanced.mp4"] = VIDEO[:-1] + b"X"
        result = self.verify(s3, table)
        self.assertEqual(result["code"], "hash_mismatch")
        self.assertFalse(table.item["deliveryVerification"]["verified"])

    def test_missing_s3_artifact_is_structured_and_does_not_change_job_status(self):
        _, s3, table = fixture()
        del s3.objects[f"{PREFIX}/enhanced.mp4"]
        result = self.verify(s3, table)
        self.assertEqual(result["code"], "artifact_not_found")
        self.assertEqual(table.item["status"], "completed")

    def test_truncated_media_or_missing_audio_cannot_pass_delivery(self):
        _, s3, table = fixture()
        self.assertEqual(self.verify(s3, table, inspector=lambda *_: {
            "durationMs": 500, "width": 1280, "height": 900, "audioStreams": 1})["code"], "media_mismatch")
        _, s3, table = fixture()
        self.assertEqual(self.verify(s3, table, inspector=lambda *_: {
            "durationMs": 1024, "width": 1280, "height": 900, "audioStreams": 0})["code"], "media_mismatch")

    def test_decode_failure_is_a_rejection_never_a_success_substitute(self):
        _, s3, table = fixture()
        def corrupt(*_):
            raise subprocess.CalledProcessError(1, ["ffmpeg"])
        result = self.verify(s3, table, inspector=corrupt)
        self.assertEqual(result["code"], "media_check_failed")
        self.assertFalse(result["verified"])

    def test_concurrent_analysis_change_cannot_receive_a_stale_success_receipt(self):
        _, s3, table = fixture()
        def changed_during_decode(path, budget):
            table.item["analysis"]["modelId"] = "other-model"
            return media(path, budget)
        result = self.verify(s3, table, inspector=changed_during_decode)
        self.assertEqual(result["code"], "job_changed")
        self.assertTrue(result["retryable"])
        self.assertNotIn("deliveryVerification", table.item)

    def test_stream_size_and_time_limits_are_enforced(self):
        _, s3, table = fixture()
        table.item["analysis"]["outputVideo"]["bytes"] = delivery.MAX_VIDEO_BYTES + 1
        self.assertEqual(self.verify(s3, table)["code"], "artifact_too_large")
        _, s3, table = fixture()
        class Expiring:
            def get_remaining_time_in_millis(self):
                return 1000
        result = delivery.verify_delivery({"jobId": JOB}, s3, table, CONFIG, context=Expiring(), inspector=media)
        self.assertEqual(result["code"], "verification_timeout")
        self.assertFalse(s3.gets)

    def test_probe_metadata_alone_cannot_claim_full_decode(self):
        probe = {"format": {"duration": "1.024"}, "streams": [
            {"codec_type": "video", "codec_name": "h264", "width": 1280, "height": 900},
            {"codec_type": "audio", "codec_name": "aac"}]}
        with patch.object(delivery.subprocess, "run", side_effect=[
                subprocess.CompletedProcess(["ffprobe"], 0, json.dumps(probe).encode(), b""),
                subprocess.CalledProcessError(1, ["ffmpeg"])]) as runner:
            with self.assertRaises(subprocess.CalledProcessError):
                delivery.inspect_and_decode(Path("/tmp/test.mp4"), delivery.Budget())
            self.assertEqual(runner.call_count, 2)


if __name__ == "__main__":
    unittest.main()
