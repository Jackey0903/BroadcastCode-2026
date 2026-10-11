# AWS Team02 连接说明

更新日期：2026-10-10。正式比赛已开始，Portal 使用原登录账号，但正式 AWS 账号已换为 **`555726205424`**。Team02 Portal 已锁定新私有仓库 [Jackey0903/BroadcastCode-2026](https://github.com/Jackey0903/BroadcastCode-2026)；[正式重连说明](../../正式比赛重连与新仓库-20261010.md)与[账号审计](../../../product/evidence/formal-account-audit-20261010.json)记录当前证据。

|项目|正式配置|
|---|---|
|Team Portal|https://du5imhgxabl0d.cloudfront.net/portal|
|资源账号与角色|`555726205424` / `NBAHackathonParticipantRole`|
|资源区域|`us-east-1`|
|日常操作配置|`nba`|
|SSO 登录配置|`nba-sso`，仅身份中转|
|兼容配置|`broadcastcode-team02`，已同步新正式角色|
|SSO 中转账号与角色|`405496568869` / `NBAHackathon-Team02`|
|SSO 登录区域|`us-west-2`|
|预置工作负载角色|`arn:aws:iam::555726205424:role/NBAHackathonWorkloadRole`|

本机 `~/.aws/config` 中 `nba` 与兼容配置的 role_arn 已修改，`default` 和 SSO 中转配置保持原用途。没有把临时密钥写入项目。新机器的完整非敏感配置示例见[AI 接手说明](../../../AI接手说明.md)。

## 登录和核对

SSO 过期时重新登录；每次部署先检查身份：

```sh
aws sso login --profile nba-sso
aws sts get-caller-identity --profile nba --region us-east-1
```

返回 `Account` 必须为 `555726205424`，`Arn` 包含 `assumed-role/NBAHackathonParticipantRole/`。若返回 `AWSReservedSSO` 或中转账号，说明使用了错误配置。实际调用明确带 `--profile nba --region us-east-1`。Portal 说明 SSO 约 12 小时、浏览器切换角色约 1 小时；CLI 在有效 SSO 会话内刷新链式角色凭证。

## 当前核查与部署

10 月 10 日已只读核查：身份正确，`CDKToolkit` 为 `CREATE_COMPLETE`／bootstrap 版本32，权限边界和预置 Workload Role 存在。产品同名 Stack 尚不存在，AgentCore Runtime列表为空。Bedrock模型目录读取成功，共124条；**目录不等于推理权限**，本次未调用模型或GPU。

活跃产品部署目标统一在 [product/deployment.json](../../../product/deployment.json)，使用 `product/` 的 CDK，不从 `readiness-lab/` 部署。**不执行 cdk bootstrap**；新建角色必须带 `NBAHackathonParticipantBoundary`，保留已有 cdk.json context。当前发布脚本会拒绝旧账号 outputs，不回退练习输出。正式部署后仍须单独验证网页→Agent→完整成片→播放；目前配置迁移和离线合成不代表正式在线功能已恢复。

## 历史边界与本机备份

旧 `962768510637` 是练习账号，10 月8日角色接入被拒绝，旧CloudFront不可用。该账号曾验证Claude Sonnet4.6、Qwen3-VL、AgentCore完整MP4及T4 CUDA；Nova Lite曾拒绝。详见[服务历史报告](AWS-Team02-服务实际验证报告.md)和[赛前流水线报告](../../../readiness-lab/赛前准备实测报告-20261006.md)。这些不证明新正式账号相同能力。

本次配置备份为本机 `~/.aws/config.before-formal-20261010-090531`；旧备份为 `~/.aws/config.before-team02-role-20261005-182332` 和 `~/.aws/config.before-broadcastcode-20261005`。备份、SSO缓存及密码不进入Git。
