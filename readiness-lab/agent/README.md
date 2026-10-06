# Team02 最小视频观察 Agent

此目录用于剩余赛前准备的真实链路验证。协议 `team02-readiness-v1` 是**本队测试协议，不是主办方最终评测 schema**。没有官方指标输入，输出不能用作完整战术分析或评分认证。

## 服务和协议

- Python 3.12，标准库 HTTP 服务，监听 `0.0.0.0:8080`；`GET /ping` 返回 `Healthy`，`POST /invocations` 接收 JSON。
- 必需环境变量 `READINESS_BUCKET`；可选 `READINESS_BUCKET_OWNER`。只读该桶中的输入图片；S3/模型调用使用 Runtime 执行角色，代码不含 profile 或凭证。
- 通过 Bedrock `global.anthropic.claude-sonnet-4-6`、区域 `us-east-1` 实际观察 1–6 张 JPEG/PNG 帧。SDK请求包含实际图片字节，不是仅传文件名。
- 输入见 [example-request.json](example-request.json)。视频元数据仅做来源关联；图片必须由该真实训练视频抽取，时间戳由调用方的抽帧步骤确定。Agent 不能单凭 S3 URI 证明图片属于某个视频。
- 输出包含原 `request_id`/`video`、`processing_message`、模型生成的 `observation`、`subtitle`、`source_frame_times_ms`、`model_id`、`usage`、`status`。来源时间只允许取自输入帧集合。
- 无效输入返回 400；模型输出不合约或上游失败返回 502。不会用固定成功字幕替代失败的模型结果。
- 字幕最多 40 字；调用方把它烧录到完整训练视频后上传。Agent 不直接渲染、上传结果或创建资源。

输入限制：请求不超过 64 KiB；短片最多 10 分钟；单图不超过 3.5 MB；时间戳必须在视频范围内且不重复；图片格式和文件头必须一致。不接受任意 HTTP URL。该示例没有实现最终业务身份系统或官方数据适配器。

## 本地检查

在本目录执行 `python3 -m unittest -v test_main.py`。测试只使用假 S3/Bedrock 客户端，其中本地 HTTP 测试覆盖 `/ping`、错误输入和成功响应。**离线通过不等于真实云模型调用通过**；后者须由主流程记录 Runtime、Web前端、请求和结果证据。

## 打包

优先在独立环境安装 [requirements.txt](requirements.txt)，再执行：

```sh
python build_package.py ../artifacts/agent.zip
```

打包器只读取已安装的 boto3 及其纯 Python 依赖，加入 `main.py`；不安装依赖、不上传、不部署、不读取 AWS 配置。Runtime 使用 `PYTHON_3_12`、入口 `['main.py']`，设置上述环境变量。正式资源仍须由主流程的 CDK 定义，不能直接重跑历史测试创建请求。

Web 客户端由后端代理调用 Runtime；浏览器不保存 AWS 凭证。单次模型读超时 120 秒，客户端/代理应采用相应超时或异步任务状态，不能以短 API 等待时间判断模型已经失败。
