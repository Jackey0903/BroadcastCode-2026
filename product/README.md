# 关键一拍 · THE HIDDEN PLAY

一个把“看见进球”推进到“看懂这次出手”的篮球视频产品。观众先看原片并选择关注点，再通过章节回放、官方出手数据和可点击证据发现关键细节。AgentCore 上的智能体按工具返回的证据组织故事，确定性渲染器输出带永久标注的完整 MP4。

## 产品主线与评分对应

**先看进球，再看懂这一拍。** 观看区让评委先选关注对象，慢放同一回合的关键时刻，再看官方 xFG 与可点击来源。创作区展示一次真实的证据读取、叙事组织和完整成片，不把预写案例或装饰性的流程动画当作 Agent 执行。

|需要赢得的判断|产品给出的证据|
|---|---|
|这东西值得球迷使用|观众选择改变揭示文案、回看节点与高亮证据；两个故事各有明确问题|
|篮球内容与数据可信|画面观察、官方数值、编辑解释分开标注；具体事件、比分变化、身份与来源可核对|
|技术真正工作|AgentCore 实际读图与读取官方快照，后续模型轮次给出章节；原始执行记录、模型用量和成片哈希可查|
|展示完整且有视觉记忆点|像素街机 × 极简黑场：像素字标与球场带、卡带式案例、LED 记分条、关注点菜单、xFG 能量条、两张关键帧并排核对、慢放、原片/成片切换、官方出手图和永久标注 MP4|
|系统可重跑、可恢复|CDK、版本锁定、队列任务、失败状态、死信队列与本地源码/媒体存档|

这些是冲刺初赛准确性/交互及决赛视觉/深度的实现选择，不是预估分数或获奖保证。正式机器 35 分仍需拿到官方 schema 后适配并用新输入验证。

```mermaid
flowchart LR
  W[CloudFront 交互网页] --> API[Lambda 任务接口]
  API --> Q[SQS 队列]
  API <--> D[DynamoDB 任务状态]
  Q --> R[视频 Worker]
  R --> A[AgentCore 智能体]
  A --> B[Bedrock Claude]
  A --> E[真实帧与官方事件快照]
  A --> V[章节与引用校验]
  V --> R
  R --> M[FFmpeg 完整视频烧录]
  M --> S[S3 视频与生成记录]
  S --> W
  R --> D
```

## 当前开发结构

- `court-lab/`：[桌面俯视战术示意](court-lab/README.md)，本地弗拉格观看页有入口。覆盖完整 21.548 秒，31 帧编辑锚点、9 段球权、最近位置保留、单视频时钟、半场/全场、持球聚焦与整段轨迹；尚未加入云端发布与 Agent 成片。
- `web/`：无需打包的交互前端，故事揭示、章节回放、原片/成片切换与真实创作任务。
- `web/arcade.css` / `web/arcade.js` / `web/assets/`：当前唯一视觉层（像素街机 × 极简黑场）。像素字标由随仓库的 FusionPixel12 光栅化，球场带为卡通装饰、不含比赛坐标，离屏/后台/减少动态时暂停；规则见[视觉系统](../docs/前端像素街机视觉系统-20261009.md)。`styles.css`、`broadcast.css`、`atmosphere.js` 为旧视觉层，主页面不再加载。
- `data/stories.json`：两段公开练习片的策展案例与来源；不冒充正式赛事评测输入。
- `data/match_events.py`：基于官方记录和已标注视频锚点的事件核对。AI 辅助编辑的锚点和机器校验各自标注。
- `research/`：官方事件响应摘录、视频映射依据与核查报告。
- `agent/`：AgentCore Python 入口、Bedrock 工具循环及共同验证契约。
- `worker/`：队列任务、调用智能体、时间化标注、完整视频渲染与媒体检查。
- `api/`：同源异步任务接口。只接受两个登记样片，并限制公共运行次数。
- `app.js` / `cdk.json`：更新保留的 `BroadcastCodeTeam02Readiness20261006`，保持既有资源 ID。不要同时从两个版本部署。

## 本地开发预览

2026-10-09 当前在本地继续开发，云端最后一次核查为 10 月 8 日权限被拒绝。启动：

```sh
python3 product/scripts/serve.py
```

访问 http://127.0.0.1:4173/product/。仅绑定本机回环地址，预览不读取 AWS 凭证、不代理云请求。原片、关键帧和最终两份完整 MP4 均从本地白名单读取，视频支持 Range 拖动；启动时检查原片及成片 SHA-256。缺少媒体时按[源码保存与恢复](../docs/源码保存与恢复.md)恢复存档，不能只克隆 Git 就假定视频存在。

创作工作台提供「历史成片与处理记录」，保存 10 月 7 日真实工具调用与分析，清楚标明历史结果。`POST /api/jobs` 返回 503，不创建任务；新 Agent 推理须在赛事服务恢复后验证。观看区仍是编辑策展视角，创作记录来自独立的真实 Agent 运行。

