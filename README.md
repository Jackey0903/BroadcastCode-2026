# BroadcastCode「深度赛场」黑客松准备资料

最后整理：2026-10-06（北京时间）。队伍：Team02。

本项目的目标是参加 NBA / AWS BroadcastCode 12h 黑客松：用官方比赛视频和数据驱动 AI Agent 分析关键事件与战术，将真实数据标注烧录成完整增强视频，并通过 CloudFront 交互网页交付评委体验；解说可选。

**目前已完成规则与账号核查，并通过 CDK 部署可在线操作的赛前练习流水线：网页提交 → AgentCore 模型观察 → 完整视频烧录 → CloudFront 播放。私有 GitHub 仓库已推送并在 Portal 锁定绑定。** [当前练习入口](https://d2x8td5d05xg8h.cloudfront.net)和新 Stack 保留；`aws-validation/` 对应的旧测试资源已删除。练习流水线验证工程通路，正式篮球产品、官方数据对齐与统一评测适配仍待完成。

## 给新 AI 的阅读顺序

1. 先读 [AI 接手说明](AI接手说明.md)：任务背景、已完成工作、关键结论、环境迁移和待办。
2. 读 [正式指南核准更新](docs/2026-10-06-正式指南核准更新.md) 和 [比赛规则与需求分析](BroadcastCode-比赛规则与需求分析.md)：最新硬性要求、评分、输入数据与剩余未知项。
3. 读 [关键一拍：冲冠产品与技术方案](docs/关键一拍-冲冠产品与技术方案.md)：本轮推荐开发基线，尚未实现。
4. 开发或部署前读 [AWS 连接说明](AWS-Team02-连接说明.md) 和 [CDK 与 GPU 部署约束](BroadcastCode-CDK与GPU部署约束.md)。
5. 当前开发先读[赛前准备实测报告](readiness-lab/赛前准备实测报告-20261006.md)和[练习工程说明](readiness-lab/README.md)；历史服务及 GPU 证据见[服务实际验证报告](AWS-Team02-服务实际验证报告.md)和[旧验证工程说明](aws-validation/README.md)。

准备复用研究模块或与学长交流时，读 [上交 AI for Sports 研究借鉴与交流建议](docs/上交AI4Sports研究借鉴与交流建议.md)。其中区分论文方法、公开代码、权重和待核验的实际运行效果；目前未接入任何研究模型。

用户最新明确：与学长交流主要为了借鉴**产品创新和展示体验**。优先读[产品创新与学长交流提纲](docs/产品创新与学长交流提纲.md)，其中推荐“选择关注对象 → 关键一拍回放 → 发现漏看细节”的体验；尚未定稿或实现。

最新开工核对见[评分导向开发决策与准备状态](docs/评分导向开发决策与准备状态-20261006.md)。弗拉格 21.548 秒、阿门 22.895 秒两段完整成片均已在浏览器播放到末尾，独立下载、哈希、媒体时长、音轨、HTTP Range 206 和永久字幕检查通过；32 项离线测试通过。Portal 已确认锁定 `Jackey0903/BroadcastCode`，默认分支为 `main`。

[AGENTS.md](AGENTS.md) 为后续编程代理提供操作约束。原始培训材料在 [赛前培训会议纪要及逐字稿](<BroadcastCode「深度赛场」赛事 · 赛前培训直播 会议纪要.md>)；口头说明和纪要中的转写不能替代最新正式指南。

## 当前进度

|工作|状态|
|---|---|
|赛题、评分结构与交付要求分析|已读终极指南及新版 Quick Start；统一评测 schema 与视频事件映射仍待取得|
|冲冠产品方案|已形成推荐开发基线；尚未实现|
|上交 AI for Sports 研究借鉴|已核查 BasketballSkills、BasketEvent 等论文及公开实现；交流问题已整理，尚未联系作者或运行模型|
|正确 Team Portal 登录与队伍账号切换|已成功，CLI 配置为 `nba`|
|当前 CDK 练习流水线|AgentCore、CloudFront、Lambda API、SQS、视频 Worker、S3、DynamoDB 已真实部署，资源保留|
|Claude Sonnet 4.6、Qwen3-VL|文本及图片调用已成功；其他模型不能据此视为开放|
|AgentCore Runtime|当前练习网页通过异步任务真实调用 Runtime 与 Claude，并生成完整 MP4|
|SageMaker GPU|`ml.g4dn.xlarge` Training 的 T4 CUDA 运算成功|
|资源状态|旧 `aws-validation/` 已清理；新 `BroadcastCodeTeam02Readiness20261006` 保留；无保留 GPU 作业|
|公开训练样片|两段已下载并检查媒体信息、26 张关键帧；合计约 44.44 秒，见[核查报告](docs/research/公开训练样片核查.md)|
|官网深度数据参考|10 份真实 JSON 已保存并复制到[可随仓库克隆的 fixtures](readiness-lab/fixtures/official/)；不是配套视频映射或正式评测 schema|
|练习完整成片|弗拉格和阿门两段均生成完整 MP4、浏览器播放到末尾并核对永久字幕；正式产品与招牌交互仍待实现|
|离线验证|32 项测试通过；不等于官方评分认证|
|私有参赛仓库和 Portal 绑定|[Jackey0903/BroadcastCode](https://github.com/Jackey0903/BroadcastCode) 已推送、Portal 已锁定；[绑定证据](readiness-lab/repository-binding.json)|

服务和配额结论是 **2026-10-05 至 10-06 的实测快照**。后续会话先核对当前身份、权限有效期和主办方更新，再部署。练习账号通知写明权限至 **2026-10-08 09:00**；[本轮 IAM 只读核查](readiness-lab/account-expiry-audit.json)未发现可见时间条件，但这不能证明续期，正式比赛账号安排仍需组委会确认。

## 最新规则要点

- 必须 Amazon Bedrock AgentCore、AWS CDK、CloudFront Web 交互；P0 包含把数据烧录到真实比赛画面的完整增强成片。
- 官方数据只有出手瞬间点位、无逐帧轨迹；题目排除实时接入、数字孪生、跑动轨迹复原、判罚和博彩预测。
- 初赛为机器 35 + 准确性 30 + UX/UI 25 + 问答 4 + 投篮 6。决赛单轮、每队 5 分钟讲解，提问时长遵现场安排；权重为架构 18、实现深度 18、数据准确 15、讲解答辩 9、视觉效果 40，初赛分不带入。
- 10 月 10 日 20:00 截止，CloudFront 完整成片及交互入口在 20:00–22:20 保持可访问。官方 Agent 输入、输出和产物路径的完整 schema 仍待拿到，不能把本队内部格式当作官方协议。
- 指南个别 GPU、Nova Lite、旧 Claude 前缀示例与本队后续通知和实测冲突；依 [核准更新](docs/2026-10-06-正式指南核准更新.md) 处理，保留既有 SageMaker 和模型白名单限制。

## 分享和迁移

本目录已初始化 Git，远端为私有仓库 [Jackey0903/BroadcastCode](https://github.com/Jackey0903/BroadcastCode)，默认分支 `main`，已完成推送与 Portal 锁定绑定。赛事 GitHub App 仅获该仓库的代码和元数据读取权限。绑定不可自行更换；如有错误须联系组委会，不要重新绑定其他仓库。当前练习 URL 尚未作为正式作品提交，详见[绑定记录](readiness-lab/repository-binding.json)。

文档中的内部链接使用相对路径，可随项目迁移。账号 ID、角色名和区域用于准确接手；密码、访问密钥和会话令牌没有写入交接文档。AWS SSO 配置与登录缓存位于本机 `~/.aws/`，不会随仓库迁移，新机器需按接手说明重新配置并登录。

根目录 [.gitignore](.gitignore) 已排除含登录密码的账号通知 PDF、本地凭证、依赖目录及临时部署产物。`.gitignore` 只影响 Git；手工打包或上传目录时，同样应排除这些文件。非敏感的 GPU 配额截图保留在 [参考资料](参考资料/SageMaker-GPU-配额-20261005.jpg)。

可以把下面这段话交给下一位 AI：

> 请先阅读 README.md、AGENTS.md、AI接手说明.md 和 readiness-lab/赛前准备实测报告-20261006.md。私有仓库已绑定，当前练习流水线及新 Stack 保留，旧 aws-validation 资源已删除；正式产品与官方协议适配未完成。在当前用户授权范围内继续推进，不重复绑定仓库、不自动清理保留资源、不执行 CDK bootstrap、不使用默认 AWS 账号或上传账号密码。
