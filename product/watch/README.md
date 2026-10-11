# GameBuddy · 观赛前端

沉浸式、全场和半场连续切换的桌面观赛界面，采用原生 JavaScript ESM。产品与合影见[主 README](../../README.md)，本页介绍可运行的本地入口。比赛期间的逐轮材质和交接记录见[历史前端说明](../../docs/archive/competition-2026/观赛前端说明-比赛期间.md)。

## 启动

需要 Python 3.11+，推荐近期桌面 Chrome 或 Edge。从仓库根目录运行：

```bash
python3 product/watch/preview.py --port 4178
```

打开 http://127.0.0.1:4178/。服务仅绑定本机地址，不读取 AWS 凭据、不创建云任务。前端所需 vendor 已随源码保留，不需要先安装 npm。

也可以在仓库根目录执行：

```bash
./product/watch/start-local.command
```

该脚本适合 macOS；跨平台优先使用 Python 入口。按 Control-C 停止。

## 媒体

原始 MP4 不随 Git 分发。将已授权注册样片保存为 `flagg.mp4`、`amen.mp4`，用显式媒体目录启动：

```bash
python3 product/watch/preview.py --port 4178 --media-dir /path/to/local-media
```

还可使用 `BROADCASTCODE_MEDIA_DIR`。解析优先级是命令行 → 环境变量 → 既有本地媒体目录；没有文件时显示缺失状态，仍可打开观赛设置。

这两个名字对应当前案例的事件与编辑标注，不是任意视频识别接口。加入新的比赛素材需要同步登记并适配数据、时间映射和标注。

## 交互

- **三态布局**：沉浸式观看，以及全场、半场战术板。可用 `/?mode=fullCourt` 或 `/?mode=halfCourt` 直接查看。
- **边缘 Dock**：按需打开章节、球员数据、来源、素材和历史记录。
- **战术视图**：独行侠 / 火箭皮肤、攻防配色、已编辑的站位与路线阅读。
- **观赛偏好**：界面设置、提示和现有证据展示；配置保存在当前浏览器。
- **可调材质**：默认清透 CSS 毛玻璃；`/?glass=liquid` 显式启用保留的 liquidGL 实验实现。

参数契约、导入导出和本地预设见[调参与组件指南](docs/调参与组件指南.md)与[参数契约](dev/CONFIG_CONTRACT.md)。

## 实现与验证

默认 CSS 方案没有持续运行的 liquidGL 镜片输出循环。`window.broadcastDiagnostics()` 可以读取材质模式、布局和视频帧统计；外观本身不证明启用了 WebGL。第三方补丁见 [VENDOR_PATCH.md](glass/VENDOR_PATCH.md)。

前端离线测试从本目录执行：

```bash
cd product/watch
npm test
```

这些检查验证布局、配置与标注契约，不能替代真实浏览器中的媒体播放和材质验收。

## 数据范围

`data/stories.json` 保存故事和来源，`data/flagg.json` 保存编辑战术示意，`adapters/` 处理历史运行及来源呈现。历史位置、估计锚点和当前可见位置保留不同含义；缺少对应素材时保持缺失状态。

战术点、箭头与空间提示不是官方逐帧追踪数据。队伍名单不证明某人是本次出手的直接防守者。观看区的全部偏好尚未传给创作 Agent。

正式产品的同源媒体及历史结果入口由[产品预览服务器](../scripts/serve.py)提供。独立 `preview.py` 是前端本地开发工具，不等同于生产服务。

球队标志来源见[球队素材说明](assets/teams/README.md)；liquidGL 保留其[原始 MIT 许可证](vendor/liquid-gl/LICENSE)。
