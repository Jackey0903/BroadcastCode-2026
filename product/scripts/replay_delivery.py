#!/usr/bin/env python3
"""Replay a completed story's delivery notification, never its inference/render.

Default is a read-only dry run. Use --execute after reviewing the selected job.
The EventBridge event contains only the existing job ID. Delivery verification
is independent and is not claimed by this notification recovery script.
"""

import argparse
import json
from pathlib import Path
import re
import time

from deployment import load_outputs

ACCOUNT = "555726205424"
REGION = "us-east-1"
PROFILE = "nba"
ROLE = "NBAHackathonParticipantRole"
SOURCE = "broadcastcode.product"
DETAIL_TYPE = "VideoRendered"
DEFAULT_OUTPUTS = Path(__file__).resolve().parents[1] / "outputs.json"


class RecoveryError(ValueError):
    """A recovery was rejected or its outcome needs review; receipt is nonsecret."""

    def __init__(self, message, receipt=None):
        super().__init__(message)
        self.receipt = receipt


def validate_job_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{32}", value):
        raise RecoveryError("Job ID must be exactly 32 lowercase hexadecimal characters.")
    return value


def validate_outputs(outputs):
    if not isinstance(outputs, dict) or outputs.get("Account") != ACCOUNT or outputs.get("Region") != REGION:
        raise RecoveryError("Outputs must explicitly target formal account 555726205424 in us-east-1.")
    table, bus = outputs.get("Table"), outputs.get("DeliveryEventBus")
    if not isinstance(table, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{3,255}", table):
        raise RecoveryError("Outputs do not contain a valid Table name.")
    if not isinstance(bus, str) or not (
        re.fullmatch(r"[A-Za-z0-9_.-]{1,256}", bus)
        or re.fullmatch(rf"arn:aws:events:{REGION}:{ACCOUNT}:event-bus/[A-Za-z0-9_.-]{{1,256}}", bus)
    ):
        raise RecoveryError("Outputs do not contain a local DeliveryEventBus name or ARN.")
    website_value = outputs.get("Website")
    website = website_value.rstrip("/") if isinstance(website_value, str) else ""
    if not re.fullmatch(r"https://[a-z0-9.-]+\.cloudfront\.net", website):
        raise RecoveryError("Outputs do not contain a valid HTTPS CloudFront Website.")
    return table, bus, website


def validate_identity(identity):
    expected = rf"arn:aws:sts::{ACCOUNT}:assumed-role/{ROLE}/[^/]+"
    if (not isinstance(identity, dict) or identity.get("Account") != ACCOUNT
            or not re.fullmatch(expected, str(identity.get("Arn", "")))):
        raise RecoveryError("Wrong AWS account or participant role; recovery is aborted.")


def validate_completed_job(item, job_id, website):
    if (not isinstance(item, dict) or item.get("id") != job_id
            or item.get("status") != "completed" or item.get("mode") != "story"):
        raise RecoveryError("Only an existing completed story job may be replayed.")
    prefix = f"product/outputs/{job_id}"
    if (item.get("videoPath") != prefix + "/enhanced.mp4"
            or item.get("videoUrl") != f"{website}/{prefix}/enhanced.mp4"
            or item.get("analysisUrl") != f"{website}/{prefix}/analysis.json"
            or not re.fullmatch(r"[a-f0-9]{64}", str(item.get("outputSha256", "")))):
        raise RecoveryError("Completed job is missing its validated artifact references.")


def safe_error_code(error):
    response = getattr(error, "response", {})
    code = response.get("Error", {}).get("Code") if isinstance(response, dict) else None
    return code if isinstance(code, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", code) else None


def save_receipt(receipt, receipt_file):
    if receipt_file is not None:
        path = Path(receipt_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def replay_delivery(job_id, outputs, sts, table, events_client=None, *, execute=False,
                    receipt_file=None, clock=time.time):
    """Read-only by default; dependencies are injected for offline verification."""
    validate_job_id(job_id)
    table_name, bus_name, website = validate_outputs(outputs)
    validate_identity(sts.get_caller_identity())
    item = table.get_item(Key={"id": job_id}, ConsistentRead=True).get("Item")
    validate_completed_job(item, job_id, website)
    receipt = {"jobId": job_id, "account": ACCOUNT, "region": REGION, "table": table_name,
               "eventBus": bus_name, "source": SOURCE, "detailType": DETAIL_TYPE,
               "detail": {"jobId": job_id}, "status": "dry_run", "execute": execute,
               "verification": "not_requested", "receiptPersisted": False}
    if not execute:
        save_receipt(receipt, receipt_file)
        return receipt
    receipt.update(status="publication_unconfirmed", attemptedAt=int(clock()), verification="not_confirmed")
    try:
        if events_client is None:
            raise RecoveryError("EventBridge client is required for --execute.")
        response = events_client.put_events(Entries=[{
            "EventBusName": bus_name, "Source": SOURCE, "DetailType": DETAIL_TYPE,
            "Detail": json.dumps({"jobId": job_id}, separators=(",", ":")),
        }])
        entries = response.get("Entries", []) if isinstance(response, dict) else []
        entry = entries[0] if len(entries) == 1 and isinstance(entries[0], dict) else {}
        if (not isinstance(response, dict) or response.get("FailedEntryCount") != 0
                or entry.get("ErrorCode") or not isinstance(entry.get("EventId"), str) or not entry["EventId"]):
            code = entry.get("ErrorCode")
            receipt.update(status="failed", errorType="EventBridgeEntryRejected",
                awsErrorCode=code if isinstance(code, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", code) else None)
            raise RecoveryError("EventBridge did not accept the delivery event.", receipt)
    except Exception as error:
        if not isinstance(error, RecoveryError) or error.receipt is None:
            receipt.update(errorType=type(error).__name__, awsErrorCode=safe_error_code(error))
        save_receipt(receipt, receipt_file)
        raise RecoveryError("Publication was not confirmed; inspect the receipt before another replay. Original job is unchanged.", receipt) from error
    receipt.update(status="published", eventId=entry["EventId"], verification="pending")
    try:
        table.update_item(
            Key={"id": job_id},
            UpdateExpression="SET #recovery = :receipt",
            ConditionExpression="attribute_exists(#id) AND #status = :completed AND #mode = :story",
            ExpressionAttributeNames={"#recovery": "deliveryRecoveryEvent", "#id": "id", "#status": "status", "#mode": "mode"},
            ExpressionAttributeValues={":receipt": {**receipt, "receiptPersisted": True}, ":completed": "completed", ":story": "story"},
        )
    except Exception as error:
        receipt.update(receiptErrorType=type(error).__name__, receiptAwsErrorCode=safe_error_code(error))
        save_receipt(receipt, receipt_file)
        raise RecoveryError("Event was accepted, but its recovery receipt was not saved; inspect delivery verification before replaying again.", receipt) from error
    receipt["receiptPersisted"] = True
    save_receipt(receipt, receipt_file)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--profile", choices=[PROFILE], default=PROFILE)
    parser.add_argument("--outputs", type=Path, default=DEFAULT_OUTPUTS)
    parser.add_argument("--execute", action="store_true", help="Publish the notification; default performs only reads.")
    parser.add_argument("--receipt-file", type=Path, help="Optional local JSON recovery receipt.")
    args = parser.parse_args(argv)
    try:
        validate_job_id(args.job_id)
        outputs = load_outputs(args.outputs)
        table_name, _, _ = validate_outputs(outputs)
        import boto3
        from botocore.config import Config
        session = boto3.Session(profile_name=args.profile, region_name=REGION)
        client_config = Config(connect_timeout=5, read_timeout=15, retries={"total_max_attempts": 1})
        sts = session.client("sts", config=client_config)
        table = session.resource("dynamodb", config=client_config).Table(table_name)
        events_client = session.client("events", config=client_config) if args.execute else None
        receipt = replay_delivery(args.job_id, outputs, sts, table, events_client,
            execute=args.execute, receipt_file=args.receipt_file)
    except Exception as error:
        record = {"status": "aborted", "errorType": type(error).__name__, "awsErrorCode": safe_error_code(error),
                  "error": str(error) if isinstance(error, RecoveryError) else "Recovery aborted; inspect the error type and AWS error code."}
        if isinstance(error, RecoveryError) and error.receipt is not None:
            record["receipt"] = error.receipt
        print(json.dumps(record, ensure_ascii=False, allow_nan=False), flush=True)
        return 1
    print(json.dumps(receipt, ensure_ascii=False, allow_nan=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
