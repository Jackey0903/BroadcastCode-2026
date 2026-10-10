#!/usr/bin/env python3
"""Prepare one <=30-minute CPU merge job; only --execute creates it.

Source job, RL adapter, base revision and formal AWS account are fixed. Never
creates or changes an endpoint. Uses the same image previously exercised by the
team's CPU packaging job; the instance itself is ml.m5.2xlarge.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import tarfile

from package_evidence import SOURCE_JOB, BASE_MODEL, BASE_REVISION

HERE = Path(__file__).resolve().parent
ACCOUNT, REGION, PROFILE = "555726205424", "us-east-1", "nba"
BUCKET = "nba-hackathon-555726205424-team02"
ROLE = f"arn:aws:iam::{ACCOUNT}:role/NBAHackathonWorkloadRole"
IMAGE = "763104351884.dkr.ecr.us-east-1.amazonaws.com/pytorch-training:2.9.0-gpu-py312-cu130-ubuntu22.04-sagemaker"


def build():
    registered = json.loads((HERE / "runs" / f"{SOURCE_JOB}.json").read_text())
    report = json.loads((HERE / "results/evidence-v1/training-report.json").read_text())
    audit = json.loads((HERE / "results/evidence-v1/rl-update-audit-20261010.json").read_text())
    if (registered["TrainingJobName"] != SOURCE_JOB or report["sourceJob"] != SOURCE_JOB
            or report["baseRevision"] != BASE_REVISION or report["model"] != BASE_MODEL
            or audit["job"] != SOURCE_JOB or not audit["hasActualRLGradientUpdates"]):
        raise ValueError("Registered training identity/update evidence mismatch")
    for key in ("storeSha256", "tasksSha256"):
        if registered["EvidenceInputs"][key] != report[key]:
            raise ValueError("Training input hash mismatch")
    expected = {"sourceTrainingJob": SOURCE_JOB, "baseModel": BASE_MODEL, "baseRevision": BASE_REVISION,
                "selectedStage": "rl", "storeSha256": report["storeSha256"], "tasksSha256": report["tasksSha256"],
                "sourceArchiveSha256": registered["CodeArchiveSha256"],
                "optimizerUpdateSteps": audit["optimizerUpdateSteps"], "updateGroups": audit["updateGroupsTotal"]}
    files = {name: (HERE / name).read_bytes() for name in (
        "package_evidence.py", "serve_evidence/inference.py", "serve_evidence/requirements.txt")}
    files["requirements.txt"] = (HERE / "requirements_package_evidence.txt").read_bytes()
    files["expected-source.json"] = json.dumps(expected, ensure_ascii=False, indent=2).encode()
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for name, data in sorted(files.items()):
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(data), 0o644, 0
            tar.addfile(info, io.BytesIO(data))
    return expected, buffer.getvalue()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--execute", action="store_true")
    a = p.parse_args()
    expected, archive = build()
    job = "rl-scout-pkg-evidence-rl-" + datetime.now(timezone.utc).strftime("%m%d-%H%M%S")
    key = f"rl-scout/code/{job}/sourcedir.tar.gz"
    prefix = f"s3://{BUCKET}/rl-scout/checkpoints/{SOURCE_JOB}/"
    inputs = {"adapter": prefix + "adapter-rl/", "report": prefix + "training-report.json",
              "metrics": prefix + "metrics.jsonl", "source": f"s3://{BUCKET}/rl-scout/code/{SOURCE_JOB}/sourcedir.tar.gz"}
    request = {"TrainingJobName": job, "AlgorithmSpecification": {"TrainingImage": IMAGE, "TrainingInputMode": "File"},
        "RoleArn": ROLE, "HyperParameters": {"sagemaker_program": json.dumps("package_evidence.py"),
          "sagemaker_submit_directory": json.dumps(f"s3://{BUCKET}/{key}"), "sagemaker_region": json.dumps(REGION),
          "sagemaker_container_log_level": "20"},
        "InputDataConfig": [{"ChannelName": name, "DataSource": {"S3DataSource": {"S3DataType": "S3Prefix",
              "S3DataDistributionType": "FullyReplicated", "S3Uri": uri}}} for name, uri in inputs.items()],
        "OutputDataConfig": {"S3OutputPath": f"s3://{BUCKET}/rl-scout/output"},
        "ResourceConfig": {"InstanceType": "ml.m5.2xlarge", "InstanceCount": 1, "VolumeSizeInGB": 100},
        "StoppingCondition": {"MaxRuntimeInSeconds": 1800},
        "Environment": {"PYTHONUNBUFFERED": "1", "HF_HOME": "/tmp/hf", "TOKENIZERS_PARALLELISM": "false",
                        "RL_PACKAGE_JOB": job},
        "Tags": [{"Key": "project", "Value": "broadcastcode"}, {"Key": "component", "Value": "rl-scout"},
                 {"Key": "owner", "Value": "codex"}, {"Key": "scope", "Value": "HOU-DAL-evidence-package"}]}
    if not a.execute:
        print(json.dumps({"mode": "dry_run_no_AWS", "expected": expected, "codeBytes": len(archive),
                          "codeSha256": hashlib.sha256(archive).hexdigest(), "request": request}, ensure_ascii=False, indent=2))
        return
    import boto3
    session = boto3.Session(profile_name=PROFILE, region_name=REGION)
    who = session.client("sts").get_caller_identity()
    if who["Account"] != ACCOUNT or ":assumed-role/NBAHackathonParticipantRole/" not in who["Arn"]:
        raise SystemExit("Wrong formal AWS identity")
    sm = session.client("sagemaker")
    source = sm.describe_training_job(TrainingJobName=SOURCE_JOB)
    if source["TrainingJobStatus"] != "Completed":
        raise SystemExit("Registered source training has not completed")
    for status in ("InProgress", "Stopping"):
        for page in sm.get_paginator("list_training_jobs").paginate(StatusEquals=status, NameContains="rl-scout-"):
            if page["TrainingJobSummaries"]:
                raise SystemExit("Another RL job is active; no concurrent package job will be created")
    session.client("s3").put_object(Bucket=BUCKET, Key=key, Body=archive)
    # No automatic creation retry; reconcile an unknown outcome by this exact name.
    sm.create_training_job(**request)
    (HERE / "runs" / f"{job}.json").write_text(json.dumps({**request, "EvidencePackageSource": expected,
        "CodeArchiveSha256": hashlib.sha256(archive).hexdigest()}, ensure_ascii=False, indent=2))
    print(json.dumps({"created": job, "sourceStage": "rl", "instance": "ml.m5.2xlarge", "maxRuntime": 1800}))


if __name__ == "__main__":
    main()
