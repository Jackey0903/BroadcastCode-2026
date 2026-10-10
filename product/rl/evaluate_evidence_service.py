#!/usr/bin/env python3
"""Run six bounded, real product requests against a verified evidence endpoint.

This checks the typed model-plus-validator service. It never changes the frozen
raw-model evaluation, retrains, deploys, or counts an unavailable result as success.
"""
import argparse
from datetime import datetime
import json
from pathlib import Path
import time
from zoneinfo import ZoneInfo

from evidence_client import EvidenceClient, default_request, sagemaker_invoker
from evidence_store import load_store

HERE = Path(__file__).resolve().parent
CASES = [("flagg", "gravity"), ("amen", "leverage"), ("flagg", "leverage"),
         ("amen", "gravity"), ("flagg", "shotdifficulty"), ("amen", "shotdifficulty")]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", default=str(HERE / "results/evidence-v1/endpoint-check.json"))
    parser.add_argument("--out", default=str(HERE / "results/evidence-v1/service-evaluation.json"))
    parser.add_argument("--cases", nargs="+", choices=["/".join(case) for case in CASES],
                        help="Only affected cases; preserve earlier successful calls instead of repeating them")
    args = parser.parse_args()
    checked = json.loads(Path(args.check).read_text())
    expected = checked["expectedLineage"]
    if expected["endpoint"] != "rl-scout":
        raise SystemExit("Only the verified team evidence endpoint is supported")
    store = load_store()
    client = EvidenceClient(sagemaker_invoker(expected["endpoint"], max_tokens=160),
                            expected_lineage=expected, store=store)
    out = Path(args.out)
    if out.exists():
        raise SystemExit("Use a new --out path to preserve prior successes and failures")
    out.parent.mkdir(parents=True, exist_ok=True)
    report = {"schema": "rl-scout-evidence-product-acceptance-v1", "startedAt": now(),
              "scope": "Two registered practice events, three typed depth choices each; no video quality score",
              "system": "RL checkpoint + explicit typed metrics + source validation + at most one model correction",
              "rawModelEvaluationGatePassed": False, "rlGainOverSftObserved": 0,
              "deployment": expected, "cases": [], "complete": False, "releaseEligible": False,
              "workerIntegrated": False, "renderVerified": False}

    def save():
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")

    save()
    # Main demonstration requests first; variations check each supported depth tool.
    cases = [tuple(case.split("/")) for case in args.cases] if args.cases else CASES
    if len(set(cases)) != len(cases):
        raise SystemExit("Duplicate cases are not supported")
    report["requestedCases"] = ["/".join(case) for case in cases]
    report["requestTimeoutSeconds"] = client.invoke.request_timeout_seconds
    for story, depth in cases:
        request = default_request(story, depth_family=depth, store=store)
        started = time.monotonic()
        result = client.analyse(request)
        selected = {(r["family"], r["metric"], r["grain"]) for r in result.get("evidence", [])}
        required = {(r["family"], r["metric"], r["grain"]) for r in request["requiredMetrics"]}
        passed = (result.get("available") is True and result.get("lineageVerified") is True
                  and result.get("actualRL") is True and result.get("modelInvoked") is True
                  and selected == required)
        case = {"story": story, "depthFamily": depth, "passed": passed,
                "seconds": round(time.monotonic() - started, 3), "result": result}
        report["cases"].append(case)
        save()
        print(json.dumps({k: v for k, v in case.items() if k != "result"}), flush=True)
    report.update(complete=True, completedAt=now(),
                  selectedCasesPassed=all(r["passed"] for r in report["cases"]),
                  releaseEligible=set(cases) == set(CASES) and all(r["passed"] for r in report["cases"]),
                  successes=sum(r["passed"] for r in report["cases"]))
    save()
    print(json.dumps({k: report[k] for k in ("complete", "successes", "releaseEligible")}), flush=True)


def now():
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()


if __name__ == "__main__":
    main()
