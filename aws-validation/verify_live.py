import base64
import json
import uuid
from pathlib import Path
from urllib.request import urlopen
import boto3

ROOT = Path(__file__).resolve().parent
manifest = json.loads((ROOT/'manifest.json').read_text())
session = boto3.Session(profile_name='nba', region_name='us-east-1')
assert session.client('sts').get_caller_identity()['Account'] == manifest['account']
resources = session.client('cloudformation').describe_stack_resources(StackName=manifest['stack'])['StackResources']
physical = {r['ResourceType']: r['PhysicalResourceId'] for r in resources}
report = {'account': manifest['account'], 'region': manifest['region']}
lambda_result = session.client('lambda').invoke(
    FunctionName=physical['AWS::Lambda::Function'], Payload=b'{}', LogType='Tail')
payload = json.loads(lambda_result['Payload'].read())
assert not lambda_result.get('FunctionError'), payload
assert payload == {'status': 'SERVICE_CHECK_OK', 's3_read': True, 'dynamodb_read_write': True}, payload
report['lambda_s3_dynamodb'] = payload
report['lambda_logs'] = base64.b64decode(lambda_result.get('LogResult', '')).decode()
(ROOT/'live-tests.json').write_text(json.dumps(report, indent=2))
print(json.dumps({'lambda_s3_dynamodb': 'success', **payload}), flush=True)

dist = session.client('cloudfront').get_distribution(Id=physical['AWS::CloudFront::Distribution'])['Distribution']
url = 'https://' + dist['DomainName'] + '/index.html'
with urlopen(url, timeout=30) as response:
    html = response.read().decode()
    assert response.status == 200 and 'SERVICE_CHECK_OK' in html
    report['cloudfront'] = {'status': 'success', 'http_status': response.status, 'url': url}
print(json.dumps(report['cloudfront']), flush=True)
(ROOT/'live-tests.json').write_text(json.dumps(report, indent=2))

runtime_session = str(uuid.uuid4())
manifest['runtime_session'] = runtime_session
(ROOT/'manifest.json').write_text(json.dumps(manifest, indent=2))
client = session.client('bedrock-agentcore')
try:
    response = client.invoke_agent_runtime(
        agentRuntimeArn=manifest['agent_arn'], runtimeSessionId=runtime_session,
        qualifier='DEFAULT', contentType='application/json', accept='application/json',
        payload=json.dumps({'prompt': 'Reply with exactly AGENT_CHECK_OK.'}).encode(),
    )
    agent_result = response['response'].read().decode()
    agent_payload = json.loads(agent_result)
    assert agent_payload['status'] == 'AGENT_CHECK_OK' and 'AGENT_CHECK_OK' in agent_payload['model_response']
    report['agentcore'] = {'status': 'success', 'response': agent_payload}
    print(json.dumps(report['agentcore']), flush=True)
finally:
    try:
        client.stop_runtime_session(agentRuntimeArn=manifest['agent_arn'], runtimeSessionId=runtime_session, qualifier='DEFAULT')
        report['agentcore_session_stopped'] = True
    except Exception as error:
        report['agentcore_session_stop'] = str(error)
    (ROOT/'live-tests.json').write_text(json.dumps(report, indent=2))
