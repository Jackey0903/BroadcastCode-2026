# Claude 交接：RL-SCOUT 与前端（2026-10-10 11:02）

给下一个 Claude 会话。先读本文，再读 [RL-SCOUT 执行文档](RL-SCOUT强化学习执行文档-20261010.md)（方案、接口契约、进度日志）、[AGENTS.md](../AGENTS.md) 和 [README](../README.md)。正式比赛进行中：**北京时间 10 月 10 日 20:00 截止**，考试视频预计 18:00 发放，比赛视频为**火箭 vs 独行侠**。

## 1. 你是谁、在做什么

- 用户同时用 **Codex**（主线：正式部署、登记新素材、Agent/Worker/API/CDK/发布）和 **Claude**（你：前端视觉 + RL-SCOUT 强化学习）并行开发。用户用中文交流，偏好先给结论、少废话、直接执行。
- 你负责的范围：`product/rl/**`、`product/web/camp.*`、`product/web/arcade.*`、`product/court-lab/lab.css` 与相关文档；`product/scripts/serve.py` 只加过两处白名单。**不要改** Codex 的 `product/agent/**`、`worker/**`、`api/**`、CDK、`app.js` 行为、`check.py`；需要改时写进执行文档请 Codex 做。
- 产品名仍为「关键一拍 / THE HIDDEN PLAY」（用户否定过 BEAT/前一拍 等改名，未定新名）。

## 2. 环境与身份

|项目|值|
|---|---|
|Claude 工作树|`/Users/jack/work/BroadcastCode/.claude/worktrees/hackathon-prototype-analysis-d23acb`，分支 `claude/hackathon-prototype-analysis-d23acb`|
|主目录（Codex 工作区）|`/Users/jack/work/BroadcastCode`，分支 `main`，`origin` = `Jackey0903/BroadcastCode-2026`（Portal 已锁定），`practice` = 旧仓库|
|合并方式|在工作树提交 → `git rebase main` → `git -C /Users/jack/work/BroadcastCode merge --ff-only claude/hackathon-prototype-analysis-d23acb`。Codex 常有未提交改动，只要文件不重叠 ff 就能成功。**推送 GitHub 由 Codex 负责**（用户授权其比赛期间持续推送）；你推送前先确认用户意图|
|AWS|`--profile nba`、`us-east-1`、账号 `555726205424`、角色 `NBAHackathonParticipantRole`；不要 bootstrap|
|带 boto3 的 Python|`/Users/jack/work/BroadcastCode/readiness-lab/.venv/bin/python`（系统 python3 没有 boto3）|
|S3|预置桶 `nba-hackathon-555726205424-team02`，RL 只用前缀 `rl-scout/`（code/checkpoints/output）|
|执行角色|`arn:aws:iam::555726205424:role/NBAHackathonWorkloadRole`（信任 SageMaker/Bedrock/AgentCore/States）|
|本地预览|工作树里 `.claude/launch.json` 配置 `arcade-preview`（`serve.py --port 4174`）；Codex 用 4173|
|截图|此前用无头 Chrome + 小型 CDP 脚本（`Google Chrome --headless=new --remote-debugging-port`，Node 22 自带 WebSocket）；脚本在旧会话临时目录，需要时重写|

## 3. 正在运行的云资源（交接时）

|资源|状态|说明|
|---|---|---|
|训练 `rl-scout-main-3b-v1-1010-105846`|InProgress（`ml.g5.4xlarge`）|**正式线**，奖励 v1、冻结数据、Qwen2.5-3B、lr 1e-5、训练循环预算 6000s；预计 **≈12:50** 训练结束，随后自动做最终评测与合并（≈13:00 完成）|
|训练 `rl-scout-early-3b-1010-104358`|InProgress（`ml.g5.2xlarge`）|先导线 **v0**（旧奖励），已坍缩为只调区域参考，测试集 MAE 0.222→0.099；保留作 v0 证据与兜底模型，预计 ≈12:35 结束|
|端点 `rl-scout`|**InService**（`ml.g5.xlarge`，约 $1.4/h）|当前挂的是冒烟 0.5B 模型（估计值无意义），**接口可用**；正式模型训练完后原地更新，端点名不变|
|已停止|`rl-scout-smoke-1010-103612`（g6e 无容量）、`…-g64xlarge-…`、`…-g58xlarge-…`|只停止未删除|
|本机后台|`eval_baselines.py --claude-n 120`（v1 奖励重跑对照组，nohup）|完成后覆盖 `product/rl/results/baselines.json`；**判断是否为新结果：`testSets.h2h` 应为 390**（旧结果是 217）|

