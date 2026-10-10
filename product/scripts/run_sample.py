#!/usr/bin/env python3
"""Reproduce a registered product sample through its real API (not the official evaluation schema)."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import urllib.error
import urllib.request
from deployment import load_outputs

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--sample', choices=['flagg', 'amen'], required=True)
parser.add_argument('--wait', action='store_true')
args = parser.parse_args()
BASE = load_outputs()['Website'].rstrip('/')
body = json.dumps({'sample': args.sample, 'mode': 'story'}, separators=(',', ':')).encode()
request = urllib.request.Request(BASE + '/api/jobs', data=body, method='POST', headers={
    'Content-Type': 'application/json', 'x-amz-content-sha256': hashlib.sha256(body).hexdigest()})
# Never retry submission: a lost response does not prove the server rejected it.
try:
    with urllib.request.urlopen(request, timeout=30) as response:
        submitted = json.load(response)
except Exception as error:
    raise SystemExit(f'Submission outcome not confirmed; do not blindly retry. {type(error).__name__}')
job_id = submitted.get('jobId', '')
if len(job_id) != 32 or any(c not in '0123456789abcdef' for c in job_id):
    raise SystemExit('Submission did not return a valid job id; do not blindly retry.')
print(json.dumps({'jobId': job_id, 'sample': args.sample, 'statusUrl': BASE + '/api/jobs/' + job_id}), flush=True)
if not args.wait:
    raise SystemExit(0)
deadline = time.monotonic() + 1200
last_stage = None
while time.monotonic() < deadline:
    try:
        with urllib.request.urlopen(BASE + '/api/jobs/' + job_id, timeout=30) as response:
            job = json.load(response)
    except (urllib.error.URLError, TimeoutError):
        time.sleep(5)
        continue
    stage = (job.get('status'), job.get('stage'))
    if stage != last_stage:
        print(json.dumps({'jobId': job_id, 'status': stage[0], 'stage': stage[1]}, ensure_ascii=False), flush=True)
        last_stage = stage
    if stage[0] in ('completed', 'failed'):
        output = ROOT / 'build/client-jobs' / (job_id + '.json')
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(job, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({'resultFile': str(output), 'videoUrl': job.get('videoUrl'), 'error': job.get('error')}, ensure_ascii=False), flush=True)
        raise SystemExit(0 if stage[0] == 'completed' else 1)
    time.sleep(5)
raise SystemExit(f'Stopped polling; task may still be running. Query the same jobId {job_id}.')
