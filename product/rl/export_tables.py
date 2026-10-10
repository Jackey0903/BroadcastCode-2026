#!/usr/bin/env python3
"""Write product/rl/data/reference_tables.json: the runtime tool back-ends (training split only)."""
import json
from pathlib import Path

import scout_env as env

HERE = Path(__file__).resolve().parent

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", default="v2", choices=sorted(env.REWARD_PRESETS))
    parser.add_argument("--output", type=Path, default=HERE / "data" / "reference_tables.json")
    parser.add_argument("--universe", choices=("all", "two-teams"), default="all")
    args = parser.parse_args()
    shots = env.select_universe(env.load_shots(HERE / "data" / "shots.jsonl"), args.universe)
    profiles = json.loads((HERE / "data" / "profiles.json").read_text())
    train, _ = env.split(shots)
    env.use_reward(args.policy)
    tables = env.References(train, profiles, args.universe).to_tables()
    tables["universe"] = args.universe
    tables["trainingShots"] = len(train)
    tables["policy"] = args.policy
    tables["spec"] = env.SPEC
    tables["pointStatistic"] = "conditional_median" if args.policy == "v4" else "typical_quality_estimate"
    args.output.write_text(json.dumps(tables, ensure_ascii=False))
    print(f"zone {len(tables['zone'])} · move {len(tables['move'])} · profiles {len(tables['profiles'])} · from {len(train)} training shots")
