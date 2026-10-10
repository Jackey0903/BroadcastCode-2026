"""Read the current non-secret deployment target and reject stale account outputs.

This module performs no AWS requests. Update product/deployment.json only after
the Portal allocation is verified; never infer the account from cached outputs.
"""
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parents[1]


def load_deployment(path=None):
    target = json.loads(Path(path or HERE / 'deployment.json').read_text())
    if not re.fullmatch(r'[0-9]{12}', str(target.get('account', ''))):
        raise ValueError('Deployment account must be a verified 12-digit Portal allocation.')
    if target.get('region') != 'us-east-1':
        raise ValueError('Competition resources must remain in us-east-1.')
    if target.get('profile') != 'nba':
        raise ValueError('Competition operations require the nba profile.')
    if target.get('participantRole') != 'NBAHackathonParticipantRole':
        raise ValueError('Unexpected competition participant role.')
    if target.get('workloadRole') != 'NBAHackathonWorkloadRole':
        raise ValueError('Unexpected organizer workload role.')
    if target.get('stackName') != 'BroadcastCodeTeam02Readiness20261006':
        raise ValueError('Keep the existing product Stack identity.')
    return target


def validate_identity(identity, target):
    expected = f"arn:aws:sts::{target['account']}:assumed-role/{target['participantRole']}/"
    if identity.get('Account') != target['account'] or not identity.get('Arn', '').startswith(expected):
        raise ValueError('Wrong AWS account or role; aborting product operation.')


def load_outputs(path=None, target=None):
    target = target or load_deployment()
    file = Path(path or HERE / 'outputs.json')
    if not file.is_file():
        raise ValueError('Current product outputs.json is missing. Deploy product/ to the verified account first; old readiness outputs are not reused.')
    values = json.loads(file.read_text()).get(target['stackName'])
    if not isinstance(values, dict):
        raise ValueError('Product outputs do not contain the configured Stack.')
    runtime_prefix = f"arn:aws:bedrock-agentcore:{target['region']}:{target['account']}:runtime/"
    if not values.get('RuntimeArn', '').startswith(runtime_prefix):
        raise ValueError('Product outputs belong to another account or region. Regenerate outputs by deploying to the current Portal allocation.')
    if values.get('Account', target['account']) != target['account'] or values.get('Region', target['region']) != target['region']:
        raise ValueError('Product output account or region does not match the allocation.')
    site = urlsplit(values.get('Website', ''))
    if (site.scheme != 'https' or not site.hostname or not site.hostname.endswith('.cloudfront.net')
            or site.username or site.password or site.port or site.path not in ('', '/') or site.query or site.fragment):
        raise ValueError('Product Website output must be an HTTPS CloudFront origin.')
    if not values.get('Bucket'):
        raise ValueError('Product Bucket output is missing.')
    return values
