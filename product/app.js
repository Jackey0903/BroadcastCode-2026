const cdk = require('aws-cdk-lib');
const s3 = require('aws-cdk-lib/aws-s3');
const assets = require('aws-cdk-lib/aws-s3-assets');
const ddb = require('aws-cdk-lib/aws-dynamodb');
const sqs = require('aws-cdk-lib/aws-sqs');
const lambda = require('aws-cdk-lib/aws-lambda');
const events = require('aws-cdk-lib/aws-lambda-event-sources');
const logs = require('aws-cdk-lib/aws-logs');
const iam = require('aws-cdk-lib/aws-iam');
const cf = require('aws-cdk-lib/aws-cloudfront');
const origins = require('aws-cdk-lib/aws-cloudfront-origins');
const agentcore = require('aws-cdk-lib/aws-bedrockagentcore');
const eventbridge = require('aws-cdk-lib/aws-events');
const targets = require('aws-cdk-lib/aws-events-targets');
const sfn = require('aws-cdk-lib/aws-stepfunctions');
const tasks = require('aws-cdk-lib/aws-stepfunctions-tasks');
const cw = require('aws-cdk-lib/aws-cloudwatch');
const path = require('path');
const target = require('./deployment.json');
if (!/^\d{12}$/.test(target.account) || target.region !== 'us-east-1' ||
    target.profile !== 'nba' || target.stackName !== 'BroadcastCodeTeam02Readiness20261006' ||
    target.participantRole !== 'NBAHackathonParticipantRole' || target.workloadRole !== 'NBAHackathonWorkloadRole') {
  throw new Error('Invalid verified competition deployment target in product/deployment.json.');
}

const app = new cdk.App();
const boundary = app.node.tryGetContext('@aws-cdk/core:permissionsBoundary');
if (!boundary || boundary.name !== 'NBAHackathonParticipantBoundary') {
  throw new Error('Run CDK from product/ using its cdk.json; the organizer permissions boundary is required.');
}
const stack = new cdk.Stack(app, target.stackName, {
  env: {account:target.account, region:target.region},
  description:'Team02 The Hidden Play: evidence-led basketball stories and complete enhanced video',
});
cdk.Tags.of(stack).add('Purpose','BroadcastCodeTeam02Readiness');
const bucket = new s3.Bucket(stack,'Files', {
  blockPublicAccess:s3.BlockPublicAccess.BLOCK_ALL,
  encryption:s3.BucketEncryption.S3_MANAGED,
  enforceSSL:true,
  removalPolicy:cdk.RemovalPolicy.DESTROY,
});
const table = new ddb.Table(stack,'Jobs', {
  partitionKey:{name:'id',type:ddb.AttributeType.STRING},
  billingMode:ddb.BillingMode.PAY_PER_REQUEST,
  timeToLiveAttribute:'expiresAt',removalPolicy:cdk.RemovalPolicy.DESTROY,
});
const deadLetters = new sqs.Queue(stack,'RenderDeadLetters', {
  retentionPeriod:cdk.Duration.days(7),
});
const queue = new sqs.Queue(stack,'RenderQueue', {
  deadLetterQueue:{queue:deadLetters,maxReceiveCount:2},
  visibilityTimeout:cdk.Duration.seconds(1800),
  retentionPeriod:cdk.Duration.days(1),
});
const codeAsset = new assets.Asset(stack,'AgentCode',{path:path.join(__dirname,'build/agent.zip')});
const workloadArn = stack.formatArn({service:'iam',region:'',resource:'role',resourceName:target.workloadRole});
bucket.addToResourcePolicy(new iam.PolicyStatement({
  principals:[new iam.ArnPrincipal(workloadArn)],
  actions:['s3:GetObject'],resources:[bucket.arnForObjects('frames/*'),bucket.arnForObjects('product/data/*')],
}));
const runtime = new agentcore.CfnRuntime(stack,'Agent',{
  agentRuntimeName:'Team02Readiness20261006',roleArn:workloadArn,
  agentRuntimeArtifact:{codeConfiguration:{
    code:{s3:{bucket:codeAsset.s3BucketName,prefix:codeAsset.s3ObjectKey}},
    runtime:'PYTHON_3_12',entryPoint:['main.py'],
  }},
  networkConfiguration:{networkMode:'PUBLIC'},
  environmentVariables:{READINESS_BUCKET:bucket.bucketName,READINESS_BUCKET_OWNER:stack.account},
  lifecycleConfiguration:{idleRuntimeSessionTimeout:60,maxLifetime:600},
  tags:{Purpose:'BroadcastCodeTeam02Readiness'},
});
const layer = new lambda.LayerVersion(stack,'MediaTools',{
  code:lambda.Code.fromAsset(path.join(__dirname,'../readiness-lab/build/layer')),
  compatibleRuntimes:[lambda.Runtime.PYTHON_3_12],
  compatibleArchitectures:[lambda.Architecture.X86_64],
  description:'FFmpeg Linux x64 and OFL Noto Sans CJK font for full-clip subtitle test',
});
function log(id) {return new logs.LogGroup(stack,id,{
  retention:logs.RetentionDays.ONE_DAY,removalPolicy:cdk.RemovalPolicy.DESTROY,
});}
const api = new lambda.Function(stack,'Api',{
  runtime:lambda.Runtime.PYTHON_3_12,handler:'handler.handler',
  code:lambda.Code.fromAsset(path.join(__dirname,'api')),
  memorySize:256,timeout:cdk.Duration.seconds(20),logGroup:log('ApiLogs'),
  environment:{BUCKET:bucket.bucketName,TABLE:table.tableName,QUEUE_URL:queue.queueUrl,
    RUNTIME_ARN:runtime.attrAgentRuntimeArn,MAX_RUNS:'30'},
});
table.grantReadWriteData(api);queue.grantSendMessages(api);bucket.grantRead(api,'config/*');
const url = api.addFunctionUrl({authType:lambda.FunctionUrlAuthType.AWS_IAM});
const prettyPaths = new cf.Function(stack,'ProductPaths',{code:cf.FunctionCode.fromInline("function handler(event) { var request = event.request; if (request.uri === '/product') return {statusCode:302,headers:{location:{value:'/product/'}}}; if (request.uri === '/product/') request.uri = '/product/index.html'; return request; }")});
const mediaOrigin = origins.S3BucketOrigin.withOriginAccessControl(bucket);
// Zero minimum TTL respects origin no-store. Unique completed-job keys are immutable;
// registered practice media uses a shorter policy because its path is reusable.
const completedCache = new cf.CachePolicy(stack,'CompletedMediaCache',{
  minTtl:cdk.Duration.seconds(0),defaultTtl:cdk.Duration.days(1),maxTtl:cdk.Duration.days(365),
  enableAcceptEncodingGzip:true,enableAcceptEncodingBrotli:true,
});
const sourceCache = new cf.CachePolicy(stack,'SourceMediaCache',{
  minTtl:cdk.Duration.seconds(0),defaultTtl:cdk.Duration.days(1),maxTtl:cdk.Duration.days(1),
});
const mediaBehavior = cachePolicy => ({origin:mediaOrigin,cachePolicy,
  viewerProtocolPolicy:cf.ViewerProtocolPolicy.HTTPS_ONLY,
  allowedMethods:cf.AllowedMethods.ALLOW_GET_HEAD_OPTIONS});
