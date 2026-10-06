# 赛前连通测试前端

原生 HTML、CSS、JavaScript，无构建或外部依赖。发布 `index.html`、`styles.css`、`app.js` 到静态站点；CloudFront 将同域 `/api/*` 转发到后端，API 响应应禁止缓存。页面不会访问 AWS 凭证，也不会直接调用 AWS SDK。

## 接口

- `GET /api/status`：返回 JSON 对象即表明入口已响应；`ready:false` 或 `status:failed/error/offline/unavailable` 将禁用提交。可选展示字段：`region`、`modelId`、`runtimeStatus`、`message`、`environment`（字符串或环境对象）。可选 `samples:["flagg","amen"]`，或 `[{id:"flagg",available:true}, ...]`；提供列表时，未列入或不可用的样片将禁用。不要用模型目录存在来代替实际就绪结论。
- `POST /api/jobs`，JSON 请求 `{"sample":"flagg"}` 或 `{"sample":"amen"}`。响应必需 `{"jobId":"...","status":"queued"}`，可选 `runId`。前端不会自动重试 POST；同一任务进行中禁止再次提交。
- `GET /api/jobs/{jobId}`，返回 `status`、可选 `stage`、`runId`、`error`、`videoUrl`、`analysis`、`runtimeArn`、`evidence`。状态支持大小写；完成建议 `completed`，失败建议 `failed`，其余按处理中查询。`stage` 按服务原文显示，不推算百分比。

推荐结果形状：

```json
{
  "jobId": "example-job",
  "runId": "example-runtime-session",
  "status": "completed",
  "stage": "成片已上传",
  "videoUrl": "https://YOUR_DISTRIBUTION/output/example-job.mp4",
  "runtimeArn": "本次实际 Runtime ARN",
  "preservesSourceTimeline": true,
  "analysis": {
    "summary": "本次模型实际返回的摘要",
    "observations": [
      {"text": "本次模型实际返回的观察", "timeSeconds": 16.5, "source": "frame-16.50.jpg"}
    ]
  },
  "evidence": [
    {"timeSeconds": 16.5, "description": "本次来源帧说明", "frameUrl": "https://YOUR_DISTRIBUTION/frames/example-job/16.50.jpg"}
  ]
}
```

以上是接口示意，不是已运行结果。`analysis` 也可直接返回字符串；未识别结构保留 JSON 显示。证据时间支持 `timeSeconds`、`timestampSeconds`、`sourceTimeSeconds`、`time_seconds`、`timestamp_seconds`、`timestamp_sec`、`time_sec`、`timestamp`、`time`，其中后两项也可为 `mm:ss.ss`。来源图支持 `frameUrl`、`imageUrl`、`url` 与对应 snake_case。建议使用推荐形状，避免字段歧义。

证据跳转仅在单帧明确提供 `outputTimeSeconds`，或任务明确返回 `preservesSourceTimeline:true` 时开放；页面不会假定成片与原片时轴相同。前端只显示服务返回的分析和证据，不预填篮球结论。Runtime ARN 等完整结果可在“本次任务原始响应”复核。无 `runId` 时明确标注使用 Job ID。

每 3 秒查询；连续请求失败按 6/12/24 秒间隔重试 3 次，再暂停查询。自动查询最多持续 30 分钟，之后用户可继续查询同一任务。轮询失败保留编号并禁止重复启动，不能误写成任务本身失败。URL 的 `?job=` 和同一标签页的 sessionStorage 用于刷新后恢复只读查询。提交响应不明确时，不自动重试，并提示核对后台任务。

所有后端文本用 `textContent` 展示；媒体链接仅接受 HTTP(S)，不执行后端 HTML。原生视频控件提供播放、音量与全屏；“打开 MP4”可独立验证文件。此页面没有官方深度指标，也不宣称已完成正式篮球产品。

## 本地检查

`node --check app.js` 检查语法。静态预览可从本目录启动普通 HTTP 静态服务；没有 `/api/status` 时入口应明确显示未连接并禁用启动按钮。真实成功验收需要后端和 CloudFront 接通后，以一次实际任务检查返回内容及完整 MP4。
