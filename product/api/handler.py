"""Same-origin runner for explicitly registered, same-bucket inputs."""
import json
import math
import os
import re
import time
import uuid
from decimal import Decimal
from urllib.parse import urlsplit
import boto3
from botocore.exceptions import BotoCoreError, ClientError

table = boto3.resource('dynamodb').Table(os.environ['TABLE'])
s3 = boto3.client('s3')
sqs = boto3.client('sqs')

SAMPLE_ID = re.compile(r'[a-z0-9][a-z0-9_-]{0,59}')
MAX_REGISTRY_BYTES = 1024 * 1024


def safe_sample_id(value):
    return isinstance(value, str) and SAMPLE_ID.fullmatch(value) is not None


def finite_number(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def same_bucket_object(uri):
    if not isinstance(uri, str):
        return False
    parsed = urlsplit(uri)
    return (parsed.scheme == 's3' and parsed.netloc == os.environ['BUCKET']
            and bool(parsed.path.lstrip('/')) and not parsed.query and not parsed.fragment)


def registered_samples():
    """Reject an unavailable or malformed registry before consuming run budget.

    The public request supplies an ID, never a source URI. Registration is a
    deployment operation; only this configured bucket can provide media inputs.
    """
    body = s3.get_object(Bucket=os.environ['BUCKET'], Key='config/samples.json')['Body']
    try:
        raw = body.read(MAX_REGISTRY_BYTES + 1)
    finally:
        body.close()
    if not raw or len(raw) > MAX_REGISTRY_BYTES:
        raise ValueError('Input registry is empty or exceeds its size limit.')
    samples = json.loads(raw)
    if not isinstance(samples, dict) or not samples:
        raise ValueError('Input registry must be a nonempty object.')
    for sample, entry in samples.items():
        if not safe_sample_id(sample) or not isinstance(entry, dict):
            raise ValueError('Input registry contains an invalid sample identity.')
        video, frames = entry.get('video'), entry.get('frames')
        if (not isinstance(video, dict) or video.get('id') != sample
                or not isinstance(video.get('name'), str) or not video['name'].strip()
                or len(video['name']) > 180
                or not finite_number(video.get('duration_ms')) or not 0 < video['duration_ms'] <= 600000
                or not same_bucket_object(video.get('s3_uri'))
                or not isinstance(frames, list) or not 1 <= len(frames) <= 6):
            raise ValueError('Input registry contains invalid video or frame metadata.')
        if 'sha256' in video and (not isinstance(video['sha256'], str)
                                 or not re.fullmatch(r'[0-9a-f]{64}', video['sha256'])):
            raise ValueError('Input registry contains an invalid source hash.')
        timestamps = set()
        for frame in frames:
            if (not isinstance(frame, dict) or not finite_number(frame.get('timestamp_ms'))
                    or not 0 <= frame['timestamp_ms'] <= video['duration_ms']
                    or frame['timestamp_ms'] in timestamps or frame.get('format') not in ('jpeg', 'png')
                    or not same_bucket_object(frame.get('s3_uri'))):
                raise ValueError('Input registry contains invalid source-frame metadata.')
            timestamps.add(frame['timestamp_ms'])
    return samples


def registry_unavailable(error):
    print(json.dumps({'event': 'input_registry_unavailable', 'type': type(error).__name__,
                      'code': getattr(error, 'response', {}).get('Error', {}).get('Code')}))
    return response(503, {'error': '登记素材暂不可用，请检查输入配置后重试。'})


def response(status, payload):
    return {'statusCode':status, 'headers':{'content-type':'application/json; charset=utf-8',
        'cache-control':'no-store'}, 'body':json.dumps(payload,ensure_ascii=False,
            default=lambda value: float(value) if isinstance(value,Decimal) else str(value))}

def handler(event, context):
    method = event.get('requestContext',{}).get('http',{}).get('method','GET')
    path = event.get('rawPath','')
    if method == 'GET' and path == '/api/status':
        try:
            samples = registered_samples()
            return response(200,{'status':'ready','region':'us-east-1','runtimeArn':os.environ['RUNTIME_ARN'],
                'samples':[{'id':key,'name':item['video']['name'],'durationSeconds':item['video']['duration_ms']/1000}
                           for key,item in samples.items()],
                'modes':['readiness','story'],
                'notice':'关键一拍：真实 AgentCore 生成与完整视频烧录；官方评测协议待适配。'})
        except (BotoCoreError, ClientError, OSError, ValueError, TypeError, KeyError, AttributeError) as error:
            return registry_unavailable(error)
    if method == 'POST' and path == '/api/jobs':
        job=None
        try:
            body=json.loads(event.get('body') or '{}')
            sample=body.get('sample')
            mode=body.get('mode','readiness')
            if mode not in ('readiness','story'):return response(400,{'error':'请选择支持的创作模式。'})
            if not safe_sample_id(sample):return response(400,{'error':'请选择有效的登记素材编号。'})
            try:
                samples = registered_samples()
            except (BotoCoreError, ClientError, OSError, ValueError, TypeError, KeyError, AttributeError) as error:
                return registry_unavailable(error)
            if sample not in samples:return response(400,{'error':'该素材尚未登记，不能启动任务。'})
            # Public calls can only select deployment-registered assets. Budget
            # and queue writes happen after the complete registry is validated.
            table.update_item(Key={'id':'_budget'},UpdateExpression='ADD runs :one',
                ConditionExpression='attribute_not_exists(runs) OR runs < :maximum',
                ExpressionAttributeValues={':one':1,':maximum':int(os.environ.get('MAX_RUNS','30'))})
            job=uuid.uuid4().hex
            table.put_item(Item={'id':job,'jobId':job,'runId':job,'sample':sample,'mode':mode,
                'status':'queued','stage':'queued','createdAt':int(time.time()),
                'expiresAt':int(time.time())+7*86400})
            sqs.send_message(QueueUrl=os.environ['QUEUE_URL'],MessageBody=json.dumps({'jobId':job,'sample':sample,'mode':mode}))
            return response(202,{'jobId':job,'status':'queued'})
        except (ValueError,TypeError,AttributeError):return response(400,{'error':'请求格式不正确。'})
        except ClientError as error:
            if error.response['Error']['Code']=='ConditionalCheckFailedException':
                return response(429,{'error':'练习运行次数已达上限，请联系队伍补充测试额度。'})
            print(json.dumps({'event':'enqueue_failed','code':error.response['Error']['Code']}))
            if job:
                try:
                    table.update_item(Key={'id':job},UpdateExpression='SET #s = :s, stage = :s, #e = :e',
                        ExpressionAttributeNames={'#s':'status','#e':'error'},
                        ExpressionAttributeValues={':s':'failed',':e':'队列提交失败，请重新启动任务。'})
                except ClientError:
                    print(json.dumps({'event':'failed_job_record_update','jobId':job}))
            return response(503,{'error':'任务暂时无法启动，请稍后重试。',**({'jobId':job} if job else {})})
    if method == 'GET' and path.startswith('/api/jobs/'):
        job=path.rsplit('/',1)[-1]
        if len(job)!=32 or any(c not in '0123456789abcdef' for c in job):return response(400,{'error':'无效任务编号。'})
        try:
            item=table.get_item(Key={'id':job}).get('Item')
            return response(200,item) if item else response(404,{'error':'任务不存在。'})
        except ClientError:
            return response(503,{'error':'任务状态暂时无法查询，请稍后重试。','jobId':job})
    return response(404,{'error':'未找到该接口。'})
