"""Offline recovery tests; no AWS SDK or cloud credentials are required."""

import copy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from replay_delivery import (ACCOUNT, DETAIL_TYPE, REGION, ROLE, SOURCE, RecoveryError,
                             main, replay_delivery, validate_outputs)

JOB_ID = "1" * 32
OUTPUTS = {"Account": ACCOUNT, "Region": REGION, "Table": "formal-jobs",
           "DeliveryEventBus": "formal-delivery", "Website": "https://test.cloudfront.net"}
IDENTITY = {"Account": ACCOUNT, "Arn": f"arn:aws:sts::{ACCOUNT}:assumed-role/{ROLE}/Team02"}


def completed_job():
    prefix = f"product/outputs/{JOB_ID}"
    return {"id": JOB_ID, "status": "completed", "mode": "story",
            "videoPath": prefix + "/enhanced.mp4", "videoUrl": OUTPUTS["Website"] + "/" + prefix + "/enhanced.mp4",
            "analysisUrl": OUTPUTS["Website"] + "/" + prefix + "/analysis.json", "outputSha256": "a" * 64,
            "analysis": {"realInference": True}, "deliveryVerification": {"status": "pending"}}


class FakeSts:
    def __init__(self, identity=None):
        self.identity, self.calls = identity if identity is not None else IDENTITY, 0

    def get_caller_identity(self):
        self.calls += 1
        return copy.deepcopy(self.identity)


class FakeTable:
    def __init__(self, item=None, receipt_error=None):
        self.item = copy.deepcopy(item if item is not None else completed_job())
        self.receipt_error, self.reads, self.writes = receipt_error, [], []

    def get_item(self, **kwargs):
        self.reads.append(kwargs)
        return {"Item": copy.deepcopy(self.item)}

    def update_item(self, **kwargs):
        self.writes.append(copy.deepcopy(kwargs))
        if self.receipt_error:
            raise self.receipt_error
        self.item["deliveryRecoveryEvent"] = copy.deepcopy(kwargs["ExpressionAttributeValues"][":receipt"])


