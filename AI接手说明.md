# BroadcastCode Team02：AI 接手说明

整理时间：2026-10-06，北京时间。本文记录前期对话落实到本地文件和测试证据的结果，便于新的 AI 或新电脑继续工作。它不包含账号密码、访问密钥或会话令牌。

## 1. 用户要完成什么，目前做到哪里

用户准备参加 NBA / AWS BroadcastCode「深度赛场」12h 黑客松，希望先理解规则、接通账号并确认服务和 GPU 真正可用，再推进作品开发。此前用户要求把准备工作完整留在项目里；本轮进一步要求仔细分析赛题并提出冲冠方案，目前处于方案研究，尚未实施正式产品。

用户随后提供学长[饶珈源的主页](https://jyrao.github.io/)，说明自己曾在该 AI for Sports 组实习，希望分析研究借鉴与交流机会。已完成[相关研究与复用路径核查](docs/上交AI4Sports研究借鉴与交流建议.md)：优先关注 BasketballSkills 的证据与工具编排，以及 BasketEvent 的篮球事件候选能力。没有联系作者、获取内部代码、安装运行研究模型或把研究组件接入产品。

**用户随后纠正交流重点：面向评委的黑客松产品原型，需要可借鉴的创新点，而非科研积累或模型复用。** 当前优先参考[产品创新与学长交流提纲](docs/产品创新与学长交流提纲.md)：把观众参与、人物焦点切换、关键动作揭示与证据回看组合为短体验。建议仍处于讨论阶段；不要将用户这次纠正理解为选定方案或授权向学长发送消息。

用户又要求重读手册并按评分确定开工状态。本轮再次读取 Quick Start、终极指南评分/提交章节和 Team Portal，当前 CLI 身份核对成功；Portal 的 GitHub 仍未绑定。核心环境已足以开工，但手册 Web 调用 Agent 和真实视频烧录后在网页播放的两项应用准备还未完整完成。具体评分映射与第一里程碑见[开工核对](docs/评分导向开发决策与准备状态-20261006.md)。本轮没有新增付费调用或部署。

最终作品应形成真实流程：**官方比赛视频与数据 → AgentCore 中的 Agent 识别和解释关键事件、战术 → 带时间和来源的标注 → 烧录到原视频并导出完整增强成片 → CloudFront 交互网页**。重点是篮球解读准确、画面表达清楚、网页可操作，并符合部署与提交要求。

当前已完成最新终极指南及新版 Quick Start 阅读、规则分析、正确 Portal 登录、AWS 双身份配置、部署限制核准、核心服务真实调用、GPU 运算和测试清理。本轮还下载公开训练视频，核查媒体信息并观察 26 张关键帧。**[关键一拍推荐方案](docs/关键一拍-冲冠产品与技术方案.md) 已形成，正式篮球处理流程尚未实现；尚未完成 GitHub 仓库绑定或最终作品提交。** 测试示例的 S3 / Lambda / DynamoDB 组合不等于已经选定最终架构。

目录原位置为 `/Users/jack/work/BroadcastCode`，但内部链接均使用相对路径。2026-10-06 整理时目录没有 `.git`，没有已配置的远端、提交或 PR；如果以后初始化了 Git，请以实际状态为准。

## 2. 阅读资料与证据层级

|资料|用途与状态|
|---|---|
|[正式指南核准更新](docs/2026-10-06-正式指南核准更新.md)|本轮已读终极指南与新版 Quick Start；覆盖旧材料中的评分、决赛及赛题边界信息|
|[关键一拍推荐方案](docs/关键一拍-冲冠产品与技术方案.md)|本轮推荐开发基线，尚未实现|
|[上交 AI for Sports 研究借鉴](docs/上交AI4Sports研究借鉴与交流建议.md)|BasketballSkills、BasketEvent 与跨项目借鉴核查；包括作者交流问题和最小接入实验建议，尚未实际复用|
|[公开训练样片核查](docs/research/公开训练样片核查.md)|两段视频的媒体信息、实际画面、标注难点与叙事建议；不是完整战术标注|
|[比赛规则与需求分析](BroadcastCode-比赛规则与需求分析.md)|已按最新指南更新硬性要求、评分、时间安排、建议和剩余未知项；是规则主文档|
|[赛前培训纪要及逐字稿](<BroadcastCode「深度赛场」赛事 · 赛前培训直播 会议纪要.md>)|9 月 28 日培训来源；包含转写，需结合公开页面和后续通知|
|[AWS 连接说明](AWS-Team02-连接说明.md)|账号切换原因、现有配置、登录和验证方法|
|[CDK 与 GPU 部署约束](BroadcastCode-CDK与GPU部署约束.md)|用户转交的主办方补充通知、权限边界和截图配额|
|[服务实际验证报告](AWS-Team02-服务实际验证报告.md)|10 月 5 日夜间至 6 日的真实操作结果、限制和清理|
|[验证工程说明](aws-validation/README.md)|历史脚本与 JSON 证据的索引、复用注意事项|
|[GPU 实际配额表](aws-validation/SageMaker-实际GPU配额.md)|本队账号、指定区域的实际查询结果；与原通知截图区分|

外部资料入口：

- [正确 Team Portal](https://du5imhgxabl0d.cloudfront.net/portal)：登录、队伍账号切换、仓库和作品提交。
- [CSDN 官方赛事页面](https://builderx.csdn.net/bcast-code)：已用于规则交叉核对。
- [参赛终极指南](https://csdn.feishu.cn/wiki/B3NSwj16GiSCR7kcM5vc9RjMnQb)、[新版 Rules & Quick Start](https://csdn.feishu.cn/docx/Y21TdJqrHopofmx2w21cmqHLnLb)：本轮已通过浏览器实际读取，摘要见核准更新。旧 `H0N3d4467osmp5x45VLc7RRgnqh` 链接为历史入口，不再作为当前 Quick Start。统一评测请求、字段与产物路径的完整 schema 仍未取得。
- [AWS 服务指南](https://du5imhgxabl0d.cloudfront.net/services)：已用于 CDK、模型和 AgentCore 实现路径核对；其通用 bootstrap 示例须服从主办方后续明确的“不要 bootstrap”通知。
- [训练视频压缩包](https://comfile.csdnimg.cn/file/train_video.zip)：本轮已下载至 `data/reference/` 并抽帧核查；包内仅有两段 MP4，无官方深度数据，尚未跑通自动加工与出片。
- [NBA 深度赛场](https://china.nba.cn/inside-the-game)、[NBA 比赛入口](https://www.nba.com/games)：数据入口，不代表已经拿到比赛数据字典或可直接对齐的样例。

最新指南已核准初赛 30+25 人工拆分、决赛五项权重、AgentCore 必须、完整成片与评审访问窗口。具体评测 schema、实际数据样例和部分执行细节仍待取得。不要把工程建议改写成官方必须，也不要仅凭 AWS 功能文档推断赛事计分方式。更新时优先使用主办方最新明确通知，并保留来源和日期。

## 3. 已知比赛要求与实施影响

|事项|当前已知内容|
|---|---|
|部署与访问|指定 AWS 账号、CDK、Amazon Bedrock AgentCore 必须；CloudFront 公网提供 Web 交互和烧录标注的完整增强成片|
|区域与 IAM|资源仅 `us-east-1`；不执行 bootstrap；新建角色必须带指定权限边界|
|GPU|通过 SageMaker 使用，按机型和用途分别核对配额|
|代码|GitHub 仓库必须私有并绑定正确 Team Portal；本次尚未绑定，先确定实际参赛仓库|
|素材|普通直播画面；公开包实测两段合计约 44.44 秒（培训口述约 48 秒）；早上抽签用于白天练习分配，最终考试素材 18:00 发布，按现场文件处理|
|核心数据|预期命中率、球员引力、胜负影响率；只有出手瞬间点位，没有逐帧轨迹；具体字段、坐标、单位和时间映射仍需样例|
|初赛分数|机器 35、数据/内容准确性 30、UX/UI 25、球迷问答 4、投篮 6；机器 35 的精确内部公式未取得|
|决赛|单轮、每队 5 分钟讲解，提问时长遵现场；架构 18、实现深度 18、数据准确 15、讲解答辩 9、视觉效果 40；初赛分不带入|
|时间|10 月 10 日 18:00 发考试素材；18:00–19:45 调优、19:45–20:00 提交；20:00 硬截止；CloudFront 成片和 Web 在 20:00–22:20 保持可访问|
|后续安排|10 月 9 日珠海报到；前八名晋级 10 月 11 日澳门决赛。物流、具体时段以最终通知为准|

完整解释见比赛分析。主要判断和边界：

- 初赛准确性 30 + UX/UI 25；并列依次人工、机器、准确性、UX/UI、问答。机器评分看架构稳定性、AWS 有效使用、服务协同和完整链路，从仓库重跑；不能声称新增一个服务固定增加某个分数。
- 29 个骨骼关键点是官方数据生产背景；最新指南已明确**只有出手瞬间点位，没有逐帧轨迹**，不要继续把逐帧轨迹是否提供当作未知。
- 题目明确排除实时接入、数字孪生、跑动轨迹复原、判罚认定和博彩预测；不要求训练模型参数。短时标签定位和出手快照叠加不等于轨迹复原。
- 正式指南明确解说可选，可为 AI 或人工；若采用 AI 解说须声明。篮球内容和叠加数据仍须准确。
- 开源、外部 API、额外合规素材与 AI 编程工具可用；人工校正与赛前成果复用边界仍待核准。机器会从仓库重跑，统一 Agent 输入/输出和产物路径必须依官方 schema，当前尚未拿到完整样例。
- 原培训纪要写“120 支队伍”，公开页面为 **120 人、每队 2–3 人**；使用已纠正的规模。

## 4. 前期完成的工作与关键问题的解决

|阶段|做了什么|留下的结论|
|---|---|---|
|规则梳理|读取培训纪要与逐字稿，核对官方公开页面|形成比赛分析，并列出尚未确认的实施边界|
|初次账号检查|登录 AWS Access Portal，测试初始 SSO 身份|登录本身成功，但中转角色无资源权限，多个服务读取报 AccessDenied|
|入口更正与角色切换|按老师更正通知进入正确 Team Portal，使用双配置切换本队账号|资源读取恢复；先前拒绝由身份选择错误造成|
|本机配置|建立 `nba-sso` 登录配置与 `nba` 实际操作配置，修正兼容别名，保留原 default|SSO 可刷新，无需把截图里的临时密钥写入项目|
|只读检查|身份、CloudFormation、CloudFront、Bedrock、AgentCore、bootstrap 和权限边界查询|目标账号与区域正确；服务入口可查询，但此阶段不能证明实际功能全可用|
|主办方补充要求|整理 CDK 通知与 GPU 配额截图，读取真实配额和相关权限|确定不 bootstrap、必须带边界、GPU 用途配额和可传递执行角色|
|真实服务验证|部署临时 CDK 工程，执行模型、应用、AgentCore 与 GPU 调用|功能验证成功，具体覆盖范围见下一节|
|清理与留证|保存结果 JSON，删除本次测试资源并逐项核实|历史证据保留，计算实例与临时部署已清理|
|最新指南与方案研究|10 月 6 日实际读取终极指南与新版 Quick Start，形成推荐方案|正式评分、AgentCore、完整成片和边界已核准；本轮没有再次部署或开始正式产品实现|

旧 SSO 入口仍用于身份登录；它不是比赛提交 Portal。此前旧示例应用指向本地 `localhost:5173`，不再作为比赛入口使用。当前没有需要继续追查的“中转账号服务读取失败”问题。

用户最初提供的账号开通通知 PDF 曾用于登录准备，目前该文件不在目录中；登录地址更正通知 PDF 仍在本机，含登录密码，已列入上传排除规则。新 AI 需要密码时由用户在本机提供或自行登录，不从交接文档获取。

## 5. AWS 身份、登录与换机器

|配置项|值|
|---|---|
|队伍|Team02|
|实际资源账号|`962768510637`|
|实际参赛角色|`NBAHackathonParticipantRole`|
|实际操作 profile|`nba`|
|SSO 登录 profile|`nba-sso`|
|兼容 profile|`broadcastcode-team02`，也指向实际参赛角色|
|SSO 中转账号与角色|`405496568869` / `NBAHackathon-Team02`，无应用资源权限|
|SSO 登录区域|`us-west-2`，仅身份登录使用|
|应用资源区域|`us-east-1`|
|直接服务调用的执行角色|`arn:aws:iam::962768510637:role/NBAHackathonWorkloadRole`|

本机配置在 `~/.aws/config`，没有写入项目。下面为可迁移的**非敏感配置示例**；在新机器上合并到自己的配置，不覆盖其他账号：

```ini
[profile nba-sso]
sso_session = broadcastcode-team02
sso_account_id = 405496568869
sso_role_name = NBAHackathon-Team02
region = us-east-1
output = json

[profile nba]
role_arn = arn:aws:iam::962768510637:role/NBAHackathonParticipantRole
source_profile = nba-sso
region = us-east-1
output = json

[profile broadcastcode-team02]
role_arn = arn:aws:iam::962768510637:role/NBAHackathonParticipantRole
source_profile = nba-sso
region = us-east-1
output = json

[sso-session broadcastcode-team02]
sso_start_url = https://identitycenter.amazonaws.com/ssoins-79078e660a07957b
sso_region = us-west-2
sso_registration_scopes = sso:account:access
```

登录和核对：

```sh
aws sso login --profile nba-sso
aws sts get-caller-identity --profile nba --region us-east-1
```

返回 `Account` 应为 `962768510637`，`Arn` 包含 `assumed-role/NBAHackathonParticipantRole/`。如果返回 `AWSReservedSSO` 或中转账号，修正调用配置后再操作。本机 `default` 属于其他用途，已保留，不用于比赛。

Portal 说明 SSO 约 12 小时、浏览器切换角色约 1 小时；CLI 在有效 SSO 会话内刷新角色凭证。新 AI 账号读取 GitHub 不会获得本机 AWS 登录状态；同机切换 AI 也须核对当前会话，不能根据历史报告假定仍有效。

更正通知写明练习权限至 **2026-10-08 09:00**。10 月 10 日正式比赛账号、续期和权限保留安排没有核准，不要默认届时一定使用同一账号。

此前配置备份在本机 `~/.aws/config.before-broadcastcode-20261005` 和 `~/.aws/config.before-team02-role-20261005-182332`，不在项目中，不会随仓库迁移。本次没有将临时密钥写入 `~/.aws/credentials`。

## 6. 实际验证了什么，以及不能推导什么

验证完成于 2026-10-06 00:05 左右，随后完成资源清理。以下是当时账号和区域的实测结果：

|能力|实测结果|范围|
|---|---|---|
|CDK / CloudFormation|临时栈成功部署 10 个资源|未执行 bootstrap；新 Lambda 角色实际带指定边界|
|S3 / Lambda / DynamoDB|上传、读取、写入再读取成功；Lambda 返回 `SERVICE_CHECK_OK`|用于验证业务读写通路，未做真实视频应用|
|CloudFront|公网 HTTPS 返回 200 和预期页面|临时分发已删除，不是最终入口|
|CloudWatch Logs|Lambda、AgentCore、GPU 运行日志生成|本次测试日志按范围清理|
|Claude Sonnet 4.6|文本成功；合成红色 PNG 正确返回 `Red`|ID：`global.anthropic.claude-sonnet-4-6`|
|Qwen3-VL|文本成功；相同图片正确返回 `Red`|ID：`qwen.qwen3-vl-235b-a22b`|
|AgentCore Runtime|Python 3.12 代码包发布至 READY；内部调用 Claude 返回 `AGENT_CHECK_OK`|已停止并删除；正式指南现已明确必须 AgentCore，统一评测接口仍需适配|
|SageMaker GPU|`ml.g4dn.xlarge` Training Completed；T4 执行 CUDA 矩阵运算返回 `128`|任务计费 199 秒，计算实例完成后释放|

GPU 证据为 Tesla T4，`nvidia-smi` 报 15360 MiB，PyTorch `2.9.0+cu130`，CUDA 13.0。它证明 CUDA 计算通路可用，**没有验证某个篮球视觉模型、真实视频吞吐或大模型显存需求**。

新版指南有“GPU 为 0”的旧描述，但主办方后续通知和本队 SageMaker 实测证明指定用途可用；按真实用途配额处理。Quick Start 的 Nova Lite / Haiku 调试建议和旧 `us.` Claude 示例不能覆盖本队实际权限；Haiku 未验证可用，Claude 保持已验证 `global.` ID。

两个模型是通过指南和账号策略核准的白名单。Nova Lite 实际调用被策略明确拒绝；读取到 120 个 Bedrock 模型目录条目不能推导全部可调用。Claude 使用 global inference profile，但请求仍从 `us-east-1` 发出，不据此将其他资源部署到别的区域。

直接 CLI / SDK 需要 `iam:PassRole` 的 SageMaker 和 AgentCore 调用使用主办方预置 `NBAHackathonWorkloadRole`。参赛身份直接修改 IAM 受限；CDK 利用既有部署角色路径创建带边界的新角色已经成功。不要混淆两种执行路径，或用任意新角色替换直接 API 的执行角色。

配额查询取得 358 个相关条目，整理 32 个尺寸。30 个 g4dn/g5/g6/g6e 尺寸的 **Processing 均为 0**，不能拿 Training 配额运行 Processing 任务。Endpoint、Training、Spot、Notebook、JupyterLab 分别计数；p3、trn1 部分条目未返回，不能认定为 0。`ml.trn1` 是 Trainium / Neuron 体系，不能当作 NVIDIA CUDA 的直接替代。

只有 `ml.g4dn.xlarge` Training 实际启动过；其他尺寸与用途仅查询配额。配额不保证即时容量。所有服务结论都是日期快照，未覆盖全部 AWS 服务、ECS、完整视频流程、并发性能或全部 GPU 尺寸。

## 7. 正式工程必须保留的 CDK 条件

将以下片段合并进实际项目的 `cdk.json`，保留原有 `app` 和其他 `context`：

```json
{
  "context": {
    "@aws-cdk/core:permissionsBoundary": {
      "name": "NBAHackathonParticipantBoundary"
    }
  }
}
```

主办方已完成 `us-east-1` bootstrap，已查到 `CDKToolkit` 为 `CREATE_COMPLETE`。**不执行 `cdk bootstrap`。** 正式 Stack 的环境必须明确匹配目标账号和区域；命令行指定区域不会修正代码中硬编码的错误环境。

在实际 CDK 工程中、当前任务已授权部署时使用：

```sh
AWS_REGION=us-east-1 AWS_DEFAULT_REGION=us-east-1 npx --no-install cdk synth --profile nba
AWS_REGION=us-east-1 AWS_DEFAULT_REGION=us-east-1 npx --no-install cdk deploy --profile nba
```

先核对身份、合成模板中的新建角色边界与实际资源，再部署。此配置是权限上限，业务所需权限仍须按资源授予。上述命令要求项目已安装本地 CDK；本机验证项目使用本地 CLI，没有依赖全局 `cdk`。

## 8. 测试资源已清理，保留的是历史证据

[cleanup.json](aws-validation/cleanup.json) 记录本次清理与独立核验：GPU Completed；AgentCore 会话、Runtime、自动工作负载身份和相应日志清理；临时 S3 对象和桶、Lambda、DynamoDB、CloudFront、新建 IAM 角色、测试栈以及本次发布到 bootstrap 桶的模板删除。主办方 bootstrap 和预置执行角色保留。

SageMaker Completed 任务的历史元数据仍可存在，**不表示 GPU 还在运行**。共享日志组未因本队测试而整体删除。`manifest.json`、请求 JSON 和任务 JSON 中的 ARN、桶名、会话 ID、URL 是历史记录，不用于新的部署。

旧测试 CloudFront 地址 `https://d2cw7gwcmc6u41.cloudfront.net` 对应分发已删除，不能当作当前演示或提交链接。这次文档整理没有再次连接云端核验；清理结论依据已保存的完成记录。

本机验证环境记录：AWS CLI v2.35.9，Node v22.22.0；验证工程锁定 `aws-cdk` CLI 2.1144.0、`aws-cdk-lib` 2.272.0、`constructs` 10.8.1；本地 Python 虚拟环境安装 boto3。包锁文件保留，`node_modules`、`.venv`、`cdk.out` 与临时代码包排除上传。这些是当时验证环境，不是赛事规定版本。

不要直接重跑旧 `prepare.py`、部署或清理脚本：名称固定含 `20261005`，会上传文件、覆写证据或操作历史资源；已完成的 SageMaker 任务名也不能用作新任务。确需复测时在当前用户授权范围内使用新名称、新清单和明确清理范围，详见验证工程说明。

## 9. 后续工作顺序与尚未确认事项

建议从以下步骤继续，按用户新指令调整：

1. **完成剩余协议与账号核验。** 终极指南和新版 Quick Start 已读，AgentCore 必须及正式评分已确认；取得统一评测请求、响应及产物路径 schema，确认 10 月 8 日之后账号安排。
2. **拿到训练视频和实际数据样例。** 检查字段、单位、时间粒度、球员身份、位置数据及视频时钟映射；先完成一个回合的可靠对应，避免依据不存在的逐帧轨迹选架构。
3. **确定参赛仓库再绑定。** 用户尚未给出目标 GitHub 仓库。应为私有仓库；Portal 绑定错误可能需组委会重置，不要替用户猜一个仓库或把临时验证工程直接绑定。
4. **确认推荐方案后实施最小闭环。** 阅读关键一拍方案并按用户确认推进；保留时间、来源与推断依据，优先自动输入到烧录增强 MP4 及 CloudFront Web，再打磨视觉与交互。
5. **演练新素材交付。** 测量分析、渲染、上传、部署和提交总时间；检查线上与远端代码对应。18:00 前应已有可更新的有效入口，最终截止以 20:00 为准。
6. **准备说明、演示与决赛讲法。** 说明自动流程、数据来源、云服务用途和限制；安排队员准备问答与投篮分数。

研究复用可与上述主线并行：截至本轮未找到作者公开的 BasketballSkills 整套实现；BasketEvent 有真实代码与列出的权重，但需要许可确认、帧率/GPU/输出适配及实际样片验证。公开 BasketEvent 流程也不等于论文 BasketballSkills 的全部工具。不得把“权重可下载”或“T4 CUDA 已测试”写成“篮球模型已跑通”；不要为等作者回复停下可独立完成的成片与交互开发。

仍需取得或核准：统一评测 schema 和可运行样例；实际数据字段、坐标系与视频时间映射；机器 35 分更细公式；人工校正与赛前代码复用范围；扫描分支与版本确认；视频/说明的进一步文件规格；决赛语言、提问时长及晋级后修改规则；费用上限、模型限流及视频输入路径。不要把已确认的 30+25、18/18/15/9/40、AgentCore、成片、可选解说和评审窗口继续记为未知。

截至整理，已下载并核查两段公开训练样片，但没有随包的官方深度数据，尚未跑通完整流程；已形成关键一拍推荐产品与技术基线，未开发正式前后端、未做完整视频或并发测试、未提交作品 URL。新 AI 应按用户后续开发指令继续，无需重复把所有服务从零测试一遍。

## 10. 可按任务选用的 AI 技能

此前 AI 使用 `handoff` 技能整理交接，并按用户要求保存在项目中。后续 AI 若有对应技能，可按需要选用：`pdf` 读取新通知，`frontend-design` 设计正式网页，`diagnosing-bugs` 定位实际问题，`handoff` 更新接手材料。技能是否可用取决于新环境，不是赛事硬性要求，也不应成为继续工作的前置障碍。
