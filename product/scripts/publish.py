#!/usr/bin/env python3
"""Publish verified registered practice media and UI to the current product bucket.

Default initializes an empty bucket. --web-only checks every current media,
frame, historical analysis and both sample configurations before writes.
--reuse-unchanged verifies existing objects and uploads only missing/changed
objects. It cannot be combined with --web-only.
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
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--web-only', action='store_true')
    mode.add_argument('--reuse-unchanged', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    if not args.dry_run and (ROOT / "product/web/pixel.html").is_file():
        raise SystemExit("Practice-page publication is retired. Use publish_formal.py for glass or publish_pixel_formal.py for the formal pixel page.")
    target = load_deployment()
    outputs = load_outputs(target=target)
    # Complete every local verification before client creation or S3 writes.
    plan = build_plan(ROOT, outputs['Bucket'], outputs['Website'], current_runtime_arn=outputs['RuntimeArn'])
    if args.dry_run:
        print(json.dumps({'dryRun': True, 'webOnlyPrerequisitesNotQueried': args.web_only,
                          'reuseUnchangedNotQueried': args.reuse_unchanged,
                          **plan.summary()}, ensure_ascii=False, indent=2))
        return 0
    import boto3
    from botocore.config import Config
    session = boto3.Session(profile_name=target['profile'], region_name=target['region'])
    validate_identity(session.client('sts').get_caller_identity(), target)
    s3 = session.client('s3', config=Config(connect_timeout=10, read_timeout=120,
                       retries={'mode': 'standard', 'total_max_attempts': 2}))
    uploaded = publish_plan(plan, s3, target['account'], args.web_only,
        progress=lambda key, size: print(json.dumps({'published': key, 'bytes': size}), flush=True),
        reuse_unchanged=args.reuse_unchanged)
    print(json.dumps({'uploaded': uploaded, 'website': plan.website + '/product/',
                      'historicalRepublish': plan.historical_republish, 'newInference': False, 'courtLabPublished': False,
                      'reuseUnchanged': args.reuse_unchanged,
                      'trainingCamp': plan.summary()['trainingCamp'],
                      'reusedVerifiedObjects': len(plan.assets) - len(uploaded) if args.reuse_unchanged else 0}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
