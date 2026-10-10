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


def stat_rows(rows, predict, refs=None):
    out = []
    for shot in rows:
        prediction = predict(shot)
        answer = dict(prediction) if isinstance(prediction, dict) else {"quality": prediction}
        answer["reason"] = "训练集统计参考"
        if env.SPEC == "interval" and "low" not in answer:
            low, high = refs.zone_band.get((shot["zone"], shot["shotType"]), (0.0, 1.0))
            answer.update(low=min(low, answer["quality"]), high=max(high, answer["quality"]))
        parts = env.reward(answer, shot["quality"], [], False, "")
        out.append({**parts, "quality": shot["quality"]})
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
    p.add_argument("--reward", default="v1", choices=sorted(env.REWARD_PRESETS))
    p.add_argument("--output-dir", type=Path, default=HERE / "results")
    p.add_argument("--universe", choices=("all", "two-teams"), default="all")
    a = p.parse_args()
    env.use_reward(a.reward)
    a.output_dir.mkdir(parents=True, exist_ok=True)

    shots = env.select_universe(env.load_shots(HERE / "data" / "shots.jsonl"), a.universe)
    profiles = json.loads((HERE / "data" / "profiles.json").read_text())
    train, _ = env.split(shots)
    refs = env.References(train, profiles, a.universe)
    sets = {name: rows for name, rows in env.test_sets(shots).items() if rows}
    report = {"universe": a.universe, "policy": a.reward, "model": MODEL, "testSets": {k: len(v) for k, v in sets.items()}, "train": len(train), "results": {}}
    for name, rows in sets.items():
        report["results"][name] = {
            "stat_global": env.summarize(stat_rows(rows, lambda s: refs.global_mean, refs)),
            "stat_zone": env.summarize(stat_rows(rows, refs.baseline_zone, refs)),
            "stat_zone_move": env.summarize(stat_rows(rows, refs.baseline_combined, refs)),
        }
        if a.reward == "v4":
            def joint(shot):
                (mean, count, median, low, high), _ = refs.situation_values(shot)
                return {"quality": median, "low": low, "high": high}
            report["results"][name]["stat_joint_median"] = env.summarize(stat_rows(rows, joint, refs))
    if a.claude_n:
        import boto3
        client = boto3.Session(profile_name="nba", region_name="us-east-1").client("bedrock-runtime")
        rng = random.Random(a.seed)
        for name, rows in sets.items():
            sample = rng.sample(rows, min(a.claude_n, len(rows)))
            with ThreadPoolExecutor(max_workers=a.workers) as pool:
                episodes = list(pool.map(lambda s: claude_episode(client, s, refs), sample))
            report["results"][name]["claude"] = env.summarize(episodes)
            with (a.output_dir / f"claude-{name}.jsonl").open("w") as stream:
                for e in episodes:
                    stream.write(json.dumps(e, ensure_ascii=False) + "\n")
    (a.output_dir / "baselines.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print(json.dumps(report["results"], ensure_ascii=False, indent=1))


if __name__ == "__main__":
    (HERE / "results").mkdir(exist_ok=True)
    main()
