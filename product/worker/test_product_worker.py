"""Offline product worker tests with explicit fake AWS and media tools."""

import copy
import io
import json
from pathlib import Path
import sys
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
from test_story import BUCKET, FakeS3, execute, fixture
from handler import process_records, run_job, run_story_job
from delivery_events import EVENT_DETAIL_TYPE, EVENT_SOURCE, METRIC_NAMESPACE, SERVICE
from readiness_worker import JobError, validate_message

CONFIG = {"bucket": BUCKET, "runtime": "test-runtime", "host": "test.cloudfront.net"}


class FakeTable:
    def __init__(self):
        self.item = {"id": "job-1", "status": "queued"}

    def get_item(self, **kwargs):
        return {"Item": self.item.copy()}

    def update_item(self, **kwargs):
        for key, name in kwargs["ExpressionAttributeNames"].items():
            self.item[name] = kwargs["ExpressionAttributeValues"][":v" + key[2:]]


class FakeRuntime:
    def __init__(self, result=None, fail=False):
        self.result, self.fail, self.calls, self.stops = result, fail, 0, 0

    def invoke_agent_runtime(self, **kwargs):
        self.calls += 1
        if self.fail:
            raise RuntimeError("offline upstream failure")
        return {"response": io.BytesIO(json.dumps(self.result).encode())}

    def stop_runtime_session(self, **kwargs):
        self.stops += 1


class FakeEvents:
    def __init__(self, response=None, error=None, before_publish=None):
        self.response = response if response is not None else {"FailedEntryCount": 0, "Entries": [{"EventId": "event-1"}]}
        self.error, self.before_publish, self.calls = error, before_publish, []

    def put_events(self, **kwargs):
        self.calls.append(kwargs)
        if self.before_publish:
            self.before_publish()
        if self.error:
            raise self.error
        return self.response


def fake_renderer(source, output, result, context):
    output.write_bytes(b"offline-enhanced-video-fixture")


def fake_inspector(path, context):
    return {"durationMs": 22000, "width": 1280, "height": 900 if path.name == "enhanced.mp4" else 720, "audioStreams": 1}


