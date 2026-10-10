# RL-SCOUT：NBA / AWS 深度数据与训练任务设计

核查日期：2026-10-10，北京时间。仅读取本地资料、官方公开页面及其实际使用的少量 GET 接口；未启动云资源、模型调用或训练，未更改主链路代码。本文件是工程研究建议，不是官方评测协议。

**最新用户范围：下一轮只使用火箭 HOU 与独行侠 DAL 两队数据。** 本文中的全联盟响应和最初规模统计保留为来源核查历史，不加入下一轮训练；有效检索数据入口为 [two-team-context.json](../product/rl/data/depth/two-team-context.json)。两队过滤规则、源文件 hash、字段单位、球员 ID 与缺失列表均已写入该文件。

## 1. 现在可做什么

**真实的赛季球员引力、持球/无球引力、胜率影响力数据已经取得，可以用于有来源的检索和解释训练。** 本轮保存了 234 名球员的引力、261 名球员的影响力、125 名球员的投篮难度数据及逐字段可用率。它们均为 `2025-26 / Regular Season` 的球员赛季汇总，不能冒充两段视频里的瞬时引力。

当前 xFG 估计任务应继续用逐出手标签，清除全赛季档案泄漏；另设“选对指标—查询—解释—必要时说明缺失”的小型工具任务。这两类任务的标签、指标和评价应分别保留。

两队当前可用范围：

|当前来源快照球队标签|Gravity 球员|Leverage 球员|Shot Difficulty 球员|已有逐出手样本|
|---|---:|---:|---:|---:|
|HOU / 火箭 / 1610612745|8|8|5|3,086 次，5 人|
|DAL / 独行侠 / 1610612742|10|12|3|1,525 次，3 人|
|合计|18|20|8|4,611 次，8 人|

这里合并覆盖 20 名球员，12 人仅有赛季背景而没有当前采集的逐出手样本。两队出手数据实际日期为 2025-10-27 至 2026-03-01；不能沿用全联盟数据的 4 月终点。DAL 的加福德 `1629655` 与华盛顿 `1629023` 在当前 Leverage 表中出现、Gravity 表中缺失，应返回 `not_in_source_cohort`，不填零。

Shot Difficulty 按官方 `TEAMID` 筛选；Gravity/Leverage 使用官方响应中的 `lightLogo/darkLogo` 文件名精确匹配 HOU/DAL，并映射到上述已知 ID。只要两个可读标识冲突就不纳入。**这些是当前赛季响应的球队标签，不是历史比赛日名单**；不据此断言转队球员在某段旧视频里属于该队。原始三份响应未改写，cohort 每行记录源行号与球队标签的来源字段，便于复现。

原始数据、抓取时间、HTTP 状态、原始字节 SHA-256 与字段统计见 [depth/manifest.json](../product/rl/data/depth/manifest.json)，摘要见 [审计 JSON](../product/rl/results/depth-data-audit-20261010.json)。当前页面引用的 bundle 是 `index-8c467dd5.js`，与 10 月 6 日核查的文件已不同。

## 2. 来源和真实字段

