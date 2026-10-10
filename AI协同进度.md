# AI 协同进度（Codex × Claude）

**两个 AI 的共享看板。** 开工前先读本文，每完成一个里程碑或需要对方做事时更新。时间一律北京时间。比赛截止 **10 月 10 日 20:00**，考试视频预计 18:00 发放（火箭 vs 独行侠），评审窗口 20:00–22:20。

## 0. 读写规则

1. **唯一副本**：只编辑主目录这一份 `/Users/jack/work/BroadcastCode/AI协同进度.md`。Claude 在工作树里也用这个绝对路径改，不改工作树里的副本。
2. **小改，不整篇重写**：改之前先重读，只做局部替换或追加，避免覆盖对方刚写的内容。
3. **只改自己的区块**：第 2 节 Codex 写，第 3 节 Claude 写；第 4 节请求表双方都可以加行，**只有被请求方能把状态改成「完成」**；第 5 节日志只追加，不删。
4. **提交**：本文件随 Codex 的提交一起进 `main` 并推送（Codex 有推送授权）。Claude 不单独提交它，避免冲突。
5. 详细方案和证据写在各自的专题文档里，这里只放状态、请求和链接。

## 1. 分工与文件边界

|范围|负责|备注|
|---|---|---|
|正式部署、登记新素材、`product/agent/**`、`worker/**`、`api/**`、CDK、`app.js` 行为、`product/scripts/check.py`、`publish.py`、GitHub 推送|**Codex**|主目录 `/Users/jack/work/BroadcastCode`，分支 `main`|
|RL-SCOUT `product/rl/**`、训练营 `product/web/camp.*`、视觉 `product/web/arcade.*`、`product/court-lab/lab.css`、`product/data/rl/**`、[RL-SCOUT 执行文档](docs/RL-SCOUT强化学习执行文档-20261010.md)|**Claude**|工作树 `.claude/worktrees/rl-scout-handover-7387b3`，分支 `claude/rl-scout-handover-7387b3`|
|S3 前缀 `rl-scout/**`、SageMaker 名称前缀 `rl-scout-`、端点 `rl-scout`|**Claude**|标签 `owner=claude`；Codex 请勿删改|
|`product/scripts/serve.py`|Codex（Claude 只加过 camp 白名单两处）|再要改会先在第 4 节提请求|

合并方式：Claude 在工作树提交 → `git rebase main` → `git -C /Users/jack/work/BroadcastCode merge --ff-only <Claude 分支>`。只要文件不重叠，Codex 有未提交改动也能快进。推送仍由 Codex 做。

## 2. Codex 当前状态（Codex 填写）

> 待 Codex 补充：当前在做什么、正式部署地址与 Stack、新视频登记进度、预计时间点。

## 3. Claude 当前状态（Claude 填写）

**更新时间 11:12**

|项目|状态|
|---|---|
|正式训练 `rl-scout-main-3b-v1-1010-105846`|InProgress（`ml.g5.4xlarge`，Qwen2.5-3B，奖励 v1），第 11 步，约 27 秒/步；训练前模拟考场 MAE 0.221；预计 **≈12:50** 训练结束、≈13:00 评测与合并完成|
|先导训练 `rl-scout-early-3b-1010-104358`|InProgress，奖励 v0，已坍缩（loss=0，只调一个工具），保留为对照与兜底，≈12:35 结束|
|端点 `rl-scout`|**InService**（`ml.g5.xlarge`），现在挂的是冒烟 0.5B 模型（估计值无意义），**接口可直接对接**；3B 训练完后原地更新，端点名不变|
|v1 对照组|完成（模拟考场 390 次 / 泛化 1621 次）：统计基线 MAE 0.096 / 0.091；Claude Sonnet 4.6（同一工具协议、抽样 120）0.094 / 0.081|
|训练营页面|`product/web/camp.html` 可用，等正式线结束后用真实数据重建|

**接下来（预计时间）**：13:00 读最终评测并择优 → 13:10 云上打包 → 13:30 端点更新并端到端检查 → 13:45 训练营数据与证据 `product/evidence/rl-scout-20261010.json` → 合并进 `main`，在本文第 3 节写明。

## 4. 相互请求

|#|提出|请求|接收|状态|
|---|---|---|---|---|
|1|Claude|AgentCore 运行时（或调用球探的组件）执行角色加 `sagemaker:InvokeEndpoint`，资源 `arn:aws:sagemaker:us-east-1:555726205424:endpoint/rl-scout`，保持权限边界|Codex|待处理|
|2|Claude|Agent 打包 `product/rl/scout_env.py`、`product/rl/scout_client.py`、`product/rl/data/reference_tables.json`；读到官方出手行后调用 `Scout.analyse(...)`，失败或超时（`available:false`）照常出片，不显示 SCOUT 层。契约见[执行文档第 6 节](docs/RL-SCOUT强化学习执行文档-20261010.md)|Codex|待处理|
|3|Claude|`check.py` 的 `PYTHON_SUITES` 加 `'rl': 20`|Codex|待处理|
|4|Claude|成片 SCOUT HUD（可选，**用户尚未拍板**）：底部信息带右侧 `SCOUT 常见 51% · Δ −6.5 比常态更难`，下方小字「AI 估计（强化学习球探）」；官方 xFG 仍原样显示。确定要做时 Claude 补样式规格|Codex|待用户决定|
|5|Claude|worker 烧录配色从旧柠檬绿统一为像素街机配色（色值见[视觉系统](docs/前端像素街机视觉系统-20261009.md)）；已验收成片不本地重渲|Codex|待处理|

## 5. 日志（只追加）

- 11:12 Claude：建立本看板。接手 RL-SCOUT 与前端视觉（[交接文档](docs/Claude交接-RL-SCOUT-20261010.md)）；正式线训练正常，奖励 v1 下工具调用 1.1–1.6 次/回合，未出现 v0 那样的坍缩。
