# 完整出片准备验证 Worker

入口 `handler.handler`，接收 SQS 消息 `{"jobId":"...","sample":"flagg"}`；`sample` 允许 `flagg`、`amen`。环境变量：`BUCKET`、`TABLE`、`RUNTIME_ARN`、`CLOUDFRONT_HOST`。DynamoDB 主键为 `id`。

读取 `s3://BUCKET/config/samples.json` 的对应样片配置，配置采用 [Agent 测试协议](../agent/README.md)中的 `video` 与 `frames`。校验原视频哈希后真实调用 AgentCore，把其生成的字幕加上“AI画面观察”和来源帧时刻，烧录到完整视频。导出 1280×720、30 fps、libx264 veryfast CRF 24、AAC 128k；探测时长与源片不符时拒绝发布。

工具层需要 `/opt/bin/ffmpeg`（含 drawtext/libx264/AAC）、`/opt/bin/ffprobe` 和 `/opt/fonts/NotoSansCJKsc-Regular.otf`。可用 `FFMPEG_PATH`、`FFPROBE_PATH`、`FONT_PATH` 覆盖，仅用于已知本地工具路径。新 SDK 由主部署流程打包。

输出在 `outputs/{jobId}/enhanced.mp4` 和 `analysis.json`。DynamoDB 更新阶段及 `completed/failed` 状态，完成项包含 `videoUrl`、`analysisUrl`、`analysis`；其中 `summary` 来自真实模型观察，`observations` 提供 `text/timeSeconds/timestampMs`，还保存模型、Runtime、来源时间、源/输出哈希和输出时长。

模型或渲染失败不会用固定字幕或假成片补成功；失败任务写入 `failed`，SQS handler 返回空 `batchItemFailures`，由用户明确重试以避免自动重复计费。Runtime 会话尝试停止，停止失败只记日志，不覆盖原结果。已完成的同一 jobId 不再次调用模型。

本地执行 `python3 -m unittest -v test_handler.py`；这些测试使用明确的假 AWS 客户端和假渲染器，只验证参数、控制流、失败拒绝、时长完整性与证据留存。它们不证明云端或 FFmpeg 已成功，真实端到端证据由主流程另行保存。
