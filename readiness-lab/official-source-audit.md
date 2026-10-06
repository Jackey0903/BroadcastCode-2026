# 官方来源核查：深度数据、评测契约与账号期限

核查日期：2026-10-06。NBA 样例保存时间：15:58:03–15:58:05（北京时间，UTC+8）。本轮只进行公开页面、页面所用公开 GET 接口和本地既有记录的只读核查；没有读取含密码的通知 PDF、发送询问、创建资源或下载比赛视频。

## 结论与可执行边界

|核查项|本轮证据|当前结论|
|---|---|---|
|真实深度数据样例|从 NBA 中国官网实际使用的公开接口取得两名训练视频同名球员、相同日期的逐次投篮 JSON，已保留原始响应和哈希|**已取得官网参考样例**，可以做解析、缺失值处理、出手点位可视化与候选事件核对；尚不是组委会配套文件，也未完成视频逐事件匹配|
|统一机器评测 schema|服务页及其服务示例脚本没有赛事请求、响应、异步状态、产物路径的完整约定；既有正式指南核查也未取得完整样例|**仍是外部依赖**。内部 `team02-readiness-v1` 只能作为本队测试协议，不能称为官方适配完成|
|10 月 8 日以后账号安排|既有更正通知记录只明确练习权限到 2026-10-08 09:00；本轮服务页没有续期或正式账号安排|**仍是外部依赖**。当前能登录、STS 能刷新，均不能证明 10 月 10 日权限已获续期|

## 来源与本轮读取方式

