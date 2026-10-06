# BroadcastCode CDK 与 GPU 部署约束

更新日期：2026 年 10 月 6 日。赛事专属要求来自用户转交的主办方 CDK 通知和 GPU 配额截图；AWS 官方资料用于核验技术含义。

## CDK 的必需配置

主办方已经在 `us-east-1` 完成 CDK bootstrap。**不要执行 `cdk bootstrap`，直接使用 `cdk deploy`。** 本次只读检查已确认 Team02 账号 `962768510637` 中的 `CDKToolkit` 栈状态为 `CREATE_COMPLETE`，且以下托管策略存在：

`arn:aws:iam::962768510637:policy/NBAHackathonParticipantBoundary`

在实际 CDK 项目的 `cdk.json` 中，将以下配置合并进现有 `context`，保留原有 `app`、其他 context 和配置项：

```json
{
  "context": {
    "@aws-cdk/core:permissionsBoundary": {
      "name": "NBAHackathonParticipantBoundary"
    }
  }
}
```

这段 JSON 是需合并的配置片段，不是一个能独立部署的完整 CDK 项目。后续已在 `aws-validation` 临时测试项目中加入该配置并实际部署成功；正式参赛项目也必须加入。

主办方说明：创建 IAM 角色时必须带这一权限边界；遗漏后，Lambda、ECS 等涉及角色创建的部署会因 `iam:CreateRole AccessDenied` 失败。AWS 官方也确认，CDK 可通过该 context 为所创建的 IAM 实体设置默认权限边界。[AWS 官方配置示例](https://aws.amazon.com/blogs/devops/secure-cdk-deployments-with-iam-permission-boundaries/)

权限边界限定角色的权限上限，本身不授予业务权限；应用仍需按用途配置角色权限，例如读取指定 S3 文件或调用模型。[AWS 官方说明](https://docs.aws.amazon.com/cdk/v2/guide/customize-permissions-boundaries.html)

## 部署身份与操作顺序

|项目|固定值|
|---|---|
|目标账号|`962768510637`|
|参赛角色|`NBAHackathonParticipantRole`|
|资源区域|`us-east-1`|
|实际操作配置|`nba`|
|SSO 登录配置|`nba-sso`|

在实际 CDK 项目内执行：

```sh
# SSO 会话过期时重新登录
aws sso login --profile nba-sso

# 先核对目标身份
aws sts get-caller-identity --profile nba --region us-east-1

# 合成模板，核对新建 IAM 角色的 PermissionsBoundary
AWS_REGION=us-east-1 AWS_DEFAULT_REGION=us-east-1 npx --no-install cdk synth --profile nba

# 应用准备好后部署
AWS_REGION=us-east-1 AWS_DEFAULT_REGION=us-east-1 npx --no-install cdk deploy --profile nba
```

上述命令使用已安装在实际项目内的 CDK CLI；本机验证工程没有依赖全局 `cdk`。Stack 的目标环境也应明确为账号 `962768510637`、区域 `us-east-1`；硬编码在应用中的其他环境不会因为命令设置区域就自动改变。日常调用使用 `nba`，不能误用仅负责中转登录的 `nba-sso`。

首次整理本说明时未运行 CDK；后续已完成真实 CDK 部署和 GPU 运算测试，详见 [服务实际验证报告](AWS-Team02-服务实际验证报告.md)。测试过程没有执行 bootstrap。

## GPU 必须通过 SageMaker 使用

通知中的“segamaker”应指 **Amazon SageMaker AI**。按主办方要求，GPU 通过 SageMaker 创建。截图中的 `ml.g*` 等名称对应 SageMaker 机型，不能据此推断直接创建 EC2 GPU 实例已获许可。

配额按用途区分：

|用途列|含义|
|---|---|
|Endpoint|部署模型推理端点使用的实例配额|
|Training|常规训练任务的实例配额|
|Spot 训练|使用 Spot 的训练实例配额|
|Notebook|Notebook 实例的配额|
|JupyterLab|相应 JupyterLab 应用机型的配额|

某一列有配额不能替代另一列的配额。例如 `ml.g4dn.8xlarge` 的 Endpoint 为 0，而 Training 为 1；按通知不能用它创建一个推理 Endpoint，但训练用途有配额。

下表逐行保留截图的分组与数字，单位为台：

|机型|Endpoint|Training|Spot 训练|Notebook|JupyterLab|
|---|---:|---:|---:|---:|---:|
|`ml.g4dn.xlarge`|2|1|1|4|4|
|`ml.g4dn.2xlarge`|2|1|1|2|2|
|`ml.g4dn.4xlarge`|1|1|1|1|1|
|`ml.g4dn.8xlarge`|0|1|1|1|1|
|`ml.g4dn.12xlarge / 16xlarge`|1 / 0|1|1|0|0|
|`ml.g5.xlarge – 16xlarge`|2,2,1,1,1,1|1|0|1|1|
|`ml.g5.24xlarge / 48xlarge`|0|0|0|1|0|
|`ml.g6.xlarge – 16xlarge`|1|1|0|1|1|
|`ml.g6.24xlarge / 48xlarge`|0|0|0|1|0|
|`ml.g6e.xlarge – 16xlarge`|1|1|1|1|1|
|`ml.g6e.24xlarge / 48xlarge`|0|0|0|1|0|
|`ml.p3.2xlarge`|1|0|0|2|0|
|`ml.trn1.2xlarge`|0|1|0|0|0|

[查看原始配额截图](参考资料/SageMaker-GPU-配额-20261005.jpg)。区间与斜线写法沿用截图；选择具体尺寸时，应读取本队账号该机型、用途的实际配额。截图没有给出 Processing 等其他用途的配额，不能自行套用 Training 列。

配额是账号与区域的资源上限，不能理解成预留了现成实例；实际启动还取决于对应机型的可用容量。[AWS 配额定义](https://docs.aws.amazon.com/general/latest/gr/sagemaker.html)、[AWS 训练容量说明](https://docs.aws.amazon.com/en_en/sagemaker/latest/dg/train-instance-preferences.html)

`ml.trn1` 属于 AWS Trainium 体系，使用 Neuron 软件栈，不能作为 NVIDIA CUDA GPU 的直接替代。模型是否兼容、需要多少显存、使用哪种 SageMaker 用途，应在项目方案确定后分别核实。[AWS Trainium 官方说明](https://aws.amazon.com/ec2/instance-types/trn1/)

## Team02 实际配额核验

已用 `nba` 配置在 `us-east-1` 成功读取 SageMaker Service Quotas，并逐项查询以下代表性配额：

|具体机型及用途|本队账号当前配额|
|---|---:|
|`ml.g5.xlarge` Endpoint|2|
|`ml.g4dn.xlarge` Training|1|
|`ml.g4dn.xlarge` Studio JupyterLab|4|
|`ml.g5.xlarge` Processing|0|

前三项与截图对应值一致。第四项说明：即使同一机型能创建推理 Endpoint，也不能据此创建 Processing 任务。选择视频分析的 GPU 执行方案时，应先确认具体 SageMaker 用途的配额。

后续已核准 32 个机型尺寸的实际配额，并实际运行 `ml.g4dn.xlarge` Training：T4 GPU 的 CUDA 运算成功，任务 Completed，计费时长 199 秒后计算实例自动释放。其他尺寸和用途未逐一启动。完整配额见 [实际 GPU 配额表](aws-validation/SageMaker-实际GPU配额.md)，实际调用证据见上述报告。
