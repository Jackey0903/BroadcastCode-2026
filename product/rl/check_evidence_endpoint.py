#!/usr/bin/env python3
"""Read-only lineage check for the registered RL evidence endpoint.

Usage after the new package is deployed:
  python3 product/rl/check_evidence_endpoint.py --endpoint rl-scout \
    --package-job rl-scout-pkg-evidence-rl-MMDD-HHMMSS

Checks metadata before making one {"op":"health"} call. An old/wrong endpoint
fails before invocation. No deployment, generation, training, or resource writes.
The local report is a lineage check, not proof the semantic release gate passed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
ACCOUNT, REGION, PROFILE = "555726205424", "us-east-1", "nba"
BUCKET = "nba-hackathon-555726205424-team02"
ROLE = f"arn:aws:iam::{ACCOUNT}:role/NBAHackathonWorkloadRole"
SOURCE_JOB = "rl-scout-evidence-3b-two-teams-1010-052032"
BASE_MODEL = "Qwen/Qwen2.5-3B-Instruct"
BASE_REVISION = "aa8e72537993ba99e69dfaafa59ed015b17504d1"
OUTPUT = HERE / "results/evidence-v1/endpoint-check.json"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def hyperparameter(job, key):
    value = job.get("HyperParameters", {}).get(key)
    try:
        return json.loads(value) if isinstance(value, str) else value
    except ValueError:
        return value


def s3_parts(uri):
    parsed = urlsplit(uri)
    require(parsed.scheme == "s3" and parsed.netloc == BUCKET and not parsed.query and not parsed.fragment,
            "Artifact must be in the formal team bucket")
    return parsed.netloc, parsed.path.lstrip("/")


def read_s3(s3, uri, limit=16 * 1024 * 1024):
    bucket, key = s3_parts(uri)
    response = s3.get_object(Bucket=bucket, Key=key)
    stream = response["Body"]
    try:
        require(response.get("ContentLength", 0) <= limit, "Unexpectedly large metadata object")
        data = stream.read(limit + 1)
        require(len(data) <= limit, "Metadata object exceeds limit")
        return data
    finally:
        stream.close()


def tar_member(archive, name, limit=16 * 1024 * 1024):
    """Read a named member without extracting paths onto the filesystem."""
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        matches = [member for member in tar.getmembers() if member.name == name]
        require(len(matches) == 1 and matches[0].isfile() and matches[0].size <= limit,
                "Invalid or duplicate archive member: " + name)
        stream = tar.extractfile(matches[0])
        require(stream is not None, "Unreadable archive member: " + name)
        return stream.read()


def local_expectations(package_job, training_job, store_path, tasks_path):
    require(training_job == SOURCE_JOB, "Only the registered evidence training job is allowed")
    require(re.fullmatch(r"rl-scout-pkg-evidence-rl-\d{4}-\d{6}", package_job) is not None,
            "Only an explicitly named RL evidence package job is allowed")
    registered = read_json(HERE / "runs" / f"{SOURCE_JOB}.json")
    package = read_json(HERE / "runs" / f"{package_job}.json")
    report = read_json(HERE / "results/evidence-v1/training-report.json")
    audit = read_json(HERE / "results/evidence-v1/rl-update-audit-20261010.json")
    plan = read_json(HERE / "results/evidence-v1/experiment-plan.json")
    store = read_json(store_path)
    tasks = [json.loads(line) for line in Path(tasks_path).read_text().splitlines() if line.strip()]
    require(registered["TrainingJobName"] == report["sourceJob"] == plan["job"] == audit["job"] == SOURCE_JOB,
            "Local registered training identities disagree")
    require(package["TrainingJobName"] == package_job, "Local package identity mismatch")
    require(report["model"] == BASE_MODEL and report["baseRevision"] == BASE_REVISION,
            "Unexpected trained base model/revision")
    require(audit.get("hasActualRLGradientUpdates") is True and audit["optimizerUpdateSteps"] == 7
            and audit["updateGroupsTotal"] == 9, "Expected seven actual RL optimizer updates")
    require(store.get("schema") == "rl-scout-evidence-store-v1", "Wrong frozen store schema")
    require(store["contentSha256"] == digest({k: v for k, v in store.items() if k != "contentSha256"})
            == plan["storeContentSha256"], "Frozen store content hash mismatch")
    require(digest({"players": store["players"], "records": store["records"]}) == plan["environmentStoreDigest"],
            "Frozen environment store digest mismatch")
    for key, value in (("storeSha256", digest(store)), ("tasksSha256", digest(tasks))):
        require(value == report[key] == registered["EvidenceInputs"][key],
                "Frozen canonical input hash mismatch: " + key)
    expected = {
        "schema": "rl-scout-evidence-lineage-v1", "policy": "evidence-v1",
        "model": BASE_MODEL, "baseModel": BASE_MODEL, "baseRevision": BASE_REVISION,
        "sourceTrainingJob": SOURCE_JOB, "selectedStage": "rl", "trainingSelectedStage": "sft",
        "actualRL": True, "optimizerUpdateSteps": 7, "updateGroups": 9,
        "rlSamplingSteps": audit["rlSamplingSteps"],
        "storeSha256": report["storeSha256"], "tasksSha256": report["tasksSha256"],
        "storeContentSha256": store["contentSha256"],
        "sourceArchiveSha256": registered["CodeArchiveSha256"],
        "rawEvaluationReleaseGatePassed": False, "semanticValidationRequired": True,
        "packageJob": package_job,
    }
    require(report["selectedStage"] == expected["trainingSelectedStage"], "Original stage selection was changed")
    for key, value in package["EvidencePackageSource"].items():
        require(key in expected and expected[key] == value, "Package expected-source mismatch: " + key)
    required_source = {"sourceTrainingJob", "baseModel", "baseRevision", "selectedStage", "storeSha256",
                       "tasksSha256", "sourceArchiveSha256", "optimizerUpdateSteps", "updateGroups"}
    require(required_source <= set(package["EvidencePackageSource"]), "Package source contract is incomplete")
    return expected, registered, package, audit


def verify_endpoint(session, endpoint_name, package_job, training_job, store_path, tasks_path):
    require(endpoint_name == "rl-scout", "Only the rl-scout endpoint is allowed")
    expected, registered, local_package, audit = local_expectations(package_job, training_job, store_path, tasks_path)
    from botocore.config import Config
    config = Config(connect_timeout=10, read_timeout=60, retries={"total_max_attempts": 1})
    who = session.client("sts", config=config).get_caller_identity()
    require(who.get("Account") == ACCOUNT and re.fullmatch(
        rf"arn:aws:sts::{ACCOUNT}:assumed-role/NBAHackathonParticipantRole/[^/]+", who.get("Arn", "")),
        "Expected formal account 555726205424 and NBAHackathonParticipantRole")
    require(session.region_name == REGION, "Only us-east-1 is allowed")
    sm = session.client("sagemaker", config=config)
    training = sm.describe_training_job(TrainingJobName=SOURCE_JOB)
    package = sm.describe_training_job(TrainingJobName=package_job)
    for job, name, program in ((training, SOURCE_JOB, "train_evidence.py"), (package, package_job, "package_evidence.py")):
        require(job.get("TrainingJobName") == name and job.get("TrainingJobStatus") == "Completed",
                "Training/package job has not completed: " + name)
        require(job.get("TrainingJobArn") == f"arn:aws:sagemaker:{REGION}:{ACCOUNT}:training-job/{name}",
                "Training job account/region identity mismatch")
        require(job.get("RoleArn") == ROLE and hyperparameter(job, "sagemaker_program") == program,
                "Unexpected workload role or producer program")
    checkpoint = f"s3://{BUCKET}/rl-scout/checkpoints/{SOURCE_JOB}"
    require(training.get("CheckpointConfig", {}).get("S3Uri", "").rstrip("/") == checkpoint,
            "Training checkpoint prefix mismatch")
    channels = {row["ChannelName"]: row.get("DataSource", {}).get("S3DataSource", {}).get("S3Uri")
                for row in package.get("InputDataConfig", [])}
    expected_channels = {"adapter": checkpoint + "/adapter-rl/", "report": checkpoint + "/training-report.json",
                         "metrics": checkpoint + "/metrics.jsonl",
                         "source": f"s3://{BUCKET}/rl-scout/code/{SOURCE_JOB}/sourcedir.tar.gz"}
    require(channels == expected_channels and len(package.get("InputDataConfig", [])) == len(channels),
            "Package inputs are not the registered RL adapter/report/metrics/source")
    endpoint = sm.describe_endpoint(EndpointName=endpoint_name)
    require(endpoint.get("EndpointStatus") == "InService", "Endpoint is not InService")
    endpoint_config = endpoint["EndpointConfigName"]
    deployed = sm.describe_endpoint_config(EndpointConfigName=endpoint_config)
    variants = deployed.get("ProductionVariants", [])
    require(len(variants) == 1 and not deployed.get("ShadowProductionVariants"),
            "Require exactly one production model and no shadow variants")
    model_name = variants[0]["ModelName"]
    model = sm.describe_model(ModelName=model_name)
    container = model.get("PrimaryContainer")
    require(isinstance(container, dict) and not model.get("Containers"), "Require a single PrimaryContainer")
    require(model.get("ExecutionRoleArn") == ROLE, "Model workload role mismatch")
    model_url = container.get("ModelDataUrl")
    artifact = package.get("ModelArtifacts", {}).get("S3ModelArtifacts")
    require(model_url == artifact == f"s3://{BUCKET}/rl-scout/output/{package_job}/output/model.tar.gz",
            "Endpoint model artifact does not match the completed evidence package; health was not invoked")
    require(container.get("Environment", {}).get("SAGEMAKER_PROGRAM") == "inference.py",
            "Unexpected serving entrypoint")

    # Only after the endpoint chain matches do we read source artifacts and call health.
    s3 = session.client("s3", config=config)
    source_archive = read_s3(s3, expected_channels["source"])
    require(hashlib.sha256(source_archive).hexdigest() == expected["sourceArchiveSha256"],
            "Original training source archive SHA mismatch")
    frozen_store = tar_member(source_archive, "data/evidence/store.json")
    frozen_tasks = tar_member(source_archive, "data/evidence/tasks.jsonl")
    require(digest(json.loads(frozen_store)) == expected["storeSha256"], "Archived store differs from registered training")
    require(digest([json.loads(x) for x in frozen_tasks.decode().splitlines() if x.strip()]) == expected["tasksSha256"],
            "Archived tasks differ from registered training")
    expected["frozenStoreFileSha256"] = hashlib.sha256(frozen_store).hexdigest()
    expected["frozenTasksFileSha256"] = hashlib.sha256(frozen_tasks).hexdigest()
    package_code_uri = hyperparameter(package, "sagemaker_submit_directory")
    require(package_code_uri == f"s3://{BUCKET}/rl-scout/code/{package_job}/sourcedir.tar.gz",
            "Unexpected package source location")
    package_code = read_s3(s3, package_code_uri)
    require(hashlib.sha256(package_code).hexdigest() == local_package["CodeArchiveSha256"],
            "Package code archive SHA mismatch")
    require(json.loads(tar_member(package_code, "expected-source.json")) == local_package["EvidencePackageSource"],
            "Uploaded package expected-source differs from registered package")
    expected["handlerSha256"] = hashlib.sha256(tar_member(package_code, "serve_evidence/inference.py")).hexdigest()
    metrics = read_s3(s3, expected_channels["metrics"])
    expected["metricsSha256"] = hashlib.sha256(metrics).hexdigest()
    require(expected["metricsSha256"] == audit["sourceSha256"], "RL update source log hash mismatch")
    rl_rows = [row for row in (json.loads(x) for x in metrics.decode().splitlines() if x.strip()) if row.get("kind") == "rl"]
    require([r["step"] for r in rl_rows] == list(range(1, 31)) and sum(r["updateGroups"] > 0 for r in rl_rows) == 7
            and sum(r["updateGroups"] for r in rl_rows) == 9, "Actual RL update log differs from registered audit")
    report_bytes = read_s3(s3, expected_channels["report"])
    require(json.loads(report_bytes) == read_json(HERE / "results/evidence-v1/training-report.json"),
            "Cloud and local completed training reports disagree")
    expected["trainingReportSha256"] = hashlib.sha256(report_bytes).hexdigest()
    adapter_uri = expected_channels["adapter"] + "adapter_model.safetensors"
    adapter_bucket, adapter_key = s3_parts(adapter_uri)
    adapter_metadata = s3.head_object(Bucket=adapter_bucket, Key=adapter_key)
    require(0 < adapter_metadata.get("ContentLength", 0) <= 512 * 1024 * 1024,
            "Unexpected source adapter size")
    adapter_config = read_s3(s3, expected_channels["adapter"] + "adapter_config.json")
    adapter_info = json.loads(adapter_config)
    require(adapter_info.get("base_model_name_or_path") == BASE_MODEL and adapter_info.get("peft_type") == "LORA",
            "Registered source adapter config has wrong model/type")
    expected["adapterConfigSha256"] = hashlib.sha256(adapter_config).hexdigest()
    bucket, key = s3_parts(model_url)
    object_metadata = s3.head_object(Bucket=bucket, Key=key)
    require(object_metadata.get("ContentLength", 0) > 0, "Package artifact is empty")
    runtime = session.client("sagemaker-runtime", config=config)
    health_response = runtime.invoke_endpoint(EndpointName=endpoint_name, ContentType="application/json",
        Accept="application/json", Body=b'{"op":"health"}')
    stream = health_response["Body"]
    try:
        health_bytes = stream.read(1024 * 1024 + 1)
    finally:
        stream.close()
    require(len(health_bytes) <= 1024 * 1024, "Unexpectedly large health response")
    health = json.loads(health_bytes)
    require(isinstance(health, dict) and health.get("status") == "ok" and isinstance(health.get("lineage"), dict),
            "Handler did not return successful loaded-model health lineage")
    lineage = health["lineage"]
    for key, value in expected.items():
        require(type(lineage.get(key)) is type(value) and lineage[key] == value,
                "Serving lineage mismatch: " + key)
    adapter_sha = lineage.get("adapterSha256")
    require(isinstance(adapter_sha, str) and re.fullmatch(r"[a-f0-9]{64}", adapter_sha),
            "Package did not report a valid source adapter SHA-256")
    # The completed CPU packager calculated this SHA from its fixed adapter
    # channel. Its code archive/expected-source and deployed artifact URI were
    # verified above. Do not download ~120 MB again or call ETag a SHA-256.
    expected["adapterSha256"] = adapter_sha
    weights = lineage.get("modelWeights")
    require(isinstance(weights, dict) and bool(weights) and all(
        isinstance(name, str) and Path(name).name == name and name.endswith(".safetensors")
        and isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value)
        for name, value in weights.items()), "Invalid loaded weight manifest")
    require(lineage.get("mergedWeightsSha256") == digest(weights), "Merged weight manifest digest mismatch")
    latest = sm.describe_endpoint(EndpointName=endpoint_name)
    require(latest.get("EndpointStatus") == "InService" and latest.get("EndpointConfigName") == endpoint_config,
            "Endpoint changed during verification")
    expected.update(endpoint=endpoint_name, endpointConfig=endpoint_config,
                    sagemakerModel=model_name, mergedWeightsSha256=lineage["mergedWeightsSha256"])
    return {
        "schema": "rl-scout-evidence-endpoint-check-v1", "available": True, "lineageVerified": True,
        "account": who["Account"], "identityArn": who["Arn"], "region": REGION, "profile": PROFILE,
        "endpoint": endpoint_name, "endpointStatus": endpoint["EndpointStatus"],
        "endpointConfig": endpoint_config, "sagemakerModel": model_name, "modelDataUrl": model_url,
        "packageJob": package_job, "packageJobStatus": package["TrainingJobStatus"],
        "trainingJob": SOURCE_JOB, "trainingJobStatus": training["TrainingJobStatus"],
        "sourceAdapter": {"uri": adapter_uri, "bytes": adapter_metadata["ContentLength"],
                          "etag": adapter_metadata.get("ETag"), "versionId": adapter_metadata.get("VersionId"),
                          "sha256": adapter_sha, "sha256ComputedBy": "verified_completed_CPU_package_job",
                          "independentlyRehashedLocally": False, "etagIsNotSha256": True},
        "modelArtifact": {"bytes": object_metadata["ContentLength"], "etag": object_metadata.get("ETag"),
                          "etagIsNotSha256": True},
        "health": health, "expectedLineage": expected,
        "semanticReleaseGatePassed": None, "rawEvaluationReleaseGatePassed": False,
        "limits": "One health call and source/artifact lineage verification only; no semantic evaluation. Adapter SHA is calculated by the verified completed CPU packager. Loaded shards are verified by the audited handler. This checker downloads neither adapter nor merged weights.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", choices=("rl-scout",), default="rl-scout")
    parser.add_argument("--package-job", required=True)
    parser.add_argument("--training-job", choices=(SOURCE_JOB,), default=SOURCE_JOB)
    parser.add_argument("--store", type=Path, default=HERE / "data/evidence/store.json")
    parser.add_argument("--tasks", type=Path, default=HERE / "data/evidence/tasks.jsonl")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    result = {"schema": "rl-scout-evidence-endpoint-check-v1", "available": False, "lineageVerified": False,
              "endpoint": args.endpoint, "packageJob": args.package_job, "trainingJob": args.training_job}
    try:
        import boto3
        session = boto3.Session(profile_name=PROFILE, region_name=REGION)
        result = verify_endpoint(session, args.endpoint, args.package_job, args.training_job, args.store, args.tasks)
    except Exception as error:
        result["error"] = f"{type(error).__name__}: {error}"
    result["checkedAt"] = datetime.now(timezone.utc).isoformat()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps({k: result.get(k) for k in ("available", "lineageVerified", "endpoint", "endpointConfig",
        "sagemakerModel", "packageJob", "trainingJob", "error")}, ensure_ascii=False))
    print(str(args.output))
    if not result["lineageVerified"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