|主源|读取结果与用途|
|---|---|
|[AWS 服务指南](https://du5imhgxabl0d.cloudfront.net/services)|无需登录的 HTTP 200；读取页面与页面引用的服务示例脚本。页脚说明其用于练习，不是生产配置。|
|[服务示例脚本](https://du5imhgxabl0d.cloudfront.net/_next/static/chunks/app/services/page-67fdf6c557304042.js)|280,105 字节；内容为 CDK、AgentCore、S3、Transcribe 等服务概述、示例代码和常见问题。没有发现可直接实现的赛事统一契约。|
|[新版 Rules & Quick Start](https://csdn.feishu.cn/docx/Y21TdJqrHopofmx2w21cmqHLnLb)|本轮无登录 HTTP 读取遇到重定向循环，不能据此声称再次读到全文。此前人工浏览器读取结论见[正式指南核准更新](../docs/2026-10-06-正式指南核准更新.md)。|
|[参赛终极指南](https://csdn.feishu.cn/wiki/B3NSwj16GiSCR7kcM5vc9RjMnQb)|同上；本轮不绕过登录或权限。最新版是否新增附件需以已授权浏览器复核结果更新。|
|[NBA 深度赛场](https://china.nba.cn/inside-the-game)|HTTP 200，页面为动态应用；从其实际引用的脚本确认公开数据接口，随后执行少量 GET。|
|[NBA 页面脚本](https://res.nba.cn/static/webmaster/assets/js/index-8848e9f0.js)|450,070 字节；确认接口路径、字段展示及点位绘制方法。脚本只作为来源证据读取，没有执行或绕过接口校验。|
|[NBA 指标术语页](https://china.nba.cn/inside-the-game/glossary)|定义内容存在上述官方页面脚本内；可用于理解 xFG、FG%+ 等指标，但不能据字段名擅自映射所有 API 聚合值。|
|[官方训练包](https://comfile.csdnimg.cn/file/train_video.zip)|既有本地压缩包内只有两段 MP4，无深度数据 JSON/CSV。本轮没有重复下载。|
|[既有账号连接说明](../AWS-Team02-连接说明.md)|沿用已记录的 10 月 8 日 09:00 期限，不重新打开含密码的通知 PDF。|

来源快照哈希（SHA-256）：

- 服务页 HTML：`3db3af96fbd6a550a09a0e316e404bf29757c148b0f2bbdb16f227308209a501`。
- 服务示例脚本：`5b4f7e812e50c141bf079cf32ef2eccbb4cf414f72864c323ffc28e52bb73869`。
- NBA 深度赛场 HTML：`b840442bc9b2a83fb6ba5f0b54f4c3b24411a005e9969c2abeaec42c134e7276`。
- NBA 页面脚本：`d76a33b9b81c145bcc2eaea6a21d11abf4875815aadb381db01fffc8c82a7698`。

## 已取得的真实投篮参考样例

发现路径为“官网页面脚本 → 赛程与球队赛季数据 → 球员单场出手接口”。比赛 ID 来自官网日期查询，球员 ID 来自官网球队赛季数据，未凭记忆编造。所有保存响应均为 HTTP 200、`code: 0`，原始字节未重排或改写。

|本地原始文件|主源 URL|字节数|说明|
|---|---|---:|---|
|[2 月 1 日赛程](fixtures/official/nba-games-2026-02-01.json)|[game?date=2026-02-01](https://api.nba.cn/nba-web/api/web/inside/game?date=2026-02-01)|1,074|含独行侠与火箭比赛 `0022500701`|
|[1 月 4 日赛程](fixtures/official/nba-games-2026-01-04.json)|[game?date=2026-01-04](https://api.nba.cn/nba-web/api/web/inside/game?date=2026-01-04)|1,424|含独行侠与火箭比赛 `0022500491`|
|[独行侠赛季数据](fixtures/official/nba-season-shotdifficulty-dal-2025-26.json)|[shotDifficulty：DAL](https://api.nba.cn/nba-web/api/web/inside/season/shotDifficulty?season=2025-26&seasonType=Regular+Season&teamId=1610612742)|2,096|弗拉格 `PLAYERID: 1642843`|
|[火箭赛季数据](fixtures/official/nba-season-shotdifficulty-hou-2025-26.json)|[shotDifficulty：HOU](https://api.nba.cn/nba-web/api/web/inside/season/shotDifficulty?season=2025-26&seasonType=Regular+Season&teamId=1610612745)|3,403|阿门·汤普森 `PLAYERID: 1641708`|
|[弗拉格逐次出手](fixtures/official/nba-gpshot-flagg-0022500701.json)|[gpShot：弗拉格](https://api.nba.cn/nba-web/api/web/inside/gpShot?gameId=0022500701&playerId=1642843)|5,712|23 次出手、13 次命中；23 条 `gameClock` 均为空；13 条有 `newsId`|
|[阿门逐次出手](fixtures/official/nba-gpshot-amen-0022500491.json)|[gpShot：阿门](https://api.nba.cn/nba-web/api/web/inside/gpShot?gameId=0022500491&playerId=1641708)|4,429|18 次出手、8 次命中；18 条 `gameClock` 均为空，`newsId` 均为 null|
|[弗拉格场次球队出手](fixtures/official/nba-shot-0022500701.json)|[shot：0022500701](https://api.nba.cn/nba-web/api/web/inside/shot?gameId=0022500701)|6,987|两队聚合与 `success/shotQuality` 列表；列表没有 eventId，不能直接替代事件表|
|[阿门场次球队出手](fixtures/official/nba-shot-0022500491.json)|[shot：0022500491](https://api.nba.cn/nba-web/api/web/inside/shot?gameId=0022500491)|6,683|同上|
|[弗拉格场次防守空响应](fixtures/official/nba-def-0022500701-null.json)|[def：0022500701](https://api.nba.cn/nba-web/api/web/inside/def?gameId=0022500701)|33|`data: null`；已记录缺失，不当作零值|
|[阿门场次防守空响应](fixtures/official/nba-def-0022500491-null.json)|[def：0022500491](https://api.nba.cn/nba-web/api/web/inside/def?gameId=0022500491)|33|`data: null`；已记录缺失，不当作零值|

全部十份响应合计 31,874 字节。保存的是小型公开参考数据，没有下载新闻视频或海量比赛媒体。参考数据可支持赛前原型验证，但对外分发与正式比赛使用仍遵主办方提供的数据与素材范围。

### 逐次出手的实际结构

外层为 `{code, msg, data}`，`data.shotList` 为事件数组。以下是样例实际观察到的字段，不是主办方评测请求协议：

|字段|样例类型|目前可确定的含义与限制|
|---|---|---|
|`gameId`, `playerId`|string|比赛、球员标识；保留字符串，避免丢失比赛 ID 前导零|
|`eventId`|integer|该比赛中的事件标识；应与 gameId 联合使用，不能当作视频秒数|
|`period`|integer|样例为 1–4 节|
|`gameClock`|string|本次两名球员样例全为空；其他公开场次可见 `10:16`、`45.4` 等不同格式，不能假设必填或固定为 mm:ss|
|`shotDesc`, `shotType`|string|官方返回的动作描述与 2/3 分类型|
|`success`|integer|本次为 0 或 1；官网按数值 1 判定命中|
|`value`|number|逐次投篮的官网数值；对应出手难度页面的概率型展示，应保留原值与来源，不升级为本队训练出的命中预测|
|`locX`, `locY`|string|样例内为数值字符串；不是画面像素坐标，也不是逐帧轨迹|
|`side`|string|本次出现 `left/right`，官网绘制使用它镜像半场|
|`newsId`|string 或 null|关联新闻标识；可缺失，不能依赖它保证每个事件都有可下载视频|

官网绘制代码将 `locX/100` 缩放到 94 长度，并结合 `side` 翻转、把 `locY/100` 缩放到 50 宽度，再绘制半场。这是可复核的官网展示实现，不是组委会声明的通用坐标规范。正式适配还应取得坐标原点、方向、单位和异常点处理定义；不能直接把点位叠到真实视频人物脚下，更不能据此复原跑动轨迹。

### 数据质量核查：必须避免字段名称误读

这两个样例的聚合字段存在可验证的命名/展示语义疑点：

|球员|逐事件 `value` 算术均值|命中事件 `value` 均值|原始 `avgShotQuality`|原始 `fgPctAboveExpected`|
|---|---:|---:|---:|---:|
|弗拉格|0.4760434783|0.5138461538|0.089|0.514|
|阿门|0.4284444444|0.5131250000|0.016|0.513|

由样例计算，`avgShotQuality` 近似等于实际命中率减逐事件均值；`fgPctAboveExpected` 近似等于仅命中事件的均值。官网脚本却把后者放入“预期投篮命中率”卡片。这里记录的是数值关系及源码映射，不据此私自修订官方字段定义。

工程处理：逐事件保留原始 `value`；如需聚合，明确标注“按已返回出手事件计算”，保存公式与事件集合。对语义未核准的聚合字段不直接展示为全场 xFG 或 FG%+；不从空防守接口编造防守压力、引力或胜率影响。

### 与两段训练视频的关系

文件名日期、球员与查询结果一致，因此可用作**候选匹配数据**。但官网响应没有这两段剪辑的文件名、视频时间戳或帧号；`gameClock` 又为空，尚不能证明某个 eventId 就对应剪辑中的那次投篮。

下一步应逐段核对真实视频中的节次、比分、球员、动作与命中结果，记录匹配依据、剪辑秒数与候选 eventId。若无法唯一匹配，则保持未匹配；需要组委会提供视频—比赛事件映射或标准样例，不应凭相似动作指定一个事件。

## 服务页面没有解决的评测契约

服务指南的 AgentCore 卡片包含 Bedrock `converse`、IAM 执行角色、控制面 harness 和 CDK 权限示例；S3 卡片使用 `nba-demo-assets-ACCOUNT_ID/videos/highlight.mp4` 等示例路径。它们是服务使用示例，不能认定为参赛 Agent 的请求结构或规定产物路径。

本轮对服务页完整示例脚本检查到的 `schema` 均属于 Transcribe、DynamoDB、Glue/Athena 的一般用法；未找到赛事统一输入、输出、考试调用样例或账号续期通知。该结论限于本轮实际读取的这些来源，不能推断组委会内部没有协议。

实现官方契约仍至少缺少：

1. 实际调用入口、鉴权方式、必填与可选请求字段，以及视频和深度数据如何传入。
2. 同步返回还是异步任务、状态查询结构、超时与重试规则、失败时的响应约定。
3. JSON 结果、完整成片、辅助素材的文件名/媒体类型/路径，S3 URI 与 CloudFront URL 的责任边界。
4. 评测器如何从私有仓库启动、依赖版本、环境变量、分支/提交版本选择及一个可成功运行的请求响应样例。

可以继续实现内部流水线与薄适配层，不能把这些待定项猜成官方要求。服务指南中的通用 `cdk bootstrap` 等例子也不能覆盖主办方“不执行 bootstrap”的明确通知。

### 同日补充：Portal 公开页面

进一步只读检查了 [Portal](https://du5imhgxabl0d.cloudfront.net/portal) 与其实际引用的 [Portal 页面脚本](https://du5imhgxabl0d.cloudfront.net/_next/static/chunks/app/portal/page-41a2a0c6ea6e02af.js)：公开部分仍指向既有指南、服务、NBA 数据页面和训练视频，没有发现完整赛事调用 schema。没有猜测隐藏 API 或绕过权限。

公共共享脚本 `/_next/static/chunks/32-50a6859c5a69a3ee.js` 中存在模拟评分、设计预览及“后端未连接”的占位内容；它不是主办方正式评分细则或本队实际评测结果。前端内部常量和占位百分比不能覆盖已读取的正式指南。

## 账号期限：已知与未知

已有记录唯一明确的练习账号截止时间为 **2026-10-08 09:00**，见[连接说明](../AWS-Team02-连接说明.md)与[接手说明](../AI接手说明.md)。本轮服务页关于“有效期”的两处内容分别是 ECR 登录令牌 12 小时及 STS 临时会话时长，均不是赛事账号权限续期通知；“资源存续期间”也不是续期安排。

本轮未取得 10 月 8 日 09:00 以后是否延长原账号、是否发新账号、是否保留现有资源和配额、何时重新登录的明确公告。不能把当前 AWS 实测成功升级为正式比赛日权限确认。无需为确认未来权限反复创建资源；这项依赖只能由组委会明确通知解决。

## 可直接发给组委会的一句话（未发送）

> 请提供与两段训练视频逐事件对应的深度数据样例和字段/坐标/时间映射说明，以及统一 Agent 评测的完整请求、响应、异步状态和产物路径示例，并确认 10 月 8 日 09:00 练习权限到期后，10 月 10 日正式比赛是否续用原账号、何时恢复权限及现有资源是否保留？

## 原始样例哈希

```text
fd50dbff6c13199ba9689b8222f2c748089e4a0c3d549d5db0afd895e4156c27  nba-games-2026-02-01.json
5816910a32c5aae47688ced2af9e8a049b564b44ea4059c6d02ebc4a478d23b8  nba-games-2026-01-04.json
c9b106781e45d38d389a06de5b8f3ebbf2dc9f01b34ce613126dfc4df1c38571  nba-season-shotdifficulty-dal-2025-26.json
75646d7d4c253507cce96af5d0fb98e0bc0495ad97b1797a87de72e0977f3887  nba-season-shotdifficulty-hou-2025-26.json
95238bb31f32bd07c5588b0e26331fc0f1a12181567e339150058d23826d265d  nba-gpshot-flagg-0022500701.json
4b75a51aa4620ce879850dc30ade9246b25bf5c47d4957a3f769c527c7ceccf7  nba-gpshot-amen-0022500491.json
dc89d06bfae299087a1279eef7e4022eb51d475e20563ce177023ab5dcb65005  nba-shot-0022500701.json
274dc8cb87cf82598f9198655bdd02a09ea9285022db2c33dd12ecdf1de605ef  nba-shot-0022500491.json
32de289b6b32ddafc0f7590cabcb3b7586b08e53feed14289f38db9761388ab1  nba-def-0022500701-null.json
32de289b6b32ddafc0f7590cabcb3b7586b08e53feed14289f38db9761388ab1  nba-def-0022500491-null.json
```
