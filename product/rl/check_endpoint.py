#!/usr/bin/env python3
"""End-to-end check of the live rl-scout endpoint on the two practice-clip shots (official rows)."""
import json
from pathlib import Path
import time

import boto3

from scout_client import Scout, sagemaker_invoker

HERE = Path(__file__).resolve().parent
FIXTURES = HERE.parents[1] / "readiness-lab" / "fixtures" / "official"
CASES = [("nba-gpshot-amen-0022500491.json", 396), ("nba-gpshot-flagg-0022500701.json", 666)]

if __name__ == "__main__":
    runtime = boto3.Session(profile_name="nba", region_name="us-east-1").client("sagemaker-runtime")
    scout = Scout(sagemaker_invoker("rl-scout", client=runtime), tables_path=HERE / "data" / "reference_tables.json")
    report = []
    for name, event in CASES:
        data = json.loads((FIXTURES / name).read_text())["data"]
        row = next(r for r in data["shotList"] if r["eventId"] == event)
        started = time.time()
        result = scout.analyse(row, data["playerId"], official_quality=row["value"])
        report.append({"case": name, "eventId": event, "official": row["value"], "seconds": round(time.time() - started, 2), **result})
        print(json.dumps(report[-1], ensure_ascii=False), flush=True)
    (HERE / "runs").mkdir(exist_ok=True)
    (HERE / "runs" / f"endpoint-check-{time.strftime('%m%d-%H%M%S')}.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
