"""Offline API boundary checks. AWS modules are replaced before handler import.

Run: python3 -m unittest discover -s product/api -p 'test_*.py' -v
These tests do not establish deployment, IAM, capacity, or video-playback success.
"""

import copy
import importlib.util
import io
import json
import os
from decimal import Decimal
from pathlib import Path
import types
import unittest
from unittest.mock import MagicMock, patch


class FakeClientError(Exception):
    """The response interface used by this handler, without loading an AWS SDK."""

    def __init__(self, code, operation="OfflineTest"):
        self.response = {"Error": {"Code": code, "Message": "offline test failure"}}
        self.operation_name = operation
        super().__init__(code)


class FakeBotoCoreError(Exception):
    """Represent transport errors without an installed or active SDK."""


def registered_entry(sample, duration=22000):
    return {'video': {'id': sample, 'name': f'{sample}.mp4',
                      's3_uri': f's3://offline-bucket/samples/{sample}.mp4', 'duration_ms': duration},
            'frames': [{'timestamp_ms': 1000, 'format': 'jpeg',
                        's3_uri': f's3://offline-bucket/frames/{sample}.jpg'}]}


def event(method, path, body=None):
    request = {"requestContext": {"http": {"method": method}}, "rawPath": path}
    if body is not None:
        request["body"] = body if isinstance(body, str) else json.dumps(body)
    return request


class HandlerBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.table = MagicMock(name="offline_dynamodb_table")
        self.s3 = MagicMock(name="offline_s3")
        self.sqs = MagicMock(name="offline_sqs")
        boto = types.ModuleType("boto3")
        boto.resource = MagicMock(return_value=types.SimpleNamespace(Table=lambda _: self.table))
        boto.client = MagicMock(side_effect=lambda name: {"s3": self.s3, "sqs": self.sqs}[name])
        botocore = types.ModuleType("botocore")
        exceptions = types.ModuleType("botocore.exceptions")
        exceptions.ClientError = FakeClientError
        exceptions.BotoCoreError = FakeBotoCoreError
        botocore.exceptions = exceptions
        modules = patch.dict("sys.modules", {"boto3": boto, "botocore": botocore, "botocore.exceptions": exceptions})
        environment = patch.dict(os.environ, {
            "TABLE": "offline-table", "BUCKET": "offline-bucket",
            "QUEUE_URL": "https://sqs.invalid/offline-queue",
            "RUNTIME_ARN": "arn:aws:bedrock-agentcore:us-east-1:000000000000:runtime/offline",
            "MAX_RUNS": "30",
        })
        modules.start()
        environment.start()
        self.addCleanup(modules.stop)
        self.addCleanup(environment.stop)
        spec = importlib.util.spec_from_file_location("readiness_api_under_test", Path(__file__).with_name("handler.py"))
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.set_manifest({'flagg': registered_entry('flagg'), 'amen': registered_entry('amen')})

    def invoke(self, request, expected_status):
        response = self.module.handler(request, None)
        self.assertEqual(response["statusCode"], expected_status)
        self.assertIn("application/json", response["headers"]["content-type"])
        self.assertEqual(response["headers"]["cache-control"], "no-store")
        return json.loads(response["body"])

    def set_manifest(self, value):
        raw = json.dumps(value).encode()
        self.s3.get_object.side_effect = lambda **kwargs: {"Body": io.BytesIO(raw)}

    def assert_no_work_started(self):
        self.table.update_item.assert_not_called()
        self.table.put_item.assert_not_called()
        self.sqs.send_message.assert_not_called()

    def test_invalid_samples_and_request_shapes_have_no_aws_writes(self):
        for payload in ({}, {"sample": "external-url"}, {"sample": "https://example.invalid/a.mp4"},
                        {"sample": "../amen"}, {"sample": "Flagg"}, {"sample": "a" * 61},
                        {"sample": None}, {"sample": []}, [], "null", "not-json"):
            with self.subTest(payload=payload):
                result = self.invoke(event("POST", "/api/jobs", payload), 400)
                self.assertIn("error", result)
        self.table.update_item.assert_not_called()
        self.table.put_item.assert_not_called()
        self.sqs.send_message.assert_not_called()

    def test_invalid_job_ids_do_not_read_dynamodb(self):
        for job_id in ("", "_budget", "a" * 31, "a" * 33, "A" * 32, "g" * 32, "%2f" * 11):
            with self.subTest(job_id=job_id):
                self.invoke(event("GET", f"/api/jobs/{job_id}"), 400)
        self.table.get_item.assert_not_called()

    def test_exhausted_budget_does_not_create_or_enqueue_a_job(self):
        self.table.update_item.side_effect = FakeClientError("ConditionalCheckFailedException", "UpdateItem")
        result = self.invoke(event("POST", "/api/jobs", {"sample": "amen"}), 429)
        self.assertIn("error", result)
        self.assertNotIn("jobId", result)
        self.table.put_item.assert_not_called()
        self.sqs.send_message.assert_not_called()

    def test_accepted_job_is_the_same_one_persisted_and_sent_to_worker(self):
        result = self.invoke(event("POST", "/api/jobs", {"sample": "flagg"}), 202)
        self.assertRegex(result["jobId"], r"^[0-9a-f]{32}$")
        self.assertEqual(result["status"], "queued")
        item = self.table.put_item.call_args.kwargs["Item"]
        message = json.loads(self.sqs.send_message.call_args.kwargs["MessageBody"])
        self.assertEqual((item["jobId"], item["sample"]), (result["jobId"], "flagg"))
        self.assertEqual(message, {"jobId": result["jobId"], "sample": "flagg", "mode": "readiness"})
        self.assertEqual(item["status"], "queued")

    def test_story_mode_is_persisted_and_sent_without_changing_sample_identity(self):
        result = self.invoke(event("POST", "/api/jobs", {"sample": "amen", "mode": "story"}), 202)
        item = self.table.put_item.call_args.kwargs["Item"]
        message = json.loads(self.sqs.send_message.call_args.kwargs["MessageBody"])
        self.assertEqual(item["mode"], "story")
        self.assertEqual(message, {"jobId": result["jobId"], "sample": "amen", "mode": "story"})

    def test_unsupported_modes_do_not_spend_budget(self):
        for mode in ("train", "story;run", None, [], {}):
            self.invoke(event("POST", "/api/jobs", {"sample": "amen", "mode": mode}), 400)
        self.table.update_item.assert_not_called()
        self.sqs.send_message.assert_not_called()

    def test_queue_failure_is_recoverable_and_does_not_leave_a_queued_orphan(self):
        self.sqs.send_message.side_effect = FakeClientError("ServiceUnavailable", "SendMessage")
        result = self.invoke(event("POST", "/api/jobs", {"sample": "flagg"}), 503)
        job_id = self.table.put_item.call_args.kwargs["Item"]["jobId"]
        # A user must be able to correlate the failure with the job already created.
        self.assertEqual(result.get("jobId"), job_id, "return the allocated job ID when queue submission fails")
        failed_update = any(
            call.kwargs.get("Key", {}).get("id") == job_id
            and "failed" in call.kwargs.get("ExpressionAttributeValues", {}).values()
            for call in self.table.update_item.call_args_list
        )
        removed = any(call.kwargs.get("Key", {}).get("id") == job_id for call in self.table.delete_item.call_args_list)
        self.assertTrue(failed_update or removed, "the persisted job must not remain queued after enqueue fails")

    def test_status_manifest_matches_frontend_sample_contract(self):
        self.set_manifest({
            'flagg': registered_entry('flagg', duration=21548),
            'amen': registered_entry('amen', duration=22895),
        })
        result = self.invoke(event("GET", "/api/status"), 200)
        self.assertEqual(result["status"], "ready")
        samples = {sample["id"]: sample for sample in result["samples"]}
        self.assertEqual(set(samples), {"flagg", "amen"})
        self.assertAlmostEqual(samples["flagg"]["durationSeconds"], 21.548)
        self.assertTrue(result["runtimeArn"])
        self.table.update_item.assert_not_called()
        self.sqs.send_message.assert_not_called()

    def test_missing_manifest_reports_not_ready_without_starting_work(self):
        self.s3.get_object.side_effect = FakeClientError("NoSuchKey", "GetObject")
        result = self.invoke(event("GET", "/api/status"), 503)
        self.assertIn("error", result)
        self.table.update_item.assert_not_called()
        self.sqs.send_message.assert_not_called()

    def test_bad_manifest_returns_json_unavailable_instead_of_crashing(self):
        for manifest in (b"not-json", b"null", b"[]", b'{"flagg": {}}'):
            with self.subTest(manifest=manifest):
                self.s3.get_object.side_effect = None
                self.s3.get_object.return_value = {"Body": io.BytesIO(manifest)}
                result = self.invoke(event("GET", "/api/status"), 503)
                self.assertIn("error", result)
        self.sqs.send_message.assert_not_called()

    def test_new_registered_case_can_be_queued_without_a_hardcoded_name(self):
        self.set_manifest({'formal-play-1': registered_entry('formal-play-1')})
        result = self.invoke(event('POST', '/api/jobs', {'sample': 'formal-play-1', 'mode': 'story'}), 202)
        self.s3.get_object.assert_called_once_with(Bucket='offline-bucket', Key='config/samples.json')
        message = json.loads(self.sqs.send_message.call_args.kwargs['MessageBody'])
        self.assertEqual(message, {'jobId': result['jobId'], 'sample': 'formal-play-1', 'mode': 'story'})
        self.assertEqual(self.table.put_item.call_args.kwargs['Item']['sample'], 'formal-play-1')

    def test_unknown_safe_id_does_not_spend_budget_or_enqueue(self):
        result = self.invoke(event('POST', '/api/jobs', {'sample': 'not-registered'}), 400)
        self.assertNotIn('jobId', result)
        self.assert_no_work_started()

    def test_registered_lowercase_id_can_reach_the_shared_60_character_limit(self):
        sample = 'a' * 60
        self.set_manifest({sample: registered_entry(sample)})
        self.invoke(event('POST', '/api/jobs', {'sample': sample, 'mode': 'story'}), 202)
        self.assertEqual(self.table.put_item.call_args.kwargs['Item']['sample'], sample)

    def test_registry_read_errors_do_not_spend_budget_or_enqueue(self):
        for error in (FakeClientError('NoSuchKey'), FakeClientError('AccessDenied'),
                      FakeBotoCoreError('offline connection failure'), OSError('offline stream failure')):
            with self.subTest(error=type(error).__name__):
                self.s3.get_object.side_effect = error
                result = self.invoke(event('POST', '/api/jobs', {'sample': 'flagg'}), 503)
                self.assertNotIn('jobId', result)
        self.assert_no_work_started()

    def test_malformed_registry_is_unavailable_before_any_write(self):
        valid = {'flagg': registered_entry('flagg')}
        wrong_identity = copy.deepcopy(valid)
        wrong_identity['flagg']['video']['id'] = 'amen'
        wrong_bucket = copy.deepcopy(valid)
        wrong_bucket['flagg']['video']['s3_uri'] = 's3://another-bucket/source.mp4'
        external_frame = copy.deepcopy(valid)
        external_frame['flagg']['frames'][0]['s3_uri'] = 'https://example.invalid/image.jpg'
        null_duration = copy.deepcopy(valid)
        null_duration['flagg']['video']['duration_ms'] = None
        bool_duration = copy.deepcopy(valid)
        bool_duration['flagg']['video']['duration_ms'] = True
        infinite_time = copy.deepcopy(valid)
        infinite_time['flagg']['frames'][0]['timestamp_ms'] = float('inf')
        duplicate_time = copy.deepcopy(valid)
        duplicate_time['flagg']['frames'] *= 2
        for manifest in ({}, [], None, {'../flagg': registered_entry('flagg')}, {'flagg': {}},
                         wrong_identity, wrong_bucket, external_frame, null_duration, bool_duration,
                         infinite_time, duplicate_time):
            with self.subTest(manifest=manifest):
                self.set_manifest(manifest)
                self.invoke(event('POST', '/api/jobs', {'sample': 'flagg'}), 503)
        self.assert_no_work_started()

    def test_registry_size_is_bounded_and_stream_is_closed(self):
        body = io.BytesIO(b' ' * (self.module.MAX_REGISTRY_BYTES + 1))
        self.s3.get_object.side_effect = None
        self.s3.get_object.return_value = {'Body': body}
        self.invoke(event('POST', '/api/jobs', {'sample': 'flagg'}), 503)
        self.assertTrue(body.closed)
        self.assert_no_work_started()

    def test_missing_job_is_distinct_from_transient_lookup_failure(self):
        job_id = "a" * 32
        self.table.get_item.return_value = {}
        self.invoke(event("GET", f"/api/jobs/{job_id}"), 404)
        self.table.get_item.side_effect = FakeClientError("ProvisionedThroughputExceededException", "GetItem")
        result = self.invoke(event("GET", f"/api/jobs/{job_id}"), 503)
        self.assertIn("error", result)

    def test_completed_job_keeps_analysis_media_and_decimal_times_for_frontend(self):
        job_id = "b" * 32
        self.table.get_item.return_value = {"Item": {
            "id": job_id, "jobId": job_id, "runId": job_id, "status": "completed", "stage": "completed",
            "videoUrl": "https://cdn.invalid/outputs/example/enhanced.mp4",
            "analysis": {"summary": "本次离线测试观察", "observations": [{"text": "测试文字", "timeSeconds": Decimal("17.5")}]},
            "evidence": [{"timeSeconds": Decimal("17.5"), "frameUrl": "https://cdn.invalid/frame.jpg"}],
            "preservesSourceTimeline": True,
        }}
        result = self.invoke(event("GET", f"/api/jobs/{job_id}"), 200)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["analysis"]["observations"][0]["timeSeconds"], 17.5)
        self.assertEqual(result["evidence"][0]["timeSeconds"], 17.5)
        self.assertTrue(result["videoUrl"].endswith(".mp4"))
        self.assertTrue(result["preservesSourceTimeline"])
        self.table.update_item.assert_not_called()
        self.sqs.send_message.assert_not_called()


if __name__ == "__main__":
    unittest.main()
