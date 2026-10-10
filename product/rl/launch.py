#!/usr/bin/env python3
"""Launch an RL-SCOUT GRPO training job on SageMaker (formal Team02 account only).

    python3 product/rl/launch.py --name smoke --model Qwen/Qwen2.5-0.5B-Instruct --steps 3 ...
Creates exactly one tagged training job; prints its name. Never deletes anything.
"""
import argparse
import io
import json
import tarfile
import time
from pathlib import Path

import boto3

HERE = Path(__file__).resolve().parent
ACCOUNT, REGION, PROFILE = "555726205424", "us-east-1", "nba"
BUCKET = "nba-hackathon-555726205424-team02"
ROLE = f"arn:aws:iam::{ACCOUNT}:role/NBAHackathonWorkloadRole"
IMAGE = "763104351884.dkr.ecr.us-east-1.amazonaws.com/pytorch-training:2.9.0-gpu-py312-cu130-ubuntu22.04-sagemaker"
FILES = ["scout_env.py", "train_grpo.py", "requirements.txt",
         "data/shots.jsonl", "data/profiles.json", "data/manifest.json"]
TAGS = [{"Key": "project", "Value": "broadcastcode"}, {"Key": "component", "Value": "rl-scout"},
        {"Key": "owner", "Value": "claude"}]
METRICS = [
    {"Name": "train:reward", "Regex": r"METRIC step=\d+ reward=(-?[0-9.]+)"},
    {"Name": "train:mae", "Regex": r"METRIC step=\d+ reward=\S+ mae=([0-9.]+)"},
    {"Name": "train:tools", "Regex": r"tools=([0-9.]+)"},
    {"Name": "eval:mae", "Regex": r"eval_mae=([0-9.]+)"},
    {"Name": "eval:reward", "Regex": r"eval_reward=(-?[0-9.]+)"},
]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--name", required=True)
    p.add_argument("--instance", default="ml.g6e.2xlarge")
    p.add_argument("--max-runtime", type=int, default=9000)
    p.add_argument("--hp", nargs="*", default=[], help="key=value hyperparameters for train_grpo.py")
    a = p.parse_args()

    session = boto3.Session(profile_name=PROFILE, region_name=REGION)
    who = session.client("sts").get_caller_identity()
    if who["Account"] != ACCOUNT or ":assumed-role/NBAHackathonParticipantRole/" not in who["Arn"]:
        raise SystemExit(f"Wrong identity {who['Arn']}; aborting.")

    job = f"rl-scout-{a.name}-{time.strftime('%m%d-%H%M%S')}"
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for name in FILES:
            tar.add(HERE / name, arcname=name)
    key = f"rl-scout/code/{job}/sourcedir.tar.gz"
    session.client("s3").put_object(Bucket=BUCKET, Key=key, Body=buffer.getvalue())

    hyper = {"sagemaker_program": json.dumps("train_grpo.py"),
             "sagemaker_submit_directory": json.dumps(f"s3://{BUCKET}/{key}"),
             "sagemaker_region": json.dumps(REGION), "sagemaker_container_log_level": "20"}
    for item in a.hp:
        k, v = item.split("=", 1)
        hyper[k] = v if v.replace(".", "", 1).replace("-", "", 1).isdigit() else json.dumps(v)

    request = dict(
        TrainingJobName=job,
        AlgorithmSpecification={"TrainingImage": IMAGE, "TrainingInputMode": "File", "MetricDefinitions": METRICS},
        RoleArn=ROLE, HyperParameters=hyper,
        OutputDataConfig={"S3OutputPath": f"s3://{BUCKET}/rl-scout/output"},
        ResourceConfig={"InstanceType": a.instance, "InstanceCount": 1, "VolumeSizeInGB": 100},
        StoppingCondition={"MaxRuntimeInSeconds": a.max_runtime},
        CheckpointConfig={"S3Uri": f"s3://{BUCKET}/rl-scout/checkpoints/{job}", "LocalPath": "/opt/ml/checkpoints"},
        Environment={"PYTHONUNBUFFERED": "1", "HF_HOME": "/tmp/hf", "TOKENIZERS_PARALLELISM": "false"},
        Tags=TAGS,
    )
    session.client("sagemaker").create_training_job(**request)
    record = {k: v for k, v in request.items() if k != "Environment"}
    runs = HERE / "runs"
    runs.mkdir(exist_ok=True)
    (runs / f"{job}.json").write_text(json.dumps(record, ensure_ascii=False, indent=1))
    print(job)


if __name__ == "__main__":
    main()
