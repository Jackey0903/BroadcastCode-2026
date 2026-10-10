#!/usr/bin/env python3
"""Verify model/training/table lineage, then check the two official practice shots.

    python3 product/rl/check_endpoint.py --training-job rl-scout-main-...
Read-only AWS metadata plus two endpoint invocations; never deploys resources.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time
from urllib.parse import urlsplit

import boto3
from botocore.config import Config

from scout_client import Scout, sagemaker_invoker

HERE = Path(__file__).resolve().parent
FIXTURES = HERE.parents[1] / "readiness-lab" / "fixtures" / "official"
CASES = [("nba-gpshot-amen-0022500491.json", 396), ("nba-gpshot-flagg-0022500701.json", 666)]
ACCOUNT, REGION, PROFILE = "555726205424", "us-east-1", "nba"
BUCKET = "nba-hackathon-555726205424-team02"
SDK_CONFIG = Config(connect_timeout=10, read_timeout=60, retries={"max_attempts": 2})


def hyperparameter(job, name, default=None):
    value = job.get("HyperParameters", {}).get(name, default)
    try:
        return json.loads(value) if isinstance(value, str) else value
    except (ValueError, TypeError):
        return value


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify_lineage(session, endpoint_name, training_job, tables):
    who = session.client("sts", config=SDK_CONFIG).get_caller_identity()
    require(who["Account"] == ACCOUNT and ":assumed-role/NBAHackathonParticipantRole/" in who["Arn"],
            "Expected formal account 555726205424 and NBAHackathonParticipantRole")
    require(training_job.startswith("rl-scout-"), "Selected training job must be an rl-scout job")
    sm = session.client("sagemaker", config=SDK_CONFIG)
    selected = sm.describe_training_job(TrainingJobName=training_job)
    require(selected["TrainingJobStatus"] == "Completed", "Selected training job is not Completed")
    require(hyperparameter(selected, "model") == "Qwen/Qwen2.5-3B-Instruct",
            "Selected training job is not the Qwen2.5-3B model advertised by this check")
    endpoint = sm.describe_endpoint(EndpointName=endpoint_name)
    require(endpoint["EndpointStatus"] == "InService", "Endpoint is not InService")
    config_name = endpoint["EndpointConfigName"]
    config = sm.describe_endpoint_config(EndpointConfigName=config_name)
    variants = config.get("ProductionVariants", [])
    require(len(variants) == 1, "This check requires one production variant for unambiguous model identity")
    model_name = variants[0]["ModelName"]
    model = sm.describe_model(ModelName=model_name)
    container = model.get("PrimaryContainer")
    require(isinstance(container, dict), "Expected one PrimaryContainer")
    model_url = container.get("ModelDataUrl", "")
    uri = urlsplit(model_url)
    parts = uri.path.strip("/").split("/")
    require(uri.scheme == "s3" and uri.netloc == BUCKET and len(parts) == 5
            and parts[:2] == ["rl-scout", "output"] and parts[3:] == ["output", "model.tar.gz"]
            and parts[2].startswith("rl-scout-"), "ModelDataUrl is not an RL-SCOUT package artifact")
    package_name = parts[2]
    package = sm.describe_training_job(TrainingJobName=package_name)
    require(package["TrainingJobStatus"] == "Completed", "Model package job is not Completed")
    require(package.get("ModelArtifacts", {}).get("S3ModelArtifacts") == model_url,
            "ModelDataUrl does not match the completed package job artifact")
    require(hyperparameter(package, "sagemaker_program") == "package_model.py",
            "Artifact producer is not the model packaging program")
    channels = [c for c in package.get("InputDataConfig", []) if c.get("ChannelName") == "merged"]
    require(len(channels) == 1, "Package job must have one merged input channel")
    merged_uri = channels[0].get("DataSource", {}).get("S3DataSource", {}).get("S3Uri", "")
    expected_uri = f"s3://{BUCKET}/rl-scout/checkpoints/{training_job}/merged/"
    require(merged_uri.rstrip("/") == expected_uri.rstrip("/"),
            "Package merged weights do not come from the selected training job")
    checkpoint_uri = selected.get("CheckpointConfig", {}).get("S3Uri", "")
    require(checkpoint_uri.rstrip("/") + "/merged/" == expected_uri,
            "Selected training job checkpoint location does not match the packaged weights")
    reward = hyperparameter(selected, "reward", "v1")
    universe = hyperparameter(selected, "universe", "all")
    require(tables.get("policy", "v2") == reward,
            f"Table policy {tables.get('policy', 'v2')} does not match trained reward {reward}")
    require(tables.get("universe", "all") == universe,
            f"Table universe {tables.get('universe', 'all')} does not match trained universe {universe}")
    return {"trainingJob": training_job, "trainingJobStatus": selected["TrainingJobStatus"],
            "packageJob": package_name, "packageJobStatus": package["TrainingJobStatus"],
            "sagemakerModel": model_name, "endpointConfig": config_name, "endpoint": endpoint_name,
            "endpointStatus": endpoint["EndpointStatus"], "modelDataUrl": model_url,
            "mergedSource": merged_uri, "policy": reward, "universe": universe,
            "baseModel": hyperparameter(selected, "model"),
            "account": who["Account"], "identityArn": who["Arn"], "lineageVerified": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-job", required=True)
    parser.add_argument("--endpoint", default="rl-scout")
    parser.add_argument("--tables", type=Path, default=HERE / "data" / "reference_tables.json")
    args = parser.parse_args()
    stamp = time.strftime("%m%d-%H%M%S")
    common = {"trainingJob": args.training_job, "sagemakerModel": None, "endpointConfig": None,
              "tablesSha256": None, "endpoint": args.endpoint, "lineageVerified": False}
    report = []
    try:
        table_bytes = args.tables.read_bytes()
        common["tablesSha256"] = hashlib.sha256(table_bytes).hexdigest()
        tables = json.loads(table_bytes)
        session = boto3.Session(profile_name=PROFILE, region_name=REGION)
        common.update(verify_lineage(session, args.endpoint, args.training_job, tables))
        runtime = session.client("sagemaker-runtime", config=SDK_CONFIG)
        scout = Scout(sagemaker_invoker(args.endpoint, client=runtime), tables=tables,
                      model_name=f"rl-scout-qwen2.5-3b-grpo-{common['policy']}")
        for name, event in CASES:
            data = json.loads((FIXTURES / name).read_text())["data"]
            row = next(r for r in data["shotList"] if r["eventId"] == event)
            started = time.time()
            result = scout.analyse(row, data["playerId"], official_quality=row["value"])
            record = {"case": name, "eventId": event, "official": row["value"],
                      "seconds": round(time.time() - started, 2), **result, **common}
            report.append(record)
            print(json.dumps(record, ensure_ascii=False), flush=True)
    except Exception as exc:
        record = {**common, "case": "verification_error", "available": False,
                  "error": f"{type(exc).__name__}: {exc}"}
        report.append(record)
        print(json.dumps(record, ensure_ascii=False), flush=True)
    (HERE / "runs").mkdir(exist_ok=True)
    output = HERE / "runs" / f"endpoint-check-{stamp}.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=1))
    if len(report) != len(CASES) or not all(r.get("available") is True and r.get("lineageVerified") for r in report):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
