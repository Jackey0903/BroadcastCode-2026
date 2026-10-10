# 历史资产来源工具

`track.py` 与 `camera2.py` 为 Claude 原型的原样来源保存，不属于任意视频追踪 API。它们使用命令行传入的工作目录，没有临时目录常量。

- `track.py` 中 `KEYS` 为弗拉格人工关键帧标注，通过插值与相机运动估计生成 `track.json`；出手后短段沿用锚点用于淡出效果，不能当作持续观测。
- `camera2.py` 使用 960 × 540 的 `all/fNNNN.jpg` 估计图像相似变换，保存全分辨率像素单位的 `camera2.json`。
- 这两个工具仅保存算法来源。默认复现使用校验后的持久 JSON，不重新估计或替换它们。
- 需检查源算法时，可先从已核验的原片生成 `all/f%04d.jpg`：FFmpeg 视频过滤器设为 `scale=960:540`，`-start_number 0 -q:v 2`，然后依次运行 `camera2.py WORKDIR`、`track.py WORKDIR`。重算结果必须另存工作目录并复核；不得无证据替换持久资产。

源数据适用范围及文件 SHA-256 见 [manifest.json](../manifest.json)。