const distribution = new cf.Distribution(stack,'Web',{
  defaultRootObject:'index.html',priceClass:cf.PriceClass.PRICE_CLASS_100,
  defaultBehavior:{origin:mediaOrigin,
    functionAssociations:[{function:prettyPaths,eventType:cf.FunctionEventType.VIEWER_REQUEST}],
    viewerProtocolPolicy:cf.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
    cachePolicy:cf.CachePolicy.CACHING_DISABLED},
  additionalBehaviors:{'product/outputs/*':mediaBehavior(completedCache),
    'samples/*':mediaBehavior(sourceCache),'frames/*':mediaBehavior(sourceCache),'api/*':{
    origin:origins.FunctionUrlOrigin.withOriginAccessControl(url),
    viewerProtocolPolicy:cf.ViewerProtocolPolicy.HTTPS_ONLY,
    allowedMethods:cf.AllowedMethods.ALLOW_ALL,
    cachePolicy:cf.CachePolicy.CACHING_DISABLED,
    originRequestPolicy:cf.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
  }},
  comment:'Team02 The Hidden Play: basketball storytelling with verifiable evidence',
});
// Function URLs created after Oct 2025 require both resource-policy actions.
new lambda.CfnPermission(stack,'CloudFrontInvokeFunction',{
  principal:'cloudfront.amazonaws.com',action:'lambda:InvokeFunction',
  functionName:api.functionName,invokedViaFunctionUrl:true,
  sourceArn:stack.formatArn({service:'cloudfront',region:'',resource:'distribution',
    resourceName:distribution.distributionId}),
});
const deliveryBus = new eventbridge.EventBus(stack,'DeliveryEvents',{
  eventBusName:'Team02ProductDelivery20261010',
});
const worker = new lambda.Function(stack,'Worker',{
  runtime:lambda.Runtime.PYTHON_3_12,architecture:lambda.Architecture.X86_64,
  handler:'handler.handler',code:lambda.Code.fromAsset(path.join(__dirname,'build/worker')),
  memorySize:2048,ephemeralStorageSize:cdk.Size.mebibytes(1024),
  timeout:cdk.Duration.seconds(300),reservedConcurrentExecutions:1,
  logGroup:log('WorkerLogs'),layers:[layer],
  environment:{BUCKET:bucket.bucketName,TABLE:table.tableName,
    RUNTIME_ARN:runtime.attrAgentRuntimeArn,CLOUDFRONT_HOST:distribution.distributionDomainName,
    DELIVERY_EVENT_BUS:deliveryBus.eventBusName,ENABLE_RL_SCOUT:'1'},
});
bucket.grantReadWrite(worker);table.grantReadWriteData(worker);
worker.addToRolePolicy(new iam.PolicyStatement({
  actions:['bedrock-agentcore:InvokeAgentRuntime','bedrock-agentcore:StopRuntimeSession'],
  resources:[runtime.attrAgentRuntimeArn,runtime.attrAgentRuntimeArn+'/*'],
}));
worker.addToRolePolicy(new iam.PolicyStatement({
  actions:['sagemaker:InvokeEndpoint'],
  resources:[stack.formatArn({service:'sagemaker',resource:'endpoint',resourceName:'rl-scout'})],
}));
worker.addEventSource(new events.SqsEventSource(queue,{batchSize:1,reportBatchItemFailures:true}));
deliveryBus.grantPutEventsTo(worker);
const deliveryEnvironment = {BUCKET:bucket.bucketName,TABLE:table.tableName,
  RUNTIME_ARN:runtime.attrAgentRuntimeArn,MODEL_ID:'global.anthropic.claude-sonnet-4-6',
  CLOUDFRONT_HOST:distribution.distributionDomainName};
