#!/usr/bin/env python3
"""Write product/evidence/rl-scout-20261010.json from the real RL-SCOUT artifacts.

    python3 product/rl/write_evidence.py --selected rl-scout-main-3b-v2-... [--note "..."]
Reads each run's metrics in S3, SageMaker job descriptions (instance, billable time), the local
baseline report, data manifest and the latest endpoint check. Read-only on AWS.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time

import boto3

HERE = Path(__file__).resolve().parent
OUT = HERE.parents[0] / "evidence" / "rl-scout-20261010.json"
BUCKET, REGION, PROFILE = "nba-hackathon-555726205424-team02", "us-east-1", "nba"
RUNS = {"rl-scout-early-3b-1010-104358": "v0", "rl-scout-main-3b-v1-1010-105846": "v1",
        "rl-scout-main-3b-v2-1010-111807": "v2", "rl-scout-main-3b-v2-1010-113144": "v2"}
REWARDS = {
    "v0": "0.75·(1−((q̂−y)/0.4)²) + 0.15·格式 + 0.10·有据 − 0.03·工具数 − 0.2·无效",
    "v1": "0.75·max(0, 1−|q̂−y|/0.5) + 0.15·格式 + 0.10·有据 − 0.01·工具数 − 0.2·无效",
    "v2": "0.75·max(0, 1−|q̂−y|/0.5) + 0.15·格式 + 0.10·有据 − 0.002·工具数 − 0.2·无效",
}
# Approximate public SageMaker on-demand prices (USD/hour, us-east-1); an estimate, not a bill.
PRICE = {"ml.g5.xlarge": 1.408, "ml.g5.2xlarge": 1.515, "ml.g5.4xlarge": 2.03, "ml.g5.8xlarge": 3.06,
         "ml.m5.2xlarge": 0.461}


def lines(s3, key):
    try:
        body = s3.get_object(Bucket=BUCKET, Key=key)["Body"].read().decode("utf-8")
    except s3.exceptions.NoSuchKey:
        return []
    return [json.loads(row) for row in body.splitlines() if row.strip()]


def run_summary(sm, s3, job, version):
    d = sm.describe_training_job(TrainingJobName=job)
    instance = d["ResourceConfig"]["InstanceType"]
    seconds = d.get("BillableTimeInSeconds") or 0
    metrics = lines(s3, f"rl-scout/checkpoints/{job}/metrics.jsonl")
    train = [m for m in metrics if m["kind"] == "train"]
    finals = {m["kind"]: {k: m.get(k) for k in ("step", "episodes", "answered", "mae", "mse", "formatRate",
                                                 "groundedRate", "toolsPerEpisode", "meanReward")}
              for m in metrics if m["kind"].startswith("final_")}
    data = next((m for m in metrics if m["kind"] == "data"), {})
    last = train[-20:]
    return {
        "job": job, "rewardVersion": version, "reward": REWARDS[version], "status": d["TrainingJobStatus"],
        "instance": instance, "model": data.get("model"),
        "hyperParameters": {k: v.strip('"') for k, v in d["HyperParameters"].items() if not k.startswith("sagemaker_")},
        "start": str(d.get("TrainingStartTime")), "end": str(d.get("TrainingEndTime")),
        "billableSeconds": seconds, "estimatedUsd": round(seconds / 3600 * PRICE.get(instance, 0), 2),
        "testSetSizes": {k: data.get(k) for k in ("train", "trainFocus", "test_h2h", "test_league")},
        "steps": len(train),
        "flatStepShare": round(sum(1 for m in train if m.get("loss") == 0.0) / max(1, len(train)), 3),
        "lastStepsToolsPerEpisode": round(sum(m["toolsPerEpisode"] for m in last) / max(1, len(last)), 3),
        "evalCurve": [{k: m.get(k) for k in ("step", "mae", "toolsPerEpisode", "meanReward")}
                      for m in metrics if m["kind"] == "eval"],
        "final": finals,
        "artifacts": f"s3://{BUCKET}/rl-scout/checkpoints/{job}/",
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--selected", required=True, help="training job whose merged model serves rl-scout")
    p.add_argument("--note", default="")
    a = p.parse_args()
    session = boto3.Session(profile_name=PROFILE, region_name=REGION)
    sm, s3 = session.client("sagemaker"), session.client("s3")
    runs = [run_summary(sm, s3, job, version) for job, version in RUNS.items()]

    endpoint = sm.describe_endpoint(EndpointName="rl-scout")
    config = sm.describe_endpoint_config(EndpointConfigName=endpoint["EndpointConfigName"])
    variant = config["ProductionVariants"][0]
    model = sm.describe_model(ModelName=variant["ModelName"])
    checks = sorted((HERE / "runs").glob("endpoint-check-*.json"))
    check = json.loads(checks[-1].read_text()) if checks else []
    packaging = sorted((HERE / "runs").glob("rl-scout-pkg-*.json"))
    hours_up = (time.time() - endpoint["CreationTime"].timestamp()) / 3600

    shots = (HERE / "data" / "shots.jsonl").read_bytes()
    manifest = json.loads((HERE / "data" / "manifest.json").read_text())
    report = {
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "owner": "claude", "account": "555726205424",
        "region": REGION,
        "summary": "GRPO 多轮强化学习训练会调用工具的 Qwen2.5-3B 球探，奖励为 NBA 官方出手质量值（程序计算）；"
                   "四场火箭 vs 独行侠交手整场不训练，作为模拟考场。",
        "data": {"source": manifest["source"], "fetchedAt": manifest["fetchedAt"], "season": manifest["season"],
                 "games": manifest["games"], "shots": manifest["shots"], "profiledPlayers": manifest["profiledPlayers"],
                 "focusGames": manifest["focusGames"], "headToHeadGames": manifest["headToHeadGames"],
                 "shotsSha256": hashlib.sha256(shots).hexdigest(),
                 "note": "v0 线在数据冻结前启动，测试集划分与 v1/v2 不同（模拟考场 217 次），其数字不与 v1/v2 直接比较。"},
        "baselines": json.loads((HERE / "results" / "baselines.json").read_text()),
        "runs": runs,
        "selected": {"job": a.selected, "note": a.note},
        "endpoint": {"name": "rl-scout", "status": endpoint["EndpointStatus"], "config": endpoint["EndpointConfigName"],
                     "instance": variant["InstanceType"], "model": variant["ModelName"],
                     "modelData": model["PrimaryContainer"].get("ModelDataUrl"),
                     "image": model["PrimaryContainer"].get("Image"),
                     "packagingJobs": [f.stem for f in packaging],
                     "hoursInServiceSoFar": round(hours_up, 2),
                     "estimatedUsdPerHour": PRICE.get(variant["InstanceType"]),
                     "latestCheck": check, "checkFile": checks[-1].name if checks else None},
        "estimatedTrainingUsd": round(sum(r["estimatedUsd"] for r in runs), 2),
        "boundaries": [
            "球探估计的是同类出手的常见质量，不是命中预测，不替代官方 xFG；官方值始终原样显示。",
            "模型只读结构化出手记录与三张参考表，不看视频，不理解战术意图。",
            "难度差 = 官方值 − 球探估计，由代码计算，只陈述数值差，不写因果。",
            "Bedrock 自定义模型导入被组织 SCP 显式拒绝，模型由 SageMaker 实时端点托管。",
            "费用为按公开按需价估算，不是账单。",
        ],
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