|公开入口|粒度与键|本轮结果|可用字段及限制|
|---|---|---|---|
|[season/playerGravity](https://api.nba.cn/nba-web/api/web/inside/season/playerGravity?season=2025-26&seasonType=Regular+Season)|`PLAYERID + 请求中的 season + seasonType`|234 名；五类引力全部非空|`OVERALL_GRAV`、`ON_BALL_PERIM_GRAV`、`ON_BALL_INTERIOR_GRAV`、`OFF_BALL_PERIM_GRAV`、`OFF_BALL_INTERIOR_GRAV`；另有 `GP`、`MP`、PTS/REB/AST。没有 gameId、eventId、时间、引力分钟数或各类样本量。|
|[season/playerLeverage](https://api.nba.cn/nba-web/api/web/inside/season/playerLeverage?season=2025-26&seasonType=Regular+Season)|同上|261 名；影响力字段全部非空|`TOT_LVG`、`OFF_LVG`、`DEF_LVG`、`ON_BALL_DEF_LVG`、`SHOT_LVG`、`CREATION_LVG`、`REB_LVG`、`TOV_LVG`。没有本次回合贡献值；保留原始分值，不转换为获胜概率百分比。|
|[season/shotDifficulty](https://api.nba.cn/nba-web/api/web/inside/season/shotDifficulty?season=2025-26&seasonType=Regular+Season)|同上，另有 `TEAMID`|125 名；数值字段全部非空|`AVGSHOTQUALITY`、两分/三分 xFG、`FGPCT`、`FGPCTABOVEEXPECTED`、命中/未中条件均值、最低命中 xFG、`AVGDEFENDERBALLDISTANCE`、`AVGDEFENDERPRESSURESCORE`。没有赛季内截止日期或逐场值。|
|[gpShot：弗拉格](https://api.nba.cn/nba-web/api/web/inside/gpShot?gameId=0022500701&playerId=1642843)|`gameId + eventId`；playerId 为请求/记录关联|既有 23 次出手；阿门为 18 次|`value` 为单次官方 xFG；`success` 为结果；还有 period、shotType、shotDesc、locX/locY/side。两片样例 gameClock 为空。完整字段/坐标边界见[既有审计](../readiness-lab/official-source-audit.md)。|
|[def：弗拉格场次](https://api.nba.cn/nba-web/api/web/inside/def?gameId=0022500701)|gameId|本轮再次 HTTP 200、code 0、`data:null`|不可用，不能转成零防守压力。阿门既有样例也为 null，本轮没有重复查询。|
|[season/year](https://api.nba.cn/nba-web/api/web/inside/season/year)|赛季目录|6 条|2025-26 的常规赛、季后赛、季前赛、全明星、附加赛，以及 2026-27 季前赛；目录存在不等于每种指标均有足够数据。|

数据事实与定义来源：NBA 中国[指标说明](https://china.nba.cn/inside-the-game/glossary)、[球员引力页](https://china.nba.cn/inside-the-game/player-gravity)及页面实际引用的[公开 bundle](https://res.nba.cn/static/webmaster/assets/js/index-8c467dd5.js)。本次只读取公开 GET 路由，没有执行下载的脚本、猜测隐藏接口或绕过鉴权。

### 单位、覆盖和联接

- xFG 原始范围是 0–1；显示百分比乘 100。FG%+ 是 `FG% − xFG`，显示应使用“百分点”；本轮 125 行该恒等式全部成立。`gpShot` 的单场聚合字段另有既有语义疑点，不能从赛季表的正确性推导所有同名字段都可信。
- GRAV 为高于/低于空间布局预期的防守关注分值，允许负数，不是概率、时长或吸引了几名防守人。四类按持球/无球及距篮筐 20 英尺的内外线划分；不得自行把它们简单平均为 OVERALL_GRAV。
- 公开中国术语页定义了 DEF DIST 的测量对象，但**未确认原始单位**。本轮 `AVGDEFENDERBALLDISTANCE` 为 26.8–50.1，不能自行标为英尺、厘米或换算。DEF PS 为专有防守压力分值，本轮 0.768–0.879，不能从此推定其完整理论范围。
- Leverage 是官方影响力分值；中国赛季表没有明确每场/每回合等归一化口径。AWS 的[技术介绍](https://aws.amazon.com/blogs/media/how-the-nba-and-aws-built-an-ai-system-to-measure-what-actually-wins-basketball-games/)说明其核心为反事实比较和回合归因，但不能把该介绍当成本接口输出粒度的证明。
- 三套榜单覆盖不同，均不是全联盟完整球员表。只有 LASTNAME 各有 1 个空值；数值非空不代表抽样完整。三分字段还存在 0 值且没有出手次数，无法仅据 0 判断真实概率或无出手。
- 最初全联盟来源快照的 15,171 条记录实际含 168 个有数据的比赛、121 名球员，日期为 2025-10-27 至 2026-04-10；原 manifest 的 233 是采集计划选中的比赛数，不能说 233 场都有训练样本。引力可关联 106 名/13,879 次出手，影响力可关联 112 名/14,405 次。这是历史来源审计；当前只用顶部的两队 4,611 条记录。
- 球员 ID 保留字符串；赛季与赛季类型由请求元数据补齐。引力/影响力没有数值 TEAMID；本轮已按用户授权用官方球队 logo 标签建立 HOU/DAL 当前快照映射，但不能给旧视频断言归属。转队和不同统计区间必须另处理。
- 两段已核对的事件使用 `gameId + gpShot.eventId = gameId + PBP.actionNumber`；不能把 eventId 当视频秒数。抓取时间 `retrievedAt` 也不是比赛时刻或赛前截止日期。

## 3. 各指标适合什么训练用途

|指标|可以做|目前不成立的用途|
|---|---|---|
|逐出手 xFG `value`|隐藏标签；评价估计误差和条件区间；或在“查官方值”任务中让工具返回并检验引用|在估计任务里把它、命中结果或由它构造的答案提示直接给策略|
|赛季五类 Gravity|工具检索、同范围排序/差值、正确解释负号及持球/无球差别|逐帧引力标签、该次助攻因果证明、回合即时防守注意力|
|赛季 Defensive Pressure/Distance|带“赛季平均”的背景查询；距离单位未知时诚实保留未知|视频瞬时测量、距离监督标签或自行换算后的几何监督|
|赛季 xFG 与 FG%+|区分机会质量和实际投篮表现；单位/百分点训练|当前同赛季、同球员、留出比赛的无泄漏预测特征|
|赛季 Leverage / Creation LVG|检索球员赛季背景、选择与问题相关的统计项|本事件胜率变化或对一次传球/掩护的贡献分摊|

AWS 的[合作说明](https://www.aboutamazon.com/news/aws/nba-aws-cloud-ai-partnership-basketball-innovation)把 Shot Difficulty 与站位、出手准备、防守干扰联系起来，也将 Gravity 描述为有球/无球时吸引防守的影响。这些上游模型依赖追踪资料，不能由“我们取得其结果表”推导为“我们拥有其逐帧输入”。赛题仍按[核准指南](2026-10-06-正式指南核准更新.md)排除轨迹复原。

## 4. 对当前 RL-SCOUT 的直接建议

1. **xFG 预测主线先去泄漏。** 现有 `References` 的区域/动作表只用训练行，但 `player_profile` 直接载入完整 2025-26 赛季档案；其中有目标均值和结果统计，覆盖 90 名留出球员。工具名称为“档案”不会消除泄漏。预测主线禁用该工具，球员参考改由训练行构建；新取得的 Gravity/Leverage 也不加入该主线特征。
2. 继续整场分组留出全部 HOU–DAL 对阵；在当前两队范围内按比赛划分训练、验证，其他球队的出手不得作为下一轮样本或先验。原后期联盟集只保留为旧实验记录。若需要严格时间声明，应统一训练截止日，再冻结参考表；先检查两队实际只有截至 3 月 1 日的已取得样本，不按请求日期范围假设后续数据存在。
3. 区域×动作联合先验值得优先做；保持罕见动作回退与样本量。不应靠增加工具次数制造 agentic 优势。检验的是策略能否在信息有用时查询，并获得比固定表基线更好的误差/区间分数。
4. 点估计若优化 MAE，其理想解是条件中位数；若需要“条件平均官方质量”，使用平方误差并报告相应指标。区间使用未截断 interval score 或 20%/80% pinball loss；对 score 做硬裁剪后不能继续声称严格 proper。条件区间描述“同类出手官方 xFG 的分布”，并不是该球进/不进的 60% 置信区间。
5. 自然语言理由不能仅以“没有新数字”获得 grounded 满分；应验证引用的字段、统计范围、符号与允许的算术。不要奖励未经视觉证据支持的“他吸引包夹，所以产生空位”等因果句。

## 5. 小型多任务方案：官方指标检索与解释

独立任务包已实现，**尚未训练**：[depth_tasks.py](../product/rl/depth_tasks.py) 仅从两队快照生成 **410 个可程序核验任务**，其中 290 检索、40 同指标差值、80 缺失或边界判断（46 事件粒度、14 源表缺失、6 历史截止、6 错赛季、6 错球队、2 因果证据不足）。实际组成与下表建议比例不同；换算/自然语言解释扩展仍是建议，不能说已实现。

`generate_tasks(cohort, player_ids)` 生成任务，`policy_view(task)` 隐藏答案和任务类别，`lookup(cohort, request)` 返回来源事实，`score_answer(task, answer, tool_results)` 验证模型输出；调用轨迹必须由训练器记录，不能由模型自报。数值容差 0.0005；来源 hash、抓取时间、赛季、球队快照标签、单位和负号均纳入评分。结构化输出拒绝额外自由文本；因此当前评分只认证这些结构字段，不声称理解任意自然语言因果。6 项关键离线测试通过，包含全部 410 正解与真实查询输出的一致性。摘要见 [任务计划](../product/rl/results/depth-task-plan-20261010.json)。

后续训练按球员分组，分别传入不相交的 `player_ids`；比较题双方自动限定在同组。当前 v4 出手质量训练不载入此任务包，两种奖励不可混成同一个成功率。

工具只需 `official_player_metrics(playerId, season, seasonType, metricFamily)`，返回字段白名单、来源 URL、原始文件 hash、粒度和可用状态。当前工具只读取 `two-team-context.json` 的 20 名球员，不从保留的全联盟原始表补齐。球队查询按 cohort 已记录的来源标签过滤。工具结果带 `scope: player-season`，字段原名与单位说明一起返回；未提供的粒度按 unavailable 返回。

|任务与比例建议|输入例|可验证答案|
|---|---|---|
|单项/五项检索 35%|“查弗拉格 2025-26 常规赛五类引力。”|总体 3.828；外线持球 2.897；内线持球 −2.938；外线无球 6.217；内线无球 −2.410。必须保留赛季范围、单位 score、源字段。|
|同范围比较 20%|“同赛季弗拉格与阿门的总体引力差多少？”|3.828 − (−4.593) = 8.421 分；仅说明前者较高，不推断视频中谁造成空位。|
|指标区分/换算 20%|“弗拉格赛季 xFG 48.1%，FG% 46.8%，FG%+ 是多少？”|−1.3 个百分点；不是 −1.3% 相对变化，也不是本次出手 xFG。|
|粒度与缺失 20%|“event 666 出手前一秒弗拉格无球引力多少？”|`unavailable`，原因 `event_granularity_not_available`；可附已取得的赛季背景，但不可填进 requestedValue。也包括未知球员、def:null、缺球队映射。|
|符号/单位陷阱 5%|“阿门总体 −4.593 是否数据错误？DEF DIST 45.1 是否英尺？”|负 GRAV 可有效；距离单位未确认。不能截零或自动改成正数。|

建议结构化答复包含 `status`、`playerIds`、`season`、`seasonType`、`scope`、`metric`、`value`、`unit`、`sourceId` 和可选 `operation/operands`。保留 `missing`、`null`、`not_in_cohort`、`unsupported_grain` 的区别，JSON 数值不能用字符串“--”代替。

**奖励建议（检索任务，独立于预测分数）：**

`R = 0.45 * value_or_correct_unavailable + 0.25 * scope_and_metric + 0.20 * evidence_and_arithmetic + 0.10 * schema − 0.002 * tools`。

- 每个正确性项均程序判定；数值按公开精度容差，比较检查操作数、顺序和差值；百分数和百分点分别判单位。
- event 请求伪填 season 值、无来源改写数值、把不可用填零、给 gravity 加百分号等关键错误将总奖励限制为非正。正确无法回答只在实际缺失/不支持的 episode 得分，防止一律拒答。
- 不以检索次数多为奖励。可回答的任务和不可回答的任务均保留；同一个数值出现在错误字段或球员上不能得分。
- 训练/验证在两队 20 人之内按球员分组，比较题的两名球员必须属于同一分区；另外留出措辞和算术模板。评估时工具可读取该留出球员的官方行，这是检索任务的正常外部证据，而不是让策略背答案。报告 exact-value、scope accuracy、unsupported-claim rate、unit accuracy、工具成本；20 人的小样本不能包装成全联盟泛化验证。
- 该任务可以验证 Agent 的数据使用能力，不能据此宣称视觉模型理解了防守、从视频测出引力，或 xFG 估计的盲测提升。

## 6. 当前未取得的材料

本轮检查的 NBA 中国页面 bundle 没有找到逐事件引力或逐事件 Leverage 的公开路由，也没有找到训练所需的每次防守压力/距离和历史 as-of 参数；这仅限于已检查来源，不意味着 NBA 的其他授权系统不存在这些数据。若主办方随后提供事件级附件，可按 `gameId/eventId/playerId/time` 对齐后扩展训练，先确认单位和粒度，再设计标签。

数据源真实可用与比赛交付权限、官方评测适配、模型上线效果是不同状态。该核查没有更改[两段样片已核准事件](../product/research/)的结果，也没有触发主产品重新部署。
