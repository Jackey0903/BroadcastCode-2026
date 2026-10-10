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
const distribution = new cf.Distribution(stack,'Web',{
  defaultRootObject:'index.html',priceClass:cf.PriceClass.PRICE_CLASS_100,
  defaultBehavior:{origin:origins.S3BucketOrigin.withOriginAccessControl(bucket),
    functionAssociations:[{function:prettyPaths,eventType:cf.FunctionEventType.VIEWER_REQUEST}],
    viewerProtocolPolicy:cf.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
    cachePolicy:cf.CachePolicy.CACHING_DISABLED},
  additionalBehaviors:{'api/*':{
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
const worker = new lambda.Function(stack,'Worker',{
  runtime:lambda.Runtime.PYTHON_3_12,architecture:lambda.Architecture.X86_64,
  handler:'handler.handler',code:lambda.Code.fromAsset(path.join(__dirname,'build/worker')),
  memorySize:2048,ephemeralStorageSize:cdk.Size.mebibytes(1024),
  timeout:cdk.Duration.seconds(300),reservedConcurrentExecutions:1,
  logGroup:log('WorkerLogs'),layers:[layer],
  environment:{BUCKET:bucket.bucketName,TABLE:table.tableName,
    RUNTIME_ARN:runtime.attrAgentRuntimeArn,CLOUDFRONT_HOST:distribution.distributionDomainName},
});
bucket.grantReadWrite(worker);table.grantReadWriteData(worker);
worker.addToRolePolicy(new iam.PolicyStatement({
  actions:['bedrock-agentcore:InvokeAgentRuntime','bedrock-agentcore:StopRuntimeSession'],
  resources:[runtime.attrAgentRuntimeArn,runtime.attrAgentRuntimeArn+'/*'],
}));
worker.addEventSource(new events.SqsEventSource(queue,{batchSize:1,reportBatchItemFailures:true}));
for(const [key,value] of Object.entries({Account:stack.account,Region:stack.region,Bucket:bucket.bucketName,Table:table.tableName,
  Api:api.functionName,Worker:worker.functionName,DeadLetterQueue:deadLetters.queueName,RuntimeArn:runtime.attrAgentRuntimeArn,
  Distribution:distribution.distributionId,Website:'https://'+distribution.distributionDomainName,
  WorkerLogs:worker.logGroup.logGroupName}))new cdk.CfnOutput(stack,key+'Output',{value}).overrideLogicalId(key);
