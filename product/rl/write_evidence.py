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

import scout_env as env

HERE = Path(__file__).resolve().parent
OUT = HERE.parents[0] / "evidence" / "rl-scout-20261010.json"
BUCKET, REGION, PROFILE = "nba-hackathon-555726205424-team02", "us-east-1", "nba"
RUNS = {"rl-scout-early-3b-1010-104358": "v0", "rl-scout-main-3b-v1-1010-105846": "v1",
        "rl-scout-main-3b-v2-1010-111807": "v2", "rl-scout-main-3b-v2-1010-113144": "v2",
        "rl-scout-main-3b-v3-1010-114018": "v3", "rl-scout-main-3b-v4-1010-115100": "v4",
        "rl-scout-main-3b-v4-two-teams-1010-115441": "v4"}
REWARDS = {
    "v0": "0.75·(1−((q̂−y)/0.4)²) + 0.15·格式 + 0.10·有据 − 0.03·工具数 − 0.2·无效",
    "v1": "0.75·max(0, 1−|q̂−y|/0.5) + 0.15·格式 + 0.10·有据 − 0.01·工具数 − 0.2·无效",
    "v2": "0.75·max(0, 1−|q̂−y|/0.5) + 0.15·格式 + 0.10·有据 − 0.002·工具数 − 0.2·无效",
    "v3": "0.45·max(0,1−|q−y|/0.5)+0.30·max(0,1−IS/1.5)+0.15·格式+0.10·数字有据−0.002·工具数−0.2·无效",
    "v4": "有效:0.45·(1−|q−y|/0.5)+0.30·(1−IS/1.5)+0.15·格式+0.10·数字有据−0.002·工具数;硬无效:−2",

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
    seconds = d.get("BillableTimeInSeconds")
    metrics = lines(s3, f"rl-scout/checkpoints/{job}/metrics.jsonl")
    train = [m for m in metrics if m["kind"] == "train"]
    finals = {m["kind"]: {k: m.get(k) for k in ("step", "episodes", "answered", "mae", "mse", "formatRate",
                                                 "groundedRate", "toolsPerEpisode", "meanReward", "validRate", "allEpisodeMAE",
                                                 "intervalRate", "intervalScore", "coverage", "width")}
              for m in metrics if m["kind"].startswith("final_")}
    data = next((m for m in metrics if m["kind"] == "data"), {})
    last = train[-20:]
    return {
        "job": job, "rewardVersion": version, "reward": REWARDS[version], "status": d["TrainingJobStatus"],
        "failureReason": d.get("FailureReason"), "universe": data.get("universe", "all"),
        "referenceFolds": data.get("referenceFolds", 0), "instance": instance, "model": data.get("model"),
        "hyperParameters": {k: v.strip('"') for k, v in d["HyperParameters"].items() if not k.startswith("sagemaker_")},
        "start": str(d.get("TrainingStartTime")), "end": str(d.get("TrainingEndTime")),
        "billableSeconds": seconds, "estimatedUsd": round(seconds / 3600 * PRICE[instance], 2) if seconds is not None and instance in PRICE else None,
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

    chosen = next((r for r in runs if r["job"] == a.selected), None)
    if not chosen or chosen["status"] != "Completed":
        raise SystemExit("Selected training job must be a recorded Completed run.")
    endpoint = sm.describe_endpoint(EndpointName="rl-scout")
    if endpoint["EndpointStatus"] != "InService":
        raise SystemExit("Endpoint must be InService")
    config = sm.describe_endpoint_config(EndpointConfigName=endpoint["EndpointConfigName"])
    variant = config["ProductionVariants"][0]
    model = sm.describe_model(ModelName=variant["ModelName"])
    checks = sorted((HERE / "runs").glob("endpoint-check-*.json"))
    check = json.loads(checks[-1].read_text()) if checks else []
    if not check or any(row.get("trainingJob") != a.selected or not row.get("available") for row in check):
        raise SystemExit("Run check_endpoint.py --training-job SELECTED after deploying the matching model/tables.")
    if any(row.get("sagemakerModel") != variant["ModelName"] for row in check):
        raise SystemExit("Latest endpoint check does not match the live SageMaker model.")
    table_hash = hashlib.sha256((HERE / "data/reference_tables.json").read_bytes()).hexdigest()
    if any(row.get("tablesSha256") != table_hash for row in check):
        raise SystemExit("Reference tables changed after endpoint check")
    comparison = json.loads((HERE / "results/v4-two-teams/comparison.json").read_text())
    if comparison.get("job") != a.selected or not comparison.get("passesFormatGate"):
        raise SystemExit("Requires matching evaluation passing the preregistered validity gate")
    packaging = sorted((HERE / "runs").glob("rl-scout-pkg-*.json"))
    hours_up = (time.time() - endpoint["CreationTime"].timestamp()) / 3600

    shots = (HERE / "data" / "shots.jsonl").read_bytes()
    manifest = json.loads((HERE / "data" / "manifest.json").read_text())
    all_shots = env.load_shots(HERE / "data/shots.jsonl")
    selected_shots = env.select_universe(all_shots, chosen["universe"])
    training, heldout = env.split(selected_shots)
    report = {
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "owner": "codex-rl", "account": "555726205424",
        "region": REGION,
        "summary": "GRPO 多轮强化学习训练会调用工具的 Qwen2.5-3B 球探，奖励为 NBA 官方出手质量值（程序计算）；"
                   "四场火箭 vs 独行侠交手整场不训练，作为模拟考场。",
        "data": {"source": manifest["source"], "fetchedAt": manifest["fetchedAt"], "season": manifest["season"],
                 "universe": chosen["universe"], "games": len({s["gameId"] for s in selected_shots}),
                 "shots": len(selected_shots), "players": len({s["playerId"] for s in selected_shots}),
                 "trainingShots": len(training), "heldoutShots": len(heldout),
                 "trainingGames": len({s["gameId"] for s in training}),
                 "dateRange": [min(s["gameDate"] for s in selected_shots), max(s["gameDate"] for s in selected_shots)],
                 "sourceSnapshot": {"queriedGames": manifest["games"], "gamesWithShots": len({s["gameId"] for s in all_shots}),
                                    "shots": len(all_shots), "playersWithShots": len({s["playerId"] for s in all_shots})},
                 "teamScopeNote": "teamId follows official season profile snapshot, not a historical as-of roster",
                 "headToHeadGames": manifest["headToHeadGames"],
                 "shotsSha256": hashlib.sha256(shots).hexdigest(),
                 "note": "v0 线在数据冻结前启动，测试集划分与 v1/v2 不同（模拟考场 217 次），其数字不与 v1/v2 直接比较。"},
        "baselines": json.loads((HERE / "results" / "baselines.json").read_text()),
        "twoTeamBaselines": json.loads((HERE / "results/v4-two-teams/baselines.json").read_text()),
        "selectionScope": "Existing holdout sets were reused for development and selection; not untouched-test evidence.",
        "runs": runs,
        "selected": {"job": a.selected, "note": a.note, "matchedComparison": comparison, "tablesSha256": table_hash},
        "endpoint": {"name": "rl-scout", "status": endpoint["EndpointStatus"], "config": endpoint["EndpointConfigName"],
                     "instance": variant["InstanceType"], "model": variant["ModelName"],
                     "modelData": model["PrimaryContainer"].get("ModelDataUrl"),
                     "image": model["PrimaryContainer"].get("Image"),
                     "packagingJobs": [f.stem for f in packaging],
                     "endpointAgeHoursIncludingUpdates": round(hours_up, 2),
                     "estimatedUsdPerHour": PRICE.get(variant["InstanceType"]),
                     "latestCheck": check, "checkFile": checks[-1].name if checks else None},
        "estimatedTrainingUsdKnownOnly": round(sum(r["estimatedUsd"] for r in runs if r["estimatedUsd"] is not None), 2),
        "boundaries": [
            "球探估计的是同类出手的常见质量，不是命中预测，不替代官方 xFG；官方值始终原样显示。",
            "模型只读结构化出手记录与对应版本参考表；v4仅两队，不读全季档案，不看视频。",
            "v4质量为同类出手条件中位数；区间是官方出手质量的60%中心区间，非命中概率置信区间。",
            "难度差 = 官方值 − 球探估计，由代码计算，只陈述数值差，不写因果。",
            "Bedrock 自定义模型导入被组织 SCP 显式拒绝，模型由 SageMaker 实时端点托管。",
            "费用为按公开按需价估算，不是账单。",
        ],
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
