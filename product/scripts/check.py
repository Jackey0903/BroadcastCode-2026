#!/usr/bin/env python3
"""Offline product gate: python3 product/scripts/check.py [--quick|--full].

Full (default) runs source/privacy checks, syntax checks, every existing product
suite and the actual CDK app. Quick omits the suites, never the CDK assertions.
No AWS credentials, source videos, FFmpeg binaries or cloud outputs are needed.
CDK uses real application/agent/worker sources with a clearly named synthetic
media-layer asset in a temporary tree. This checks the infrastructure template,
not the deployable SDK/FFmpeg package, inference, GPU or browser playback.
Install the locked JS dependencies first: npm ci --prefix product --ignore-scripts.
"""
import argparse
import ast
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

ROOT = Path(__file__).resolve().parents[2]
PRODUCT = ROOT / 'product'
OLD_ACCOUNT = '962768510637'
PYTHON_SUITES = {'agent': 20, 'worker': 8, 'api': 12, 'data': 16, 'scripts': 21, 'rl': 42, 'delivery': 22}
EXCLUDED = {'node_modules', 'build', 'cdk.out', '.venv', '__pycache__', '.git'}


class CheckFailure(Exception):
    pass


def execute(command, *, env, cwd=ROOT, timeout=120):
    try:
        result = subprocess.run(command, cwd=cwd, env=env, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise CheckFailure(f'{Path(command[0]).name}: {type(error).__name__}') from error
    if result.returncode:
        tail = '\n'.join(result.stdout.splitlines()[-45:])
        raise CheckFailure(f'{Path(command[0]).name} exited {result.returncode}\n{tail}')
    return result.stdout


def source_files():
    result = []
    for directory, children, files in os.walk(PRODUCT):
        children[:] = [name for name in children if name not in EXCLUDED]
        for name in files:
            file = Path(directory) / name
            if file.suffix in ('.py', '.js', '.cjs', '.mjs'):
                result.append(file)
    return sorted(result)


def privacy_check(env):
    # Ignored local PDFs, credentials and media are never opened or packaged.
    names = execute(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], env=env).split('\0')
    forbidden = re.compile(r'(^|/)(?:\.aws|\.env(?:\..*)?|credentials|.*\.(?:pem|key))($|/)|'
                           r'账号开通通知.*\.pdf$|登录地址更正通知.*\.pdf$', re.I)
    secrets = [re.compile(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
               re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
               re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,})\b'),
               re.compile(r'(?im)^\s*(?:export\s+)?(?:AWS_SECRET_ACCESS_KEY|AWS_SESSION_TOKEN|aws_secret_access_key|aws_session_token)\s*=\s*["\x27]?[A-Za-z0-9+/]{20,}')]
    for name in sorted(set(filter(None, names))):
        file = ROOT / name
        if forbidden.search(name) and not name.endswith('.env.example'):
            raise CheckFailure(f'Sensitive source path must not be committed: {name}')
        if not file.is_file() or file.is_symlink():
            continue
        try:
            content = file.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            continue
        if any(pattern.search(content) for pattern in secrets):
            # Report the filename only; never echo the matching secret.
            raise CheckFailure(f'Possible credential in tracked source: {name}')


