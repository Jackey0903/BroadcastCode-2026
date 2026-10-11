# GameBuddy · 当前维护交接

2026-10-12。比赛已经结束，用户确认 **Team02 获得银奖**。当前工作转为仓库整理与开源文档，主入口是 [README.md](README.md)。原逐轮交接完整保留在[比赛期间接手说明](docs/archive/competition-2026/AI接手说明-比赛期间.md)，协同日志在[归档目录](docs/archive/competition-2026/README.md)。

## 当前结构

- `product/` 为产品源码与部署工程；启动见[产品工程指南](product/README.md)。
- `product/watch/` 为玻璃观赛前端；Python 本地入口无需云凭据。
- `docs/README.md` 导航架构、模型、视频、AWS 和验收材料。
- `SHOWCASE.md` 保留原比赛作品说明。发布脚本读取它，GitHub README 与比赛 CloudFront `/readme` 分开维护。
- 比赛根目录的规则、账号说明和 AI 协同流水归入 `docs/archive/competition-2026/`；历史成功与失败回执没有删除。
- 重复 PPT 交付 ZIP / 解压副本移入忽略的 `product/build/handoff-20261011/`；三页 PPT 与讲稿保留在 `docs/ppt-materials/20261011/three-slides-output/`。
- 比赛合影原样保存，新首页配图从最终英文 55 秒答辩片截取；来源见 `docs/assets/project/sources.json`。

## 维护时必须保留的事实

自动弗拉格 RL 样片真实调用训练后 Qwen2.5-3B，三层证据进入 Agent 叙事与 MP4。正式 55 秒 Christie 作品使用编辑视觉和 AgentCore 稿件审核，提交版豆包双人语音与赛后英文 MOSS 版分别记录。最新本地答辩片仍是 `product/build/ppt-demo-20261011/english-v6/GameBuddy-PPT-Final-Demo-20261011.mp4`；媒体不随 Git 分发。

RL 实验相对 SFT 无额外增益，原失败保留；6/6 指模型、程序语义检查与有限纠错的已知案例组合验收。三层证据共 1,993 条：基础 1,513、高阶派生 166、深度 314。官方 xFG 事件记录单独保存，赛季快照不能冒充实时数据。

赛后云模型和管理权限曾被收回，历史在线展示与重新生成不是同一个状态。仓库维护不自动触发新的云部署、训练或计费。

## 本轮整理

参考用户的 DraftCode、VoxSprite、PosterMELD README，建立品牌区、银奖与合影、演示图库、架构、数据与模型说明、AWS 清单、快速开始、仓库导航和许可。原创代码使用 MIT，第三方权利单列。发布器只做文档源切换，产品算法与云端部署未改变。

整理后的统一离线门禁通过：126 个 Python 文件、53 个 JavaScript 文件、514 项行为测试（无跳过）、50 项 CDK 资源合成检查。主入口文档的本地链接核验无缺失；不将这些离线结果记为重新部署、媒体或模型验收。
