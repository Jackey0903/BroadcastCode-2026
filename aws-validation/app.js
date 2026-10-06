const cdk = require('aws-cdk-lib');
const s3 = require('aws-cdk-lib/aws-s3');
const dynamodb = require('aws-cdk-lib/aws-dynamodb');
const lambda = require('aws-cdk-lib/aws-lambda');
const logs = require('aws-cdk-lib/aws-logs');
const cloudfront = require('aws-cdk-lib/aws-cloudfront');
const origins = require('aws-cdk-lib/aws-cloudfront-origins');

const app = new cdk.App();
const stack = new cdk.Stack(app, 'BroadcastCodeTeam02Validation20261005', {
  env: { account: '962768510637', region: 'us-east-1' },
  description: 'Temporary BroadcastCode Team02 functional service validation',
});
cdk.Tags.of(stack).add('Purpose', 'BroadcastCodeTeam02Validation');

const bucket = new s3.Bucket(stack, 'ValidationFiles', {
  blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
  encryption: s3.BucketEncryption.S3_MANAGED,
  removalPolicy: cdk.RemovalPolicy.DESTROY,
});
const table = new dynamodb.Table(stack, 'ValidationRecords', {
  partitionKey: { name: 'id', type: dynamodb.AttributeType.STRING },
  billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
  removalPolicy: cdk.RemovalPolicy.DESTROY,
});
const logGroup = new logs.LogGroup(stack, 'ValidationLogs', {
  retention: logs.RetentionDays.ONE_DAY,
  removalPolicy: cdk.RemovalPolicy.DESTROY,
});
const fn = new lambda.Function(stack, 'ValidationFunction', {
  runtime: lambda.Runtime.PYTHON_3_12,
  handler: 'index.handler',
  timeout: cdk.Duration.seconds(20),
  memorySize: 128,
  logGroup,
  environment: { BUCKET: bucket.bucketName, TABLE: table.tableName },
  code: lambda.Code.fromInline(`import boto3, json, os
def handler(event, context):
    table = boto3.resource('dynamodb').Table(os.environ['TABLE'])
    table.put_item(Item={'id': 'service-check', 'result': 'SERVICE_CHECK_OK'})
    result = table.get_item(Key={'id': 'service-check'})['Item']['result']
    data = boto3.client('s3').get_object(Bucket=os.environ['BUCKET'], Key='index.html')['Body'].read().decode()
    payload = {'status': result, 's3_read': 'SERVICE_CHECK_OK' in data, 'dynamodb_read_write': True}
    print(json.dumps(payload))
    return payload
`),
});
bucket.grantRead(fn);
table.grantReadWriteData(fn);

const distribution = new cloudfront.Distribution(stack, 'ValidationWebsite', {
  defaultRootObject: 'index.html',
  defaultBehavior: {
    origin: origins.S3BucketOrigin.withOriginAccessControl(bucket),
    viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
    cachePolicy: cloudfront.CachePolicy.CACHING_DISABLED,
  },
  priceClass: cloudfront.PriceClass.PRICE_CLASS_100,
  comment: 'Temporary Team02 verification page; contains no private data',
});
new cdk.CfnOutput(stack, 'Bucket', { value: bucket.bucketName });
new cdk.CfnOutput(stack, 'Table', { value: table.tableName });
new cdk.CfnOutput(stack, 'Function', { value: fn.functionName });
new cdk.CfnOutput(stack, 'Logs', { value: logGroup.logGroupName });
new cdk.CfnOutput(stack, 'Distribution', { value: distribution.distributionId });
new cdk.CfnOutput(stack, 'Website', { value: 'https://' + distribution.distributionDomainName });
