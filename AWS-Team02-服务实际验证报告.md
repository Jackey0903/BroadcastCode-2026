# Team02 AWS 服务实际验证报告

完成实际功能验证：2026 年 10 月 06 日 00:05（北京时间）。测试横跨 10 月 5 日夜间和 10 月 6 日；测试资源清理已完成。

这是凌晨的历史服务验证报告。10 月 6 日下午新建并保留了独立的网页→Agent→完整视频流水线，最新入口、仓库绑定和两段真实视频结果见[赛前准备实测报告](readiness-lab/赛前准备实测报告-20261006.md)。下文“已清理”只指旧 `aws-validation/` 资源。

目标账号 `962768510637`，角色 `NBAHackathonParticipantRole`，配置 `nba`，区域 `us-east-1`。

## 结论

比赛常用核心服务已通过实际部署、调用和读写测试，GPU 已实际执行 CUDA 运算。服务开放仍受主办方的模型白名单、区域、IAM 操作和机型用途配额限制，不能将“服务开放”理解为任意服务、任意模型、任意 GPU 用途都可使用。

此前读取失败来自无资源权限的 SSO 中转账号，已经通过切换本队账号修复。GPU Processing 配额为 0 是具体用途受到限制，与账号登录是否成功是两回事。

## 实际功能验证结果

|项目|实际操作与结果|
|---|---|
|CDK / CloudFormation|成功部署 10 个资源，栈达到 CREATE_COMPLETE；没有执行 bootstrap|
|IAM 权限边界|新建 Lambda 执行角色成功；实际角色带 NBAHackathonParticipantBoundary|
|S3|上传和读取测试页面、代码包及 GPU 结果均成功|
|DynamoDB|Lambda 中写入记录后再读取，结果一致|
|Lambda|实际执行成功，返回 SERVICE_CHECK_OK，并成功记录运行日志|
|CloudFront|从公网 HTTPS 地址读取 S3 页面，HTTP 200，返回预期内容|
|CloudWatch Logs|取得 Lambda 运行日志；GPU 与 AgentCore 运行日志也已生成|
|Claude Sonnet 4.6|文本调用成功，图片调用正确返回 Red；ID 为 global.anthropic.claude-sonnet-4-6|
|Qwen3-VL|文本调用成功，图片调用正确返回 Red；ID 为 qwen.qwen3-vl-235b-a22b|
|AgentCore Runtime|成功发布 Python 代码包并调用；Runtime 内实际调用 Claude，返回 AGENT_CHECK_OK；会话已停止|
|SageMaker GPU|ml.g4dn.xlarge Training 任务 Completed；GPU 为 Tesla T4，CUDA 矩阵运算正确返回 128|

GPU 的 nvidia-smi 报告为 `Tesla T4, 15360 MiB`，PyTorch 为 `2.9.0+cu130`。任务计费运行时长为 **199 秒**，任务完成后计算实例自动释放。

## 明确的使用限制

1. **模型只能使用白名单。** 账号策略认可上表中的 Claude Sonnet 4.6 与 Qwen3-VL 调用资源。本次 Nova Lite 实际调用被明确拒绝；能读取 120 个模型目录条目不代表可以调用全部模型。
2. **区域固定 us-east-1。** Claude 的 global inference profile 是主办方指南使用、账号策略认可的模型调用路径；请求仍从 us-east-1 发出。其他应用资源不要部署到别的区域。
3. **GPU 配额按机型和用途分别限制。** 已读取 358 个相关 SageMaker 配额条目，整理 32 个机型尺寸；其中 30 个 g4dn/g5/g6/g6e 尺寸的 Processing 配额均为 0。p3 与 trn1 的部分用途条目未由接口返回，表中如实标出；不能把未返回当成 0。Training、Endpoint、Notebook、JupyterLab 按各自配额使用。
4. **CLI 的服务执行角色有要求。** 需要传递执行角色时，当前参赛身份仅被允许传递预置 `arn:aws:iam::962768510637:role/NBAHackathonWorkloadRole`。本次 SageMaker 和 AgentCore 直接调用使用该角色。直接修改 IAM 被限制；通过 CDK 创建的新角色必须带指定权限边界，本次已经验证此路径成功。
5. **其他 GPU 尺寸只核准了配额。** 实际计算测试覆盖 ml.g4dn.xlarge Training；没有启动全部 32 个尺寸或所有用途。配额不保证某个时间点的硬件容量，也不能证明任意模型都装得进显存。

完整配额见 [SageMaker 实际 GPU 配额](aws-validation/SageMaker-实际GPU配额.md)。

## 测试证据与边界

- [模型图片调用结果](aws-validation/model-tests.json)
- [Lambda、CloudFront、AgentCore 调用结果](aws-validation/live-tests.json)
- [GPU 运算结果](aws-validation/gpu-result.json)
- [GPU 任务状态与计费秒数](aws-validation/gpu-job.json)

本次是账号和服务能力验证，未覆盖最终篮球应用、真实视频流程、并发性能或评分细则。临时测试页面不是正式参赛作品。

## 测试资源清理

GPU 任务已完成并释放计算实例；AgentCore 会话、Runtime、自动创建的工作负载身份和运行日志已清理。CDK 测试栈已删除；随后分别核实测试 S3 桶、Lambda、DynamoDB 表、CloudFront 分发及新建 IAM 角色均已不存在，发布到 bootstrap 桶的本次测试模板也已删除。主办方现有 bootstrap 和预置执行角色保留。SageMaker 保留 Completed 任务的历史记录，计算实例已停止。

[查看清理核验结果](aws-validation/cleanup.json)。