查询命令：
```sh
aws sagemaker describe-training-job --training-job-name rl-scout-main-3b-v1-1010-105846 --profile nba --region us-east-1 --query '[TrainingJobStatus,SecondaryStatus,FailureReason]' --output text
aws logs tail /aws/sagemaker/TrainingJobs --log-stream-name-prefix rl-scout-main-3b-v1-1010-105846 --since 30m --profile nba --region us-east-1 | grep '"kind"'
```
训练指标（`metrics.jsonl`）、GRPO 组（`rollouts.jsonl`）、逐题评测（`final_base_*`/`final_trained_*`）、检查点与 `merged/` 持续同步在 `s3://nba-hackathon-555726205424-team02/rl-scout/checkpoints/<job>/`。

## 4. 已完成

**RL-SCOUT（`product/rl/`，20 项纯 Python 测试）**
- `harvest.py`：NBA 中国官方接口（`inside/game`、`season/shotDifficulty`、`gpShot`）抓取，带缓存（`data/rl-raw/`，git 忽略）、限流退避、`--offline` 重建。接口曾限流（SSL EOF），慢速可恢复。
- 冻结数据 `data/shots.jsonl`：**233 场、15,171 次出手**（只覆盖每队约 5 名档案球员），SHA-256 前缀 `363694a79d43ae1e`；两队整季 154 场；`profiles.json`、`manifest.json`、`reference_tables.json`（运行时工具表）。
- `scout_env.py`：坐标→距离/区域、切分、三个工具、提示词、解析、奖励 v1、汇总。**测试集 A「模拟考场」= 四场交手（0022500160/0356/0491/0701，390 次）整场不训练；B「泛化」= 3 月起非两队比赛（1621 次）**。训练 13,160 次（两队 8,092），采样 80% 两队。
- 奖励 v1：`0.75·max(0,1−|q̂−y|/0.5) + 0.15·格式 + 0.10·有据 − 0.01·工具数 − 0.2·无效`。v0（平方误差、工具 0.03）导致坍缩，诊断见执行文档进度日志——这是讲解“实现深度”的好素材。
- `train_grpo.py`：自写多轮 GRPO（transformers+peft，LoRA r32，每题 8 条，组内标准化优势，无 KL，只对模型生成 token 计损失），`--time-budget` 保证最终评测与合并能跑完。
- `launch.py`（创建训练任务；`--package-from <job>` 改为云上打包推理模型）、`package_model.py` + `serve/inference.py`（PyTorch 推理镜像 2.6）、`deploy_endpoint.py`（创建或原地更新端点）、`check_endpoint.py`（两段练习片真实出手端到端）、`scout_client.py`（运行时客户端，契约见执行文档第 6 节）、`eval_baselines.py`、`build_camp.py`（生成网页数据）、`export_tables.py`。`import_model.py` 保留但 **Bedrock 导入被组织 SCP 显式拒绝**，不要再试。
- 对照（v0 奖励口径，旧测试集 217/1621）：统计基线 MAE 0.091/0.092；Claude Sonnet 4.6（同一工具协议，抽样 120）0.092/0.082，每回合约 3 次工具。v1 口径重跑中。

**前端**
- 主产品与俯视板统一像素街机 × 极简黑场（`arcade.css`/`arcade.js`），中英双语短标签，见[视觉系统](前端像素街机视觉系统-20261009.md)。
- 训练营 `product/web/camp.html`/`camp.css`/`camp.js`：等级经验条、回路图、奖励/误差/工具曲线（误差图带 STAT 与 CLAUDE 参考线）、GRPO 八条轨迹对比、成绩单、校准散点、数据边界；数据 `product/data/rl/training-camp.json`（由 `build_camp.py` 生成；当前文件是先导线中途数据，未提交）。主页刊头已有 CAMP 链接；`serve.py` 已放行。

