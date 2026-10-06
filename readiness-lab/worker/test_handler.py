"""Offline worker control-flow tests; they do not prove cloud or FFmpeg success."""

import hashlib
import io
import json
from pathlib import Path
import unittest

from handler import JobError, PROTOCOL, run_job, validate_message

BUCKET = "team02-readiness-test"
CONFIG = {"bucket": BUCKET, "runtime": "arn:aws:bedrock-agentcore:us-east-1:962768510637:runtime/test", "host": "test.cloudfront.net"}
VIDEO = b"offline fixture bytes, not an actual video"


class FakeS3:
    def __init__(self):
        self.samples = {"flagg": {
            "video": {"id": "clip-1", "name": "训练样片", "s3_uri": f"s3://{BUCKET}/inputs/clip.mp4", "duration_ms": 22000,
                      "sha256": hashlib.sha256(VIDEO).hexdigest(), "width": 1920, "height": 1080},
            "frames": [{"timestamp_ms": 15000, "s3_uri": f"s3://{BUCKET}/frames/15000.jpg", "format": "jpeg"}],
        }}
        self.uploads = []
        self.objects = {}

    def get_object(self, **kwargs):
        data = json.dumps(self.samples).encode() if kwargs["Key"] == "config/samples.json" else VIDEO
        return {"Body": io.BytesIO(data)}

    def upload_file(self, filename, bucket, key, **kwargs):
        self.uploads.append((bucket, key, Path(filename).read_bytes()))

    def put_object(self, **kwargs):
        self.objects[kwargs["Key"]] = kwargs["Body"]


class FakeTable:
    def __init__(self):
        self.item = {"id": "job-1", "status": "queued"}

    def get_item(self, **kwargs):
        return {"Item": self.item.copy()}

    def update_item(self, **kwargs):
        for key, name in kwargs["ExpressionAttributeNames"].items():
            self.item[name] = kwargs["ExpressionAttributeValues"][":v" + key[2:]]


class FakeAgent:
    def __init__(self, fail=False, stop_fail=False, wrong_time=False):
        self.fail, self.stop_fail, self.wrong_time = fail, stop_fail, wrong_time
        self.calls = self.stops = 0

    def invoke_agent_runtime(self, **kwargs):
        self.calls += 1
        if self.fail:
            raise RuntimeError("deliberate offline model failure")
        request = json.loads(kwargs["payload"])
        return {"response": io.BytesIO(json.dumps({
            "protocol_version": PROTOCOL, "request_id": request["request_id"], "video": request["video"], "status": "completed",
            "observation": "画面中可见白衣与深衣球员。", "subtitle": "观察球员相对位置",
            "source_frame_times_ms": [999 if self.wrong_time else 15000],
            "inference_source": "bedrock_converse", "model_id": "offline-fake-model", "usage": {"inputTokens": 99},
        }).encode())}

    def stop_runtime_session(self, **kwargs):
        self.stops += 1
        if self.stop_fail:
            raise RuntimeError("deliberate offline stop failure")


def fake_renderer(source, output, subtitle, context):
    assert "观察球员相对位置" in subtitle.read_text()
    assert source.read_bytes() == VIDEO
    output.write_bytes(b"offline rendered-video fixture")


def fake_inspector(path, context):
    return {"durationMs": 22000, "width": 1280, "height": 720}


class WorkerTests(unittest.TestCase):
    def run_case(self, agent=None, s3=None, inspector=fake_inspector):
        s3, table, agent = s3 or FakeS3(), FakeTable(), agent or FakeAgent()
        result = run_job({"jobId": "job-1", "sample": "flagg"}, s3, table, agent, CONFIG,
                         renderer=fake_renderer, inspector=inspector)
        return result, s3, table, agent

    def test_invalid_ids_and_unknown_sample(self):
        for message in ({"jobId": "../bad", "sample": "flagg"}, {"jobId": "job", "sample": "unknown"}, None):
            with self.assertRaises(JobError):
                validate_message(message)

    def test_success_records_provenance_duration_hash_and_publishes(self):
        result, s3, table, agent = self.run_case()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(agent.calls, 1)
        self.assertEqual(agent.stops, 1)
        self.assertEqual(len(s3.uploads), 1)
        analysis = json.loads(s3.objects["outputs/job-1/analysis.json"])
        self.assertEqual(analysis["observations"][0]["timeSeconds"], 15)
        self.assertTrue(analysis["preservesSourceTimeline"])
        self.assertEqual(analysis["evidence"][0]["frameUrl"], "https://test.cloudfront.net/frames/15000.jpg")
        self.assertEqual(analysis["outputVideo"]["durationMs"], 22000)
        self.assertEqual(analysis["sourceVideo"]["sha256"], hashlib.sha256(VIDEO).hexdigest())
        self.assertEqual(table.item["status"], "completed")

    def test_model_failure_marks_failed_and_never_uploads_fake_success(self):
        result, s3, table, agent = self.run_case(agent=FakeAgent(fail=True))
        self.assertEqual(result["status"], "failed")
        self.assertEqual(table.item["status"], "failed")
        self.assertEqual(s3.uploads, [])
        self.assertEqual(agent.stops, 1)

    def test_bad_source_hash_prevents_model_spend(self):
        s3 = FakeS3()
        s3.samples["flagg"]["video"]["sha256"] = "0" * 64
        result, s3, table, agent = self.run_case(s3=s3)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(agent.calls, 0)
        self.assertEqual(s3.uploads, [])

    def test_truncated_video_is_not_published(self):
        def short_video(path, context):
            return {"durationMs": 10000, "width": 1280, "height": 720}
        result, s3, table, agent = self.run_case(inspector=short_video)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(s3.uploads, [])

    def test_unavailable_evidence_time_is_rejected(self):
        result, s3, table, agent = self.run_case(agent=FakeAgent(wrong_time=True))
        self.assertEqual(result["status"], "failed")
        self.assertEqual(s3.uploads, [])

    def test_stop_error_does_not_replace_success(self):
        result, s3, table, agent = self.run_case(agent=FakeAgent(stop_fail=True))
        self.assertEqual(result["status"], "completed")
        self.assertEqual(table.item["status"], "completed")

    def test_completed_job_does_not_run_model_again(self):
        table, s3, agent = FakeTable(), FakeS3(), FakeAgent()
        table.item["status"] = "completed"
        result = run_job({"jobId": "job-1", "sample": "flagg"}, s3, table, agent, CONFIG)
        self.assertTrue(result["idempotent"])
        self.assertEqual(agent.calls, 0)


if __name__ == "__main__":
    unittest.main()