class FakeEvents:
    def __init__(self, response=None, error=None):
        self.response = response if response is not None else {"FailedEntryCount": 0, "Entries": [{"EventId": "accepted-event"}]}
        self.error, self.calls = error, []

    def put_events(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        if self.error:
            raise self.error
        return self.response


class ReplayTests(unittest.TestCase):
    def test_default_dry_run_reads_only_and_never_publishes_or_changes_job(self):
        sts, table, events = FakeSts(), FakeTable(), FakeEvents()
        original = copy.deepcopy(table.item)
        receipt = replay_delivery(JOB_ID, OUTPUTS, sts, table, events)
        self.assertEqual(receipt["status"], "dry_run")
        self.assertFalse(receipt["execute"])
        self.assertEqual(sts.calls, 1)
        self.assertEqual(table.reads, [{"Key": {"id": JOB_ID}, "ConsistentRead": True}])
        self.assertEqual(events.calls, [])
        self.assertEqual(table.writes, [])
        self.assertEqual(table.item, original)

    def test_execute_publishes_only_job_reference_and_saves_independent_receipt(self):
        table, events = FakeTable(), FakeEvents()
        original = copy.deepcopy(table.item)
        receipt = replay_delivery(JOB_ID, OUTPUTS, FakeSts(), table, events, execute=True, clock=lambda: 123456)
        self.assertEqual(len(events.calls), 1)
        entry = events.calls[0]["Entries"][0]
        self.assertEqual(entry, {"EventBusName": "formal-delivery", "Source": SOURCE,
                               "DetailType": DETAIL_TYPE, "Detail": json.dumps({"jobId": JOB_ID}, separators=(",", ":"))})
        self.assertEqual(receipt["status"], "published")
        self.assertEqual(receipt["verification"], "pending")
        self.assertEqual(receipt["attemptedAt"], 123456)
        self.assertTrue(receipt["receiptPersisted"])
        self.assertTrue(table.item["deliveryRecoveryEvent"]["receiptPersisted"])
        self.assertEqual({k: v for k, v in table.item.items() if k != "deliveryRecoveryEvent"}, original)
        update = table.writes[0]
        self.assertEqual(update["UpdateExpression"], "SET #recovery = :receipt")
        self.assertIn("#status = :completed", update["ConditionExpression"])
        self.assertIn("#mode = :story", update["ConditionExpression"])

    def test_wrong_identity_aborts_before_job_read_or_event_write(self):
        identities = [
            {"Account": "962768510637", "Arn": IDENTITY["Arn"]},
            {"Account": ACCOUNT, "Arn": f"arn:aws:sts::{ACCOUNT}:assumed-role/Admin/Team02"},
            {"Account": ACCOUNT, "Arn": f"arn:aws:iam::{ACCOUNT}:user/NBAHackathonParticipantRole"},
        ]
        for identity in identities:
            with self.subTest(identity=identity):
                table, events = FakeTable(), FakeEvents()
                with self.assertRaises(RecoveryError):
                    replay_delivery(JOB_ID, OUTPUTS, FakeSts(identity), table, events, execute=True)
                self.assertEqual(table.reads, [])
                self.assertEqual(events.calls, [])

    def test_unsafe_or_missing_outputs_aborts_without_aws_reads(self):
        invalid = [{**OUTPUTS, "Account": "962768510637"}, {**OUTPUTS, "Region": "us-west-2"},
                   {**OUTPUTS, "DeliveryEventBus": None}, {**OUTPUTS, "Table": "../table"},
                   {**OUTPUTS, "DeliveryEventBus": f"arn:aws:events:us-east-1:962768510637:event-bus/wrong"},
                   {**OUTPUTS, "DeliveryEventBus": f"arn:aws:events:us-west-2:{ACCOUNT}:event-bus/wrong"},
                   {**OUTPUTS, "Website": None}]
        for outputs in invalid:
            with self.subTest(outputs=outputs):
                sts, table, events = FakeSts(), FakeTable(), FakeEvents()
                with self.assertRaises(RecoveryError):
                    replay_delivery(JOB_ID, outputs, sts, table, events, execute=True)
                self.assertEqual(sts.calls, 0)
                self.assertEqual(table.reads, [])
                self.assertEqual(events.calls, [])

    def test_local_bus_arn_is_accepted(self):
        outputs = {**OUTPUTS, "DeliveryEventBus": f"arn:aws:events:{REGION}:{ACCOUNT}:event-bus/formal-delivery"}
        self.assertEqual(validate_outputs(outputs)[1], outputs["DeliveryEventBus"])

    def test_invalid_ids_aborts_without_aws_reads(self):
        for job_id in ("", "a" * 31, "A" * 32, "../" + JOB_ID, True, None):
            with self.subTest(job_id=job_id):
                sts, table, events = FakeSts(), FakeTable(), FakeEvents()
                with self.assertRaises(RecoveryError):
                    replay_delivery(job_id, OUTPUTS, sts, table, events, execute=True)
                self.assertEqual(sts.calls, 0)
                self.assertEqual(table.reads, [])

    def test_missing_incomplete_nonstory_or_missing_artifacts_are_rejected(self):
        invalid = [{}, {**completed_job(), "status": "processing"}, {**completed_job(), "mode": "readiness"},
                   {**completed_job(), "id": "2" * 32}, {**completed_job(), "outputSha256": ""},
                   {**completed_job(), "videoPath": "another-output.mp4"},
                   {**completed_job(), "analysisUrl": "https://other.invalid/analysis.json"}]
        for item in invalid:
            with self.subTest(item=item):
                table, events = FakeTable(item), FakeEvents()
                with self.assertRaises(RecoveryError):
                    replay_delivery(JOB_ID, OUTPUTS, FakeSts(), table, events, execute=True)
                self.assertEqual(table.writes, [])
                self.assertEqual(events.calls, [])

    def test_http_200_entry_rejection_saves_local_receipt_without_changing_job(self):
        table, events = FakeTable(), FakeEvents(response={"FailedEntryCount": 1, "Entries": [{
            "ErrorCode": "ThrottlingException", "ErrorMessage": "sensitive payload not recorded",
        }]})
        original = copy.deepcopy(table.item)
        with tempfile.TemporaryDirectory() as directory:
            receipt_file = Path(directory) / "recovery.json"
            with self.assertRaises(RecoveryError) as raised:
                replay_delivery(JOB_ID, OUTPUTS, FakeSts(), table, events, execute=True, receipt_file=receipt_file)
            receipt = json.loads(receipt_file.read_text())
            self.assertEqual(receipt["status"], "failed")
            self.assertEqual(receipt["awsErrorCode"], "ThrottlingException")
            self.assertEqual(raised.exception.receipt, receipt)
            self.assertNotIn("sensitive payload", receipt_file.read_text())
        self.assertEqual(table.item, original)
        self.assertEqual(table.writes, [])

    def test_transport_failure_is_unconfirmed_and_never_updates_job(self):
        table, events = FakeTable(), FakeEvents(error=RuntimeError("private failure payload"))
        original = copy.deepcopy(table.item)
        with self.assertRaises(RecoveryError) as raised:
            replay_delivery(JOB_ID, OUTPUTS, FakeSts(), table, events, execute=True)
        self.assertEqual(raised.exception.receipt["status"], "publication_unconfirmed")
        self.assertNotIn("private failure", json.dumps(raised.exception.receipt))
        self.assertEqual(len(events.calls), 1)
        self.assertEqual(table.writes, [])
        self.assertEqual(table.item, original)

    def test_receipt_write_failure_retains_accepted_event_and_original_job_fields(self):
        table, events = FakeTable(receipt_error=RuntimeError("storage unavailable")), FakeEvents()
        original = copy.deepcopy(table.item)
        with self.assertRaises(RecoveryError) as raised:
            replay_delivery(JOB_ID, OUTPUTS, FakeSts(), table, events, execute=True)
        receipt = raised.exception.receipt
        self.assertEqual(receipt["status"], "published")
        self.assertEqual(receipt["eventId"], "accepted-event")
        self.assertFalse(receipt["receiptPersisted"])
        self.assertEqual(table.item, original)
        self.assertEqual(len(events.calls), 1)

    def test_malformed_success_response_cannot_claim_an_event_was_published(self):
        for response in ({}, {"FailedEntryCount": 0, "Entries": []},
                         {"FailedEntryCount": 0, "Entries": [{"EventId": ""}]}):
            with self.subTest(response=response):
                table, events = FakeTable(), FakeEvents(response=response)
                with self.assertRaises(RecoveryError):
                    replay_delivery(JOB_ID, OUTPUTS, FakeSts(), table, events, execute=True)
                self.assertEqual(table.writes, [])

    def test_dry_run_can_save_an_explicit_nonverification_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "dry.json"
            replay_delivery(JOB_ID, OUTPUTS, FakeSts(), FakeTable(), receipt_file=file)
            receipt = json.loads(file.read_text())
            self.assertEqual(receipt["status"], "dry_run")
            self.assertEqual(receipt["verification"], "not_requested")

    def test_cli_rejects_bad_job_before_loading_sdk_or_deployment(self):
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["--job-id", "invalid"]), 1)
        self.assertEqual(json.loads(output.getvalue())["status"], "aborted")


if __name__ == "__main__":
    unittest.main()
