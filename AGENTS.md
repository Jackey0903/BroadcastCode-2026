# 后续 AI 的工作约束

先读 [README.md](README.md) 和 [AI接手说明.md](AI接手说明.md)。详细规则以 [10 月 6 日正式指南核准更新](docs/2026-10-06-正式指南核准更新.md)、[比赛分析](BroadcastCode-比赛规则与需求分析.md) 和主办方最新通知为依据，区分已核准要求、工程建议与未确认事项。

## 当前状态

- 2026-10-10 最新用户授权：正式比赛重新连接、新建私有 `Jackey0903/BroadcastCode-2026`、绑定 Team02 并迁入既有代码后继续开发。本次 Portal 已锁定新仓库，App 仅对它读取代码和元数据；`origin` 为新仓库，`practice` 为旧仓库，默认 main。旧“不能重新绑定”针对练习阶段，已被正式 Portal 重置和本次明确指令取代；新绑定完成后勿再次更换。正式 AWS 账号为 `555726205424`，身份已核对，product/ CDK 已实际创建／更新，AgentCore READY，原片／帧／配置／网页已发布。正式端到端链路已跑通：弗拉格d143c261ef194f27ab1683b9fff1b15e由网页创建、真实生成、独立核验、Chrome完整播放及内容通过，选为观看区成片。阿门7a2a70d1c2b348ceb16b5129ef1a4bd1技术成功但早段时钟措辞内容拒收，保留失败；观看区阿门沿用已验收历史ce008e75d25d4e2e8e88b57412f6c762并标注historical。时钟防护已部署；用户收敛为整链路跑通即收尾，不追加阿门重跑。见[正式验收](docs/正式账号端到端验收-20261010.md)。最新269项核心门禁通过；此前262项CI成功，最新CI另核对对应提交，本轮主链路不验证GPU或RL集成。见[正式重连](docs/正式比赛重连与新仓库-20261010.md)、[审计](product/evidence/formal-account-audit-20261010.json)、[绑定](product/evidence/formal-repository-binding-20261010.json)。用户最新进一步授权：比赛期间所有验收增量持续整理、提交并推送新 `origin/main`，并本地存档，不逐次询问，不向旧 `practice` 推送。
- 2026-10-10 评分与质量：先读[冲刺与评分对齐](docs/比赛冲刺与评分对齐-20261010.md)和[快速迭代门禁](docs/工程质量与快速迭代-20261010.md)。初赛机器35/准确30/体验25/问答4/投篮6，决赛18/18/15/9/40；现场照片第五项遮挡，40依据核准指南。有效服务协同、真实完整成片和可重跑优先，不按服务数量堆资源。每个增量运行 `python3 product/scripts/check.py --full`；GitHub main/PR自动执行同一离线门禁。门禁使用明确合成媒体占位，只核验模板，不认证实际媒体部署包、模型或上线。用户确认目前仍用Portal两训练片、没有另发材料；受控注册表与本地新素材登记已实现，完整官方评测schema仍待取得，俯视板维持本地研究示意，不包装成正式自动追踪。
- 10 月 9 日历史安排：Claude 前端已合并；俯视底角与路线优化完成202项测试并本地存档，现已迁入正式仓库。保留像素街机风格与来源边界，见[Claude 接手](docs/Claude前端接手说明.md)及[俯视证据](product/evidence/court-clarity-20261009.json)。
- 10 月 9 日最新 `product/court-lab/` 覆盖弗拉格全片 0–21.548118 秒，31 源帧 × 10 匿名编号，9 段编辑球权 D5→出手命中→W3→传球→W2（W4 接球猜测已否定）。estimated 足点、inferred/image:null 粗略站位、last-known 历史快照明确不同；全部 reviewed:false。保留过去位置不计当前更新、不延伸轨迹或原片标记，未入镜不倒填未来。半场/全场、跟随持球、1秒/3秒/全段轨迹、阶段解析均已测试；184 项离线测试及全片浏览器播放见[最新证据](product/evidence/court-full-20261009.json)与[复现说明](product/court-lab/README.md)。旧三秒、失败光流和独立检测为历史，非默认来源。未接入云端、Agent 或增强成片，仍是编辑示意，不称自动/官方追踪或已获正式许可。
- 10 月 9 日用户要求只做桌面网页展示，优先复用上一场 `/Users/jack/draftcode` 前端素材，不采用外部 skill 方案。当前视觉为像素街机 × 极简黑场（`product/web/arcade.css` / `arcade.js`，俯视板 `product/court-lab/lab.css`），中英双语短标签，见[像素街机视觉系统](docs/前端像素街机视觉系统-20261009.md)；此前暖纸视觉见[旧素材复用](docs/前端视觉更新与旧素材复用-20261009.md)。像素字标与球场带等装饰不得包装成追踪结果；来源与边界说明可以压缩，不能删除。
- 10 月 9 日本地预览已去掉云代理，运行 `python3 product/scripts/serve.py`，入口 http://127.0.0.1:4173/product/。原片/最终成片按 SHA-256 核对，本地历史记录明确标注，不启动新推理；含后续视觉回归的 111 项离线测试通过。详见[本地开发进度](docs/本地开发进度-20261009.md)。10 月 8 日参赛角色被拒绝、原 CloudFront 地址不可用；旧账号资源是否删除未知；正式新账号已按10月10日顶部状态重连，不用历史保留结论冒充当前可用。
- 10 月 9 日用户明确先在本地开发。本轮可以提交本地 Git 并存档，**10 月 9 日晚已按用户授权同步推送 `main`；10 月 10 日比赛期间持续推送授权已覆盖旧逐次询问约束**。此前准备工程已推送为既有事实。服务器仅保存部署副本，源码、依赖锁定文件、CDK 与说明都须在本地；运行 `python3 scripts/archive-source.py` 可生成可恢复的源码/Git/媒体存档。赛前成果正式复用边界仍待主办方确认。

