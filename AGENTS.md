# 后续 AI 的工作约束

先读 [README.md](README.md) 和 [AI接手说明.md](AI接手说明.md)。详细规则以 [10 月 6 日正式指南核准更新](docs/2026-10-06-正式指南核准更新.md)、[比赛分析](BroadcastCode-比赛规则与需求分析.md) 和主办方最新通知为依据，区分已核准要求、工程建议与未确认事项。

## 当前状态

- 最新终极指南与新版 Quick Start 已读取；规则、账号和历史服务/GPU 验证已完成。旧 `aws-validation/` 资源已删除，其 URL、ARN、桶名仅作历史证据。
- 本轮已通过 CDK 部署 `readiness-lab/` 练习流水线：CloudFront → Lambda API → SQS → 视频 Worker → AgentCore/Claude → 完整 MP4 → S3/CloudFront，含 DynamoDB 任务状态。[当前入口](https://d2x8td5d05xg8h.cloudfront.net)对应 Stack `BroadcastCodeTeam02Readiness20261006` **保留**，不要按旧测试清理结论删除新资源。先读[本轮实测报告](readiness-lab/赛前准备实测报告-20261006.md)和[工程说明](readiness-lab/README.md)。
- 弗拉格任务 `030eb6203d694a9d9e8a97c25755f9c1`（21.548 秒）与阿门任务 `4da872a6dac44ad49607b98865c43705`（22.895 秒）均完成，成片均在浏览器播放到末尾；独立下载、哈希、媒体时长、音轨、HTTP Range 206 和永久字幕检查通过。32 项离线测试通过。练习字幕为稀疏图像的模型观察，不是已对齐的官方深度数据；练习工程不是正式参赛产品或评分认证。
- [关键一拍推荐方案](docs/关键一拍-冲冠产品与技术方案.md) 仍为产品建议，不能记为用户已定稿或全部实现。10 份 NBA 官网真实参考 JSON 已放入 `readiness-lab/fixtures/official/`，可随仓库克隆；正式视频事件映射和评测 schema 仍未知。按用户当前开发指令推进，不额外设立审批步骤。
- 用户希望借鉴其学长所在 AI for Sports 组的研究；[研究核查与交流建议](docs/上交AI4Sports研究借鉴与交流建议.md) 已整理。研究论文、公开代码、权重存在与实际运行验证是不同状态；尚未联系作者或接入研究模型。BasketEvent 不等于 BasketballSkills 的整套实现，不因有 GPU 就假定完整流程可用。
- 用户最新明确该交流主要为了**产品创新与评委展示体验**，不是科研或模型复用；优先读[产品创新与学长交流提纲](docs/产品创新与学长交流提纲.md)。提案尚未实现或定稿，不自动转成模型训练任务。
- 最新[评分与开工核对](docs/评分导向开发决策与准备状态-20261006.md)已补上真实 Web→Agent→完整成片→播放验证。对新输入的鲁棒性、篮球内容准确性与正式交付仍按各自证据验收，不将练习通路当作全部准备完成。
- 本目录已初始化 Git 并推送至私有 `Jackey0903/BroadcastCode`，默认分支 `main`；Portal 已显示仓库 locked in。赛事 App 仅对该仓库读取代码和元数据，见[绑定证据](readiness-lab/repository-binding.json)。不要重新选择或绑定仓库；后续仍以实际 Git 状态和 Portal 证据为准。
- 历史或当前脚本本身均不构成再次创建、计费或删除云资源的指令。按当前用户任务判断授权范围；当前练习资源的保留是明确状态。

## 已核准的产品与评分要求

- 必须使用 Amazon Bedrock AgentCore、AWS CDK、CloudFront Web 交互。增强完整成片为 P0：把准确数据叠加并烧录到真实比赛视频；页面临时叠加不能替代成片。解说可选，AI 解说须声明。
- 官方数据只有出手瞬间点位，没有逐帧轨迹；排除实时接入、数字孪生、跑动轨迹复原、判罚认定和博彩预测。短时标签定位不要包装成轨迹重建。
- 初赛机器 35、准确性 30、UX/UI 25、问答 4、投篮 6。决赛单轮、每队 5 分钟讲解、提问时间遵现场安排；架构/深度/准确性/讲解/视觉权重为 18/18/15/9/40，初赛成绩不带入。
- 10 月 10 日 20:00 提交截止，CloudFront 完整成片与交互入口须覆盖 20:00–22:20 评审窗口。私有仓库、部署 Agent、说明和演示视频均为交付物。
- 机器评测要从代码重跑；统一 Agent 接口、输入结构、产物路径的完整 schema 仍未取得，必须按主办方实际样例适配。

## AWS 部署必须遵守

- 实际操作使用 `--profile nba`，资源区域为 `us-east-1`。`nba-sso` 只负责 SSO 登录中转；不要使用本机 `default`。
- 部署前核对身份：目标账号 `962768510637`，角色 `NBAHackathonParticipantRole`。新会话或新机器不能假定登录缓存仍有效。
- 主办方已完成 bootstrap，**不要执行 `cdk bootstrap`**。通用教程中的 bootstrap 步骤不适用于本赛事。
- 实际项目的 `cdk.json` 必须合并 `context["@aws-cdk/core:permissionsBoundary"] = { "name": "NBAHackathonParticipantBoundary" }`，保留已有配置；Stack 的账号和区域也须正确。
- 直接通过 CLI / SDK 创建需要执行角色的服务时，当前已核准的可传递角色是 `arn:aws:iam::962768510637:role/NBAHackathonWorkloadRole`。CDK 创建新角色需走已有部署路径并带指定边界。不要尝试更改主办方 IAM 限制。
- 已实测的模型为 `global.anthropic.claude-sonnet-4-6`、`qwen.qwen3-vl-235b-a22b`；请求从 `us-east-1` 发出。模型目录条目不代表调用权限，Nova Lite 已被策略拒绝。
- 正式指南中的“GPU 配额为 0”、Quick Start 的 Nova Lite / Haiku 建议和旧 `us.` Claude 前缀不能覆盖本队后续通知与实测：SageMaker GPU 已验证，Nova Lite 已拒绝，Claude 保持已验证 `global.` ID；Haiku 未被验证可用。
- GPU 按通知走 SageMaker，按具体机型和用途核对配额。30 个已查询的 g4dn/g5/g6/g6e 尺寸 Processing 配额为 0。仅 `ml.g4dn.xlarge` Training 做过实际启动验证。
- 测试清理只针对本次自己创建的资源；保留主办方 `CDKToolkit`、预置执行角色及其他团队或共享资源。

## 数据、规则和文档

- 不编造官方指标、球员身份或逐帧坐标；对可观察事实、官方数据和模型推断分别标明依据。
- 不把 GPU 配额当成容量保证，不把服务实测当成评分认证，不把未返回的配额当成 0。
- 已确认的正式评分、AgentCore、成片和提交窗口不要继续写成未知。官网参考 JSON 不等于正式比赛样例；统一评测 schema、视频事件/坐标/时钟映射、人工校正与赛前复用边界、评测器锁定提交方式及更细文件格式仍待确认。仓库默认分支已确认为 `main`。
- 练习账号通知期限仍为 2026-10-08 09:00；[权限期限核查](readiness-lab/account-expiry-audit.json)只说明当前可读 IAM 策略没有可见时间条件，不证明 10 月 8 日以后续期。没有明确通知前保留未知状态。
- 通知 PDF 可能含密码。不要把密码、临时访问密钥、SSO 缓存、外部 API 密钥或 `.env` 提交到仓库或写入前端。
- 本目录内的文档链接用相对路径，便于其他电脑与 GitHub 阅读。更新进度时同步 README、接手说明及受影响的专题文档。
- `aws-validation` 的脚本绑定历史名称和资源，含上传、调用、计费及清理操作。阅读 [该目录说明](aws-validation/README.md) 后再决定如何复用，不要直接重跑整套脚本。
