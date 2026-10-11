# GameBuddy · Repository guidance

先读 [README.md](README.md)、[产品工程指南](product/README.md) 和 [AI接手说明.md](AI接手说明.md)。当前阶段是赛后维护与开源文档整理；用户于 2026-10-12 确认 Team02 获得 NBA × AWS 黑客松银奖。

## 工作范围

- 当前实现位于 `product/`。`readiness-lab/` 与 `aws-validation/` 是历史工程；前者仍提供主链构建依赖的固定媒体工具。
- 比赛规则、协同日志和旧状态保存在 [docs/archive/competition-2026/](docs/archive/competition-2026/README.md)。历史指令和脚本不自动授权重新部署、创建、计费或删除资源。
- 保留用户已有改动与真实运行记录；清理以归档和明确入口为主，不删除唯一的源码、来源、失败证据或已验收媒体。
- 更新文档使用相对链接。主 README 面向新读者，不追加逐轮联调快照。
- 原创代码采用 MIT；第三方数据、媒体、字体、模型和商标遵循 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## 内容真实性

- 产品名统一为 **GameBuddy**。
- 自动 RL 样片与编辑 55 秒展示片分别验收，不互借模型调用或媒体证据。
- 数值从来源记录读取，区分事件、本场完整赛后统计和赛季快照；不编造身份、坐标、单位和缺失值。
- 官方 xFG 是检索到的事件事实。Gravity / Leverage 是来源分数，不换算为胜率；赛季背景不证明单回合因果。
- 战术板、箭头、空间区域与人物轮廓属于编辑示意，不称自动追踪或真实空间重建。
- SFT 后验证 15/16、测试 16/16；RL 相对 SFT 无额外增益。产品 6/6 是已知样片上的模型与语义护栏组合验收。
- 观看区全部偏好尚未传给创作 Agent，不宣称任意偏好的整片自动重生成。

## 工程检查与凭据

- 运行 `python3 product/scripts/check.py --full` 核验修改后的工程；首次需要 `npm ci --prefix product --ignore-scripts`。门禁不认证云端、实际媒体包或模型效果。
- 不提交 `.env`、凭据、SSO 缓存、私钥、含密码的主办方 PDF、MP4、权重、构建目录和依赖目录。
- `SHOWCASE.md` 是冻结的比赛作品说明；`publish_readme.py` 读取它，维护主 README 不自动改线上 `/readme`。

## 赛事 AWS 约束

赛事环境使用 `--profile nba`、`us-east-1`，部署前核对 `deployment.json` 中的账号与角色；不使用 `default`。主办方已 bootstrap，禁止重复执行。角色须带 `NBAHackathonParticipantBoundary`，不得尝试绕过 IAM 限制。

赛后参赛身份的模型与资源管理权限曾被限制；STS 成功或旧 CloudFront 可访问不代表重新生成可用。自己的 AWS 环境需独立适配并验收。不要从 `readiness-lab/` 覆盖主产品 Stack；旧 `practice` 远端不接受新产品增量。

完整比赛期约束及出处见[历史 AGENTS](docs/archive/competition-2026/AGENTS-比赛期间.md)，已结束的排期和旧状态按其日期理解。
