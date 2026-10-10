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

HERE = Path(__file__).resolve().parent
OUT = HERE.parents[0] / "data" / "rl" / "training-camp.json"
BUCKET, REGION, PROFILE = "nba-hackathon-555726205424-team02", "us-east-1", "nba"


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
    a = p.parse_args()
    s3 = boto3.Session(profile_name=PROFILE, region_name=REGION).client("s3")
    prefix = f"rl-scout/checkpoints/{a.job}/"
    metrics = read_lines(s3, prefix + "metrics.jsonl")
    rollouts = read_lines(s3, prefix + "rollouts.jsonl")
    keys = [o["Key"] for o in s3.list_objects_v2(Bucket=BUCKET, Prefix=prefix).get("Contents", [])]

    data_row = next((m for m in metrics if m["kind"] == "data"), {})
    train = [m for m in metrics if m["kind"] == "train"]
    curve = [{k: m.get(k) for k in ("step", "meanReward", "mae", "toolsPerEpisode", "invalidRate", "calibration",
                                     "format", "grounded", "genSeconds", "stepSeconds")} for m in train]
    evals = [{k: m.get(k) for k in ("step", "mae", "meanReward", "toolsPerEpisode")} for m in metrics if m["kind"] == "eval"]
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
                                             "advantage": t["advantage"], "say": short(t["turns"][-1] if t["turns"] else "")}
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

    baselines = json.loads((HERE / "results" / "baselines.json").read_text()) if (HERE / "results" / "baselines.json").exists() else {}
    board = {}
    for name in ("h2h", "league"):
        row = baselines.get("results", {}).get(name, {})
        board[name] = {
            "statZoneMove": row.get("stat_zone_move"), "claude": row.get("claude"),
            "base": finals.get(f"final_base_{name}"), "trained": finals.get(f"final_trained_{name}"),
        }

    manifest = json.loads((HERE / "data" / "manifest.json").read_text())
    report = {
        "job": a.job, "model": data_row.get("model"), "status": "done" if any(m["kind"] == "done" for m in metrics) else "training",
        "data": {"shots": manifest["shots"], "games": manifest["games"], "players": manifest["profiledPlayers"],
                 "focusGames": manifest.get("focusGames"), "train": data_row.get("train"),
                 "trainFocus": data_row.get("trainFocus"), "testH2H": data_row.get("test_h2h"),
                 "testLeague": data_row.get("test_league"), "source": manifest["source"]},
        "curve": curve, "evalCurve": evals, "groups": picked, "scoreboard": board,
        "calibration": scatter, "toolMix": tool_mix,
        "claudeModel": baselines.get("model"),
        "honesty": ["奖励来自 NBA 官方出手质量值（基于追踪数据的官方模型），程序自动计算，无人工打分。",
                    "火箭 vs 独行侠交手比赛整场不参与训练，作为模拟考场测试集。",
                    "球探估计的是同类出手的常见质量，不是命中预测，也不替代官方 xFG。"],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB): {len(curve)} steps, {len(picked)} groups, status {report['status']}")


if __name__ == "__main__":
    main()
