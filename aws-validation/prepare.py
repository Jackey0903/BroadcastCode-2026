import json
import shutil
import struct
import tarfile
import zlib
import zipfile
from pathlib import Path
import boto3

ROOT = Path(__file__).resolve().parent
session = boto3.Session(profile_name='nba', region_name='us-east-1')
identity = session.client('sts').get_caller_identity()
assert identity['Account'] == '962768510637'
cfn = session.client('cloudformation')
resources = cfn.describe_stack_resources(StackName='BroadcastCodeTeam02Validation20261005')['StackResources']
bucket = next(r['PhysicalResourceId'] for r in resources if r['ResourceType'] == 'AWS::S3::Bucket')
s3 = session.client('s3')
s3.head_bucket(Bucket=bucket, ExpectedBucketOwner=identity['Account'])
s3.upload_file(str(ROOT/'index.html'), bucket, 'index.html', ExtraArgs={'ContentType': 'text/html; charset=utf-8'})
with tarfile.open(ROOT/'source.tar.gz', 'w:gz') as archive:
    archive.add(ROOT/'gpu_check.py', arcname='gpu_check.py')
s3.upload_file(str(ROOT/'source.tar.gz'), bucket, 'gpu/source.tar.gz')

import boto3 as installed_boto3
site = Path(installed_boto3.__file__).resolve().parent.parent
with zipfile.ZipFile(ROOT/'agent.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
    archive.write(ROOT/'agent.py', 'agent.py')
    for module in ('boto3', 'botocore', 's3transfer', 'jmespath', 'dateutil', 'urllib3'):
        for path in (site/module).rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts:
                archive.write(path, path.relative_to(site).as_posix())
    archive.write(site/'six.py', 'six.py')
s3.upload_file(str(ROOT/'agent.zip'), bucket, 'agent/agent.zip')

manifest = {
    'account': identity['Account'], 'region': 'us-east-1', 'profile': 'nba',
    'stack': 'BroadcastCodeTeam02Validation20261005', 'bucket': bucket,
    'gpu_job': 'team02-gpu-validation-20261005',
    'agent_name': 'Team02Validation20261005',
    'workload_role': 'arn:aws:iam::962768510637:role/NBAHackathonWorkloadRole',
}
(ROOT/'manifest.json').write_text(json.dumps(manifest, indent=2))
gpu = {
    'TrainingJobName': manifest['gpu_job'],
    'RoleArn': manifest['workload_role'],
    'AlgorithmSpecification': {
        'TrainingImage': '763104351884.dkr.ecr.us-east-1.amazonaws.com/pytorch-training:2.9.0-gpu-py312-cu130-ubuntu22.04-sagemaker',
        'TrainingInputMode': 'File',
    },
    'HyperParameters': {
        'sagemaker_program': json.dumps('gpu_check.py'),
        'sagemaker_submit_directory': json.dumps('s3://'+bucket+'/gpu/source.tar.gz'),
        'sagemaker_region': json.dumps('us-east-1'),
        'sagemaker_container_log_level': '20',
    },
    'ResourceConfig': {'InstanceType': 'ml.g4dn.xlarge', 'InstanceCount': 1, 'VolumeSizeInGB': 10},
    'OutputDataConfig': {'S3OutputPath': 's3://'+bucket+'/gpu/output'},
    'StoppingCondition': {'MaxRuntimeInSeconds': 300},
    'Tags': [{'Key': 'Purpose', 'Value': 'BroadcastCodeTeam02Validation'}],
}
(ROOT/'gpu-request.json').write_text(json.dumps(gpu, indent=2))
agent = {
    'agentRuntimeName': manifest['agent_name'],
    'agentRuntimeArtifact': {'codeConfiguration': {
        'code': {'s3': {'bucket': bucket, 'prefix': 'agent/agent.zip'}},
        'runtime': 'PYTHON_3_12', 'entryPoint': ['agent.py'],
    }},
    'roleArn': manifest['workload_role'],
    'networkConfiguration': {'networkMode': 'PUBLIC'},
    'lifecycleConfiguration': {'idleRuntimeSessionTimeout': 60, 'maxLifetime': 600},
    'description': 'Temporary Team02 functional validation',
    'clientToken': 'team02-validation-20261005-agent-runtime',
    'tags': {'Purpose': 'BroadcastCodeTeam02Validation'},
}
(ROOT/'agent-request.json').write_text(json.dumps(agent, indent=2))
print(json.dumps({'artifacts_uploaded': True, 'bucket': bucket, 'gpu_request_ready': True, 'agent_request_ready': True}))

def chunk(kind, data):
    return struct.pack('!I',len(data))+kind+data+struct.pack('!I',zlib.crc32(kind+data)&0xffffffff)
png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!IIBBBBB',16,16,8,2,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+b'\xff\0\0'*16)*16))+chunk(b'IEND',b'')
models = {}
client = session.client('bedrock-runtime')
for model in ('global.anthropic.claude-sonnet-4-6', 'qwen.qwen3-vl-235b-a22b'):
    try:
        response = client.converse(modelId=model, messages=[{'role': 'user', 'content': [
            {'image': {'format': 'png', 'source': {'bytes': png}}},
            {'text': 'Name the dominant color in this image in one word.'},
        ]}], inferenceConfig={'maxTokens': 24, 'temperature': 0})
        text=response['output']['message']['content']
        models[model]={'status': 'success', 'response': text, 'usage': response.get('usage')}
    except Exception as error:
        models[model]={'status':'failed','error':str(error)}
    print(json.dumps({'multimodal_model':model, **models[model]}))
(ROOT/'model-tests.json').write_text(json.dumps(models, indent=2))
