# GameBuddy · 产品工程指南

项目介绍、银奖合影与演示见[主 README](../README.md)。本页说明实际开发入口及依赖，比赛期间的逐轮状态保存在[工程归档](../docs/archive/competition-2026/产品工程说明-比赛期间.md)。

## 模块入口

| 模块 | 作用 | 入口 |
|---|---|---|
| `watch/` | 玻璃播放器、三态布局与观赛偏好 | `python3 product/watch/preview.py` |
| `web/` | 像素风展示及历史创作界面 | `python3 product/scripts/serve.py` |
| `agent/` | AgentCore 多轮读图、查证与叙事 | `agent/story_agent.py`、`agent/story_contract.py` |
| `rl/` | 三层证据、数据球探训练与 SageMaker 客户端 | `rl/train_evidence.py`、`rl/evidence_client.py` |
| `broadcast-fx/` | 编辑视觉、战术板与完整成片渲染 | [视觉库](broadcast-fx/README.md)、[正式素材](broadcast-fx/formal/README.md) |
| `worker/`、`api/` | 异步生成、任务状态与预算控制 | `app.js` 中的 Lambda 和 SQS 定义 |
| `delivery/` | 独立验收与可选语音处理 | [验收模块](delivery/README.md) |
| `evidence/` | 来源、真实任务、媒体与失败记录 | [证据索引](evidence/README.md) |
| `court-lab/` | 编辑俯视示意研究原型 | [研究说明](court-lab/README.md) |

以下命令均从仓库根目录执行。

## 本地预览

需要 Python 3.11+。前端预览使用随仓库的原生 ESM，无需安装 npm 或连接 AWS：

```bash
python3 product/watch/preview.py --port 4178 --media-dir /path/to/local-media
```

媒体目录应包含注册样片 `flagg.mp4`、`amen.mp4`；省略目录时使用既有本地解析规则。文件缺失会显示提示，界面与设置仍可打开。详细交互见[观赛前端](watch/README.md)。

本地产品预览与历史回执：

```bash
python3 product/scripts/serve.py
```

访问 http://127.0.0.1:4173/product/。服务仅绑定本机地址，使用媒体白名单与哈希检查，不代理 AWS。所需媒体不会通过 Git 自动恢复：

- 两段注册样片位于 `data/reference/train_video/train_video/`，精确文件名见 `scripts/serve.py` 的 `SOURCES`。
- 正式原片为 `data/正式视频.mp4`。
- 已验收自动成片为 `product/build/verified/<jobId>/enhanced.mp4`，需要与对应运行回执匹配。
- 正式编辑片为 `product/build/formal-assets/` 中的 MP4 及配套 manifest。

大媒体必须来自已有授权与正确版本。通过 `scripts/archive-source.py` 生成的旧存档可用于本地恢复；其媒体白名单不覆盖每一个赛后答辩导出。

## 离线质量检查

需要 Node.js 22、Python 3.11+：

```bash
npm ci --prefix product --ignore-scripts
python3 product/scripts/check.py --full
```

现有 GitHub Actions 使用同一命令，隔离云凭证与外部网络。门禁检查源码、语法、Python/JavaScript 行为及真实 CDK 合成模板；媒体层使用明确合成占位，不认证实际模型、媒体打包或在线部署。

## 模型训练与本地渲染

先查看标准库即可执行的训练计划：

```bash
python3 product/rl/train_evidence.py --dry-run --out product/build/rl-plan
```

真实训练依赖分别保存在 `rl/requirements_evidence.txt`、`rl/requirements_package_evidence.txt` 和 `rl/serve_evidence/requirements.txt`。训练、打包、实时端点不是同一步；完整来源和限制见[训练结果](../docs/RL三层联合训练结果-20261010.md)与[服务交付](../docs/RL服务交付-20261010.md)。

本地视觉处理依赖：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r product/broadcast-fx/requirements.txt
```

系统还需要 FFmpeg / ffprobe 及渲染路径指定的字体、源视频和预处理帧。正式渲染器校验固定源片哈希，不能通过替换文件名套用任意比赛。具体准备步骤见[正式渲染说明](broadcast-fx/formal/README.md)；英文答辩片见[最终演示说明](../docs/PPT最终演示视频-20261011.md)。这些本地工具不会自动启动新的云推理。

## AWS 构建与部署

`deployment.json`、`cdk.json` 和 `app.js` 保存赛事环境配置。赛后模型和资源管理权限曾受到限制；[赛后核查](../docs/赛后服务可用性核查-20261011.md)是历史事实记录，不是当前长期服务承诺。

下列步骤用于理解比赛环境的复现路径，需要有效的对应授权、模型访问、GPU 条件与输入媒体：

```bash
python3 -m venv readiness-lab/.venv
readiness-lab/.venv/bin/python -m pip install -r product/agent/requirements.txt
npm ci --prefix product --ignore-scripts
readiness-lab/.venv/bin/python readiness-lab/prepare_build.py
readiness-lab/.venv/bin/python product/scripts/build.py
```

`prepare_build.py` 下载固定版本 SDK、Linux 媒体二进制和字体，并校验指纹；`build.py` 打包当前 Agent、Worker 与交付模块。二者只做本地构建。SageMaker 模型训练与端点另有 SDK 脚本。

赛事部署必须使用 `nba` profile、`us-east-1`、已登记账号和指定权限边界；不使用 `default`，不再次 bootstrap，不从历史练习工程覆盖主链。

在已经核对目标身份、资源和当前权限后，从 `product/` 执行 CDK diff / deploy，再由发布脚本校验媒体并上传。完整比赛命令和部署约束保存在[工程归档](../docs/archive/competition-2026/产品工程说明-比赛期间.md)，避免读者把历史命令当成通用一键部署。

在自己的 AWS 账号复现时，需要调整部署目标、角色与权限边界、模型和端点配置；离线门禁当前锁定比赛账号，不能将修改后的自有账号模板记作原赛事验收。

## API 与发布

内部 API 不是主办方官方评测协议：

| 方法与路径 | 用途 |
|---|---|
| `GET /api/status` | 查询服务和登记素材 |
| `POST /api/jobs` | 创建一次异步生成任务，例：`{"sample":"flagg","mode":"story"}` |
| `GET /api/jobs/{jobId}` | 查询原任务状态、结果与错误 |

CloudFront 的 Lambda IAM 源要求 POST 携带请求体原始 UTF-8 字节的 `x-amz-content-sha256`；浏览器前端负责计算，不持有 AWS 凭据。创建任务会调用模型，结果查询不会创建新任务。

`scripts/publish.py` 提供媒体、配置及网页发布；`scripts/publish_readme.py` 只发布冻结的[比赛作品说明](../SHOWCASE.md)及明确白名单配图。本仓库新首页独立于比赛 CloudFront 的 `/readme`，维护 GitHub 文档不触发云更新。

## 内容与来源契约

- 官方事实、派生算术、画面观察和编辑解释分别保存。
- 单次出手、本场完整赛后统计与赛季快照使用不同粒度；缺失数据不补零。
- 模型输出证据 ID，数值由程序从记录复制，语义错误由校验与有限纠错处理。
- 俯视板、箭头、空间强调和人物轮廓属于编辑示意，不是逐帧自动追踪。
- 训练结果、真实服务调用、完整媒体解码与浏览器播放各有证据，不互相替代。
- 不把注册样片上的通过结果推广为任意比赛或实时观赛已经可用。
