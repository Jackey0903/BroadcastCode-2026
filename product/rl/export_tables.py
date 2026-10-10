#!/usr/bin/env python3
"""Write product/rl/data/reference_tables.json: the runtime tool back-ends (training split only)."""
import json
from pathlib import Path

import scout_env as env

HERE = Path(__file__).resolve().parent

if __name__ == "__main__":
    shots = env.load_shots(HERE / "data" / "shots.jsonl")
    profiles = json.loads((HERE / "data" / "profiles.json").read_text())
    train, _ = env.split(shots)
    tables = env.References(train, profiles).to_tables()
    (HERE / "data" / "reference_tables.json").write_text(json.dumps(tables, ensure_ascii=False))
    print(f"zone {len(tables['zone'])} · move {len(tables['move'])} · profiles {len(tables['profiles'])} · from {len(train)} training shots")