function deliveryFunction(id, handler) {
  return new lambda.Function(stack,id,{
    runtime:lambda.Runtime.PYTHON_3_12,architecture:lambda.Architecture.X86_64,handler,
    code:lambda.Code.fromAsset(path.join(__dirname,'build/delivery')),
    memorySize:1024,ephemeralStorageSize:cdk.Size.mebibytes(1024),
    timeout:cdk.Duration.seconds(120),reservedConcurrentExecutions:1,
    logGroup:log(id+'Logs'),layers:[layer],environment:deliveryEnvironment,
  });
}
const verifier = deliveryFunction('DeliveryVerifier','handler.handler');
const narrator = deliveryFunction('NativeNarrator','narrator.handler');
for (const fn of [verifier,narrator]) {
  for (const prefix of ['product/config/samples.json','product/data/stories.json','product/outputs/*']) {
    bucket.grantRead(fn,prefix);
  }
  table.grant(fn,'dynamodb:GetItem');
}
table.grant(verifier,'dynamodb:UpdateItem');
bucket.grantRead(narrator,'frames/*');
for (const filename of ['narrated.mp4','narration.mp3','narration.json']) {
  bucket.grantPut(narrator,'product/outputs/*/'+filename);
}
narrator.addToRolePolicy(new iam.PolicyStatement({
  actions:['polly:SynthesizeSpeech','rekognition:DetectLabels'],resources:['*'],
}));
function verifyTask(id) {
  return new tasks.LambdaInvoke(stack,id,{lambdaFunction:verifier,payloadResponseOnly:true,
    payload:sfn.TaskInput.fromObject({jobId:sfn.JsonPath.stringAt('$.jobId')}),
    resultPath:'$.verification',retryOnServiceExceptions:false,
  }).addRetry({errors:['Lambda.ServiceException','Lambda.AWSLambdaException','Lambda.SdkClientException'],
    interval:cdk.Duration.seconds(2),maxAttempts:2,backoffRate:2});
}
const originalVerified = new sfn.Succeed(stack,'OriginalVideoVerified');
const rejected = new sfn.Fail(stack,'ArtifactRejected',{
  error:'DeliveryArtifactRejected',cause:'Independent media/source verification did not pass; original job state is unchanged.',
});
const optionalSpeech = new tasks.LambdaInvoke(stack,'CreateOptionalNativeMedia',{
  lambdaFunction:narrator,payloadResponseOnly:true,retryOnServiceExceptions:false,
  payload:sfn.TaskInput.fromObject({jobId:sfn.JsonPath.stringAt('$.jobId')}),resultPath:'$.nativeMedia',
}).addCatch(originalVerified,{resultPath:'$.nativeMediaError'}).next(originalVerified);
const recheck = verifyTask('RecheckDelivery').next(new sfn.Choice(stack,'RecheckPassed')
  .when(sfn.Condition.booleanEquals('$.verification.verified',true),optionalSpeech).otherwise(rejected));
