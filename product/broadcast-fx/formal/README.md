# GameBuddy · 正式素材二次进攻解读

以用户提供的 [正式视频](../../../data/正式视频.mp4) 为唯一比赛影音输入，复用上一版的橙黑视觉、球员提示、战术定格、回放与数字入场动画，重新匹配这段素材的球员、事件、时钟和数据。原片 SHA-256 为 `f2c0fb6aa1ec10bd78ea9e6724190b7f03bf48f21af2f743c694bbdb49254c91`；不接受此前弗拉格或阿门素材替代。

本片核心是：**克里斯蒂首次出手被封盖 → 鲍威尔抢回进攻篮板 → 克里斯蒂后撤步打板三分命中。** 正式素材来自 2025 年 12 月 6 日美国东部时间 HOU 客场对 DAL，比赛 `0022500356`。主角是 DAL 00 号 Max Christie。

## 可烧录的事实

|项目|已核对值|来源|
|---|---|---|
|核心出手|event / actionNumber 273，Q2 4:58，后撤步打板三分命中|NBA.com PBP 与 NBA 中国 gpShot 交叉匹配|
|本球官方 xFG|30.0%|`shotList[eventId=273].value=0.3`|
|出手距离|25 英尺|NBA.com `shotDistance=25`|
|三分后比分|DAL 43 / HOU 44|PBP 与源片后段比分牌|
|进攻延续|鲍威尔进攻篮板，event 272|NBA.com PBP；不是本球助攻|
|犯规|Smith Jr. 投篮犯规，event 274|引用 NBA.com 已记录事实|

后续 event 276 加罚命中、44 平在官方记录中存在，但**原片没有罚球画面**。成片不能把 44 平提前当作源片比分。NBA 中国响应的中文主客场字符串写反，比赛身份采用 NBA.com `gameCode` / `homeTeamId` 与真实主场画面；原始错误字符串保留在证据中。

保留用户确认的数字递增视觉，在本片显示 **0→30%**。递增过程是入场动画；最终 30% 才是该出手的官方 xFG。不能沿用旧片的 51%，也不能误取球员汇总命中率 50%。官方事件时间 4:58 与画面中不断变化的时钟分别呈现，不能将 4:58 固定覆盖到整个持球过程。

详细原始字段及来源见 [官方事件核验](data/官方事件核验.md)、[标准事实入口](data/official.json)、[NBA.com 事实摘录](data/nba-page-christie.json) 和 [NBA 中国原始响应](data/gpshot-christie.json)。可在线复核 [NBA.com 逐回合](https://www.nba.com/game/hou-vs-dal-0022500356/play-by-play) 与 [NBA 中国 gpShot](https://api.nba.cn/nba-web/api/web/inside/gpShot?gameId=0022500356&playerId=1631108)。

## 标注和时间线

[data/annotations.json](data/annotations.json) 使用 1920×1080 原片像素坐标，帧号从 0 开始，源帧率为 `60000/1001`：

- T1：源帧 240，约 4.004 秒，切入吸引防守。
- T2：源帧 719，约 11.995 秒，借掩护回到中路。

每幅定格只标 9 名清楚入镜的球员，不补齐被遮挡或出画的第十人。可见足点使用 `visible-foot`；脚部遮挡则 `foot=null`、`body-only`，绘制身体提示。黑灰 30 号裁判已单独排除，不能和红衣 30 号球员混淆。号码与角色分开存储；未确认号码为 null，邻近帧确认但当前帧看不清时 `numberVisible=false`。

这些坐标与箭头是 AI 助手根据真实帧所作的**编辑战术示意**。它们不是官方逐帧数据、自动追踪、球员真实意图测量或篮球专家人工验收。箭头仅说明短时动作方向，不重建全场轨迹；不能使用官方单次出手坐标去续接编辑路线。

[timeline.py](timeline.py) 保留全部 1424 个源帧，并安排片头、两段定格、原片播放、倒带、半速回放、数据卡和片尾。当前时间线共 2710 帧，即约 45.212 秒；最终输出参数与是否完成以实际导出的媒体验证记录为准。

## 本地复现

从仓库根目录运行。Python 依赖继承 [视觉资产库依赖](../requirements.txt)，本机需有 FFmpeg / FFprobe。代码、JSON 和字体许可随源码保存，原片与生成视频留在本地媒体目录；输入文件需由持有正式素材的操作方放回上述路径。

```sh
python3 product/broadcast-fx/formal/render.py \
  --source data/正式视频.mp4 \
  --workdir product/build/formal-video \
  --output product/build/formal-video/GameBuddy-克里斯蒂二次进攻-正式版.mp4
```

正式版使用本次原片的广播音轨；回放音频来自同一素材，定格和转场使用程序合成音效。没有复用旧片解说、没有新增 TTS、没有借本次编辑导出去声称实际执行了 AgentCore 或 RL。Agent 如需复用可读取 `official.json` 和 `annotations.json`，按照 `timeline.py` 的源帧映射调用绘制、音轨和渲染组件；接入云端生产链路需要另行验证。

```sh
python3 -m unittest discover -s product/broadcast-fx/formal -p 'test_*.py'
python3 product/scripts/check.py --full
```

[test_data.py](test_data.py) 检查正式源绑定、事件连接、xFG 取值、三分与片外罚球区分、号码/角色/脚点边界及战术帧映射；[test_timeline.py](test_timeline.py) 检查完整源帧覆盖、回放连续性、声音样本对齐和拒收错误素材。离线数据测试不能代替成片逐段目视检查、自然片尾播放或线上验收。

`product/build/formal-video/` 中的帧缓存、成片及验证产物是构建结果，不进入 Git。保存源码时同时保留输入视频、最终 MP4 和导出清单，以便其他 Agent 根据哈希恢复及重跑。

帧缓存由 `cache-manifest.json` 绑定本段原片 SHA、帧率、插帧参数及逐帧哈希。缺少清单会重新提帧，清单或帧内容不匹配会拒绝复用。最后的半速回放延伸至源片约15.253秒，以覆盖穿网；片尾相应缩短，总长度保持45.212秒。