- 用户本轮已授权产品开发，当前工程 **`product/`**，旧练习入口 https://d2x8td5d05xg8h.cloudfront.net/product/（已不可用）；正式产品已部署于 https://deky02484tknr.cloudfront.net/product/，本轮完整验收见[正式验收](docs/正式账号端到端验收-20261010.md)。交互、两样片官方事件匹配和工具型 Agent 已实现，实时完成与验收以[产品实测](product/evidence/README.md)为准；不要用旧练习报告冒充本轮验收。下一次部署从 product/ 执行，复用同一 Stack；从 readiness-lab/ 部署会覆盖新后端。
- 10 月 7 日最后部署的产品版本：85 项产品离线测试通过；最终展示成片任务为 `81a74837370e46a890cbacb2069074e6`（弗拉格）、`ce008e75d25d4e2e8e88b57412f6c762`（阿门）。真实推理、媒体与浏览器证据在 product/evidence；保留失败及内容拒收记录。仍不代表正式评分、新输入或人类专家验收。
- 产品采用两种明确不同的内容：观看区为编辑策展的三视角；创作区为 AgentCore 真实读图、取官方快照和多轮计划。观看选择尚未传给创作 Agent。不得将编辑锚点说成自动 OCR 或把内部 product-story-v1 说成官方评测协议。
- 两段公开练习片已匹配具体官方事件：弗拉格 game 0022500701 / event 666 / xFG 51.0%，阿门 game 0022500491 / event 396 / xFG 44.5%；PBP 关联键是 actionNumber。原值、原始数据、图像锚点与核对程序在 product/data 和 product/research。当前两训练片已在正式账号登记发布；新考试素材仍按实际来源适配，不能称任意新视频已验收。
- 最新终极指南与新版 Quick Start 已读取；规则、账号和历史服务/GPU 验证已完成。旧 `aws-validation/` 资源已删除，其 URL、ARN、桶名仅作历史证据。
- 本轮已通过 CDK 部署 `readiness-lab/` 练习流水线：CloudFront → Lambda API → SQS → 视频 Worker → AgentCore/Claude → 完整 MP4 → S3/CloudFront，含 DynamoDB 任务状态。[旧练习入口](https://d2x8td5d05xg8h.cloudfront.net)对应旧账号 Stack `BroadcastCodeTeam02Readiness20261006` **保留**，不要按旧测试清理结论删除新资源。先读[本轮实测报告](readiness-lab/赛前准备实测报告-20261006.md)和[工程说明](readiness-lab/README.md)。
- 弗拉格任务 `030eb6203d694a9d9e8a97c25755f9c1`（21.548 秒）与阿门任务 `4da872a6dac44ad49607b98865c43705`（22.895 秒）均完成，成片均在浏览器播放到末尾；独立下载、哈希、媒体时长、音轨、HTTP Range 206 和永久字幕检查通过。32 项离线测试通过。练习字幕为稀疏图像的模型观察，不是已对齐的官方深度数据；练习工程不是正式参赛产品或评分认证。
- [关键一拍推荐方案](docs/关键一拍-冲冠产品与技术方案.md) 为历史设计建议，核心已进入 product/ 实现，不能将全部扩展记为已完成。10 份 NBA 官网真实参考 JSON 已放入 `readiness-lab/fixtures/official/`，可随仓库克隆；正式视频事件映射和评测 schema 仍未知。按用户当前开发指令推进，不额外设立审批步骤。
- 用户希望借鉴其学长所在 AI for Sports 组的研究；[研究核查与交流建议](docs/上交AI4Sports研究借鉴与交流建议.md) 已整理。研究论文、公开代码、权重存在与实际运行验证是不同状态；尚未联系作者或接入研究模型。BasketEvent 不等于 BasketballSkills 的整套实现，不因有 GPU 就假定完整流程可用。
- 用户最新明确该交流主要为了**产品创新与评委展示体验**，不是科研或模型复用；优先读[产品创新与学长交流提纲](docs/产品创新与学长交流提纲.md)。部分交互已在 product/ 实现，但未接入研究模型，不自动转成模型训练任务。
- 最新[评分与开工核对](docs/评分导向开发决策与准备状态-20261006.md)已补上真实 Web→Agent→完整成片→播放验证。对新输入的鲁棒性、篮球内容准确性与正式交付仍按各自证据验收，不将练习通路当作全部准备完成。
- 旧 `Jackey0903/BroadcastCode` 与[旧绑定证据](readiness-lab/repository-binding.json)仅作练习历史；正式仓库及当前锁定状态以本文顶部与10月10日证据为准。
- 历史或当前脚本本身均不构成再次创建、计费或删除云资源的指令。按当前用户任务判断授权范围；当前练习资源的保留是明确状态。

## 已核准的产品与评分要求

- 必须使用 Amazon Bedrock AgentCore、AWS CDK、CloudFront Web 交互。增强完整成片为 P0：把准确数据叠加并烧录到真实比赛视频；页面临时叠加不能替代成片。解说可选，AI 解说须声明。
- 官方数据只有出手瞬间点位，没有逐帧轨迹；排除实时接入、数字孪生、跑动轨迹复原、判罚认定和博彩预测。短时标签定位不要包装成轨迹重建。
- 初赛机器 35、准确性 30、UX/UI 25、问答 4、投篮 6。决赛单轮、每队 5 分钟讲解、提问时间遵现场安排；架构/深度/准确性/讲解/视觉权重为 18/18/15/9/40，初赛成绩不带入。
- 10 月 10 日 20:00 提交截止，CloudFront 完整成片与交互入口须覆盖 20:00–22:20 评审窗口。私有仓库、部署 Agent、说明和演示视频均为交付物。
- 机器评测要从代码重跑；统一 Agent 接口、输入结构、产物路径的完整 schema 仍未取得，必须按主办方实际样例适配。

## AWS 部署必须遵守

- 实际操作使用 `--profile nba`，资源区域为 `us-east-1`。`nba-sso` 只负责 SSO 登录中转；不要使用本机 `default`。
- 部署前核对身份：正式目标账号 `555726205424`，角色 `NBAHackathonParticipantRole`。新会话或新机器不能假定登录缓存仍有效。
- 主办方已完成 bootstrap，**不要执行 `cdk bootstrap`**。通用教程中的 bootstrap 步骤不适用于本赛事。
- 实际项目的 `cdk.json` 必须合并 `context["@aws-cdk/core:permissionsBoundary"] = { "name": "NBAHackathonParticipantBoundary" }`，保留已有配置；Stack 的账号和区域也须正确。
- 直接通过 CLI / SDK 创建需要执行角色的服务时，正式账号预置执行角色已查到 `arn:aws:iam::555726205424:role/NBAHackathonWorkloadRole`，AgentCore已使用此角色达到READY并完成正式Claude故事任务；该结果只覆盖本次部署路径，不推导所有服务PassRole均可用。CDK 创建新角色需走已有部署路径并带指定边界。不要尝试更改主办方 IAM 限制。
- 正式账号已通过阿门任务实测 `global.anthropic.claude-sonnet-4-6`；Qwen、Haiku、Nova和GPU不在本轮主链路验收。旧练习账号已实测的模型为 `global.anthropic.claude-sonnet-4-6`、`qwen.qwen3-vl-235b-a22b`；请求从 `us-east-1` 发出。模型目录条目不代表调用权限，Nova Lite 已被策略拒绝。
- 正式指南中的“GPU 配额为 0”、Quick Start 的 Nova Lite / Haiku 建议和旧 `us.` Claude 前缀不能覆盖本队后续通知与实测：SageMaker GPU 已验证，Nova Lite 已拒绝，Claude 保持已验证 `global.` ID；Haiku 未被验证可用。
- GPU 按通知走 SageMaker；正式555账号主链路未核查或启动GPU；并行研发如有结果，须按其自己的用途、配额和运行证据核对，不能由本轮成片推断。下列30个配额/T4结果仅旧练习账号。30 个已查询的 g4dn/g5/g6/g6e 尺寸 Processing 配额为 0。仅 `ml.g4dn.xlarge` Training 做过实际启动验证。
- 测试清理只针对本次自己创建的资源；保留主办方 `CDKToolkit`、预置执行角色及其他团队或共享资源。

## 数据、规则和文档

- 不编造官方指标、球员身份或逐帧坐标；对可观察事实、官方数据和模型推断分别标明依据。
- 不把 GPU 配额当成容量保证，不把服务实测当成评分认证，不把未返回的配额当成 0。
- 已确认的正式评分、AgentCore、成片和提交窗口不要继续写成未知。官网参考 JSON 不等于正式比赛样例；统一评测 schema、视频事件/坐标/时钟映射、人工校正与赛前复用边界、评测器锁定提交方式及更细文件格式仍待确认。仓库默认分支已确认为 `main`。
- 练习账号通知期限仍为 2026-10-08 09:00；[权限期限核查](readiness-lab/account-expiry-audit.json)只说明当前可读 IAM 策略没有可见时间条件，不证明 10 月 8 日以后续期。没有明确通知前保留未知状态。
- 通知 PDF 可能含密码。不要把密码、临时访问密钥、SSO 缓存、外部 API 密钥或 `.env` 提交到仓库或写入前端。
- 本目录内的文档链接用相对路径，便于其他电脑与 GitHub 阅读。更新进度时同步 README、接手说明及受影响的专题文档。
- `aws-validation` 的脚本绑定历史名称和资源，含上传、调用、计费及清理操作。阅读 [该目录说明](aws-validation/README.md) 后再决定如何复用，不要直接重跑整套脚本。

本次代码验收与同步：`1fce2c1`已推送正式`origin/main`，[269项托管门禁](https://github.com/Jackey0903/BroadcastCode-2026/actions/runs/38021795732)成功；源码和38份白名单媒体已在本地存档并验证恢复。
