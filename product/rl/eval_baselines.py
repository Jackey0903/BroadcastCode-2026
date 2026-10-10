#!/usr/bin/env python3
"""Baselines on the RL-SCOUT test sets: statistics (no learning) and Claude via Bedrock.

Claude gets exactly the policy's protocol: same system prompt, observation, JSON tool requests
and tool results, at most two turns, scored by the same verifiable reward.

    python3 product/rl/eval_baselines.py --claude-n 120
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import random
import time

import scout_env as env

HERE = Path(__file__).resolve().parent
MODEL = "global.anthropic.claude-sonnet-4-6"


def stat_rows(rows, predict):
    out = []
    for shot in rows:
        prediction = predict(shot)
        out.append({"prediction": prediction, "quality": shot["quality"], "format": 1.0, "grounded": 1.0, "tools": 0,
                    "total": env.WEIGHTS["calibration"] * max(0.0, 1 - ((prediction - shot["quality"]) / env.CALIBRATION_SCALE) ** 2)
                    + env.WEIGHTS["format"] + env.WEIGHTS["grounded"]})
    return out


def claude_episode(client, shot, refs):
    messages = [{"role": "user", "content": [{"text": env.observation(shot)}]}]
    context, tools, invalid, answer, turns = env.observation(shot), [], False, None, []
    for turn in range(2):
        for attempt in range(4):
            try:
                response = client.converse(modelId=MODEL, system=[{"text": env.SYSTEM_PROMPT}], messages=messages,
                                           inferenceConfig={"maxTokens": 300, "temperature": 0})
                break
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(2 * 2 ** attempt)
        text = "".join(part.get("text", "") for part in response["output"]["message"]["content"])
        turns.append(text)
        kind, payload, bad = env.parse_action(text)
        if kind == "answer":
            answer = payload
            break
        if kind == "tools" and turn == 0:
            tools, invalid = payload, bad
            message = env.tool_message(payload, shot, refs)["content"]
            context += "\n" + message
            messages += [{"role": "assistant", "content": [{"text": text}]},
                         {"role": "user", "content": [{"text": message}]}]
            continue
        invalid = True
        break
    if answer is None:
        invalid = True
    parts = env.reward(answer, shot["quality"], tools, invalid, context)
    return {**parts, "quality": shot["quality"], "turns": turns, "tools": len(tools), "toolNames": tools,
            "shot": {k: shot[k] for k in ("gameId", "playerId", "eventId", "shotDesc", "zone", "shotType")}}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--claude-n", type=int, default=120, help="episodes per test set for Claude (cost control)")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--seed", type=int, default=7)
    a = p.parse_args()

    shots = env.load_shots(HERE / "data" / "shots.jsonl")
    profiles = json.loads((HERE / "data" / "profiles.json").read_text())
    train, _ = env.split(shots)
    refs = env.References(train, profiles)
    sets = env.test_sets(shots)
    report = {"model": MODEL, "testSets": {k: len(v) for k, v in sets.items()}, "train": len(train), "results": {}}
    for name, rows in sets.items():
        report["results"][name] = {
            "stat_global": env.summarize(stat_rows(rows, lambda s: refs.global_mean)),
            "stat_zone": env.summarize(stat_rows(rows, refs.baseline_zone)),
            "stat_zone_move": env.summarize(stat_rows(rows, refs.baseline_combined)),
        }
    if a.claude_n:
        import boto3
        client = boto3.Session(profile_name="nba", region_name="us-east-1").client("bedrock-runtime")
        rng = random.Random(a.seed)
        for name, rows in sets.items():
            sample = rng.sample(rows, min(a.claude_n, len(rows)))
            with ThreadPoolExecutor(max_workers=a.workers) as pool:
                episodes = list(pool.map(lambda s: claude_episode(client, s, refs), sample))
            report["results"][name]["claude"] = env.summarize(episodes)
            with (HERE / "results" / f"claude-{name}.jsonl").open("w") as stream:
                for e in episodes:
                    stream.write(json.dumps(e, ensure_ascii=False) + "\n")
    (HERE / "results" / "baselines.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print(json.dumps(report["results"], ensure_ascii=False, indent=1))


if __name__ == "__main__":
    (HERE / "results").mkdir(exist_ok=True)
    main()
