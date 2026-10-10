#!/usr/bin/env python3
"""Build product/data/rl/training-camp.json for the web TRAINING CAMP view from real run artifacts.

    python3 product/rl/build_camp.py --job rl-scout-main-...
Reads the job's checkpoint prefix in S3 (metrics, GRPO groups, per-episode evaluations) and the
local baseline report. Works mid-training (partial curves) and after completion.
"""
import argparse
import collections
import json
from pathlib import Path
import random

import boto3
from botocore.config import Config
import scout_env as env

HERE = Path(__file__).resolve().parent
OUT = HERE.parents[0] / "data" / "rl" / "training-camp.json"
BUCKET, REGION, PROFILE = "nba-hackathon-555726205424-team02", "us-east-1", "nba"
SDK_CONFIG = Config(connect_timeout=10, read_timeout=60, retries={"max_attempts": 2})
SUMMARY_FIELDS = ("step", "episodes", "answered", "mae", "allEpisodeMAE", "validRate", "mse",
                  "meanReward", "toolsPerEpisode", "formatRate", "groundedRate", "intervalRate",
                  "intervalScore", "coverage", "width")


def hyperparameter(job, name, default=None):
    value = job.get("HyperParameters", {}).get(name, default)
    try:
        return json.loads(value) if isinstance(value, str) else value
    except (ValueError, TypeError):
        return value


def job_state(job):
    actual = job["TrainingJobStatus"]
    return {"status": {"Completed": "done", "InProgress": "training", "Failed": "failed",
                       "Stopped": "stopped", "Stopping": "stopping"}.get(actual, actual.lower()),
            "trainingJobStatus": actual, "secondaryStatus": job.get("SecondaryStatus"),
            "failureReason": job.get("FailureReason")}


def baseline_path(policy, universe):
    if policy == "v4":
        return HERE / "results" / ("v4-two-teams" if universe == "two-teams" else "v4") / "baselines.json"
    return HERE / "results" / "baselines.json"


def dataset_summary(data_row, universe, manifest):
    shots = env.select_universe(env.load_shots(HERE / "data" / "shots.jsonl"), universe)
    train, _ = env.split(shots)
    sets = env.test_sets(shots)
    observed = {"shots": len(shots), "games": len({s["gameId"] for s in shots}),
                "players": len({s["playerId"] for s in shots}),
                "focusGames": len({s["gameId"] for s in shots if s.get("focus")}),
                "train": len(train), "trainFocus": sum(bool(s.get("focus")) for s in train),
                "testH2H": len(sets.get("h2h", [])), "testLeague": len(sets.get("league", []))}
    logged = {key: data_row[field] for key, field in (("train", "train"), ("trainFocus", "trainFocus"),
              ("testH2H", "test_h2h"), ("testLeague", "test_league"), ("games", "games"), ("players", "players"))
              if field in data_row}
    mismatch = any(logged.get(key, observed[key]) != observed[key] for key in ("train", "testH2H", "testLeague"))
    summary = {**observed, **logged, "universe": universe, "source": manifest["source"],
               "harvestRequestedGames": manifest.get("games"),
               "countsSource": "training_log_and_filtered_frozen_rows" if not mismatch else "training_log_older_dataset",
               "localDatasetMatchesLoggedSplitCounts": not mismatch}
    if mismatch:
        summary["shots"] = sum(logged[key] for key in ("train", "testH2H", "testLeague")) if all(
            key in logged for key in ("train", "testH2H", "testLeague")) else None
        # An older run can precede the current data freeze; requested games are never observed games.
        for key in ("games", "players", "focusGames"):
            summary[key] = logged.get(key)
    return summary


def read_lines(s3, key):
    try:
        body = s3.get_object(Bucket=BUCKET, Key=key)["Body"].read().decode("utf-8")
    except s3.exceptions.NoSuchKey:
        return []
    return [json.loads(line) for line in body.splitlines() if line.strip()]


