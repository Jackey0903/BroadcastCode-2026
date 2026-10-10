#!/usr/bin/env python3
"""Runs inside a CPU SageMaker training job: merged weights (input channel) + serve code -> /opt/ml/model.

SageMaker then writes model.tar.gz, so multi-GB weights never leave AWS.
"""
import shutil
from pathlib import Path

source = Path("/opt/ml/input/data/merged")
target = Path("/opt/ml/model")
for item in source.iterdir():
    if item.is_file():
        shutil.copy2(item, target / item.name)
code = target / "code"
code.mkdir(exist_ok=True)
for name in ("inference.py", "requirements.txt"):
    shutil.copy2(Path(__file__).resolve().parent / "serve" / name, code / name)
print("packaged:", sorted(p.name for p in target.rglob("*") if p.is_file()), flush=True)