const verify = verifyTask('VerifyCompleteVideo').next(new sfn.Choice(stack,'DeliveryPassed')
  .when(sfn.Condition.booleanEquals('$.verification.verified',true),optionalSpeech)
  .when(sfn.Condition.booleanEquals('$.verification.retryable',true),
    new sfn.Wait(stack,'WaitForStorage',{time:sfn.WaitTime.duration(cdk.Duration.seconds(3))}).next(recheck))
  .otherwise(rejected));
const deliveryWorkflow = new sfn.StateMachine(stack,'DeliveryWorkflow',{
  stateMachineName:'Team02ProductDelivery20261010',stateMachineType:sfn.StateMachineType.STANDARD,
  definitionBody:sfn.DefinitionBody.fromChainable(verify),timeout:cdk.Duration.minutes(6),
  logs:{destination:log('DeliveryWorkflowLogs'),level:sfn.LogLevel.ERROR,includeExecutionData:false},
});
const eventDeadLetters = new sqs.Queue(stack,'DeliveryEventDeadLetters',{retentionPeriod:cdk.Duration.days(7)});
new eventbridge.Rule(stack,'VideoRenderedRule',{
  eventBus:deliveryBus,eventPattern:{source:['broadcastcode.product'],detailType:['VideoRendered']},
  targets:[new targets.SfnStateMachine(deliveryWorkflow,{
    input:eventbridge.RuleTargetInput.fromEventPath('$.detail'),deadLetterQueue:eventDeadLetters,
    maxEventAge:cdk.Duration.minutes(15),retryAttempts:2,
  })],
});
const metric = name => new cw.Metric({namespace:'BroadcastCode/Product',metricName:name,
  dimensionsMap:{Service:'BroadcastCodeProduct'},period:cdk.Duration.minutes(1),statistic:'Sum'});
const alarms = [
  ['RenderFailures',worker.metricErrors({period:cdk.Duration.minutes(1),statistic:'Sum'}),1],
  ['RenderDeadLetters',deadLetters.metricApproximateNumberOfMessagesVisible({period:cdk.Duration.minutes(1)}),1],
  ['DeliveryDeadLetters',eventDeadLetters.metricApproximateNumberOfMessagesVisible({period:cdk.Duration.minutes(1)}),1],
  ['DeliveryPublishFailures',metric('DeliveryEventPublishFailed'),1],
  ['DeliveryVerificationFailures',deliveryWorkflow.metricFailed({period:cdk.Duration.minutes(1),statistic:'Sum'}),1],
  ['RenderBacklog',queue.metricApproximateNumberOfMessagesVisible({period:cdk.Duration.minutes(1)}),5],
].map(([id,measured,threshold]) => new cw.Alarm(stack,id+'Alarm',{
  metric:measured,threshold,evaluationPeriods:1,
  comparisonOperator:cw.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
  treatMissingData:cw.TreatMissingData.NOT_BREACHING,
}));
const dashboard = new cw.Dashboard(stack,'OperationsDashboard',{dashboardName:'Team02ProductDelivery20261010'});
dashboard.addWidgets(new cw.TextWidget({width:24,height:2,
  markdown:'## Team02 · durable video delivery\nRendered video remains available if optional narration fails. Media verification is independent from basketball and organizer scoring.'}));
dashboard.addWidgets(new cw.GraphWidget({title:'Durable render and event outcomes',width:12,
  left:['JobCompleted','JobFailed','DeliveryEventPublished','DeliveryEventPublishFailed'].map(metric)}),
  new cw.GraphWidget({title:'Delivery executions',width:12,left:[deliveryWorkflow.metricSucceeded(),deliveryWorkflow.metricFailed()]}));
dashboard.addWidgets(new cw.AlarmStatusWidget({title:'Render and delivery recovery',alarms,width:24}));
for(const [key,value] of Object.entries({Account:stack.account,Region:stack.region,Bucket:bucket.bucketName,Table:table.tableName,
  Api:api.functionName,Worker:worker.functionName,DeadLetterQueue:deadLetters.queueName,RuntimeArn:runtime.attrAgentRuntimeArn,
  Distribution:distribution.distributionId,Website:'https://'+distribution.distributionDomainName,
  WorkerLogs:worker.logGroup.logGroupName,DeliveryEventBus:deliveryBus.eventBusName,
  DeliveryStateMachineArn:deliveryWorkflow.stateMachineArn,DeliveryVerifier:verifier.functionName,
  NativeNarrator:narrator.functionName,OperationsDashboard:dashboard.dashboardName,
  DeliveryEventDeadLetterQueue:eventDeadLetters.queueName}))new cdk.CfnOutput(stack,key+'Output',{value}).overrideLogicalId(key);