def offline_environment(temp):
    guard = temp / 'network-guard'
    guard.mkdir()
    (guard / 'sitecustomize.py').write_text('''import ipaddress, socket
def local(host):
    if host == 'localhost': return True
    try: return ipaddress.ip_address(host).is_loopback
    except (ValueError, TypeError): return False
original_connect = socket.socket.connect
original_connect_ex = socket.socket.connect_ex
original_dns = socket.getaddrinfo
def connect(self, address):
    if self.family in (socket.AF_INET, socket.AF_INET6) and not local(address[0]):
        raise RuntimeError('Quality gate forbids external network connections')
    return original_connect(self, address)
def connect_ex(self, address):
    if self.family in (socket.AF_INET, socket.AF_INET6) and not local(address[0]):
        raise RuntimeError('Quality gate forbids external network connections')
    return original_connect_ex(self, address)
def dns(host, *args, **kwargs):
    if not local(host): raise RuntimeError('Quality gate forbids external DNS')
    return original_dns(host, *args, **kwargs)
socket.socket.connect = connect
socket.socket.connect_ex = connect_ex
socket.getaddrinfo = dns
''')
    (guard / 'node-network.cjs').write_text('''const net = require('node:net');
const original = net.Socket.prototype.connect;
net.Socket.prototype.connect = function(...args) {
  const values = Array.isArray(args[0]) ? args[0] : args;
  const first = values[0];
  const host = first && typeof first === 'object' ? first.host || 'localhost' : typeof values[1] === 'string' ? values[1] : 'localhost';
  if (!(host === 'localhost' || host === '::1' || /^127\\./.test(host))) throw new Error('Quality gate forbids external network connections');
  return original.apply(this, args);
};
globalThis.fetch = async () => { throw new Error('Quality gate forbids live fetch; tests use explicit doubles'); };
''')
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(('AWS_', 'CDK_')) and key not in ('PYTHONPATH', 'NODE_OPTIONS')}
    env.update({'AWS_EC2_METADATA_DISABLED': 'true', 'AWS_CONFIG_FILE': str(guard / 'no-config'),
                'AWS_SHARED_CREDENTIALS_FILE': str(guard / 'no-credentials'),
                'PYTHONPATH': str(guard), 'PYTHONDONTWRITEBYTECODE': '1',
                'NODE_OPTIONS': '--require=' + json.dumps(str(guard / 'node-network.cjs'))})
    return env


def syntax_check(env):
    files = source_files()
    python_count = js_count = 0
    for file in files:
        if file.suffix == '.py':
            try:
                ast.parse(file.read_text(encoding='utf-8'), filename=str(file))
            except SyntaxError as error:
                raise CheckFailure(f'{file.relative_to(ROOT)}:{error.lineno}: {error.msg}') from error
            python_count += 1
        else:
            execute(['node', '--check', str(file)], env=env)
            js_count += 1
    return python_count, js_count


def python_suite(name, minimum, env):
    output = execute([sys.executable, '-m', 'unittest', 'discover', '-s', str(PRODUCT / name), '-p', 'test_*.py'], env=env)
    match = re.search(r'Ran (\d+) tests? in ', output)
    if not match or int(match[1]) < minimum or re.search(r'skipped=\d+', output):
        raise CheckFailure(f'{name}: missing tests or skipped tests; expected at least {minimum}.')
    return int(match[1])


def node_suite(env):
    files = sorted((PRODUCT / 'web').glob('test-*.cjs')) + sorted((PRODUCT / 'tests').glob('test_*.js'))
    output = execute(['node', '--test', '--test-reporter=tap', *map(str, files)], env=env)
    totals = {key: int(value) for key, value in re.findall(r'^# (tests|pass|fail|skipped|cancelled) (\d+)\s*$', output, re.M)}
    if totals.get('tests', 0) < 134 or totals.get('pass') != totals.get('tests') or any(totals.get(k, 0) for k in ('fail', 'skipped', 'cancelled')):
        raise CheckFailure(f'Node: incomplete or skipped suites: {totals}')
    return totals['tests']


def run_tests(env):
    with ThreadPoolExecutor(max_workers=6) as pool:
        tasks = [pool.submit(python_suite, name, count, env) for name, count in PYTHON_SUITES.items()]
        tasks.append(pool.submit(node_suite, env))
        return sum(task.result() for task in tasks)