def short(text, limit=90):
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--job", required=True)
    p.add_argument("--groups", type=int, default=6)
    p.add_argument("--story", nargs="*", default=[], help="other runs (any reward version) for the reward-iteration story")
    p.add_argument("--baselines", type=Path, help="explicit report with matching reward and data universe")
    a = p.parse_args()
    session = boto3.Session(profile_name=PROFILE, region_name=REGION)
    s3, sm = session.client("s3", config=SDK_CONFIG), session.client("sagemaker", config=SDK_CONFIG)
    selected_job = sm.describe_training_job(TrainingJobName=a.job)
    prefix = f"rl-scout/checkpoints/{a.job}/"
    metrics = read_lines(s3, prefix + "metrics.jsonl")
    rollouts = read_lines(s3, prefix + "rollouts.jsonl")
    keys = [o["Key"] for page in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=prefix)
            for o in page.get("Contents", [])]

    data_row = next((m for m in metrics if m["kind"] == "data"), {})
    policy = data_row.get("rewardVersion", hyperparameter(selected_job, "reward", "v0"))
    universe = data_row.get("universe", hyperparameter(selected_job, "universe", "all"))
    train = [m for m in metrics if m["kind"] == "train"]
    curve = [{k: m.get(k) for k in SUMMARY_FIELDS + ("invalidRate", "calibration", "interval", "format", "grounded",
              "genSeconds", "stepSeconds", "flatGroups", "updateGroups")} for m in train]
    evals = [{k: m.get(k) for k in SUMMARY_FIELDS} for m in metrics if m["kind"] == "eval"]
    finals = {m["kind"]: m for m in metrics if m["kind"].startswith("final_")}

    # GRPO groups spread across training.
    picked = []
    if rollouts:
        idx = sorted({round(i * (len(rollouts) - 1) / max(1, a.groups - 1)) for i in range(a.groups)})
        for row in (rollouts[i] for i in idx):
            shot = row["shot"]
            picked.append({"step": row["step"], "shot": {"desc": shot["shotDesc"], "zone": shot["zone"],
                                                         "type": shot["shotType"], "distanceFt": shot["distanceFt"],
                                                         "official": shot["quality"]},
                           "trajectories": [{"tools": t["tools"], "prediction": t["prediction"], "reward": t["total"],
                                             "advantage": t["advantage"], "low": t.get("low"), "high": t.get("high"),
                                             "say": short(t["turns"][-1] if t["turns"] else "")}
                                            for t in row["trajectories"]]})

    # Per-episode evaluations: calibration scatter and tool mix (base vs trained).
    def episodes(tag):
        key = next((k for k in keys if k.rsplit("/", 1)[-1].startswith(tag)), None)
        return read_lines(s3, key) if key else []
    rng = random.Random(7)
    scatter, tool_mix = {}, {}
    for label, tag in (("base", "final_base_h2h"), ("trained", "final_trained_h2h")):
        rows = [r for r in episodes(tag) if r.get("prediction") is not None]
        sample = rng.sample(rows, min(160, len(rows)))
        scatter[label] = [[round(r["prediction"], 3), r["quality"]] for r in sample]
        counter = collections.Counter(name for r in episodes(tag) for name in (r.get("tools") if isinstance(r.get("tools"), list) else []))
        rows_all = episodes(tag)
        tool_mix[label] = {"episodes": len(rows_all), "callsPerEpisode": round(sum(
            len(r["tools"]) if isinstance(r.get("tools"), list) else int(r.get("tools") or 0) for r in rows_all) / max(1, len(rows_all)), 3), **counter}

    baseline_file = a.baselines or baseline_path(policy, universe)
    baselines = json.loads(baseline_file.read_text()) if baseline_file.exists() else {}
    if baselines and (baselines.get("universe", "all") != universe or
                      (policy == "v4" and baselines.get("policy") != policy)):
        raise ValueError("Baseline report policy/universe does not match the selected training job")
    comparison_file = baseline_file.with_name("comparison.json")
    comparison = json.loads(comparison_file.read_text()) if comparison_file.exists() else None
    if comparison and (comparison.get("job") != a.job or comparison.get("policy") != policy
                       or comparison.get("universe") != universe):
        comparison = None  # Another run's matched evaluation must never appear as this run's result.
    board = {}
    for name in ("h2h", "league"):
        row = baselines.get("results", {}).get(name, {})
        board[name] = {
            "statZone": row.get("stat_zone"), "statZoneMove": row.get("stat_zone_move"),
            "statJointMedian": row.get("stat_joint_median"), "claude": row.get("claude"),
            "base": finals.get(f"final_base_{name}"), "trained": finals.get(f"final_trained_{name}"),
        }

    # Reward iteration: how each reward version shaped tool use and whether GRPO groups kept any signal.
    story = []
    for job in dict.fromkeys(a.story + [a.job]):
        rows = metrics if job == a.job else read_lines(s3, f"rl-scout/checkpoints/{job}/metrics.jsonl")
        steps = [m for m in rows if m["kind"] == "train"]
        head = next((m for m in rows if m["kind"] == "data"), {})
        description = selected_job if job == a.job else sm.describe_training_job(TrainingJobName=job)
        story_policy = head.get("rewardVersion", hyperparameter(description, "reward", "v0"))
        story_universe = head.get("universe", hyperparameter(description, "universe", "all"))
        story.append({
            "job": job, "rewardVersion": story_policy, "universe": story_universe, **job_state(description),
            "train": head.get("train"), "testH2H": head.get("test_h2h"), "testLeague": head.get("test_league"),
            "comparisonNote": "历史迭代；数据范围、划分或奖励不同，不按曲线高低直接排名。",
            "curve": [{"step": m["step"], "tools": m["toolsPerEpisode"], "mae": m["mae"],
                       "allEpisodeMAE": m.get("allEpisodeMAE"), "validRate": m.get("validRate"),
                       "intervalScore": m.get("intervalScore"), "coverage": m.get("coverage"),
                       "flat": m.get("flatGroups", 1.0 if m.get("loss") == 0.0 else None)} for m in steps],
            "evalCurve": [{k: m.get(k) for k in SUMMARY_FIELDS} for m in rows if m["kind"] == "eval"],
            "final": {m["kind"]: {k: m.get(k) for k in SUMMARY_FIELDS}
                      for m in rows if m["kind"].startswith("final_")},
        })

    manifest = json.loads((HERE / "data" / "manifest.json").read_text())
    report = {
        "job": a.job, "model": data_row.get("model", hyperparameter(selected_job, "model")),
        "policy": policy, "universe": universe, **job_state(selected_job),
        "artifactsComplete": any(m["kind"] == "done" for m in metrics),
        "data": dataset_summary(data_row, universe, manifest),
        "curve": curve, "evalCurve": evals, "groups": picked, "scoreboard": board,
        "calibration": scatter, "toolMix": tool_mix, "rewardStory": story,
        "claudeModel": baselines.get("model"),
        "baselineReport": str(baseline_file.relative_to(HERE)) if baseline_file.is_relative_to(HERE) else str(baseline_file),
        "baselineAvailable": bool(baselines),
        "matchedComparison": comparison,
        "comparisonNote": "同ID比较见matchedComparison；390题总表与Claude抽样120题不直接判胜负。",
        "honesty": ["奖励来自 NBA 官方出手质量值（基于追踪数据的官方模型），程序自动计算，无人工打分。",
                    "火箭 vs 独行侠交手比赛整场不参与训练；已用于开发择优，不能称从未查看的盲测。",
                    "球探估计同类出手的常见质量；v4为条件中位数，不替代官方 xFG。",
                    "allEpisodeMAE 对无效或缺答计最大误差1；mae仅统计有点估计的回答，须连同validRate查看。",
                    "groundedRate仅检查数字来源，不等于语义事实正确。Claude抽样与全量评测样本数不同。",
                    "历史v0-v3与两队v4的数据范围或划分不同，历史曲线保留，不直接比较奖励高低。",
                    f"当前云训练任务状态：{selected_job['TrainingJobStatus']}。"],
    }
    if universe == "two-teams":
        report["honesty"].append("本版仅使用记录teamId属于火箭或独行侠的出手，不纳入同场对手出手；teamId来自赛季档案。")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB): {len(curve)} steps, {len(picked)} groups, status {report['status']}")


if __name__ == "__main__":
    main()
