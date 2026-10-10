#!/usr/bin/env python3
"""Real AgentCore approval → Doubao v3 two-host speech → 55-second movie.

This command writes only the registered narration source to the allocated S3
bucket. The private Doubao key remains on the rendering backend and is never
passed to AgentCore, S3, the browser, receipts or Git.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import uuid

from deployment import load_deployment, load_outputs, validate_identity
from narrate_formal import ROOT


def approve():
    import boto3
    from botocore.config import Config
    target=load_deployment();outputs=load_outputs(target=target)
    session=boto3.Session(profile_name='nba',region_name='us-east-1')
    config=Config(connect_timeout=8,read_timeout=150,retries={'total_max_attempts':1})
    validate_identity(session.client('sts',config=config).get_caller_identity(),target)
    data=(ROOT/'product/data/formal-dialogue.json').read_bytes()
    key='product/data/formal-dialogue.json'
    session.client('s3',config=config).put_object(Bucket=outputs['Bucket'],Key=key,Body=data,
        ExpectedBucketOwner=target['account'],ContentType='application/json',
        ServerSideEncryption='AES256',Metadata={'sha256':hashlib.sha256(data).hexdigest()})
    request_id=str(uuid.uuid4())
    payload={'mode':'narration','request_id':request_id}
    response=session.client('bedrock-agentcore',config=config).invoke_agent_runtime(
        agentRuntimeArn=outputs['RuntimeArn'],runtimeSessionId=str(uuid.uuid4()),
        contentType='application/json',accept='application/json',payload=json.dumps(payload).encode())
    stream=response['response']
    try: raw=b''.join(stream)
    finally: stream.close()
    if len(raw)>128*1024:raise ValueError('Narration response exceeds budget')
    result=json.loads(raw)
    if result.get('approved') is not True or result.get('protocol_version')!='gamebuddy-narration-v1':
        raise ValueError('AgentCore did not approve narration; no substitution used')
    plan=result['plan']
    proof=plan['agentCore'];proof['runtimeArn']=outputs['RuntimeArn']
    proof['verifiedAt']=datetime.now(timezone.utc).isoformat()
    proof['awsRequestId']=response.get('ResponseMetadata',{}).get('RequestId')
    evidence=ROOT/'product/evidence/formal-narration-agentcore-20261010.json'
    evidence.write_text(json.dumps(result,ensure_ascii=False,indent=2))
    saved=ROOT/'product/build/doubao/approved-dialogue.json'
    saved.write_text(json.dumps(plan,ensure_ascii=False,indent=2))
    print(json.dumps({'approved':True,'requestId':request_id,'runtimeArn':outputs['RuntimeArn'],
                      'tools':[step['tool'] for step in result['trace']],'plan':str(saved)}),flush=True)
    return saved


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--render',action='store_true')
    parser.add_argument('--media-python',default='python3',help='Python with the locked broadcast-fx Pillow dependency')
    args=parser.parse_args();plan=approve()
    if args.render:
        subprocess.run([args.media_python,str(ROOT/'product/scripts/narrate_formal.py'),
                        '--plan',str(plan)],check=True)


if __name__=='__main__':main()
