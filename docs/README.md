# GameBuddy · 文档导航

项目概览、银奖合影与快速开始见[主 README](../README.md)。这里将实现指南、真实验收和历史比赛材料分开，便于按目的阅读。

## 开发入口

| 目的 | 文档 |
|---|---|
| 本地预览、媒体恢复、模型和云构建 | [产品工程指南](../product/README.md) |
| 三态播放器、设置与本地媒体 | [观赛前端](../product/watch/README.md) |
| 视频视觉库与复用组件 | [Broadcast FX](../product/broadcast-fx/README.md) |
| 正式素材与固定时间线 | [正式视频渲染](../product/broadcast-fx/formal/README.md) |
| 独立交付验证 | [交付模块](../product/delivery/README.md) |
| 俯视编辑示意研究 | [Court Lab](../product/court-lab/README.md) |
| 第三方权利与源码许可 | [素材说明](../THIRD_PARTY_NOTICES.md)、[MIT](../LICENSE) |

## 架构与数据球探

- [最终技术架构图](ppt-materials/20261011/figures/06-gamebuddy-paper-pipeline-v6-branded.png)
- [核心技术与答辩素材](ppt-materials/20261011/技术核心创新与答辩素材.md)
- [三页技术答辩 PPT](ppt-materials/20261011/three-slides-output/GameBuddy-技术答辩三页.pptx) · [讲稿](ppt-materials/20261011/three-slides-output/三页技术答辩讲稿.md)
- [RL 三层联合训练结果](RL三层联合训练结果-20261010.md)：固定评测、无额外 RL 增益及原语义错误。
- [RL 服务交付](RL服务交付-20261010.md)：训练后端点与语义护栏组合验收。
- [RL 产品端到端接入](RL产品端到端联调验收-20261010.md)：真实选证、Agent 叙事和完整 MP4。
- [球员攻防画像与比较](RL攻防球员画像与对比-20261010.md)：同口径比较与确定性算术。

## 视频与观赛体验

- [最终答辩展示视频](https://github.com/imhaojie/BroadcastCode-2026/releases/tag/presentation-demos)：回合解读与 GameBuddy 介绍。
- [正式 55 秒豆包双人解说与发布](正式55秒豆包双人解说与主页发布-20261010.md)
- [英文画面、攻防数据与战术板](PPT英文画面与战术板精修-20261011.md)
- [连续 MOSS 英文双人解说](连续MOSS双人解说与最新画面合成-20261011.md)
- [最终英文答辩视频](PPT最终演示视频-20261011.md)
- [公开页面路由收敛](公开路由收敛-20261010.md)
- [新首页配图来源](assets/project/sources.json)

## AWS 与验收

- [AWS 托管交付闭环](AWS托管交付闭环-20261010.md)
- [正式账号端到端验收](正式账号端到端验收-20261010.md)
- [实际运行证据索引](../product/evidence/README.md)
- [工程质量与离线门禁](工程质量与快速迭代-20261010.md)
- [赛后服务状态](赛后服务可用性核查-20261011.md)
- [源码存档与恢复](源码保存与恢复.md)

运行记录按时间和对应版本理解。后续成功不删除旧失败；历史权限、地址和已登记案例不能推导任意新输入或当前云服务可用。

## 比赛归档

[比赛归档索引](archive/competition-2026/README.md)包含规则、培训纪要、历史 AGENTS、AI 协同与旧首页。最新获奖结论以用户于 2026-10-12 确认的银奖为准。

[SHOWCASE.md](../SHOWCASE.md)是冻结的比赛作品说明，继续作为 CloudFront `/readme` 发布器的源；新 GitHub 首页不通过它发布。历史 `readiness-lab/` 和 `aws-validation/` 仍在源码树中保留，不能直接作为默认部署入口。
