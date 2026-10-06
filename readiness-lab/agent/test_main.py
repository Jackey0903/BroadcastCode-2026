"""Offline tests; fake AWS clients only. These are not cloud validation evidence."""

import copy
import io
import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from main import MODEL_ID, PROTOCOL, ModelOutputError, ReadinessAgent, ValidationError, make_server, parse_model_output, validate_request

BUCKET = "team02-readiness-test"


def request_fixture():
    return {
        "protocol_version": PROTOCOL, "request_id": "offline-001",
        "video": {"id": "clip-1", "name": "训练片段", "s3_uri": f"s3://{BUCKET}/clip.mp4", "duration_ms": 22000},
        "frames": [{"timestamp_ms": 15000, "s3_uri": f"s3://{BUCKET}/frame.jpg", "format": "jpeg"}],
    }


class FakeS3:
    def __init__(self):
        self.requests = []

    def get_object(self, **kwargs):
        self.requests.append(kwargs)
        return {"Body": io.BytesIO(b"\xff\xd8\xffoffline-test-only")}


class FakeBedrock:
    def __init__(self):
        self.requests = []

    def converse(self, **kwargs):
        self.requests.append(kwargs)
        return {"output": {"message": {"content": [{"text": json.dumps({
            "observation": "白衣球员前方可见深色球衣的防守球员。",
            "subtitle": "观察持球人与身前防守",
            "source_frame_times_ms": [15000],
        }, ensure_ascii=False)}]}}, "usage": {"inputTokens": 100, "outputTokens": 30}}


class ContractTests(unittest.TestCase):
    def test_input_rejects_cross_bucket_before_any_client_call(self):
        s3, model = FakeS3(), FakeBedrock()
        payload = request_fixture()
        payload["frames"][0]["s3_uri"] = "s3://unrelated-bucket/frame.jpg"
        with self.assertRaises(ValidationError):
            ReadinessAgent(BUCKET, s3, model).run(payload)
        self.assertEqual(s3.requests, [])
        self.assertEqual(model.requests, [])

    def test_input_rejects_out_of_range_duplicate_and_nonfinite_time(self):
        for timestamp in (-1, 22001, True, float("nan"), float("inf"), 10 ** 400):
            payload = request_fixture()
            payload["frames"][0]["timestamp_ms"] = timestamp
            with self.subTest(timestamp=timestamp), self.assertRaises(ValidationError):
                validate_request(payload, BUCKET)
        payload = request_fixture()
        payload["frames"].append(copy.deepcopy(payload["frames"][0]))
        with self.assertRaises(ValidationError):
            validate_request(payload, BUCKET)

    def test_inference_passes_actual_image_bytes_and_uses_model_reply(self):
        s3, model = FakeS3(), FakeBedrock()
        result = ReadinessAgent(BUCKET, s3, model).run(request_fixture())
        self.assertEqual(len(model.requests), 1)
        self.assertEqual(model.requests[0]["modelId"], MODEL_ID)
        images = [block["image"] for block in model.requests[0]["messages"][0]["content"] if "image" in block]
        self.assertEqual(images[0]["source"]["bytes"], b"\xff\xd8\xffoffline-test-only")
        self.assertEqual(result["subtitle"], "观察持球人与身前防守")
        self.assertEqual(result["source_frame_times_ms"], [15000])
        self.assertEqual(result["video"]["id"], "clip-1")

    def test_output_rejects_invented_source_time_and_metrics(self):
        for observation, times in (("可见防守球员", [999]), ("命中率为80%", [15000])):
            with self.subTest(observation=observation), self.assertRaises(ModelOutputError):
                parse_model_output(json.dumps({"observation": observation, "subtitle": "画面观察", "source_frame_times_ms": times}), {15000})

    def test_bad_image_never_reaches_model(self):
        class BadS3:
            def get_object(self, **kwargs):
                return {"Body": io.BytesIO(b"not a JPEG")}
        model = FakeBedrock()
        with self.assertRaises(ValidationError):
            ReadinessAgent(BUCKET, BadS3(), model).run(request_fixture())
        self.assertEqual(model.requests, [])

    def test_local_http_ping_validation_and_invocation(self):
        server = make_server(ReadinessAgent(BUCKET, FakeS3(), FakeBedrock()), "127.0.0.1", 0)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with urlopen(base + "/ping", timeout=3) as response:
                self.assertEqual(json.load(response), {"status": "Healthy"})
            invalid = Request(base + "/invocations", data=b"{}", headers={"Content-Type": "application/json"})
            with self.assertRaises(HTTPError) as context:
                urlopen(invalid, timeout=3)
            self.assertEqual(context.exception.code, 400)
            context.exception.close()
            valid = Request(base + "/invocations", data=json.dumps(request_fixture()).encode(), headers={"Content-Type": "application/json"})
            with urlopen(valid, timeout=3) as response:
                self.assertEqual(json.load(response)["status"], "completed")
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