def assert_delivery_infrastructure(resources):
    """Check the synthesized application, never a separate hand-written fixture."""
    buses = {key: resource['Properties'] for key, resource in resources.items()
             if resource['Type'] == 'AWS::Events::EventBus'}
    if len(buses) != 1:
        raise CheckFailure('Delivery requires exactly one dedicated EventBridge event bus.')
    workflows = {key: resource['Properties'] for key, resource in resources.items()
                 if resource['Type'] == 'AWS::StepFunctions::StateMachine'}
    if not workflows or any(properties.get('StateMachineType', 'STANDARD') != 'STANDARD'
                            for properties in workflows.values()):
        raise CheckFailure('Delivery verification must use a STANDARD Step Functions workflow.')
    matching_rules = []
    for resource in resources.values():
        if resource['Type'] != 'AWS::Events::Rule':
            continue
        properties = resource['Properties']
        pattern = properties.get('EventPattern', {})
        if (pattern.get('source') == ['broadcastcode.product']
                and pattern.get('detail-type') == ['VideoRendered']):
            matching_rules.append(properties)
    if not matching_rules:
        raise CheckFailure('EventBridge must route broadcastcode.product / VideoRendered events.')
    if not any(any(key in json.dumps(rule.get('EventBusName', {})) for key in buses)
               and any(key in json.dumps(rule.get('Targets', [])) for key in workflows)
               for rule in matching_rules):
        raise CheckFailure('VideoRendered rule must connect the dedicated bus to the delivery workflow.')
    types = [resource['Type'] for resource in resources.values()]
    if 'AWS::CloudWatch::Dashboard' not in types or 'AWS::CloudWatch::Alarm' not in types:
        raise CheckFailure('Delivery requires a CloudWatch dashboard and operational alarms.')

    # This AWS-managed ID is the CACHING_DISABLED policy used by our CDK app.
    disabled = '4135ea2d-6df8-44a3-9df3-4b5a84be39ad'
    distributions = [resource['Properties']['DistributionConfig'] for resource in resources.values()
                     if resource['Type'] == 'AWS::CloudFront::Distribution']
    if len(distributions) != 1:
        raise CheckFailure('Product requires one CloudFront distribution.')
    configuration = distributions[0]
    if configuration.get('DefaultCacheBehavior', {}).get('CachePolicyId') != disabled:
        raise CheckFailure('Mutable product pages must retain CACHING_DISABLED.')
    behaviors = {item['PathPattern']: item for item in configuration.get('CacheBehaviors', [])}
    if behaviors.get('api/*', {}).get('CachePolicyId') != disabled:
        raise CheckFailure('Job API must retain CACHING_DISABLED.')
    for pattern in ('product/outputs/*', 'samples/*', 'frames/*'):
        policy = behaviors.get(pattern, {}).get('CachePolicyId')
        if not policy or policy == disabled:
            raise CheckFailure(f'Immutable media requires an enabled cache policy: {pattern}')
        # A custom policy must actually retain objects; a named Ref alone is
        # insufficient if its TTLs were accidentally configured to zero.
        if isinstance(policy, dict) and 'Ref' in policy:
            resource = resources.get(policy['Ref'], {})
            properties = resource.get('Properties', {}).get('CachePolicyConfig', {})
            if (resource.get('Type') != 'AWS::CloudFront::CachePolicy'
                    or properties.get('DefaultTTL', 0) <= 0 or properties.get('MaxTTL', 0) <= 0):
                raise CheckFailure(f'Media cache policy has no positive retention: {pattern}')


