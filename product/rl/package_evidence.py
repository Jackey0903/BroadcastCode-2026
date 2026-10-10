#!/usr/bin/env python3
"""Merge the registered RL evidence adapter on CPU and emit an auditable model.

Runs in a bounded SageMaker CPU training job. The original SFT-selected training
report remains intact; this separately authorized package uses the RL adapter.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import tarfile

SOURCE_JOB = "rl-scout-evidence-3b-two-teams-1010-052032"
BASE_MODEL = "Qwen/Qwen2.5-3B-Instruct"
BASE_REVISION = "aa8e72537993ba99e69dfaafa59ed015b17504d1"
HERE = Path(__file__).resolve().parent


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_channel(root, channel, name):
    paths = list((root / channel).rglob(name))
    if len(paths) != 1 or not paths[0].is_file():
        raise ValueError(f"Expected exactly one {channel}/{name}")
    return paths[0]


def validate_inputs(input_root, expected):
    if (expected.get("sourceTrainingJob") != SOURCE_JOB or expected.get("baseModel") != BASE_MODEL
            or expected.get("baseRevision") != BASE_REVISION or expected.get("selectedStage") != "rl"):
        raise ValueError("Package is restricted to the registered RL evidence checkpoint")
    report_path = read_channel(input_root, "report", "training-report.json")
    report = json.loads(report_path.read_text())
    if (report.get("sourceJob") != SOURCE_JOB or report.get("model") != BASE_MODEL
            or report.get("baseRevision") != BASE_REVISION):
        raise ValueError("Training report identity/revision mismatch")
    for key in ("storeSha256", "tasksSha256"):
        if report[key] != expected[key]:
            raise ValueError("Registered input hash mismatch: " + key)
    metrics_path = read_channel(input_root, "metrics", "metrics.jsonl")
    metrics = [json.loads(line) for line in metrics_path.read_text().splitlines() if line.strip()]
    rl = [row for row in metrics if row.get("kind") == "rl"]
    if [r["step"] for r in rl] != list(range(1, report["rlSteps"] + 1)):
        raise ValueError("Incomplete RL update log")
    updates = sum(r["updateGroups"] > 0 for r in rl)
    update_groups = sum(r["updateGroups"] for r in rl)
    if updates != expected["optimizerUpdateSteps"] or update_groups != expected["updateGroups"] or updates < 1:
        raise ValueError("Registered real RL update count mismatch")
    archive = read_channel(input_root, "source", "sourcedir.tar.gz")
    if file_sha(archive) != expected["sourceArchiveSha256"]:
        raise ValueError("Original training source archive hash mismatch")
    frozen = {}
    with tarfile.open(archive, "r:gz") as tar:
        for name in ("data/evidence/store.json", "data/evidence/tasks.jsonl", "package-manifest.json"):
            item = tar.getmember(name)
            if not item.isfile() or item.size > 16 * 1024 * 1024:
                raise ValueError("Unexpected training archive member: " + name)
            frozen[name] = tar.extractfile(item).read()
    store = json.loads(frozen["data/evidence/store.json"])
    tasks = [json.loads(line) for line in frozen["data/evidence/tasks.jsonl"].decode().splitlines() if line.strip()]
    if digest(store) != report["storeSha256"] or digest(tasks) != report["tasksSha256"]:
        raise ValueError("Frozen source data differ from completed training report")
    if store.get("schema") != "rl-scout-evidence-store-v1":
        raise ValueError("Wrong store schema")
    adapter = read_channel(input_root, "adapter", "adapter_model.safetensors")
    config_path = adapter.parent / "adapter_config.json"
    config = json.loads(config_path.read_text())
    if config.get("base_model_name_or_path") != BASE_MODEL or config.get("peft_type") != "LORA":
        raise ValueError("Wrong adapter base/model type")
    metadata = {
        "schema": "rl-scout-evidence-lineage-v1", "policy": "evidence-v1", "model": BASE_MODEL,
        "baseModel": BASE_MODEL, "baseRevision": BASE_REVISION, "sourceTrainingJob": SOURCE_JOB,
        "selectedStage": "rl", "trainingSelectedStage": report["selectedStage"], "actualRL": True,
        "optimizerUpdateSteps": updates, "updateGroups": update_groups, "rlSamplingSteps": len(rl),
        "sftExamplesOptimized": report["sftExamplesOptimized"],
        "storeSha256": report["storeSha256"], "storeContentSha256": store.get("contentSha256"),
        "tasksSha256": report["tasksSha256"], "sourceArchiveSha256": expected["sourceArchiveSha256"],
        "adapterSha256": file_sha(adapter), "adapterConfigSha256": file_sha(config_path),
        "metricsSha256": file_sha(metrics_path), "trainingReportSha256": file_sha(report_path),
        "frozenStoreFileSha256": hashlib.sha256(frozen["data/evidence/store.json"]).hexdigest(),
        "frozenTasksFileSha256": hashlib.sha256(frozen["data/evidence/tasks.jsonl"]).hexdigest(),
        "rawEvaluationReleaseGatePassed": False, "semanticValidationRequired": True,
        "selectionDisclosure": "Original report selected SFT on validation tie. This package uses the RL adapter for separately authorized, program-validated integration; it does not revise the original failure or claim an RL accuracy improvement.",
        "rawValidation": report["evaluation"]["rl"]["val"],
        "claimBoundary": "Text evidence-selection model, not a visual encoder or an independent source of numerical facts."}
    return metadata, adapter.parent, {"report": report_path, "metrics": metrics_path, "archive": archive}, frozen


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input-root", default="/opt/ml/input/data")
    p.add_argument("--output", default="/opt/ml/model")
    p.add_argument("--expected", default=str(HERE / "expected-source.json"))
    p.add_argument("--validate-only", action="store_true")
    a = p.parse_args()
    expected = json.loads(Path(a.expected).read_text())
    lineage, adapter_dir, paths, frozen = validate_inputs(Path(a.input_root), expected)
    if a.validate_only:
        print(json.dumps(lineage, ensure_ascii=False, indent=2))
        return
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer
    torch.set_num_threads(8)
    print("Validated registered adapter and frozen source inputs; loading pinned base on CPU.", flush=True)
    base = AutoModelForCausalLM.from_pretrained(BASE_MODEL, revision=BASE_REVISION,
                torch_dtype=torch.bfloat16, device_map={"": "cpu"}, low_cpu_mem_usage=True)
    model = PeftModel.from_pretrained(base, adapter_dir, is_trainable=False).merge_and_unload(safe_merge=True)
    target = Path(a.output)
    target.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(target, safe_serialization=True, max_shard_size="2GB")
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, revision=BASE_REVISION)
    tokenizer.save_pretrained(target)
    code = target / "code"
    code.mkdir(exist_ok=True)
    for name in ("inference.py", "requirements.txt"):
        shutil.copy2(HERE / "serve_evidence" / name, code / name)
    provenance = target / "provenance"
    provenance.mkdir(exist_ok=True)
    for name, source in paths.items():
        shutil.copy2(source, provenance / {"report": "training-report.json", "metrics": "metrics.jsonl",
                                        "archive": "training-sourcedir.tar.gz"}[name])
    shutil.copy2(Path(a.expected), provenance / "expected-source.json")
    (provenance / "training-package-manifest.json").write_bytes(frozen["package-manifest.json"])
    lineage["mergedAt"] = datetime.now(timezone.utc).isoformat()
    lineage["packageJob"] = __import__("os").environ.get("RL_PACKAGE_JOB")
    lineage["modelWeights"] = {p.name: file_sha(p) for p in sorted(target.glob("*.safetensors"))}
    if not lineage["modelWeights"]:
        raise ValueError("Merge produced no model weights")
    lineage["mergedWeightsSha256"] = digest(lineage["modelWeights"])
    lineage["handlerSha256"] = file_sha(code / "inference.py")
    (target / "lineage.json").write_text(json.dumps(lineage, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"packaged": True, "sourceTrainingJob": SOURCE_JOB, "selectedStage": "rl",
                      "adapterSha256": lineage["adapterSha256"], "mergedWeightsSha256": lineage["mergedWeightsSha256"],
                      "output": str(target)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
