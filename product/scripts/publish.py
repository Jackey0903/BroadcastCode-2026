#!/usr/bin/env python3
"""Upload product UI, reviewed stories, and dense evidence frames to the retained stack.

Does not deploy infrastructure, submit an entry, or upload any credentials.
Source practice clips must already exist from the readiness setup.
"""
import argparse
import copy
import hashlib
import json
import mimetypes
import re
from pathlib import Path
import boto3

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / 'product'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--web-only', action='store_true')
args = parser.parse_args()
outputs_file = HERE / 'outputs.json'
if not outputs_file.exists():
    outputs_file = ROOT / 'readiness-lab/outputs.json'
outputs = json.loads(outputs_file.read_text())['BroadcastCodeTeam02Readiness20261006']
session = boto3.Session(profile_name='nba', region_name='us-east-1')
identity = session.client('sts').get_caller_identity()
if identity['Account'] != '962768510637' or ':assumed-role/NBAHackathonParticipantRole/' not in identity['Arn']:
    raise SystemExit('Wrong AWS account or role; aborting upload.')
s3 = session.client('s3')
bucket = outputs['Bucket']
uploaded = []
def upload(source, key, content_type=None):
    s3.upload_file(str(source), bucket, key, ExtraArgs={
        'ContentType': content_type or mimetypes.guess_type(source.name)[0] or 'application/octet-stream',
        'CacheControl': 'no-cache',
        'Metadata': {'sha256': hashlib.sha256(source.read_bytes()).hexdigest()}})
    uploaded.append(key)

for path in sorted((HERE / 'web').rglob('*')):
    if path.is_file() and path.suffix in ('.html', '.css', '.js', '.woff2', '.svg') and not path.name.startswith('test'):
        upload(path, 'product/' + path.relative_to(HERE / 'web').as_posix())
for path in sorted((HERE / 'data').rglob('*.json')):
    upload(path, 'product/data/' + path.relative_to(HERE / 'data').as_posix(), 'application/json')
if not args.web_only:
    manifest = json.loads(s3.get_object(Bucket=bucket, Key='config/samples.json')['Body'].read())
    for frame in sorted((ROOT/'data/reference/frames').glob('*.jpg')):
        if re.fullmatch(r'(?:flagg|amen)-[0-9]+(?:\.[0-9]+)?s\.jpg', frame.name):
            upload(frame, 'frames/' + frame.name, 'image/jpeg')
    dense = {
        'flagg': [('03s',3),('12s',12),('15.5s',15.5),('16.0s',16),('17.0s',17),('18s',18)],
        'amen': [('12s',12),('15s',15),('16.0s',16),('17.0s',17),('17.5s',17.5),('18s',18)],
    }
    for sample, frames in dense.items():
        manifest[sample]['frames'] = []
        for filename, seconds in frames:
            source = ROOT / f'data/reference/frames/{sample}-{filename}.jpg'
            key = f'frames/{source.name}'
            manifest[sample]['frames'].append({'timestamp_ms': int(seconds * 1000),
                's3_uri': f's3://{bucket}/{key}', 'format': 'jpeg'})
    s3.put_object(Bucket=bucket, Key='product/config/samples.json', Body=json.dumps(manifest, ensure_ascii=False).encode(),
                  ContentType='application/json', CacheControl='no-store')
    uploaded.append('product/config/samples.json')
print(json.dumps({'uploaded': uploaded, 'website': outputs['Website'] + '/product/'}, ensure_ascii=False))
