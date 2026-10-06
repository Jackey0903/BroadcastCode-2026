"""Same-origin public sample runner. No credentials or arbitrary input URLs."""
import json, os, time, uuid
from decimal import Decimal
import boto3
from botocore.exceptions import ClientError

table = boto3.resource('dynamodb').Table(os.environ['TABLE'])
s3 = boto3.client('s3')
sqs = boto3.client('sqs')

def response(status, payload):
    return {'statusCode':status, 'headers':{'content-type':'application/json; charset=utf-8',
        'cache-control':'no-store'}, 'body':json.dumps(payload,ensure_ascii=False,
            default=lambda value: float(value) if isinstance(value,Decimal) else str(value))}

def handler(event, context):
    method = event.get('requestContext',{}).get('http',{}).get('method','GET')
    path = event.get('rawPath','')
    if method == 'GET' and path == '/api/status':
        try:
            samples = json.loads(s3.get_object(Bucket=os.environ['BUCKET'],Key='config/samples.json')['Body'].read())
            return response(200,{'status':'ready','region':'us-east-1','runtimeArn':os.environ['RUNTIME_ARN'],
                'samples':[{'id':key,'name':item['video']['name'],'durationSeconds':item['video']['duration_ms']/1000}
                           for key,item in samples.items()],
                'notice':'赛前联通练习：真实模型观察与完整视频叠字，尚未接入正式深度数据和统一评测接口。'})
        except (ClientError,ValueError,TypeError,KeyError,AttributeError):
            return response(503,{'error':'练习素材尚未就绪，请稍后重试。'})
    if method == 'POST' and path == '/api/jobs':
        job=None
        try:
            body=json.loads(event.get('body') or '{}')
            sample=body.get('sample')
            if sample not in ('flagg','amen'):return response(400,{'error':'请选择已有的官方练习片。'})
            # Public link can only run these two assets, with a bounded invocation budget.
            table.update_item(Key={'id':'_budget'},UpdateExpression='ADD runs :one',
                ConditionExpression='attribute_not_exists(runs) OR runs < :maximum',
                ExpressionAttributeValues={':one':1,':maximum':int(os.environ.get('MAX_RUNS','30'))})
            job=uuid.uuid4().hex
            table.put_item(Item={'id':job,'jobId':job,'runId':job,'sample':sample,
                'status':'queued','stage':'queued','createdAt':int(time.time()),
                'expiresAt':int(time.time())+7*86400})
            sqs.send_message(QueueUrl=os.environ['QUEUE_URL'],MessageBody=json.dumps({'jobId':job,'sample':sample}))
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