def cdk_check(temp, env):
    modules = PRODUCT / 'node_modules'
    if not (modules / 'aws-cdk-lib').is_dir():
        raise CheckFailure('Locked CDK dependency missing. Run npm ci --prefix product --ignore-scripts first.')
    target = json.loads((PRODUCT / 'deployment.json').read_text())
    context = json.loads((PRODUCT / 'cdk.json').read_text()).get('context', {})
    if target.get('account') != '555726205424' or target.get('region') != 'us-east-1' or target.get('profile') != 'nba':
        raise CheckFailure('Product deployment target differs from the verified formal allocation.')
    boundary = 'NBAHackathonParticipantBoundary'
    if context.get('@aws-cdk/core:permissionsBoundary') != {'name': boundary}:
        raise CheckFailure('Organizer CDK permissions boundary is missing or incorrect.')
    stage = temp / 'cdk-source' / 'product'
    stage.mkdir(parents=True)
    for name in ('app.js', 'deployment.json', 'cdk.json'):
        shutil.copyfile(PRODUCT / name, stage / name)
    (stage / 'node_modules').symlink_to(modules, target_is_directory=True)
    shutil.copytree(PRODUCT / 'api', stage / 'api', ignore=shutil.ignore_patterns('__pycache__'))
    build = stage / 'build'
    build.mkdir()
    with zipfile.ZipFile(build / 'agent.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for file in sorted((PRODUCT / 'agent').glob('*.py')):
            if not file.name.startswith('test_'):
                archive.write(file, file.name)
    shutil.copytree(PRODUCT / 'worker', build / 'worker', ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copyfile(PRODUCT / 'agent' / 'story_contract.py', build / 'worker' / 'story_contract.py')
    shutil.copytree(PRODUCT / 'delivery', build / 'delivery', ignore=shutil.ignore_patterns('__pycache__', 'test_*.py'))
    shutil.copyfile(PRODUCT / 'agent' / 'story_contract.py', build / 'delivery' / 'story_contract.py')
    layer = stage.parent / 'readiness-lab' / 'build' / 'layer'
    layer.mkdir(parents=True)
    (layer / 'SYNTHESIS_ONLY.txt').write_text('Offline template audit placeholder; contains no deployable FFmpeg tools.\n')
    assembly = temp / 'assembly'
    synth_env = dict(env, CDK_CONTEXT_JSON=json.dumps(context), CDK_OUTDIR=str(assembly))
    execute(['node', 'app.js'], env=synth_env, cwd=stage)
    name = target['stackName']
    paths = [assembly / 'manifest.json', assembly / f'{name}.template.json', assembly / f'{name}.assets.json']
    raw = '\n'.join(file.read_text() for file in paths)
    if OLD_ACCOUNT in raw:
        raise CheckFailure('Old practice account remains in the generated CDK template/assets.')
    manifest, template, assets = [json.loads(file.read_text()) for file in paths]
    if manifest['artifacts'][name]['environment'] != f"aws://{target['account']}/{target['region']}":
        raise CheckFailure('CDK assembly environment differs from the current allocation.')
    resources = template['Resources']
    assert_delivery_infrastructure(resources)
    roles = [r['Properties'] for r in resources.values() if r['Type'] == 'AWS::IAM::Role']
    if len(roles) < 2 or any(boundary not in json.dumps(role.get('PermissionsBoundary')) or target['account'] not in json.dumps(role.get('PermissionsBoundary')) for role in roles):
        raise CheckFailure('A generated IAM role lacks the organizer boundary in the formal account.')
    runtimes = [r['Properties'] for r in resources.values() if r['Type'] == 'AWS::BedrockAgentCore::Runtime']
    if len(runtimes) != 1 or any(target['account'] not in json.dumps(r['RoleArn']) or target['workloadRole'] not in json.dumps(r['RoleArn']) for r in runtimes):
        raise CheckFailure('AgentCore runtime is not using the formal organizer workload role.')
    buckets = {d['bucketName'] for asset in assets['files'].values() for d in asset['destinations'].values()}
    if buckets != {f"cdk-hnb659fds-assets-{target['account']}-{target['region']}"}:
        raise CheckFailure('CDK file assets would publish to an unexpected bootstrap bucket.')
    return len(resources), len(roles)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--quick', action='store_true', help='Privacy, syntax and CDK template; omit behavioral suites.')
    mode.add_argument('--full', action='store_true', help='Run all checks (default).')
    args = parser.parse_args()
    start = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix='broadcastcode-quality-') as directory:
            temp = Path(directory)
            env = offline_environment(temp)
            privacy_check(env)
            print('PASS source privacy (no credentials or account notices)', flush=True)
            python_count, js_count = syntax_check(env)
            print(f'PASS syntax: {python_count} Python, {js_count} JavaScript files', flush=True)
            if not args.quick:
                count = run_tests(env)
                print(f'PASS behavioral tests: {count}, no skips, external network blocked', flush=True)
            resources, roles = cdk_check(temp, env)
            print(f'PASS offline CDK: {resources} resources, {roles} bounded roles, formal account/assets; synthesis-only media fixture', flush=True)
    except (CheckFailure, ValueError, KeyError, OSError) as error:
        print(f'FAIL {error}', file=sys.stderr)
        return 1
    print(f'PASS {"quick" if args.quick else "full"} quality gate in {time.monotonic() - start:.2f}s; no deployment/inference/media-package certification')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