本轮 100 项离线测试及本地 HTTP/媒体检查见[本地测试](evidence/local-tests-20261009.json)与[预览核查](evidence/local-preview-20261009.json)，整体待办见[本地开发进度](../docs/本地开发进度-20261009.md)。

随后完成桌面视觉与俯视战术示意，当时共 184 项离线测试通过。俯视入口 http://127.0.0.1:4173/product/court-lab/，覆盖弗拉格完整 0–21.548 秒，新增持球高亮、阶段解析与最近位置保留；编辑数据、遮挡状态、确定性复现与浏览器证据见[俯视验收](evidence/court-full-20261009.json)。它不使用 GPU、不自动识别十人，也不改变官方出手数据。来源与技术路线详见[俯视工程](court-lab/README.md)。

随后主页面与俯视板统一为像素街机 × 极简黑场视觉，中英双语短标签；最新共 193 项离线测试通过，截图与源码哈希见[视觉核查](evidence/arcade-20261009.json)，规则见[视觉系统](../docs/前端像素街机视觉系统-20261009.md)。

随后的桌面视觉版本共 111 项离线测试通过，含 10 项粒子与新增静态资产/MIME 回归；[视觉验收](evidence/visual-redesign-20261009.json)、[旧素材复用说明](../docs/前端视觉更新与旧素材复用-20261009.md)保存实际截图与功能核对范围。本轮以桌面评委展示为目标，未重新生成 MP4 或部署。

## 服务恢复后的部署

以下是服务恢复后才执行的部署步骤，本轮没有部署。使用既有 `nba` 配置，首先核验目标账号 `962768510637`、角色 `NBAHackathonParticipantRole`。资源区域固定 `us-east-1`，不执行 bootstrap。

```sh
npm ci --prefix product
# 仅首次需要：准备固定版本 SDK、FFmpeg 和字体，详见 readiness-lab/README.md。
readiness-lab/.venv/bin/python product/scripts/build.py
cd product
npx cdk diff --profile nba
npx cdk deploy --profile nba --require-approval never --outputs-file outputs.json
cd ..
readiness-lab/.venv/bin/python product/scripts/publish.py
```

CDK 必须保留权限边界 `NBAHackathonParticipantBoundary`。源码在本机；云端仅是部署实例。构建产物和视频不提交 Git；依赖锁定文件、部署定义、来源证据与测试提交源码管理。

`publish.py` 向同一受控桶发布页面、案例与用于模型观察的六个关键帧。原始练习片由之前的 `readiness-lab/upload_inputs.py` 登记；新机器应按练习工程说明取得公开视频并校验哈希。不要无目的重新运行历史云验证或清理脚本。

## 内部接口（非官方评测协议）

- `GET /api/status`：当前服务和登记样片。
- `POST /api/jobs`，JSON `{"sample":"flagg","mode":"story"}`：返回 `jobId`。
- `GET /api/jobs/{jobId}`：状态、真实错误或完成后的 `videoUrl`、`analysisUrl`、分析与验证信息。

CloudFront 的 Lambda IAM 源要求 POST 携带**请求体原始 UTF-8 字节**的 `x-amz-content-sha256`；前端完成这一计算，不持有 AWS 凭证。一次 POST 失败不得盲目重试；按已有 jobId 查询，避免重复计费。原有不带 `mode` 的请求继续走练习流程。

展示案例的视频时间保持原片时间轴。官方出手点位不是逐帧轨迹；故事解读不是因果证明。`xFG` 是该次出手的预期命中率，不是球员赛季命中率、胜率或结果保证。预先由 AI 辅助编辑的案例与模型新生成结果分别标明，不用预写工具轨迹冒充真实执行。

## 从代码重跑

浏览器按钮和命令行使用同一个真实异步接口。下面的命令会启动一次新的模型推理与视频渲染，计入公共运行次数；不得为了读取结果反复提交。

```sh
python3 product/scripts/run_sample.py --sample amen --wait
# 只读取并核验已完成任务，不重新生成：
python3 product/scripts/verify_run.py <真实jobId>
```

`run_sample.py` 对创建任务只发送一次 POST，后续只查询原编号，真实结果写入被 Git 忽略的 `product/build/client-jobs/`。`verify_run.py` 独立下载 MP4、核对 SHA-256、时长、音轨和 HTTP Range；`--promote` 仅在人工/AI 复核内容后使用，用来选为观看区成片。保留失败记录，不能把一次技术完成自动视为篮球内容正确。

## 复现与交付边界

这是基于主办方公开两段练习视频的产品原型。正式评测 schema、正式素材映射、赛前成果复用边界与账号到期后的安排仍以组委会通知为准。正式提交前必须用实际新输入验收，不能把两个案例通过等同于任意比赛视频均可用。

实际任务、内容拒收、部署与媒体核验见 [产品验收记录](evidence/README.md)。最终弗拉格 `81a74837370e46a890cbacb2069074e6` 与阿门 `ce008e75d25d4e2e8e88b57412f6c762` 均已完成内容复核、媒体核验与浏览器完整播放；中间失败与内容拒收记录保留。本轮本地回放不构成新的云端生成验收。
