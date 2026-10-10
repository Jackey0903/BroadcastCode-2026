"""Small, recoverable EventBridge notifications and low-cardinality EMF metrics.

A rendered video is already durable before this optional delivery notification.
Notification failure must never change that video's completed business state.
The independent delivery verifier owns ``deliveryVerification`` on the job.
"""

import json
import re
import time

METRIC_NAMESPACE = "BroadcastCode/Product"
SERVICE = "BroadcastCodeProduct"
EVENT_SOURCE = "broadcastcode.product"
EVENT_DETAIL_TYPE = "VideoRendered"


def emit_metrics(event, metrics, job_id=None, **fields):
    """Log AWS Embedded Metric Format; job IDs are log fields, never dimensions."""
    record = {
        "_aws": {
            "Timestamp": int(time.time() * 1000),
            "CloudWatchMetrics": [{
                "Namespace": METRIC_NAMESPACE,
                "Dimensions": [["Service"]],
                "Metrics": [{"Name": name, "Unit": "Count"} for name in metrics],
            }],
        },
        "Service": SERVICE,
        "event": event,
        **metrics,
        **fields,
    }
    if job_id is not None:
        record["jobId"] = job_id
    try:
        print(json.dumps(record, ensure_ascii=False, allow_nan=False), flush=True)
    except (OSError, ValueError, TypeError):
        # A closed log stream must not invalidate already durable media/jobs.
        pass


def emit_terminal_metric(job_id, status, **fields):
    """Count durable business outcomes independently of later delivery checks."""
    metric = {"completed": "JobCompleted", "failed": "JobFailed"}.get(status)
    if metric:
        emit_metrics("product_business_terminal", {metric: 1}, job_id, status=status, **fields)


def error_code(error):
    """Record the AWS error code, excluding exception messages and payloads."""
    response = getattr(error, "response", {})
    code = response.get("Error", {}).get("Code") if isinstance(response, dict) else None
    return code if isinstance(code, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", code) else None


def publish_video_rendered(job_id, events_client, bus_name):
    """Publish only a job reference; return an explicit receipt on every outcome.

    EventBridge can return HTTP 200 with a failed entry, so both the response
    failure count and the single entry are checked before counting success.
    """
    if not bus_name:
        return {"status": "disabled"}
    failed = {"status": "failed", "attemptedAt": int(time.time())}
    try:
        if events_client is None:
            raise RuntimeError("EventBridge client is unavailable")
        response = events_client.put_events(Entries=[{
            "EventBusName": bus_name,
            "Source": EVENT_SOURCE,
            "DetailType": EVENT_DETAIL_TYPE,
            "Detail": json.dumps({"jobId": job_id}, separators=(",", ":")),
        }])
        entries = response.get("Entries", []) if isinstance(response, dict) else []
        entry = entries[0] if len(entries) == 1 and isinstance(entries[0], dict) else {}
        if (response.get("FailedEntryCount") != 0 or entry.get("ErrorCode")
                or not isinstance(entry.get("EventId"), str) or not entry["EventId"]):
            code = entry.get("ErrorCode")
            failed["errorType"] = "EventBridgeEntryRejected"
            failed["awsErrorCode"] = code if isinstance(code, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", code) else None
        else:
            receipt = {"status": "published", "eventId": entry["EventId"], "attemptedAt": failed["attemptedAt"]}
            emit_metrics("delivery_event_published", {"DeliveryEventPublished": 1}, job_id, eventId=entry["EventId"])
            return receipt
    except Exception as error:
        failed.update(errorType=type(error).__name__, awsErrorCode=error_code(error))
    emit_metrics("delivery_event_publish_failed", {"DeliveryEventPublishFailed": 1}, job_id,
                 errorType=failed["errorType"], awsErrorCode=failed["awsErrorCode"])
    return failed