`main` 最新为 `a64ea83`（含以上全部代码与冻结数据）。

## 5. 接下来按顺序做

1. **等正式线完成**（≈13:00），读 `final_base_*`、`final_trained_*` 与 `eval` 指标；同时看先导线的最终评测。按**模拟考场 MAE**（再看工具/回合、有据率）择优；如实记录，不达预期也照写。
2. **打包并上线**（全在云上，权重不经本机）：
   ```sh
   cd product/rl
   PY=/Users/jack/work/BroadcastCode/readiness-lab/.venv/bin/python
   $PY launch.py --name pkg-main --instance ml.m5.2xlarge --max-runtime 1800 --package-from rl-scout-main-3b-v1-1010-105846
   # 打包任务完成后（约 5 分钟）：
   $PY deploy_endpoint.py --package-job <上一步打印的任务名> --endpoint rl-scout --instance ml.g5.xlarge --wait
   $PY check_endpoint.py
   ```
   3B 在 g5.xlarge（A10G 24GB）bf16 推理应可放下；若启动失败，改 `--instance ml.g5.2xlarge`（端点配额 2）。
3. **训练营数据**：`$PY build_camp.py --job rl-scout-main-3b-v1-1010-105846`（确认 `baselines.json` 已是 v1：`testSets.h2h == 390`），预览 `http://127.0.0.1:4174/product/camp.html` 截图核对，提交 `product/data/rl/training-camp.json`。v0 先导线可另作“坍缩前后”素材（`build_camp.py` 会被覆盖，必要时手动保存）。
4. **证据与文档**：写 `product/evidence/rl-scout-20261010.json`（任务名、实例、数据哈希、奖励版本、四组对照结果、端点检查、费用估计、边界）；更新执行文档进度日志、README/AI接手说明一行指引；合并进 `main`。
5. **与 Codex 对接**（执行文档第 6 节）：执行角色加 `sagemaker:InvokeEndpoint`（`endpoint/rl-scout`）、打包 `scout_env.py`/`scout_client.py`/`reference_tables.json`、读到官方出手后调用、失败降级；质量门禁加 `'rl': 20`。用户尚未决定是否由你给 Codex 写成片 SCOUT HUD 规格（建议放在底部信息带右侧：`SCOUT 常见 51% · Δ −6.5 比常态更难`，下方小字「AI 估计（强化学习球探）」，官方 xFG 仍原样显示）。
6. **费用与收尾**：两条训练任务结束后自动释放。端点按小时计费——若 Codex 接入成片流程，需保留到评审窗口（20:00–22:20）之后；否则问用户是否停用。只清理自己创建的资源。

## 6. 讲解口径（必须守住）

- 可以说：用 NBA 官方出手质量（基于追踪数据的官方模型）作为**可验证奖励**，在 **SageMaker GPU** 上用 **GRPO 多轮强化学习**训练会调用工具的 3B 球探；四场火箭-独行侠交手整场留作模拟考场；与统计基线、Claude、训练前模型同口径对照；经 **SageMaker 端点**服务、由 Agent 调用。
- 不可以说：模型看懂视频、预测命中、学会战术意图、替代官方 xFG、Bedrock 托管（被 SCP 禁止）。球探给的是“同类出手的常见质量”；难度差只陈述数值差，不写因果。

## 7. 其他历史上下文（简）

- 前端早期：像素字标由 FusionPixel12 光栅化（只用 12 倍数字号），球场带是卡通装饰（不含坐标）。已验收成片内的烧录配色仍是旧柠檬绿，需 Codex 在 worker 中统一（色值见视觉系统文档），不能本地重渲替换已验收成片。
- 正式账号 GPU：g6e（L40S）当天多次 “waiting for capacity”；A10G（g5）可用。SageMaker CPU 训练配额充足（m5.2xlarge 20）。
- NBA 美国 CDN 与 stats 接口本机 403/超时；NBA 中国 `pbp/details` 需要签名，拿不到逐回合事件链。
