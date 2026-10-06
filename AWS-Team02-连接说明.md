# AWS Team02 连接说明

配置日期：2026 年 10 月 5 日；实际功能复测横跨 10 月 5 日夜间与 10 月 6 日。正确比赛入口为 [Team Portal](https://du5imhgxabl0d.cloudfront.net/portal)，当前登录队伍为 Team02。

10 月 5 日已通过本机 CLI 和浏览器进入 Team02 的实际比赛账号；后续会话需重新核对身份与有效期。此前的 AccessDenied 来自登录中转账号：Portal 明确说明该账号没有资源权限，需要再切换到队伍账号。修复后，原先被拒绝的服务查询已成功。

|项目|已确认配置|
|---|---|
|实际比赛账号|`962768510637`|
|参赛角色|`NBAHackathonParticipantRole`|
|资源区域|`us-east-1`（美国弗吉尼亚北部）|
|日常操作配置|`nba`|
|登录配置|`nba-sso`，仅用于 SSO 登录中转|
|兼容配置|`broadcastcode-team02`，现也指向实际比赛角色|
|SSO 中转账号与角色|`405496568869` / `NBAHackathon-Team02`|
|SSO 登录区域|`us-west-2`，与资源区域用途不同|

本机配置保存在 `/Users/jack/.aws/config`。保留了原有 `default` 配置，因此比赛操作必须明确指定 `--profile nba`。采用可刷新的 SSO 会话和角色切换，没有把截图里的临时访问密钥写入项目。

## 以后如何使用

SSO 登录过期后重新登录：

```sh
aws sso login --profile nba-sso
```

验证实际比赛身份：

```sh
aws sts get-caller-identity --profile nba --region us-east-1
```

返回的 `Account` 应为 `962768510637`，`Arn` 应包含 `assumed-role/NBAHackathonParticipantRole/`。如果出现 `AWSReservedSSO`，说明使用的是中转配置。

比赛服务调用使用：

```sh
aws <服务> <操作> --profile nba --region us-east-1
```

给 AI 编程工具的账号说明可以直接写：“本项目使用 AWS 配置 nba，区域 us-east-1，目标账号 962768510637；部署前核对身份。”

Portal 说明：SSO 登录约持续 12 小时；浏览器切换角色约 1 小时，过期后再次点击 Portal 的 **Switch to your account**。CLI 会在 SSO 会话有效期内自动刷新角色凭证。其他资源区域受到限制，不能随意切换。

## CDK 与 GPU 的新增要求

主办方已完成 `us-east-1` 的 CDK bootstrap，**不要执行 `cdk bootstrap`**。实际项目的 `cdk.json` 必须在 `context` 中配置 `@aws-cdk/core:permissionsBoundary`，其 `name` 为 `NBAHackathonParticipantBoundary`，否则涉及创建 IAM 角色的部署会失败。部署使用本说明的 `nba` 配置。GPU 按通知通过 SageMaker 使用，配额需按机型和用途核对。

本次已确认 `CDKToolkit` 栈为 `CREATE_COMPLETE`，且指定权限边界策略存在。可合并的 JSON、部署步骤和 GPU 配额表见 [CDK 与 GPU 部署约束](BroadcastCode-CDK与GPU部署约束.md)。已在 `aws-validation` 中建立带此配置的临时 CDK 测试项目，并成功创建实际 IAM 角色；正式参赛应用后续也必须合并该配置。

## 本次验证结果

|验证项|结果|
|---|---|
|正确 Team Portal 登录|成功，显示 Team02|
|浏览器账号切换|成功，显示 Team02、目标账号、参赛角色和 us-east-1|
|CLI 身份查询|成功，返回目标账号和参赛角色|
|旧配置名兼容检查|成功，`broadcastcode-team02` 已指向同一实际比赛身份|
|CloudFront `ListDistributions`|请求成功，无 AccessDenied；响应未返回列表内容|
|CloudFormation `ListStacks`|成功|
|CloudFormation `ValidateTemplate`|成功，仅校验模板，没有创建资源|
|Bedrock `ListFoundationModels`|成功，返回 120 个模型目录条目|
|AgentCore `ListAgentRuntimes`|成功，当前返回 0 个 Runtime|
|CDK bootstrap 栈只读检查|`CDKToolkit` 为 `CREATE_COMPLETE`|
|权限边界策略存在性|成功，已读取 `NBAHackathonParticipantBoundary`|
|SageMaker 配额读取|成功；核验的 Endpoint、Training、JupyterLab 代表值与通知一致，`ml.g5.xlarge` Processing 为 0|

上表记录首次只读核验。随后已成功完成 CDK 真实部署、CloudFront 页面访问、Lambda / S3 / DynamoDB 读写、两个白名单模型的文本及图片调用、AgentCore 发布及模型调用、SageMaker T4 GPU 的 CUDA 运算。完整结果与清理状态见 [服务实际验证报告](AWS-Team02-服务实际验证报告.md)。

当前模型白名单为 `global.anthropic.claude-sonnet-4-6` 与 `qwen.qwen3-vl-235b-a22b`；Nova Lite 调用被账号策略明确拒绝。直接用 CLI 创建需要执行角色的服务时，使用主办方预置的 `NBAHackathonWorkloadRole`；当前参赛身份只被允许传递该执行角色。其他 GPU 尺寸核准了配额，实际启动测试覆盖 `ml.g4dn.xlarge` Training。

更正通知写明当前练习账号权限有效至 **10 月 8 日 09:00**；正式比赛账号与续期安排以组委会通知为准。

本次修改前的配置备份为 `/Users/jack/.aws/config.before-team02-role-20261005-182332`；此前的备份为 `/Users/jack/.aws/config.before-broadcastcode-20261005`。此说明不包含密码、访问密钥或会话令牌。
