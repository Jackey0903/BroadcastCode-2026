#!/usr/bin/env python3
"""Compare v4 two-team base/trained/statistical/Claude predictions on identical shots.

Missing predictions stay in each denominator. Existing holdout is development evidence.
Reads completed evaluations from S3; does not invoke models or deploy anything.
"""
import argparse
import hashlib
import json
from pathlib import Path

import scout_env as env
from eval_baselines import stat_rows
HERE = Path(__file__).resolve().parent
BUCKET, PROFILE, REGION = "nba-hackathon-555726205424-team02", "nba", "us-east-1"


def key(row):
    shot = row.get("shot", row)
    return tuple(str(shot[name]) for name in ("gameId", "playerId", "eventId"))


def index(rows):
    result = {key(row): row for row in rows}
    if len(result) != len(rows):
        raise ValueError("Duplicate episode IDs")
    return result


def summarize_on(ids, predictions, truth):
    rows = []
    for episode_id in ids:
        row = dict(predictions.get(episode_id, {"prediction": None, "invalid": True}))
        if "quality" in row and row["quality"] != truth[episode_id]["quality"]:
            raise ValueError("Evaluation label differs from frozen shot data")
        row["quality"] = truth[episode_id]["quality"]
        if isinstance(row.get("tools"), list):
            row["tools"] = len(row["tools"])
        rows.append(row)
    return env.summarize(rows)


def main():
    import boto3
    from write_evidence import lines

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--job", required=True)
    a = p.parse_args()
    session = boto3.Session(profile_name=PROFILE, region_name=REGION)
    sm, s3 = session.client("sagemaker"), session.client("s3")
    description = sm.describe_training_job(TrainingJobName=a.job)
    hp = description["HyperParameters"]
    if description["TrainingJobStatus"] != "Completed" or hp.get("reward", "").strip('"') != "v4" or hp.get("universe", "").strip('"') != "two-teams":
        raise SystemExit("Requires a completed v4 two-team training job")
    env.use_reward("v4")
    shots = env.select_universe(env.load_shots(HERE / "data/shots.jsonl"), "two-teams")
    train, heldout = env.split(shots)
    truth = index(heldout)
    refs = env.References(train, {}, "two-teams")
    prefix = f"rl-scout/checkpoints/{a.job}/"
    keys = [o["Key"] for page in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=prefix)
            for o in page.get("Contents", [])]
    predictions = {}
    for name in ("base", "trained"):
        files = [k for k in keys if k.rsplit("/", 1)[-1].startswith(f"final_{name}_h2h-step")]
        if len(files) != 1:
            raise SystemExit(f"Expected exactly one final {name} h2h file; got {files}")
        predictions[name] = index(lines(s3, files[0]))

    def joint(shot):
        (_, _, median, low, high), _ = refs.situation_values(shot)
        return {"quality": median, "low": low, "high": high}

    predictions["stat_joint_median"] = dict(zip((key(s) for s in heldout), stat_rows(heldout, joint, refs)))
    predictions["stat_zone_move"] = dict(zip((key(s) for s in heldout), stat_rows(heldout, refs.baseline_combined, refs)))
    claude_file = HERE / "results/v4-two-teams/claude-h2h.jsonl"
    predictions["claude"] = index([json.loads(line) for line in claude_file.read_text().splitlines() if line])
    if any(set(rows) - truth.keys() for rows in predictions.values()):
        raise SystemExit("Evaluation includes IDs outside the frozen two-team holdout")
    ids = sorted(truth)
    common = sorted(predictions["claude"])
    report = {"job": a.job, "policy": "v4", "universe": "two-teams",
              "scope": "Reused development holdout; not an untouched test set or proof of generalization.",
              "shotsSha256": hashlib.sha256((HERE / "data/shots.jsonl").read_bytes()).hexdigest(),
              "fullH2H": {name: summarize_on(ids, rows, truth) for name, rows in predictions.items() if name != "claude"},
              "sameClaudeEpisodes": {name: summarize_on(common, rows, truth) for name, rows in predictions.items()},
              "sameClaudeEpisodeIds": common,
              "minimumValidRate": .99}
    report["passesFormatGate"] = report["fullH2H"]["trained"]["validRate"] >= .99
    path = HERE / "results/v4-two-teams/comparison.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "sameClaudeEpisodeIds"}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
