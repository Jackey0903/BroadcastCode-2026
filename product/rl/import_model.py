#!/usr/bin/env python3
"""Import a merged RL-SCOUT model (Hugging Face safetensors in S3) into Amazon Bedrock.

    python3 product/rl/import_model.py --job rl-scout-main-... --name rl-scout-qwen25-3b-v1 --wait
Creates one tagged model-import job in the formal account; prints the imported model ARN.
"""
import argparse
import json
import time
from pathlib import Path

import boto3

HERE = Path(__file__).resolve().parent
ACCOUNT, REGION, PROFILE = "555726205424", "us-east-1", "nba"
BUCKET = "nba-hackathon-555726205424-team02"
ROLE = f"arn:aws:iam::{ACCOUNT}:role/NBAHackathonWorkloadRole"
TAGS = [{"key": "project", "value": "broadcastcode"}, {"key": "component", "value": "rl-scout"},
        {"key": "owner", "value": "claude"}]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--job", required=True, help="training job whose checkpoints/merged/ holds the model")
    p.add_argument("--name", required=True, help="imported model name")
    p.add_argument("--wait", action="store_true")
    a = p.parse_args()
    session = boto3.Session(profile_name=PROFILE, region_name=REGION)
    who = session.client("sts").get_caller_identity()
    if who["Account"] != ACCOUNT:
        raise SystemExit("Wrong account; aborting.")
    bedrock = session.client("bedrock")
    uri = f"s3://{BUCKET}/rl-scout/checkpoints/{a.job}/merged/"
    job_name = f"{a.name}-{time.strftime('%m%d-%H%M%S')}"
    created = bedrock.create_model_import_job(
        jobName=job_name, importedModelName=a.name, roleArn=ROLE,
        modelDataSource={"s3DataSource": {"s3Uri": uri}},
        jobTags=TAGS, importedModelTags=TAGS)
    record = {"jobName": job_name, "jobArn": created["jobArn"], "source": uri, "importedModelName": a.name}
    print(json.dumps(record, ensure_ascii=False), flush=True)
    while a.wait:
        job = bedrock.get_model_import_job(jobIdentifier=created["jobArn"])
        status = job["status"]
        print(time.strftime("%H:%M:%S"), status, job.get("failureMessage", ""), flush=True)
        if status in ("Completed", "Failed"):
            record.update(status=status, importedModelArn=job.get("importedModelArn"),
                          failureMessage=job.get("failureMessage"))
            break
        time.sleep(30)
    (HERE / "runs").mkdir(exist_ok=True)
    (HERE / "runs" / f"import-{job_name}.json").write_text(json.dumps(record, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
