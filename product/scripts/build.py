#!/usr/bin/env python3
"""Build product assets locally with the exact audited SDK versions.

First install product/agent/requirements.txt into readiness-lab/.venv:
readiness-lab/.venv/bin/python -m pip install -r product/agent/requirements.txt
Then run readiness-lab/.venv/bin/python product/scripts/build.py.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import zipfile
from build_dependencies import BuildDependencyError, verify_dependencies

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / 'product'
BUILD = HERE / 'build'
try:
    sdk_versions = verify_dependencies(HERE / 'agent/requirements.txt')
except BuildDependencyError as error:
    raise SystemExit(str(error)) from error
# No deployment artifact is created or replaced before the version check.
BUILD.mkdir(exist_ok=True)
expected = json.loads((ROOT / 'readiness-lab/tool-fingerprints.json').read_text())
for relative, digest in expected.items():
    path = ROOT / 'readiness-lab/build' / relative
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise SystemExit('Verified media tools missing. Run readiness-lab/prepare_build.py first.')

sdk_files = []
for module in ('boto3', 'botocore', 's3transfer', 'jmespath', 'dateutil', 'urllib3', 'six'):
    spec = importlib.util.find_spec(module)
    if spec is None or spec.origin is None:
        raise SystemExit('Use readiness-lab/.venv/bin/python or install the pinned requirements first.')
    origin = Path(spec.origin)
    if spec.submodule_search_locations:
        for path in sorted(origin.parent.rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix not in ('.pyc', '.pyo'):
                sdk_files.append((path, path.relative_to(origin.parent.parent).as_posix()))
    else:
        sdk_files.append((origin, origin.name))

with zipfile.ZipFile(BUILD / 'agent.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
    for path, relative in sdk_files:
        archive.write(path, relative)
    for path in sorted((HERE / 'agent').glob('*.py')):
        if not path.name.startswith('test_'):
            archive.write(path, path.name)

lambda_artifacts = {}
for name in ('worker', 'delivery'):
    destination = BUILD / name
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir()
    for path, relative in sdk_files:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    shutil.copyfile(HERE / 'agent/story_contract.py', destination / 'story_contract.py')
    for path in sorted((HERE / name).glob('*.py')):
        if not path.name.startswith('test_'):
            shutil.copyfile(path, destination / path.name)
    if name == 'worker':
        # Frozen inference bridge only: no GPU/training packages or local secrets.
        rl_files = ('product_bridge.py', 'player_comparison.py', 'evidence_client.py',
                    'evidence_env.py', 'evidence_store.py', 'depth_tasks.py',
                    'data/evidence/store.json', 'results/evidence-v1/runtime-handoff.json')
        for relative in rl_files:
            target = destination / 'rl' / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(HERE / 'rl' / relative, target)
    lambda_artifacts[name] = sum(path.is_file() for path in destination.rglob('*'))
print(json.dumps({'agentBytes': (BUILD / 'agent.zip').stat().st_size,
                  'workerFiles': lambda_artifacts['worker'], 'deliveryFiles': lambda_artifacts['delivery'],
                  'mediaToolHashesVerified': True,
                  'sdkVersions': sdk_versions}))
