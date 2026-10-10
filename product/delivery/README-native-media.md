# 托管语音与场景辅助

`narrator.handler` 接收 `{ "jobId": "32位小写十六进制" }`，只处理同账号、同 Runtime 的完成任务，且须先有独立 `deliveryVerification.verified=true`。它再次核对注册来源、官方指标、固定 CloudFront 产物路径、原 analysis 和实际 MP4 SHA-256。未通过前两项托管服务均不调用。

- **Amazon Polly**：按已验证章节的 `start` 分段播放，复制 caption 首句或逗号前的短语；不足4字的前短语保留首句，不编写新事实。官方指标独立在 `plan.metrics[0].revealAt` 播放，绝不提前透露结果或数值。片尾结果段与指标阶段冲突时只播官方指标短句，画面保留结果字幕。总长度上限120字符，使用 XML 转义的 SSML、`Zhiyu`、`standard`、140%语速，不做新大模型推理。
- 每段真实 Polly MP3 均经 FFprobe 测时，必须完整落在本章节、下一语音开始或视频结束之前；超出任一窗口整体 `available=false` 回退，不截音、不调整原视频。已验证段通过 FFmpeg 延迟到对应时间，混合静默底轨生成完整 `narration.mp3`，以 `segments` 记录文本、开始、窗口结束和真实语音时长。版本为 `native-media-v2`，旧连续解说回执不复用。
- **Amazon Rekognition**：只对同桶注册表中该任务的一个输入帧调用 `DetectLabels`，记录真实 `Labels` 和置信度。结果仅用于场景辅助；不是球员身份、移动轨迹或篮球准确性认证。失败独立标记 `scene.available=false`，不阻塞语音或原片。

派生产物为 `product/outputs/<jobId>/narration.mp3`、`narrated.mp4`、`narration.json`。原 `enhanced.mp4`、`analysis.json` 及任务完成状态均不修改。成片持续显示“AI语音解读 · Amazon Polly”；默认音轨为语音＋22%原声，另复制全部原始 AAC 音轨，保留完整原视频时间线。必须完整解码、校验时长、尺寸和音轨数量之后才上传语音及成片。失败仅保存安全回执，返回 `available=false` 与原视频 URL，前端应继续使用已验证原片。

部署包需包含同目录 `handler.py`、共享 `story_contract.py` 与 SDK；复用已存在 FFmpeg、ffprobe、CJK字体 Layer。环境使用 `BUCKET`、`TABLE`、`RUNTIME_ARN`、`MODEL_ID`、`CLOUDFRONT_HOST`，可覆盖 `FFMPEG_PATH`、`FFPROBE_PATH`、`FONT_PATH`。执行角色最小权限为指定任务表读取、受控 S3 对象读取/派生产物写入、`polly:SynthesizeSpeech`、`rekognition:DetectLabels`；后两项按 AWS 服务要求使用资源 `*`，区域仍为 `us-east-1`。Step Functions 应在独立验证成功后调用；此模块不创建训练、身份识别、外部 URL 或其他资源。

本地边界验证：`python3 -m unittest discover -s product/delivery -p test_narrator.py -v`。测试使用明确合成字节与注入客户端，验证错误哈希/未验证任务不调用服务、SSML转义、语音超长不截断、托管服务失败回退、全解码失败不上传媒体。离线通过不能代替云端 Polly/Rekognition 和真实成片验收。

媒体工具兼容：赛事工程锁定的Layer为FFmpeg4.1，分段合成使用显式双声道delay、静默padding和恒定归一化恢复；不使用后续版本才支持的adelay all / amix normalize。语音先测实际窗口，再把各段放入静默时间线，最后完整解码，原片不截取。媒体子进程失败记录阶段、退出码与有限本地诊断到私有日志，公开回执保留安全状态，不输出凭证或模型请求。
