#!/usr/bin/env python3
"""Read one locally registered evidence-training job; never launch or deploy."""
import argparse
from datetime import datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

HERE = Path(__file__).resolve().parent
ACCOUNT, REGION, PROFILE = "555726205424", "us-east-1", "nba"
BUCKET = "nba-hackathon-555726205424-team02"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", required=True)
    a = parser.parse_args()
    if not a.job.startswith("rl-scout-evidence-") or Path(a.job).name != a.job:
        raise SystemExit("Only registered evidence-training jobs are supported")
    run = json.loads((HERE / "runs" / f"{a.job}.json").read_text())
    if run.get("TrainingJobName") != a.job or not run.get("EvidenceInputs"):
        raise SystemExit("Missing local evidence-training registration")
    session = boto3.Session(profile_name=PROFILE, region_name=REGION)
    config = Config(connect_timeout=5, read_timeout=15, retries={"max_attempts": 1})
    sm, s3 = session.client("sagemaker", config=config), session.client("s3", config=config)
    state = sm.describe_training_job(TrainingJobName=a.job)
    if state["TrainingJobArn"] != f"arn:aws:sagemaker:{REGION}:{ACCOUNT}:training-job/{a.job}":
        raise SystemExit("Wrong formal AWS resource identity")

    def get(name):
        try:
            return s3.get_object(Bucket=BUCKET, Key=f"rl-scout/checkpoints/{a.job}/{name}",
                                 ExpectedBucketOwner=ACCOUNT)["Body"].read().decode()
        except ClientError as exc:
            if exc.response["Error"]["Code"] in {"NoSuchKey", "404"}:
                return None
            raise

    raw = get("metrics.jsonl")
    metrics = [json.loads(line) for line in (raw or "").splitlines() if line.strip()]
    report_raw = get("training-report.json")
    report = json.loads(report_raw) if report_raw else None
    result = {"capturedAt": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(), "job": a.job,
        "status": state["TrainingJobStatus"], "secondaryStatus": state["SecondaryStatus"],
        "failure": state.get("FailureReason"), "instance": state["ResourceConfig"]["InstanceType"],
        "trainingSeconds": state.get("TrainingTimeInSeconds"),
        "gpu": next((r for r in metrics if r["kind"] == "model_loaded"), None),
        "lastEvent": metrics[-1] if metrics else None,
        "evaluations": [r for r in metrics if r["kind"] == "evaluation"], "report": report,
        "modelDeployed": False}
    out = HERE / "results/evidence-v1"
    out.mkdir(parents=True, exist_ok=True)
    (out / "status-latest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    if state["TrainingJobStatus"] == "Completed" and report:
        (out / "training-report.json").write_text(report_raw)
        expected = run["EvidenceInputs"]["evaluationIds"]
        for stage in ("base", "sft", "rl"):
            for split in ("val", "test"):
                name = f"evaluation-{stage}-{split}.jsonl"
                content = get(name)
                if content is None:
                    raise ValueError("Missing completed evaluation: " + name)
                rows = [json.loads(line) for line in content.splitlines() if line.strip()]
                ids = [r["taskId"] for r in rows]
                # Incomplete runs must remain visible, never be scored as full evaluations.
                if report["evaluation"][stage][split]["complete"] and sorted(ids) != sorted(expected[split]):
                    raise ValueError("Evaluation IDs changed: " + name)
                if len(ids) != len(set(ids)):
                    raise ValueError("Duplicate evaluation IDs: " + name)
                (out / name).write_text(content)
    print(json.dumps({k: v for k, v in result.items() if k != "report"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
