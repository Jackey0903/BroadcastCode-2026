#!/usr/bin/env python3
"""Publish verified registered practice media and UI to the current product bucket.

Default initializes an empty bucket. --web-only checks every current media,
frame, historical analysis and both sample configurations before writes.
--dry-run verifies/snapshots local assets without importing AWS SDK or making
requests. Never deploys, submits an entry or seeds historical job records.
"""
import argparse
import json
from pathlib import Path
from deployment import load_deployment, load_outputs, validate_identity
from publication import build_plan, publish_plan

ROOT = Path(__file__).resolve().parents[2]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--web-only', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    target = load_deployment()
    outputs = load_outputs(target=target)
    # Complete every local verification before client creation or S3 writes.
    plan = build_plan(ROOT, outputs['Bucket'], outputs['Website'])
    if args.dry_run:
        print(json.dumps({'dryRun': True, 'webOnlyPrerequisitesNotQueried': args.web_only,
                          **plan.summary()}, ensure_ascii=False, indent=2))
        return 0
    import boto3
    session = boto3.Session(profile_name=target['profile'], region_name=target['region'])
    validate_identity(session.client('sts').get_caller_identity(), target)
    uploaded = publish_plan(plan, session.client('s3'), target['account'], args.web_only)
    print(json.dumps({'uploaded': uploaded, 'website': plan.website + '/product/',
                      'historicalRepublish': True, 'newInference': False, 'courtLabPublished': False}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
