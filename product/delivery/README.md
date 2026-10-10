# 成片交付验证任务

这是供 Step Functions 调用的独立 Lambda 任务，入口 `handler.handler`。它验证已经完成的 `story` 成片，不启动 Agent 或模型，不重新渲染，不改原任务的 `status`、`stage`、`analysis`。

## 输入和输出

输入只能包含 `jobId` 或 `runId`，值为同一个 32 位小写十六进制编号。禁止额外路径、桶名、URL 等字段。

```json
{"jobId":"3526ae13a69b42c082b2fe4f0bacfa67"}
```

成功输出包含 `verified:true`、`jobId`、实际 MP4 SHA-256、分析文件 SHA-256、注册原片 SHA-256、媒体时长与音轨检查结果，以及 `idempotent`。失败返回 `verified:false`、结构化 `code`、`retryable`；Step Functions 必须用 Choice 检查 `verified`，不能把 Lambda 的正常返回等同于交付成功。

## 实际核验范围

- DynamoDB 必须存在对应 `completed` / `story` 任务，任务 ID、Runtime、模型、调用 token、持久化输出元数据相符。
- 对象只能来自部署配置的桶。输出 Key 固定为 `product/outputs/<jobId>/enhanced.mp4` 和 `analysis.json`；客户端无法指定其他路径。CloudFront URL 必须由部署 hostname 和固定 Key 构成。
- 当前注册表 `product/config/samples.json` 的原片信息、SHA-256，与当前 `product/data/stories.json` 选定故事对应。官方事件和指标经共享 `story_contract.canonical_metrics` 校验后，与成片分析完全一致。
- S3 分析文件的原字段必须与 DynamoDB 中原分析一致；允许发布器添加独立 `publication` 包装元数据，禁止替换来源、模型、官方指标、计划或输出事实。流式下载真实 MP4，最多 50 MiB；检查 MP4 文件头、字节数及真实 SHA-256。
- 复用已核准 FFmpeg Layer：FFprobe 检查 H.264、1280×900、AAC 音轨与完整源片时长；FFmpeg 完整解码检测截断、损坏。原片限 60 秒；输出容许 250 毫秒编码尾差。内部总预算 110 秒，Lambda 应配置 120 秒超时；请求 connect/read timeout 为 5/10 秒。
- 仅写独立 `deliveryVerification`，更新条件要求任务仍存在、仍完成、输出哈希及原分析快照未改变。缺失任务、非法输入不会创建任何任务。内容拒收、媒体验证失败不会把完成的生成任务伪造成 `failed`。
- 成功重复调用核对当前注册证据、DynamoDB 分析指纹、S3 ETag／版本／大小／最后修改时间；对象身份不变则复用已有成功回执，不重新解码。发现变更必须重新验证。失败回执允许修复产物后重试。

故事 JSON 的整文件哈希可能因观看区发布链接更新而改变，故核对选定故事的原片、官方事件和指标，不以当前整文件哈希冒充任务当时不可变版本。原分析中的当时 manifest 哈希仍须存在且同桶来源合法。

此回执认证媒体和数据来源的一致性，不认证篮球解读、视觉美观或主办方评分。

## 部署配置

环境变量：

|变量|用途|
|---|---|
|`BUCKET`|唯一允许读取的 S3 桶|
|`TABLE`|已有任务 DynamoDB 表|
|`RUNTIME_ARN`|当前部署 AgentCore Runtime ARN|
|`MODEL_ID`|允许的实际模型 ID，默认 `global.anthropic.claude-sonnet-4-6`|
|`CLOUDFRONT_HOST`|当前分发 hostname，可带 `https://`|
|`FFPROBE_PATH` / `FFMPEG_PATH`|默认 `/opt/bin/ffprobe`、`/opt/bin/ffmpeg`|

部署 ZIP 需要 `handler.py` 和同版本 `product/agent/story_contract.py`，以及 pinned SDK（或 Lambda Python runtime 内置 boto3）。附已有媒体 ToolsLayer，建议 1024 MiB 内存、120 秒超时。

最小权限：

- `dynamodb:GetItem`、`dynamodb:UpdateItem`，仅现有任务表。
- `s3:GetObject`，仅指定桶的 `product/outputs/*`、`product/config/samples.json`、`product/data/stories.json`。`HeadObject` 使用 `s3:GetObject` 权限。
- Lambda CloudWatch 日志写入；Step Functions 执行角色仅需 `lambda:InvokeFunction` 指向此 Lambda。
- 不需要 `PutObject`、`ListBucket`、Bedrock、AgentCore、SageMaker 或 `iam:PassRole` 权限。

窄测试：

```sh
python3 -m unittest discover -s product/delivery -p 'test_*.py'
```

离线测试使用明确合成文件头和注入媒体检查，核验错误哈希、伪 URL、跨桶路径、缺失任务、重复验证、对象变更、音轨和时间边界；不冒充云端真实 FFmpeg 验收。上线后对已经生成的真实成片执行一次此工作流即可，无需再次模型推理。
