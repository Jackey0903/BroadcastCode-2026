#!/usr/bin/env python3
"""Serve a packaged RL-SCOUT model on a SageMaker real-time endpoint (formal account only).

    python3 product/rl/deploy_endpoint.py --package-job rl-scout-pkg-... --endpoint rl-scout --wait
Bedrock CreateModelImportJob is denied by the organisation SCP, so serving uses SageMaker.
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
IMAGE = "763104351884.dkr.ecr.us-east-1.amazonaws.com/pytorch-inference:2.6.0-gpu-py312-cu124-ubuntu22.04-sagemaker"
TAGS = [{"Key": "project", "Value": "broadcastcode"}, {"Key": "component", "Value": "rl-scout"},
        {"Key": "owner", "Value": "claude"}]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--package-job", required=True)
    p.add_argument("--endpoint", required=True)
    p.add_argument("--instance", default="ml.g5.xlarge")
    p.add_argument("--wait", action="store_true")
    a = p.parse_args()
    session = boto3.Session(profile_name=PROFILE, region_name=REGION)
    if session.client("sts").get_caller_identity()["Account"] != ACCOUNT:
        raise SystemExit("Wrong account; aborting.")
    sm = session.client("sagemaker")
    stamp = time.strftime("%m%d-%H%M%S")
    model_name, config_name = f"{a.endpoint}-model-{stamp}", f"{a.endpoint}-config-{stamp}"
    data = f"s3://{BUCKET}/rl-scout/output/{a.package_job}/output/model.tar.gz"
    sm.create_model(ModelName=model_name, ExecutionRoleArn=ROLE, Tags=TAGS, PrimaryContainer={
        "Image": IMAGE, "ModelDataUrl": data,
        "Environment": {"SAGEMAKER_PROGRAM": "inference.py", "SAGEMAKER_SUBMIT_DIRECTORY": "/opt/ml/model/code",
                        "SAGEMAKER_REGION": REGION, "SAGEMAKER_MODEL_SERVER_TIMEOUT": "120",
                        "SAGEMAKER_MODEL_SERVER_WORKERS": "1"}})
    sm.create_endpoint_config(EndpointConfigName=config_name, Tags=TAGS, ProductionVariants=[{
        "VariantName": "AllTraffic", "ModelName": model_name, "InstanceType": a.instance, "InitialInstanceCount": 1,
        "ContainerStartupHealthCheckTimeoutInSeconds": 900, "ModelDataDownloadTimeoutInSeconds": 900}])
    existing = [e["EndpointName"] for e in sm.list_endpoints(NameContains=a.endpoint)["Endpoints"]]
    if a.endpoint in existing:
        sm.update_endpoint(EndpointName=a.endpoint, EndpointConfigName=config_name)
    else:
        sm.create_endpoint(EndpointName=a.endpoint, EndpointConfigName=config_name, Tags=TAGS)
    record = {"endpoint": a.endpoint, "model": model_name, "config": config_name, "modelData": data,
              "instance": a.instance, "image": IMAGE, "createdAt": stamp}
    print(json.dumps(record), flush=True)
    while a.wait:
        status = sm.describe_endpoint(EndpointName=a.endpoint)
        print(time.strftime("%H:%M:%S"), status["EndpointStatus"], status.get("FailureReason", ""), flush=True)
        if status["EndpointStatus"] in ("InService", "Failed"):
            record["status"] = status["EndpointStatus"]
            record["failureReason"] = status.get("FailureReason")
            break
        time.sleep(30)
    (HERE / "runs").mkdir(exist_ok=True)
    (HERE / "runs" / f"endpoint-{a.endpoint}-{stamp}.json").write_text(json.dumps(record, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
