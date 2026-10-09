# 独立人体检测实验

这份脚本只在本地显式运行 Flagg 原片的 9.0s、9.5s、10.0s 三帧，未导入产品、前端或云流水线。执行记录在 [2026-10-09 检测实测](../../evidence/court-detector-20261009.json)。

通用 YOLO11n 能提供人体框候选，不能保证全员连续定位：9s 的 10 个球员身体都有框，但其中一人的脚被遮挡；10s 的三人重叠区域合为一个框。检测到的 44/39/40 个人体包括观众和裁判。框底中心不是准确脚点，人工框关联是 AI 看图核对，不是身份模型、官方追踪或专家 ground truth。

## 本地复现

需要 Python 3.11、约 819 MB 的独立依赖环境、5.61 MB 权重，以及已经按源码存档恢复的 Flagg 原片。只使用官方 PyPI 和官方 Ultralytics 资产。39 个依赖的精确版本已保存在 [requirements.lock.txt](requirements.lock.txt)；这些版本是在 macOS 15.3 / Apple Silicon 上实测的环境，尚未验证 Linux。

```sh
uv venv --python 3.11 product/build/court-lab/.venv
uv pip sync --python product/build/court-lab/.venv/bin/python --index-url https://pypi.org/simple product/court-lab/detector/requirements.lock.txt
```

另行显式下载 [官方 YOLO11n 权重](https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt)，保存为 `product/build/court-lab/detector-yolo11n.pt`。应为 5,613,764 字节，SHA-256 为 `0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1`。脚本检查权重哈希后才加载，并拒绝自动下载模型或安装依赖。

在仓库中运行：

```sh
product/build/court-lab/.venv/bin/python product/court-lab/detector/run.py --run-local-probe
```

路径根据脚本位置解析，运行目录不影响结果。`--help` 或导入文件不会开始推理。输出只写入 ignored 的 `product/build/court-lab/detector-*`，不修改另一实验的 `generate.py`、标注 JSON 或前端。它通过 AST 只读取 `generate.py` 的原始手工种子，不导入或执行该文件。

CPU 固定 4 线程；本次 MPS 可用但未使用，**没有 GPU/AWS、训练、ReID 或球检测**。推理阶段禁用网络连接；原片不外传。首次预测 10.71 秒，后两次约 0.09 秒，但三帧测试不能证明整段实时吞吐量。

## 许可与保存范围

官方明确 YOLO11 模型及 Ultralytics 代码为 **AGPL-3.0 / Enterprise**，不是 MIT。[模型许可说明](https://docs.ultralytics.com/models/yolo11/#citations-and-acknowledgments)、[厂商许可说明](https://www.ultralytics.com/license)。本地独立验证不代表私有参赛产品的接入／部署已合规；未把该模型用于对评委的产品服务。

仓库仅保存小脚本、依赖锁定文本和真实验证记录；不保存权重、虚拟环境或原始诊断图。已安装包的 LICENSE 副本与哈希仍在本机 ignored `product/build/court-lab/detector-*`。原片、截图等媒体遵循项目已有本地存档安排。
