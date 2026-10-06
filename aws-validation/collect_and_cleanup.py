import io
import json
import tarfile
from pathlib import Path
from urllib.parse import urlparse
import boto3
from botocore.exceptions import ClientError

ROOT=Path(__file__).resolve().parent
manifest=json.loads((ROOT/'manifest.json').read_text())
session=boto3.Session(profile_name='nba',region_name='us-east-1')
assert session.client('sts').get_caller_identity()['Account']==manifest['account']=='962768510637'
job=session.client('sagemaker').describe_training_job(TrainingJobName=manifest['gpu_job'])
assert job['TrainingJobStatus']=='Completed', job.get('FailureReason',job['TrainingJobStatus'])
(ROOT/'gpu-job.json').write_text(json.dumps(job,default=str,indent=2))
s3=session.client('s3')
uri=urlparse(job['ModelArtifacts']['S3ModelArtifacts'])
assert uri.netloc==manifest['bucket']
archive=s3.get_object(Bucket=uri.netloc,Key=uri.path.lstrip('/'))['Body'].read()
with tarfile.open(fileobj=io.BytesIO(archive),mode='r:gz') as tar:
    member=next(m for m in tar.getmembers() if m.isfile() and m.name.removeprefix('./')=='gpu_check.json')
    gpu=json.load(tar.extractfile(member))
assert gpu['status']=='GPU_CHECK_OK' and gpu['matrix_result']==128.0
(ROOT/'gpu-result.json').write_text(json.dumps(gpu,indent=2))
print(json.dumps({'gpu_result':gpu,'billable_seconds':job.get('BillableTimeInSeconds')}),flush=True)

cleanup={'gpu_job_completed':True,'gpu_billable_seconds':job.get('BillableTimeInSeconds')}
control=session.client('bedrock-agentcore-control')
try:
    control.get_agent_runtime(agentRuntimeId=manifest['agent_id'])
    raise RuntimeError('AgentCore runtime has not finished deletion')
except ClientError as error:
    if error.response['Error']['Code']!='ResourceNotFoundException': raise
    cleanup['agent_runtime_removed']=True
try:
    control.delete_workload_identity(name=manifest['agent_id'])
    cleanup['agent_workload_identity_removed']=True
except ClientError as error:
    if error.response['Error']['Code']!='ResourceNotFoundException': raise
    cleanup['agent_workload_identity_removed']=True

logs=session.client('logs')
runtime_prefix='/aws/bedrock-agentcore/runtimes/'+manifest['agent_id']
groups=logs.describe_log_groups(logGroupNamePrefix=runtime_prefix)['logGroups']
for group in groups:
    assert group['logGroupName'].startswith(runtime_prefix)
    logs.delete_log_group(logGroupName=group['logGroupName'])
cleanup['agent_log_groups_removed']=len(groups)
try:
    streams=logs.describe_log_streams(logGroupName='/aws/sagemaker/TrainingJobs',logStreamNamePrefix=manifest['gpu_job']+'/')['logStreams']
    for stream in streams:
        logs.delete_log_stream(logGroupName='/aws/sagemaker/TrainingJobs',logStreamName=stream['logStreamName'])
    cleanup['gpu_log_streams_removed']=len(streams)
except ClientError as error:
    if error.response['Error']['Code']!='ResourceNotFoundException': raise

resources=session.client('cloudformation').describe_stack_resources(StackName=manifest['stack'])['StackResources']
bucket=next(r['PhysicalResourceId'] for r in resources if r['ResourceType']=='AWS::S3::Bucket')
assert bucket==manifest['bucket']
objects=[]
for page in s3.get_paginator('list_objects_v2').paginate(Bucket=bucket):
    objects += [{'Key':obj['Key']} for obj in page.get('Contents',[])]
for i in range(0,len(objects),1000):
    result=s3.delete_objects(Bucket=bucket,Delete={'Objects':objects[i:i+1000]},ExpectedBucketOwner=manifest['account'])
    assert not result.get('Errors'),result['Errors']
cleanup['temporary_bucket_objects_removed']=len(objects)
(ROOT/'cleanup.json').write_text(json.dumps(cleanup,indent=2))
print(json.dumps(cleanup),flush=True)
