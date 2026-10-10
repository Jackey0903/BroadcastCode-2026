#!/usr/bin/env python3
"""Package one bounded evidence-training job; default is a local dry run.

--execute is required to create a job. It verifies the formal identity and refuses
to overlap any active rl-scout training job. No IAM, endpoints, or CDK are changed.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile

import train_evidence

HERE = Path(__file__).resolve().parent
ACCOUNT, REGION, PROFILE = "555726205424", "us-east-1", "nba"
BUCKET = "nba-hackathon-555726205424-team02"
ROLE = f"arn:aws:iam::{ACCOUNT}:role/NBAHackathonWorkloadRole"
IMAGE = "763104351884.dkr.ecr.us-east-1.amazonaws.com/pytorch-training:2.9.0-gpu-py312-cu130-ubuntu22.04-sagemaker"
CODE = ("train_evidence.py", "evidence_env.py", "evidence_store.py")


def package(store, tasks):
    files = {name: (HERE / name).read_bytes() for name in CODE}
    files["requirements.txt"] = (HERE / "requirements_evidence.txt").read_bytes()
    files["data/evidence/store.json"] = train_evidence.canonical(store).encode()
    files["data/evidence/tasks.jsonl"] = ("".join(train_evidence.canonical(t) + "\n" for t in tasks)).encode()
    # Store implementations may reuse this audited source reader.
    if (HERE / "depth_tasks.py").exists():
        files["depth_tasks.py"] = (HERE / "depth_tasks.py").read_bytes()
    manifest = {"schema": "rl-scout-evidence-package-v1", "files": {
        name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}
    files["package-manifest.json"] = json.dumps(manifest, indent=2).encode()
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for name, data in sorted(files.items()):
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(data), 0o644, 0
            tar.addfile(info, io.BytesIO(data))
    return buffer.getvalue(), manifest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--name", default="evidence-3b-two-teams")
    p.add_argument("--instance", choices=("ml.g5.xlarge",), default="ml.g5.xlarge")
    p.add_argument("--store", default=str(HERE / "data/evidence/store.json"))
    p.add_argument("--tasks", default=str(HERE / "data/evidence/tasks.jsonl"))
    p.add_argument("--max-runtime", type=int, default=4800)
    p.add_argument("--hp", nargs="*", default=[])
    p.add_argument("--execute", action="store_true")
    a = p.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,30}", a.name):
        p.error("name must be a short lower-case slug")
    hp = {"store": "data/evidence/store.json", "tasks": "data/evidence/tasks.jsonl"}
    overrides = []
    for item in a.hp:
        if "=" not in item:
            p.error("hyperparameters require key=value")
        key, value = item.split("=", 1)
        if key.startswith("sagemaker_") or key in ("store", "tasks", "out", "dry-run"):
            p.error("reserved hyperparameter " + key)
        hp[key] = value
        overrides += ["--" + key, value]
    config = train_evidence.arguments(["--store", a.store, "--tasks", a.tasks, *overrides])
    if not 2700 <= config.time_budget <= 3600:
        p.error("this experiment permits a 45–60 minute training/evaluation budget")
    if not config.time_budget + 600 <= a.max_runtime <= 5400:
        p.error("max-runtime must include setup margin and remain <= 90 minutes")
    _, store, tasks, _, _, manifest = train_evidence.load_inputs(config)
    # Execute real local teachers once; no GPU/network/model calls in preparation.
    train_evidence.dry_run(config)
    payload, package_manifest = package(store, tasks)
    job = "rl-scout-" + a.name + "-" + datetime.now(timezone.utc).strftime("%m%d-%H%M%S")
    key = f"rl-scout/code/{job}/sourcedir.tar.gz"
    hyper = {"sagemaker_program": json.dumps("train_evidence.py"),
             "sagemaker_submit_directory": json.dumps(f"s3://{BUCKET}/{key}"),
             "sagemaker_region": json.dumps(REGION), "sagemaker_container_log_level": "20"}
    hyper.update({k: str(v) for k, v in hp.items()})
    request = {"TrainingJobName": job,
        "AlgorithmSpecification": {"TrainingImage": IMAGE, "TrainingInputMode": "File"},
        "RoleArn": ROLE, "HyperParameters": hyper,
        "OutputDataConfig": {"S3OutputPath": f"s3://{BUCKET}/rl-scout/output"},
        "ResourceConfig": {"InstanceType": a.instance, "InstanceCount": 1, "VolumeSizeInGB": 100},
        "StoppingCondition": {"MaxRuntimeInSeconds": a.max_runtime},
        "CheckpointConfig": {"S3Uri": f"s3://{BUCKET}/rl-scout/checkpoints/{job}", "LocalPath": "/opt/ml/checkpoints"},
        "Environment": {"PYTHONUNBUFFERED": "1", "HF_HOME": "/tmp/hf", "TOKENIZERS_PARALLELISM": "false",
                        "PYTORCH_ALLOC_CONF": "expandable_segments:True", "RL_TRAINING_JOB": job},
        "Tags": [{"Key": "project", "Value": "broadcastcode"}, {"Key": "component", "Value": "rl-scout"},
                 {"Key": "owner", "Value": "codex"}, {"Key": "scope", "Value": "HOU-DAL-evidence"}]}
    record = {"request": request, "inputManifest": manifest, "packageManifest": package_manifest,
              "archiveSha256": hashlib.sha256(payload).hexdigest(), "archiveBytes": len(payload)}
    if not a.execute:
        print(json.dumps({"mode": "dry_run_no_AWS", **record}, ensure_ascii=False, indent=2))
        return
    import boto3
    session = boto3.Session(profile_name=PROFILE, region_name=REGION)
    who = session.client("sts").get_caller_identity()
    if who["Account"] != ACCOUNT or ":assumed-role/NBAHackathonParticipantRole/" not in who["Arn"]:
        raise SystemExit("Wrong formal AWS identity; refusing to launch")
    sm = session.client("sagemaker")
    active = []
    for status in ("InProgress", "Stopping"):
        for page in sm.get_paginator("list_training_jobs").paginate(StatusEquals=status, NameContains="rl-scout-"):
            active.extend(r["TrainingJobName"] for r in page["TrainingJobSummaries"])
    if active:
        raise SystemExit("Existing RL jobs still active; no concurrency increase: " + ", ".join(active))
    session.client("s3").put_object(Bucket=BUCKET, Key=key, Body=payload)
    # No automatic retry: an unknown response must be reconciled by this exact name.
    sm.create_training_job(**request)
    runs = HERE / "runs"
    runs.mkdir(exist_ok=True)
    (runs / f"{job}.json").write_text(json.dumps({**request, "EvidenceInputs": manifest,
        "CodeArchiveSha256": record["archiveSha256"]}, ensure_ascii=False, indent=2))
    print(json.dumps({"created": job, "checkpoints": request["CheckpointConfig"]["S3Uri"]}))


if __name__ == "__main__":
    main()