class WorkerTests(unittest.TestCase):
    def run_case(self, result=None, inspector=fake_inspector, fail=False, s3=None, table=None,
                 config=None, events_client=None):
        request, _ = fixture()
        if result is None:
            result, _, _ = execute()
        s3, table, runtime = s3 or FakeS3(request), table or FakeTable(), FakeRuntime(result, fail)
        logs = io.StringIO()
        with redirect_stdout(logs):
            response = run_story_job({"jobId": "job-1", "sample": "flagg", "mode": "story"}, s3, table, runtime, config or CONFIG,
                                     renderer=fake_renderer, inspector=inspector, events_client=events_client)
        self.last_logs = [json.loads(line) for line in logs.getvalue().splitlines()]
        return response, s3, table, runtime

    def test_render_event_is_sent_only_after_durable_completion_without_claiming_verification(self):
        request, _ = fixture()
        s3, table = FakeS3(request), FakeTable()
        observed = []
        events = FakeEvents(before_publish=lambda: observed.append({
            "status": table.item["status"], "published": "product/outputs/job-1/analysis.json" in s3.objects,
        }))
        response, _, table, _ = self.run_case(s3=s3, table=table,
            config={**CONFIG, "deliveryEventBus": "test-delivery-bus"}, events_client=events)
        self.assertEqual(response["status"], "completed")
        self.assertEqual(observed, [{"status": "completed", "published": True}])
        entry = events.calls[0]["Entries"][0]
        self.assertEqual(entry["EventBusName"], "test-delivery-bus")
        self.assertEqual(entry["Source"], EVENT_SOURCE)
        self.assertEqual(entry["DetailType"], EVENT_DETAIL_TYPE)
        self.assertEqual(json.loads(entry["Detail"]), {"jobId": "job-1"})
        self.assertEqual(table.item["deliveryEvent"]["status"], "published")
        self.assertNotIn("deliveryVerification", table.item)
        self.assertNotIn("deliveryVerification", json.loads(s3.objects["product/outputs/job-1/analysis.json"]))
        metrics = [item for item in self.last_logs if "_aws" in item]
        self.assertTrue(any(item.get("JobCompleted") == 1 for item in metrics))
        self.assertTrue(any(item.get("DeliveryEventPublished") == 1 for item in metrics))
        for item in metrics:
            definition = item["_aws"]["CloudWatchMetrics"][0]
            self.assertEqual(definition["Namespace"], METRIC_NAMESPACE)
            self.assertEqual(definition["Dimensions"], [["Service"]])
            self.assertEqual(item["Service"], SERVICE)

    def test_eventbridge_http_success_with_failed_entry_keeps_render_completed(self):
        events = FakeEvents(response={"FailedEntryCount": 1, "Entries": [{
            "ErrorCode": "ThrottlingException", "ErrorMessage": "payload must never appear in logs",
        }]})
        response, s3, table, _ = self.run_case(config={**CONFIG, "deliveryEventBus": "test-bus"}, events_client=events)
        self.assertEqual(response["status"], "completed")
        self.assertEqual(table.item["status"], "completed")
        self.assertEqual(table.item["deliveryEvent"]["status"], "failed")
        self.assertEqual(table.item["deliveryEvent"]["awsErrorCode"], "ThrottlingException")
        self.assertIn("product/outputs/job-1/analysis.json", s3.objects)
        self.assertTrue(any(item.get("DeliveryEventPublishFailed") == 1 for item in self.last_logs))
        self.assertFalse(any(item.get("JobFailed") for item in self.last_logs))
        self.assertNotIn("payload must never", json.dumps(self.last_logs))

    def test_event_transport_error_is_a_recoverable_receipt_without_logging_exception_payload(self):
        events = FakeEvents(error=RuntimeError("sensitive upstream payload"))
        response, _, table, _ = self.run_case(config={**CONFIG, "deliveryEventBus": "test-bus"}, events_client=events)
        self.assertEqual(response["status"], "completed")
        self.assertEqual(table.item["deliveryEvent"]["errorType"], "RuntimeError")
        self.assertNotIn("sensitive upstream payload", json.dumps(self.last_logs))
        self.assertTrue(any(item.get("DeliveryEventPublishFailed") == 1 for item in self.last_logs))

    def test_receipt_storage_failure_does_not_undo_completed_render_or_reinfer(self):
        class ReceiptUnavailableTable(FakeTable):
            def update_item(self, **kwargs):
                if "deliveryEvent" in kwargs["ExpressionAttributeNames"].values():
                    raise RuntimeError("offline receipt write failure")
                return super().update_item(**kwargs)
        events = FakeEvents()
        response, _, table, runtime = self.run_case(table=ReceiptUnavailableTable(),
            config={**CONFIG, "deliveryEventBus": "test-bus"}, events_client=events)
        self.assertEqual(response["status"], "completed")
        self.assertEqual(table.item["status"], "completed")
        self.assertEqual(runtime.calls, 1)
        self.assertTrue(any(item.get("DeliveryEventRecordFailed") == 1 for item in self.last_logs))
        self.assertFalse(any(item.get("JobFailed") for item in self.last_logs))

    def test_terminal_redelivery_neither_republishes_nor_counts_a_second_render(self):
        events, table = FakeEvents(), FakeTable()
        table.item["status"] = "completed"
        response, _, _, runtime = self.run_case(table=table,
            config={**CONFIG, "deliveryEventBus": "test-bus"}, events_client=events)
        self.assertTrue(response["idempotent"])
        self.assertEqual(runtime.calls, 0)
        self.assertEqual(events.calls, [])
        self.assertEqual(self.last_logs, [])

    def test_business_failure_is_counted_without_a_rendered_event(self):
        events = FakeEvents()
        response, _, table, _ = self.run_case(fail=True,
            config={**CONFIG, "deliveryEventBus": "test-bus"}, events_client=events)
        self.assertEqual(response["status"], "failed")
        self.assertEqual(table.item["status"], "failed")
        self.assertEqual(events.calls, [])
        self.assertTrue(any(item.get("JobFailed") == 1 for item in self.last_logs))
        self.assertFalse(any(item.get("JobCompleted") for item in self.last_logs))

    def test_legacy_configuration_needs_no_eventbridge_client_or_notification_receipt(self):
        response, _, table, _ = self.run_case()
        self.assertEqual(response["status"], "completed")
        self.assertNotIn("deliveryEvent", table.item)
        self.assertTrue(any(item.get("JobCompleted") == 1 for item in self.last_logs))

    def test_malformed_eventbridge_response_cannot_claim_delivery_success(self):
        for response in ({}, {"FailedEntryCount": 0, "Entries": []},
                         {"FailedEntryCount": 0, "Entries": [{"EventId": ""}]}):
            with self.subTest(response=response):
                outcome, _, table, _ = self.run_case(config={**CONFIG, "deliveryEventBus": "test-bus"},
                    events_client=FakeEvents(response=response))
                self.assertEqual(outcome["status"], "completed")
                self.assertEqual(table.item["deliveryEvent"]["status"], "failed")
                self.assertFalse(any(item.get("DeliveryEventPublished") for item in self.last_logs))

    def test_story_uses_separate_inputs_preserves_provenance_and_publishes_full_video(self):
        response, s3, table, runtime = self.run_case()
        self.assertEqual(response["status"], "completed")
        self.assertIn("product/config/samples.json", s3.reads)
        self.assertNotIn("config/samples.json", s3.reads)
        analysis = json.loads(s3.objects["product/outputs/job-1/analysis.json"])
        self.assertTrue(analysis["preservesSourceTimeline"])
        self.assertEqual(analysis["outputVideo"]["height"], 900)
        self.assertEqual(analysis["plan"]["metrics"][0]["display"], "51.0%")
        self.assertEqual(analysis["officialEvent"]["eventId"], 666)
        self.assertEqual(analysis["evidence"][-1]["frameUrl"], "https://test.cloudfront.net/frames/15000.jpg")
        self.assertEqual(runtime.stops, 1)
        self.assertEqual(table.item["status"], "completed")

    def test_modified_official_metric_or_trace_is_rejected_before_render_upload(self):
        result, _, _ = execute()
        altered = copy.deepcopy(result); altered["plan"]["metrics"][0]["display"] = "99%"
        missing = copy.deepcopy(result); missing["trace"] = missing["trace"][:2]
        wrong = copy.deepcopy(result); wrong["trace"][0]["result"]["frames"][0]["source"] = "s3://elsewhere/image.jpg"
        same_round = copy.deepcopy(result); same_round["trace"][-1]["round"] = 1
        undelivered = copy.deepcopy(result); undelivered["trace"][0]["round"] = 2
        for bad in (altered, missing, wrong, same_round, undelivered):
            with self.subTest(result=bad):
                response, s3, table, _ = self.run_case(result=bad)
                self.assertEqual(response["status"], "failed")
                self.assertEqual(s3.uploads, [])
                self.assertEqual(table.item["status"], "failed")

    def test_upstream_error_is_failed_without_any_fake_success(self):
        response, s3, table, runtime = self.run_case(fail=True)
        self.assertEqual(response["status"], "failed")
        self.assertEqual(s3.uploads, [])
        self.assertEqual(runtime.stops, 1)

    def test_lost_audio_and_truncated_output_are_never_published(self):
        for broken in ({"audioStreams": 0}, {"durationMs": 5000}):
            def inspect(path, context):
                result = fake_inspector(path, context)
                if path.name == "enhanced.mp4":
                    result.update(broken)
                return result
            with self.subTest(broken=broken):
                response, s3, _, _ = self.run_case(inspector=inspect)
                self.assertEqual(response["status"], "failed")
                self.assertEqual(s3.uploads, [])

    def test_source_hash_error_prevents_model_spend(self):
        request, _ = fixture(); request["video"]["sha256"] = "0" * 64
        response, s3, _, runtime = self.run_case(s3=FakeS3(request))
        self.assertEqual(response["status"], "failed")
        self.assertEqual(runtime.calls, 0)
        self.assertEqual(s3.uploads, [])

    def test_readiness_mode_delegates_to_existing_pipeline(self):
        with patch("handler.legacy.run_job", return_value={"status": "legacy"}) as previous:
            result = run_job({"jobId": "job-1", "sample": "flagg"}, None, None, None, CONFIG)
        self.assertEqual(result["status"], "legacy")
        self.assertEqual(previous.call_count, 1)

    def test_sqs_retries_valid_message_when_both_read_and_terminal_write_fail(self):
        class UnavailableTable:
            def get_item(self, **kwargs):
                raise RuntimeError("offline read failure")
            def update_item(self, **kwargs):
                raise RuntimeError("offline write failure")
        event = {"Records": [{"messageId": "queue-1", "body": json.dumps({"jobId": "job-1", "sample": "flagg", "mode": "story"})}]}
        request, _ = fixture(); runtime = FakeRuntime()
        with redirect_stdout(io.StringIO()):
            response = process_records(event, None, FakeS3(request), UnavailableTable(), runtime, CONFIG)
        self.assertEqual(response, {"batchItemFailures": [{"itemIdentifier": "queue-1"}]})
        self.assertEqual(runtime.calls, 0)

    def test_persisted_business_failure_is_acknowledged_and_not_reinferred_on_redelivery(self):
        request, _ = fixture()
        event = {"Records": [{"messageId": "queue-1", "body": json.dumps({"jobId": "job-1", "sample": "flagg", "mode": "story"})}]}
        s3, table, runtime = FakeS3(request), FakeTable(), FakeRuntime(fail=True)
        def offline_job(message, s3, table, runtime, config, context):
            return run_story_job(message, s3, table, runtime, config, context, renderer=fake_renderer, inspector=fake_inspector)
        with patch("handler.run_job", side_effect=offline_job), redirect_stdout(io.StringIO()):
            first = process_records(event, None, s3, table, runtime, CONFIG)
            second = process_records(event, None, s3, table, runtime, CONFIG)
        self.assertEqual(first, {"batchItemFailures": []})
        self.assertEqual(second, {"batchItemFailures": []})
        self.assertEqual(table.item["status"], "failed")
        self.assertEqual(runtime.calls, 1)

    def test_queue_accepts_safe_registered_ids_but_never_urls_or_paths(self):
        for sample in ('flagg', 'amen', 'formal-play-1', 'a' * 60):
            self.assertEqual(validate_message({'jobId': 'job-1', 'sample': sample}), ('job-1', sample))
        for sample in ('', '../flagg', 'https://example.invalid/video.mp4', 's3://other/video.mp4',
                       '_budget', 'Flagg', 'FORMAL-PLAY', 'a' * 61, None, [], {}, True):
            with self.subTest(sample=sample), self.assertRaises(JobError):
                validate_message({'jobId': 'job-1', 'sample': sample})

    def test_new_registered_story_runs_through_the_same_validated_pipeline(self):
        request, plan = fixture()
        sample = 'formal-play-1'
        request['video']['id'] = request['story']['id'] = sample
        request['video']['s3_uri'] = f's3://{BUCKET}/samples/{sample}.mp4'
        result, _, _ = execute(request=request, plan=plan)

        class RegisteredS3(FakeS3):
            def get_object(self, **kwargs):
                if kwargs['Key'] == 'product/config/samples.json':
                    self.reads.append(kwargs['Key'])
                    entry = {key: request[key] for key in ('video', 'frames')}
                    return {'Body': io.BytesIO(json.dumps({sample: entry}).encode())}
                return super().get_object(**kwargs)

        s3, table, runtime = RegisteredS3(request), FakeTable(), FakeRuntime(result)
        with redirect_stdout(io.StringIO()):
            response = run_story_job({'jobId': 'job-1', 'sample': sample, 'mode': 'story'},
                                     s3, table, runtime, CONFIG, renderer=fake_renderer, inspector=fake_inspector)
        self.assertEqual(response['status'], 'completed')
        self.assertEqual(table.item['sample'], sample)
        self.assertEqual(runtime.calls, 1)
        self.assertEqual(json.loads(s3.objects['product/outputs/job-1/analysis.json'])['sample'], sample)

    def test_unregistered_safe_id_fails_before_model_or_media_publication(self):
        request, _ = fixture()
        s3, table, runtime = FakeS3(request), FakeTable(), FakeRuntime()
        with redirect_stdout(io.StringIO()):
            response = run_story_job({'jobId': 'job-1', 'sample': 'not-registered', 'mode': 'story'},
                                     s3, table, runtime, CONFIG, renderer=fake_renderer, inspector=fake_inspector)
        self.assertEqual(response['status'], 'failed')
        self.assertEqual(runtime.calls, 0)
        self.assertEqual(s3.uploads, [])

    def test_cross_bucket_registered_media_fails_before_model_spend(self):
        for field in ('video', 'frame'):
            request, _ = fixture()
            target = request['video'] if field == 'video' else request['frames'][0]
            target['s3_uri'] = 's3://unregistered-bucket/input.mp4'
            with self.subTest(field=field):
                response, s3, _, runtime = self.run_case(s3=FakeS3(request))
                self.assertEqual(response['status'], 'failed')
                self.assertEqual(runtime.calls, 0)
                self.assertEqual(s3.uploads, [])

    def test_readiness_worker_rejects_bad_registered_metadata_before_inference(self):
        bad_requests = []
        wrong_id, _ = fixture()
        wrong_id['video']['id'] = 'another-id'
        bad_requests.append(wrong_id)
        bool_duration, _ = fixture()
        bool_duration['video']['duration_ms'] = True
        bad_requests.append(bool_duration)
        duplicate_frames, _ = fixture()
        duplicate_frames['frames'] *= 2
        bad_requests.append(duplicate_frames)
        outside_frame, _ = fixture()
        outside_frame['frames'][0]['timestamp_ms'] = 23000
        bad_requests.append(outside_frame)
        external_frame, _ = fixture()
        external_frame['frames'][0]['s3_uri'] = 'https://example.invalid/frame.jpg'
        bad_requests.append(external_frame)
        for request in bad_requests:
            s3, table, runtime = FakeS3(request), FakeTable(), FakeRuntime()
            with self.subTest(request=request), redirect_stdout(io.StringIO()):
                response = run_job({'jobId': 'job-1', 'sample': 'flagg', 'mode': 'readiness'},
                                   s3, table, runtime, CONFIG, renderer=fake_renderer, inspector=fake_inspector)
            self.assertEqual(response['status'], 'failed')
            self.assertEqual(runtime.calls, 0)
            self.assertEqual(s3.uploads, [])


if __name__ == "__main__":
    unittest.main()
