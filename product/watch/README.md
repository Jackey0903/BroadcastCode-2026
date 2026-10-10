# BroadcastCode 三态观赛前端

本目录是沉浸式、全场、半场连续切换的独立桌面前端，已集成到 `BroadcastCode-2026/product/watch/`，本地预览已可运行。**2026-10-10 按用户授权提交到独立分支 `codex/watch-liquid-glass`；不合并 main、不部署**。既有 `product/web/` 和后端保留；本前端只读取随附 JSON 与本地白名单原片，不调用任务 API、不启动新推理。

## 比赛稳定版默认材质（2026-10-10）

默认使用清透 CSS 毛玻璃（Dock、控件和菜单：默认8–9px模糊、约0.11–0.18轻染色、24%白色亮边）及低成本半透明战术板（约0.27染色、无模糊）；视频氛围画布不再采样，没有 liquidGL 镜片、输出画布或实时渲染循环。三态布局及自动展开 350ms 保持原样，动画中暂停 CSS 模糊，停稳后恢复。

原液态实现、25 点核及配置完整保留。赛后可用 `/?glass=liquid` 显式启用；关闭该参数就回到稳定版，不会修改本机保存的光学预设。观看设置中的“外观与组件”保留完整中文调参；材质模式独立选择，CSS 中不适用的光学控件禁用但保留数值。`window.broadcastDiagnostics()` 始终可用，默认报告 `mode:css`、`backend:css`、`enabled:false`、`lenses:0`、`canvases:0`，并保留视频帧统计。

验收方法、实际结果与边界见[比赛稳定版验收](docs/比赛稳定版-20261010.md)。

## 启动

需要 Python 3.9 或更新版本。浏览器脚本为原生 ESM，liquidGL 3.0.0 已固定并随源码放在 `vendor/`，本地预览无需安装 npm 依赖。

在正式目录中双击 `start-local.command`，或在任意终端目录执行：

```sh
/Users/wuguangyu/Desktop/BroadcastCode-2026/product/watch/start-local.command
```

打开终端打印的 [本地预览](http://127.0.0.1:4178/)。默认端口是 4178；仅绑定 `127.0.0.1`，没有对外监听选项。按 Control-C 停止。已有预览占用端口时，可指定另一个端口：

```sh
./start-local.command --port 4188
```

已完成本地整合，可在实际仓库根目录运行 `./product/watch/start-local.command`，浏览器入口是该独立服务器的 `/`。

## 本地媒体

`flagg.mp4`、`amen.mp4` 保持在 Git 仓库之外。本机默认目录为：

```text
/Users/wuguangyu/Desktop/NBADRAFT/broadcastcode-ui/local-media
```

解析优先级为 `--media-dir` → `BROADCASTCODE_MEDIA_DIR` → 与前端目录同级的 `local-media` → 当前用户桌面的上述已知目录。自动选择只检查文件是否存在，不下载、不上传、不扫描凭据目录；显式指定的缺失目录不会被悄悄替换。可以用以下任一方式覆盖：

```sh
./start-local.command --media-dir "/Volumes/Media/BroadcastCode"
BROADCASTCODE_MEDIA_DIR="/Volumes/Media/BroadcastCode" ./start-local.command
python3 preview.py --port 4178 --media-dir "/Volumes/Media/BroadcastCode"
```

HTTP `/samples/flagg.mp4` 与 `/samples/amen.mp4` 只映射到这个媒体目录，支持视频 Range 请求。服务器启动时打印实际路径及两份原片是否存在。缺少原片会显示缺失状态，调参面板仍可打开；媒体恢复后点击重试。

本机原片于 2026-10-10 重新核对 SHA-256：

| 文件 | 字节数 | SHA-256 |
| --- | ---: | --- |
| flagg.mp4 | 83907519 | `9c3e4606d04e7f79e29a112952fcf069ebab202af207af500bfbc3338bc079ce` |
| amen.mp4 | 87308125 | `7ec745f5f1e75b0c6d6dd27d409875f67c2ac3ab76c73f7123794c96be5aee22` |

当前本机没有两份历史增强成片。页面保留真实历史任务记录及验收信息，同时标明成片缺失；这不代表重新生成或重新验收。不要把 MP4、录像、缓存、`.env`、凭据或 `local-media/` 复制进待提交源码。

## 交互与验证

鼠标进入右侧边缘后，战术板先经过全场并连续展开到半场。菜单可手动停留全场或半场。左侧边缘唤出 Dock，再按需打开章节、数据、来源、素材和历史记录。战术板与比赛并排，保留原视频比例及原比分牌。

在菜单中打开组件调参面板。独立字号、字族、字重、玻璃等分组参数，以及命名预设、导入导出与撤销重做见 [调参与组件指南](docs/调参与组件指南.md) 和 [参数契约](dev/CONFIG_CONTRACT.md)。导入只接受受限的配置字段；“保存”存放于当前浏览器本机。

可直接使用 `/?mode=fullCourt` 或 `/?mode=halfCourt` 检查手动状态。在浏览器开发者工具执行 `window.broadcastDiagnostics()`，读取实际 liquidGL 状态、布局、视频尺寸与显式解码/丢帧统计。仅看到玻璃外观不能证明 WebGL 已启用，验收应以渲染状态与真实浏览器画面共同判断。liquidGL 补丁见 [VENDOR_PATCH](glass/VENDOR_PATCH.md)。

离线测试需要可运行原生 ESM 和 `node --test` 的 Node.js：

```sh
npm test
```

这些测试检查布局、参数和标注契约。三态截图、形变录屏、材质实际状态和视觉差异清单由独立浏览器验收交付，不能由离线测试替代。原生 Mac TV.app 已播放同一原片并取得动态材质对照，暂停13.08秒有AX记录；精确材质一致性仍有差异，tvOS机顶盒未验收。材质对照用于细节校准，仍保留三张原图布局。已保留本机命名候选“Apple TV 材质对照”，仅改controls的染色透明度0.24、磨砂1、折射0.018；旧v2预设兼容迁移补齐默认字族 / 字重后，其他组基线不变。演示后已恢复并保存baseline，候选不是新默认或精确量化匹配。

## 数据与整合边界

- `data/stories.json` 与 `adapters/historical-records.js` 保留事件来源、时间含义、章节和历史任务。官方数值、画面观察、编辑解释分别展示。
- `data/flagg.json` 是已有编辑战术示意；D/W 匿名编号不推测球员身份，历史位置与当前位置保持区分。阿门素材没有同等完整战术数据时显示缺失状态。
- 原片头顶标注只接受有效头部锚点；不从脚点推导头点。原创吉祥物不会被包装成追踪结果。
- 本轮已只新增 `product/watch/`，包含本目录前端、文档、vendor 和启动脚本。整合前后已分别核对 Git 状态，既有后端文件和部署脚本没有差异。
- 后端由队友负责。这个启动脚本只提供本地静态资源和两份原片；它不是生产服务或部署命令。
