#!/usr/bin/env python3
"""Read-only, bounded snapshot of known RL jobs; safe while training is running."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json

import boto3
from botocore.config import Config

from write_evidence import BUCKET, HERE, PROFILE, REGION, RUNS, lines


def main():
    session = boto3.Session(profile_name=PROFILE, region_name=REGION)
    config = Config(connect_timeout=10, read_timeout=20, retries={"max_attempts": 2})
    sm, s3 = session.client("sagemaker", config=config), session.client("s3", config=config)

    def read(job):
        try:
            state = sm.describe_training_job(TrainingJobName=job)
            metrics = lines(s3, f"rl-scout/checkpoints/{job}/metrics.jsonl")
            train = [r for r in metrics if r["kind"] == "train"]
            evaluations = [r for r in metrics if r["kind"] == "eval" or r["kind"].startswith("final_")]
            return {"job": job, "status": state["TrainingJobStatus"], "secondaryStatus": state["SecondaryStatus"],
                    "failure": state.get("FailureReason"), "instance": state["ResourceConfig"]["InstanceType"],
                    "start": str(state.get("TrainingStartTime")), "end": str(state.get("TrainingEndTime")),
                    "data": next((r for r in metrics if r["kind"] == "data"), None),
                    "lastStep": train[-1] if train else None, "evaluations": evaluations,
                    "lastEvent": metrics[-1] if metrics else None}
        except Exception as exc:
            return {"job": job, "readError": f"{type(exc).__name__}: {exc}"}

    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(read, RUNS))
    report = {"capturedAt": datetime.now().astimezone().isoformat(), "runs": rows}
    path = HERE / "results" / "training-status-latest.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n")
    for row in rows:
        step = row.get("lastStep") or {}
        print(json.dumps({k: row.get(k) for k in ("job", "status", "secondaryStatus", "failure", "readError")}
                         | {"step": step.get("step"), "validRate": step.get("validRate"),
                            "latestEval": (row.get("evaluations") or [None])[-1]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
