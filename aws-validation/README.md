# Team02 AWS 服务验证工程（历史归档）

本目录用于 2026-10-05 夜间至 10-06 的一次真实服务验证。结果见 [服务实际验证报告](../docs/archive/competition-2026/AWS-Team02-服务实际验证报告.md)，总体任务见 [AI 接手说明](../AI接手说明.md)。

**测试已结束，临时资源已清理。本目录不是正式参赛应用，也没有当前可用的测试网页。** 原请求和资源名称保留作证据，不是新的运行指令。

## 实际验证范围

通过带指定权限边界的 CDK 工程部署 S3、CloudFront、DynamoDB、Lambda 和日志资源；验证网页访问及 Lambda 内实际读写；调用两个白名单模型的文本与图片能力；发布 AgentCore Runtime 并由其调用 Claude；通过 SageMaker `ml.g4dn.xlarge` Training 执行 T4 CUDA 运算。GPU 任务 Completed，计费 199 秒，计算实例随后释放。

没有覆盖正式篮球应用、真实视频、并发负载、其他全部 AWS 服务或所有 GPU 尺寸。SageMaker 配额查询与实际启动测试是不同证据。

## 文件索引

|文件|作用|
|---|---|
|[app.js](app.js)、[cdk.json](cdk.json)|临时 CDK 栈与权限边界配置；资源目标账号及区域固定|
|[package.json](package.json)、[package-lock.json](package-lock.json)|本地 CDK 版本和依赖锁定|
|[index.html](index.html)|仅用于公网访问验证的测试页面|
|[prepare.py](prepare.py)|查找已部署栈、上传页面和代码包、生成请求清单、调用两个模型的图片接口；会写入本地证据|
|[agent.py](agent.py)|AgentCore Python `/ping` 与 `/invocations` 示例，内部调用 Claude|
|[gpu_check.py](gpu_check.py)|检查 CUDA、记录 GPU 信息并执行小矩阵运算|
|[verify_live.py](verify_live.py)|调用已存在的 Lambda、CloudFront、AgentCore，保存运行结果|
|[collect_and_cleanup.py](collect_and_cleanup.py)|读取 GPU 结果，并删除清单范围内部分云端文件与日志；不是完整独立清理入口|
|[manifest.json](manifest.json)|本次历史资源清单；列出的临时资源已删除|
|[gpu-request.json](gpu-request.json)、[agent-request.json](agent-request.json)|当时的创建请求；不能直接重新提交|
|[model-tests.json](model-tests.json)|两个白名单模型对红色测试 PNG 的实际回复|
|[live-tests.json](live-tests.json)|Lambda、CloudFront、AgentCore 的实际调用结果|
|[gpu-result.json](gpu-result.json)|`GPU_CHECK_OK`、Tesla T4、CUDA/PyTorch 版本和矩阵结果|
|[gpu-job.json](gpu-job.json)|历史 SageMaker 任务描述，含 Completed 与计费秒数|
|[agent-delete.json](agent-delete.json)|当时 AgentCore 删除操作返回记录；最终不存在性另见清理结果|
|[cleanup.json](cleanup.json)|完成清理后的汇总核验，包含栈及各资源删除结果|
|[SageMaker-实际GPU配额.md](SageMaker-实际GPU配额.md)|便于阅读的 32 个尺寸、各用途配额表|
|[sagemaker-quotas.json](sagemaker-quotas.json)、[sagemaker-quota-matrix.json](sagemaker-quota-matrix.json)|配额原始查询与归一化结果|

`outputs.json`、`agent.zip`、`source.tar.gz` 和本地依赖目录是可再生成产物，已排除上传。不要依赖它们在新机器存在。

## 历史执行顺序及清理边界

当时依次完成身份核对、CDK 合成与部署、上传测试包、模型调用、创建并调用 AgentCore、启动 GPU 任务、收集结果、停止会话并删除 Runtime、清理自己的对象与日志、销毁测试栈，再逐项核实资源不存在并删除本次发布的 bootstrap 模板。

这个流程由脚本和外部 CLI 操作共同完成；本目录没有一个可以安全重放全部步骤的一键入口。`collect_and_cleanup.py` 在执行时还依赖测试栈和桶存在，且不会自己完成所有 CDK 销毁步骤。最终核验结果不是声称单个脚本独立完成全部清理。

保留了主办方 `CDKToolkit`、预置 `NBAHackathonWorkloadRole` 以及共享资源。Completed GPU 任务保留历史元数据，不代表实例运行；旧 CloudFront 分发及测试 URL 已失效。

## 需要复用或复测时

先阅读 [CDK 与 GPU 约束](../docs/archive/competition-2026/BroadcastCode-CDK与GPU部署约束.md)，使用 `nba`、`us-east-1`，核对实际身份；不执行 bootstrap。正式项目可以借鉴 `cdk.json` 中的边界配置和最小服务示例，但应根据实际应用重新设计。

若仅需安装本地 JS 依赖，可在本目录使用 `npm ci`；这一步本身不部署资源。Python 环境需要另行建立并安装 boto3，原 `.venv` 不可跨机器直接复用。

确需重新进行计费或资源操作时，应按当前用户授权和测试目标创建新的工作目录或独立清单，使用新的栈、任务、Runtime 名称及幂等标识。旧名称固定包含 `20261005`，SageMaker 历史任务名不能重新使用；原脚本还会覆写结果文件。保留原始证据，明确本次创建的资源和清理范围，再根据新状态运行所需步骤。

不要因为看到归档中的 bucket、ARN、session 或 URL 就尝试调用或删除它们。当前资源状态如需确认，应重新只读查询，历史记录不能替代当前查询。
