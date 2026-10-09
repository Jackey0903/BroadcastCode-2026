# BroadcastCode「深度赛场」黑客松准备资料

**2026-10-09 本地开发：** 已恢复独立于云服务的[本地预览](http://127.0.0.1:4173/product/)。原片、已验收增强成片、关键帧及真实历史 Agent 记录均从本机读取；新的推理暂不可用。本轮状态与优先事项见[本地开发进度](docs/本地开发进度-20261009.md)，100 项离线测试通过。

**2026-10-08 11:06（北京时间）状态更新：** `nba` 接入参赛角色实测被 STS AssumeRole AccessDenied 拒绝；产品网页不可访问，公共 DNS 没有返回其 A 地址，主办方 Portal 仍响应。与通知中的 10 月 8 日 09:00 练习权限到期相符，但后台资源是否删除、正式权限何时重开仍未确认。源码及成片独立备份存在；详见[只读核查](product/evidence/service-status-20261008.json)。

最后整理：2026-10-09（北京时间）。队伍：Team02。

本项目的目标是参加 NBA / AWS BroadcastCode 12h 黑客松：用官方比赛视频和数据驱动 AI Agent 分析关键事件与战术，将真实数据标注烧录成完整增强视频，并通过 CloudFront 交互网页交付评委体验；解说可选。

**已开始实现「关键一拍 / THE HIDDEN PLAY」产品：** [在线体验](https://d2x8td5d05xg8h.cloudfront.net/product/)包含观看原片、选择关注点、关键动作慢放、官方出手数据与证据回看，以及真实 Agent 创作入口。产品工程在 [product/](product/README.md)，现场讲解在 [5 分钟演示脚本](product/PITCH.md)。两段公开练习片已与官方具体出手唯一匹配；两段均已有真实 Agent 生成并完整播放的增强成片；最新回归与内容验收状态以[产品证据](product/evidence/README.md)为准。

原[练习入口](https://d2x8td5d05xg8h.cloudfront.net)与产品此前复用 Stack `BroadcastCodeTeam02Readiness20261006`，后续应从 `product/` 部署，避免旧工程覆盖新功能。旧 `aws-validation/` 对应资源已删除。正式评测协议与新素材适配仍待完成。

## 给新 AI 的阅读顺序

1. 先读 [AI 接手说明](AI接手说明.md)：任务背景、已完成工作、关键结论、环境迁移和待办。
2. 读 [正式指南核准更新](docs/2026-10-06-正式指南核准更新.md) 和 [比赛规则与需求分析](BroadcastCode-比赛规则与需求分析.md)：最新硬性要求、评分、输入数据与剩余未知项。
3. 读 [关键一拍：冲冠产品与技术方案](docs/关键一拍-冲冠产品与技术方案.md)：历史推荐方案，当前实现以 product/ 及实测证据为准。
4. 开发或部署前读 [AWS 连接说明](AWS-Team02-连接说明.md) 和 [CDK 与 GPU 部署约束](BroadcastCode-CDK与GPU部署约束.md)。
5. 当前开发先读[产品工程](product/README.md)和[产品实测](product/evidence/README.md)，再读[赛前准备实测报告](readiness-lab/赛前准备实测报告-20261006.md)和[练习工程说明](readiness-lab/README.md)；历史服务及 GPU 证据见[服务实际验证报告](AWS-Team02-服务实际验证报告.md)和[旧验证工程说明](aws-validation/README.md)。

准备复用研究模块或与学长交流时，读 [上交 AI for Sports 研究借鉴与交流建议](docs/上交AI4Sports研究借鉴与交流建议.md)。其中区分论文方法、公开代码、权重和待核验的实际运行效果；目前未接入任何研究模型。

用户最新明确：与学长交流主要为了借鉴**产品创新和展示体验**。优先读[产品创新与学长交流提纲](docs/产品创新与学长交流提纲.md)，其中推荐“选择关注对象 → 关键一拍回放 → 发现漏看细节”的体验；该核心交互已在 product/ 实现。

历史练习链路核对见[评分导向开发决策与准备状态](docs/评分导向开发决策与准备状态-20261006.md)。弗拉格 21.548 秒、阿门 22.895 秒两段完整成片均已在浏览器播放到末尾，独立下载、哈希、媒体时长、音轨、HTTP Range 206 和永久字幕检查通过；32 项离线测试通过。Portal 已确认锁定 `Jackey0903/BroadcastCode`，默认分支为 `main`。

[AGENTS.md](AGENTS.md) 为后续编程代理提供操作约束。原始培训材料在 [赛前培训会议纪要及逐字稿](<BroadcastCode「深度赛场」赛事 · 赛前培训直播 会议纪要.md>)；口头说明和纪要中的转写不能替代最新正式指南。

10 月 7 日最后部署的产品版本：**85 项产品离线测试通过**；弗拉格与阿门均已有真实 Agent 生成、独立媒体验证和浏览器完整播放的展示成片。查看[产品验收记录](product/evidence/README.md)及其版本边界。

## 当前进度

|工作|状态|
|---|---|
|赛题、评分结构与交付要求分析|已读终极指南及新版 Quick Start；统一评测 schema 与视频事件映射仍待取得|
|关键一拍产品|已实现交互前端、工具型 Agent、官方数据关联和完整成片渲染；实测状态见产品证据|
|上交 AI for Sports 研究借鉴|已核查 BasketballSkills、BasketEvent 等论文及公开实现；交流问题已整理，尚未联系作者或运行模型|
|正确 Team Portal 登录与队伍账号切换|已成功，CLI 配置为 `nba`|
|CDK 练习流水线|截至 10 月 7 日已真实部署；10 月 8 日权限被拒绝，当前资源是否保留无法核查|
|Claude Sonnet 4.6、Qwen3-VL|文本及图片调用已成功；其他模型不能据此视为开放|
|AgentCore Runtime|10 月 7 日真实调用并生成完整 MP4；本地目前回看历史结果|
|SageMaker GPU|`ml.g4dn.xlarge` Training 的 T4 CUDA 运算成功|
|资源状态|旧 `aws-validation/` 已清理；新 Stack 原计划保留，但到期后实际状态未知；本队未保留 GPU 作业|
|公开训练样片|两段已下载并检查媒体信息、26 张关键帧；合计约 44.44 秒，见[核查报告](docs/research/公开训练样片核查.md)|
|官网深度数据参考|10 份真实 JSON 已保存并复制到[可随仓库克隆的 fixtures](readiness-lab/fixtures/official/)；另有 product/ 中的两段样片事件映射，仍不是正式评测 schema|
|练习完整成片|弗拉格和阿门两段均生成完整 MP4、浏览器播放到末尾并核对永久字幕；产品招牌交互已实现，正式评测输入仍待适配|
|离线验证|10 月 9 日本地产品 100 项通过；旧练习 32 项为历史记录，不等于官方评分认证|
|私有参赛仓库和 Portal 绑定|[Jackey0903/BroadcastCode](https://github.com/Jackey0903/BroadcastCode) 已推送、Portal 已锁定；[绑定证据](readiness-lab/repository-binding.json)|

服务和配额结论是 **2026-10-05 至 10-06 的实测快照**。后续会话先核对当前身份、权限有效期和主办方更新，再部署。练习账号通知写明权限至 **2026-10-08 09:00**；[本轮 IAM 只读核查](readiness-lab/account-expiry-audit.json)未发现可见时间条件，但这不能证明续期，正式比赛账号安排仍需组委会确认。

## 最新规则要点

- 必须 Amazon Bedrock AgentCore、AWS CDK、CloudFront Web 交互；P0 包含把数据烧录到真实比赛画面的完整增强成片。
- 官方数据只有出手瞬间点位、无逐帧轨迹；题目排除实时接入、数字孪生、跑动轨迹复原、判罚和博彩预测。
- 初赛为机器 35 + 准确性 30 + UX/UI 25 + 问答 4 + 投篮 6。决赛单轮、每队 5 分钟讲解，提问时长遵现场安排；权重为架构 18、实现深度 18、数据准确 15、讲解答辩 9、视觉效果 40，初赛分不带入。
- 10 月 10 日 20:00 截止，CloudFront 完整成片及交互入口在 20:00–22:20 保持可访问。官方 Agent 输入、输出和产物路径的完整 schema 仍待拿到，不能把本队内部格式当作官方协议。
- 指南个别 GPU、Nova Lite、旧 Claude 前缀示例与本队后续通知和实测冲突；依 [核准更新](docs/2026-10-06-正式指南核准更新.md) 处理，保留既有 SageMaker 和模型白名单限制。

## 分享和迁移

源码、部署定义和交接材料都保存在本地。10 月 9 日用户明确先在本地开发；本轮只做本地提交和存档，未经新的明确授权不推送。此前准备工程已推送为既有事实。通过 `scripts/archive-source.py` 在仓库旁的 `BroadcastCode-backups/` 保存并验证源码、Git 历史与白名单媒体，详见[源码保存与恢复](docs/源码保存与恢复.md)。

本目录已初始化 Git，远端为私有仓库 [Jackey0903/BroadcastCode](https://github.com/Jackey0903/BroadcastCode)，默认分支 `main`，已完成推送与 Portal 锁定绑定。赛事 GitHub App 仅获该仓库的代码和元数据读取权限。绑定不可自行更换；如有错误须联系组委会，不要重新绑定其他仓库。当前练习 URL 尚未作为正式作品提交，详见[绑定记录](readiness-lab/repository-binding.json)。

文档中的内部链接使用相对路径，可随项目迁移。账号 ID、角色名和区域用于准确接手；密码、访问密钥和会话令牌没有写入交接文档。AWS SSO 配置与登录缓存位于本机 `~/.aws/`，不会随仓库迁移，新机器需按接手说明重新配置并登录。

根目录 [.gitignore](.gitignore) 已排除含登录密码的账号通知 PDF、本地凭证、依赖目录及临时部署产物。`.gitignore` 只影响 Git；手工打包或上传目录时，同样应排除这些文件。非敏感的 GPU 配额截图保留在 [参考资料](参考资料/SageMaker-GPU-配额-20261005.jpg)。

可以把下面这段话交给下一位 AI：

> 请先阅读 README.md、AGENTS.md、AI接手说明.md 和 readiness-lab/赛前准备实测报告-20261006.md。私有仓库已绑定，历史云端流水线已验收，10 月 8 日练习权限被拒绝且新 Stack 存续未知；当前本地预览可用，旧 aws-validation 资源已删除；产品实现与验收详见 product/README.md、product/evidence/README.md；正式协议适配未完成。在当前用户授权范围内继续推进，不重复绑定仓库、不自动清理保留资源、不执行 CDK bootstrap、不使用默认 AWS 账号或上传账号密码。
