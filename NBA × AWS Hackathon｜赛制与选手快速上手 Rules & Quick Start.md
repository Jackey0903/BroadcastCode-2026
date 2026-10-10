# NBA × AWS Hackathon｜赛制与选手快速上手 Rules \& Quick Start

中文 English

# 中文

赛题：做一个 AI Agent，输入 NBA 深度赛场数据 \+ 一段真实比赛视频，输出**带数据可视化的比赛画面**，并通过 Web 界面对外呈现。一句话——数据进去，能看的作品出来。

## 一、硬性要求

以下是准入条件。三项技术要求必须全部满足，缺一项会直接影响最终成绩，请在开工前先确认技术路径能走通。

|\#|要求|什么情况不算满足|
|---|---|---|
|1|必须使用 **Amazon Bedrock AgentCore** 承载智能体能力|智能体逻辑跑在本地进程，或只是一段调用大模型的循环|
|2|必须以 **Amazon CloudFront** 作为对外发布形式，且作品必须具备 **Web 交互界面**|命令行工具、Notebook、录屏视频、纯 API|
|3|必须使用 **AWS CDK** 定义基础设施|控制台手工点出来的资源、只有一串 aws CLI 命令的脚本；Terraform / SAM / 裸 CloudFormation 也不能替代|

还有一条环境约束：**全部资源部署在赛事分配账号的 ****`us-east-1`**** 区域**。账号已预置区域护栏，在其他区域的操作会被直接拒绝。

## 二、时间与提交

- **比赛时长 12 小时**，以组委会公布的开始与截止时刻为准。

- **提交次数不限。**比赛结束前，可以在参赛者门户「Submit your entry」里反复提交 CloudFront URL，每次提交覆盖上一次。建议一有可访问的链接就先提交一次，之后随时覆盖。（为防误触，两次提交之间需间隔 1 分钟。）

- **截止时刻：北京时间 2026/10/10 20:00。**在此之前提交的最后一次 CloudFront URL 即为最终评分作品；该时刻之后提交按钮灰掉，无法再提交或修改。

- 请在截止前**确认提交的链接可正常访问**——评分以提交的那个链接为准，不会另行向队伍索取。

## 三、评分办法

- **AWS 原生托管服务的权重显著高于自建方案。**把开源组件搬到 EC2 上跑起来，和用对应的托管服务把同一件事做成，得分不在一个量级。托管、无服务器、事件驱动、基础设施即代码，都是我们鼓励的。

- **同一个 AWS 服务，用得深和浅不是一个分数。**用得更专业、更有效的，明显会得到更多技术分。

- 机器评分看工程链路和 AWS 用得好不好，靠你们的代码仓库重跑；人工评分看画面讲得动不动人、数据准不准，靠提交的 CloudFront 链接。

## 四、Portal 账号给了你什么

登录赛事 Portal 后，你会拿到三样东西，它们是一条流水线：

|拿到的东西|作用|
|---|---|
|**GitHub 仓库**（已锁定，不能换）|放你的 Agent 代码和 CDK。主办方从这里统一拉代码跑机器评分|
|**AWS 账号**（SSO 登录）|你的 Agent 运行在这里，所有算力、模型、存储都在这个账号内|
|**AWS CLI 双 profile**|你本地 / 开发机 / AI 编程工具操作这个账号的通道|

三者关系：**代码在 GitHub，运行在 AWS，操作靠 CLI。**

## 五、比赛流程和 AWS 服务的对应关系

```plaintext
① 官方给数据 + 视频  ──►  存进你的 S3 桶
② 你的 Agent（Bedrock AgentCore 承载）读取它们
③ 调 Bedrock 模型：识别画面、理解战术、生成解说
④ 用 ffmpeg 把数据可视化叠进视频，输出成品
⑤ 成品 + Web 界面经 CloudFront 对外发布
⑥ 提交 CloudFront URL：评委点开看（人工评分）；主办方拉代码重跑（机器评分）
⑦ 以上资源全部由 AWS CDK 定义和部署
```

对应的服务分工：

|环节|用什么|说明|
|---|---|---|
|承载智能体|**Bedrock AgentCore**|硬性要求，智能体能力必须跑在这里|
|存数据 / 存成品|**S3**|每队一个专属桶，已预置|
|看懂画面、生成解说|**Bedrock**|视觉模型识别球员、理解回合；文本模型写解说|
|语音解说（可选）|**Polly**|解说文本转配音|
|叠加渲染|**ffmpeg**|把球员名、指标、箭头画进视频|
|对外交付|**CloudFront**|硬性要求，Web 界面和成品都经它出公网链接|
|基础设施|**AWS CDK**|硬性要求，上面所有资源都要由 CDK 定义|

## 六、账号里能用哪些服务

赛题需要的全部可用。重点：

- **智能体 / AI**：Bedrock AgentCore、Bedrock、Rekognition、Transcribe、Polly、Translate

- **计算**：Lambda、ECS、Batch、EC2

- **媒体**：MediaConvert、MediaLive

- **存储 / 交付**：S3、CloudFront、DynamoDB

- **编排**：Step Functions、SQS、SNS、EventBridge

**已实测可用的 2 个 Bedrock 模型**（足够支撑赛题使用）：

- Claude Sonnet 4\.6 — Model ID：`global.anthropic.claude-sonnet-4-6`

- Qwen3 VL 235B A22B — Model ID：`qwen.qwen3-vl-235b-a22b`

Portal 里的 aws service 目录中提供了对应源码范例。

**两个限制先知道：**

1. **只能用 ****`us-east-1`**** 区域**，切别的区会报权限错，且错得像「空账号」。

2. **EC2 GPU 机型配额为 0**，不能直接开 GPU 实例。要用 GPU 需通过 **SageMaker** 申请，支持的机型为 `g4dn`、`g5`、`g6`、部分 `g6e`；可开机数量为 1、2 或 4，具体取决于当时的资源情况，不能保证。

## 七、装 AWS CLI

**必须是 v2。**

**macOS：**

```bash
curl -fsSL "https://awscli.amazonaws.com/AWSCLIV2.pkg" -o /tmp/AWSCLIV2.pkg
sudo installer -pkg /tmp/AWSCLIV2.pkg -target /
aws --version   # 确认是 aws-cli/2.x
```

**Linux：**

```bash
curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o awscliv2.zip
unzip -q awscliv2.zip && sudo ./aws/install
```

**配置**（把 Portal 里的两段 profile 原样写进 `~/.aws/config`）：

```ini
[profile nba-sso]
sso_start_url = https://d-92674d9b56.awsapps.com/start
sso_region = us-west-2
sso_account_id = YOUR_SSO_ACCOUNT_ID
sso_role_name = NBAHackathon-TeamNN
region = us-east-1
output = json

[profile nba]
role_arn = arn:aws:iam::YOUR_WORKLOAD_ACCOUNT_ID:role/NBAHackathonParticipantRole
source_profile = nba-sso
region = us-east-1
output = json
```

> ⚠️ `sso_account_id`、`sso_role_name`、`role_arn` 里的账号 ID **因队伍而异**，必须从你自己的 Portal 页面复制。profile 名称（`nba-sso` / `nba`）、`sso_start_url`、`sso_region`、`region` 所有人一致。
>
>

**登录并验证：**

```bash
aws sso login --profile nba-sso                              # 弹浏览器授权，12 小时有效
aws sts get-caller-identity --profile nba --region us-east-1 # 必须出现 NBAHackathonParticipantRole
```

> Arn 里出现 `AWSReservedSSO` = 用错了 profile，日常一律用 `--profile nba`。
>
>

**用 CDK（云开发工具包）自动化部署：**

为便于参赛队用 CDK 做自动化部署，主办方已提前完成 CDK bootstrap（us\-east\-1）。**请不要执行 ****`cdk bootstrap`**，执行会失败，也不需要，直接用 `cdk deploy` 部署即可。

**唯一的要求：**在项目的 `cdk.json` 里加上下面这段配置。CDK 会自动给你的 Lambda、ECS 等创建的 IAM 角色加上权限边界；不加的话，凡是创建 IAM 角色的部署都会失败（报 `iam:CreateRole AccessDenied`）。

```json
{
  "context": {
    "@aws-cdk/core:permissionsBoundary": { "name": "NBAHackathonParticipantBoundary" }
  }
}
```

**其他注意事项：**

- 资源只能部署在 us\-east\-1。

- 用 SSO 登录拿到的凭证执行 CDK（即上面的 `--profile nba`，例如 `cdk deploy --profile nba`）。

- 如果不是很理解，可以把上面的描述交给你的 AI Coding Agent。

## 八、用好 AI Coding 工具

我们鼓励并建议全程使用 AI coding 工具（Kiro、Claude Code、Cursor）来写代码、写 CDK、查 AWS 文档、排查报错。这不是「取巧」，在 12 小时的赛制下，它就是正常且必要的工程手段。

几条能立刻见效的用法：

- **让它写 CDK。**基础设施代码模式化程度高、样板多，正是 AI 最擅长的部分，也最容易被人工手写拖慢。

- **把 AWS profile 直接交给它用。**配好 profile 之后（`nba-sso` 登录，`nba` 日常操作），可以直接说「使用 AWS profile nba，在 us\-east\-1 为我创建一个 EC2」这类指令，让它代为执行 CLI 和部署操作。**记得每次都点明用哪个 profile**——不说的话它会去用默认 profile，可能根本不是你们的赛事账号。

- **让它读报错。**AWS 的权限、区域、配额类报错往往很长且不直观，贴给 AI 通常比自己翻文档快得多。

**下载 Kiro：**[https://kiro\.dev](https://kiro.dev)。配好 AWS CLI 后它能直接帮你建资源、写 Agent、调 Bedrock、跑 ffmpeg，全程对话完成。

标准说法举例：

> 「用 AWS profile nba、区域 us\-east\-1，帮我在 S3 桶里列出所有文件。」
>
>

> 「用 profile nba（us\-east\-1），写一套 CDK：把 Bedrock AgentCore、S3、CloudFront 和一个静态 Web 前端一起部署出来。」
>
>

**模型调用有两种，别混淆——**用 AI 工具帮你**写代码**不占比赛账号额度；Agent 代码里**运行时调 Bedrock** 花的是比赛账号额度，调试用便宜模型（Haiku / Nova Lite），跑通再换 Sonnet。

## 九、最容易踩的坑

|现象|原因|解决|
|---|---|---|
|Arn 显示 `AWSReservedSSO`|用了 `nba-sso`|改用 `--profile nba`|
|命令报权限错，像空账号|区域不对|所有命令带 `--region us-east-1`|
|调 Claude 报 ValidationException|缺前缀|模型 ID 前加 `us.`（如 `us.anthropic.claude-sonnet-4-5-...`）|
|开 GPU 实例失败|配额为 0|改用 CPU 机型（c7i / m7i / t3）|
|操作突然全部失败|SSO 12 小时过期|重跑 `aws sso login --profile nba-sso`|
|AI 工具操作 AWS 失败|没指定 profile|提示里明确写「用 profile nba，us\-east\-1」|

## 十、赛前准备与开工顺序

本届对 AWS 服务使用的要求比较高，建议赛前多加练习。我们会在比赛前预留 **2～3 天练习时间**，请在这期间就把环境和 AI 工具（登录、profile、权限）配好，比赛当天直接进入产出状态。

赛前清单：

1. 装好 AWS CLI v2，配 profile，`get-caller-identity` 验证通过

2. 装好 AI coding 工具，确认它能用 `profile nba` 操作你的账号

3. 用 CDK 部署一次最小栈：S3 \+ CloudFront \+ 一个静态页面，确认链接能公网打开

4. 跑通 Bedrock AgentCore 的最小 Agent，确认能被 Web 前端调用

5. 用练习视频跑通最小闭环：**下载视频 → 叠一行字 → 传回 S3 → 页面上能播**

12 小时不长。三项硬性要求（AgentCore、CloudFront、CDK）建议在**前两小时内先打通最小闭环**再谈创意——它们恰好可以由同一套 CDK 模板一次带出来，我们会在参赛指南里提供可直接部署的版本，把这部分压缩到半小时量级。剩下的时间，用来做那个只有你们能想出来的东西。

# English

The challenge: build an AI Agent that takes in\-depth NBA game data plus a real game video clip and produces **game footage with data visualizations baked in**, delivered through a web interface\. In one line: data goes in, a watchable product comes out\.

## 1\. Hard requirements

These are entry conditions\. All three technical requirements must be met — missing any one directly affects your final score\. Confirm the technical path works before you start building\.

|\#|Requirement|What does not count|
|---|---|---|
|1|Agent capability must run on **Amazon Bedrock AgentCore**|Agent logic in a local process, or just a loop that calls an LLM|
|2|Delivery must go through **Amazon CloudFront**, and the entry must have a **web interface**|CLI tools, notebooks, screen recordings, API\-only submissions|
|3|Infrastructure must be defined with **AWS CDK**|Resources clicked together in the console, or a pile of aws CLI commands; Terraform / SAM / raw CloudFormation are not substitutes|

One more environment constraint: **all resources must be deployed in ****`us-east-1`**** in your assigned contest account\.** A region guardrail is already in place — operations in other regions are rejected outright\.

## 2\. Timeline and submission

- **The contest runs 12 hours**, with the official start and cutoff announced by the organizing committee\.

- **Unlimited submissions\.** Until the contest ends you can submit your CloudFront URL repeatedly under "Submit your entry" in the participant portal; each submission replaces the previous one\. Submit as soon as you have a reachable link, then overwrite it as you improve\. \(To prevent accidental clicks, submissions are 1 minute apart\.\)

- **Cutoff: 2026/10/10 20:00 Beijing time\.** The last CloudFront URL submitted before then is the entry that gets scored; after that moment the submit button is greyed out and no further changes are possible\.

- **Verify your submitted link is reachable** before the cutoff — scoring uses exactly that link, and we will not ask teams for a replacement\.

## 3\. How you're scored

- **AWS native managed services weigh significantly more than self\-hosted setups\.** Running an open\-source component on EC2 and achieving the same thing with the corresponding managed service are not in the same scoring bracket\. Managed, serverless, event\-driven, infrastructure\-as\-code — all encouraged\.

- **Shallow and deep use of the same AWS service do not score the same\.** More professional, more effective use earns visibly more technical points\.

- Machine scoring looks at the engineering pipeline and how well you use AWS, re\-run from your repository; human scoring looks at how compelling the footage is and how accurate the data is, based on the submitted CloudFront link\.

## 4\. What your Portal account gives you

After signing in to the event Portal you get three things, and they form one pipeline:

|What you get|What it's for|
|---|---|
|**GitHub repo** \(locked, cannot be swapped\)|Holds your Agent code and CDK\. Organizers pull from here for machine scoring|
|**AWS account** \(SSO sign\-in\)|Where your Agent runs\. All compute, models, and storage live in this account|
|**Two AWS CLI profiles**|How your laptop / dev box / AI coding tool talks to that account|

The relationship: **code lives in GitHub, runs on AWS, is operated through the CLI\.**

## 5\. How the contest flow maps to AWS services

```plaintext
① Official data + video      ──►  land in your S3 bucket
② Your Agent (hosted on Bedrock AgentCore) reads them
③ Call Bedrock models: recognize the footage, read the play, generate commentary
④ Use ffmpeg to overlay the visualizations and render the output
⑤ Publish the output plus your web interface through CloudFront
⑥ Submit the CloudFront URL: judges open it (human scoring); organizers re-run your code (machine scoring)
⑦ Every resource above is defined and deployed with AWS CDK
```

Which service does what:

|Step|Service|Notes|
|---|---|---|
|Host the agent|**Bedrock AgentCore**|Hard requirement — agent capability must run here|
|Store data / store output|**S3**|One dedicated bucket per team, pre\-provisioned|
|Understand footage, write commentary|**Bedrock**|Vision models identify players and read possessions; text models write the commentary|
|Voice\-over \(optional\)|**Polly**|Turn commentary text into audio|
|Overlay and render|**ffmpeg**|Draw player names, metrics, and arrows into the video|
|Deliver the entry|**CloudFront**|Hard requirement — the web interface and the output are served through it|
|Infrastructure|**AWS CDK**|Hard requirement — everything above must be defined in CDK|

## 6\. Which services are available in the account

Everything the challenge needs is available\. The highlights:

- **Agent / AI**: Bedrock AgentCore, Bedrock, Rekognition, Transcribe, Polly, Translate

- **Compute**: Lambda, ECS, Batch, EC2

- **Media**: MediaConvert, MediaLive

- **Storage / delivery**: S3, CloudFront, DynamoDB

- **Orchestration**: Step Functions, SQS, SNS, EventBridge

**2 Bedrock models verified to work** \(sufficient for this challenge\):

- Claude Sonnet 4\.6 — Model ID: `global.anthropic.claude-sonnet-4-6`

- Qwen3 VL 235B A22B — Model ID: `qwen.qwen3-vl-235b-a22b`

Sample source code for both is available under "aws service" in the Portal\.

**Two limits to know up front:**

1. **`us-east-1`**** only\.** Any other region returns permission errors, and the errors look like the account is empty rather than like a wrong\-region problem\.

2. **EC2 GPU instance quota is 0** — you cannot launch a GPU instance directly\. To use a GPU, request one through **SageMaker**, which supports `g4dn`, `g5`, `g6`, and some `g6e` instance types\. The number of instances you can start \(1, 2, or 4\) depends on availability at the time and is not guaranteed\.

## 7\. Install the AWS CLI

**It must be v2\.**

**macOS:**

```bash
curl -fsSL "https://awscli.amazonaws.com/AWSCLIV2.pkg" -o /tmp/AWSCLIV2.pkg
sudo installer -pkg /tmp/AWSCLIV2.pkg -target /
aws --version   # confirm aws-cli/2.x
```

**Linux:**

```bash
curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o awscliv2.zip
unzip -q awscliv2.zip && sudo ./aws/install
```

**Configure** \(copy the two profiles from your Portal into `~/.aws/config` as\-is\):

```ini
[profile nba-sso]
sso_start_url = https://d-92674d9b56.awsapps.com/start
sso_region = us-west-2
sso_account_id = YOUR_SSO_ACCOUNT_ID
sso_role_name = NBAHackathon-TeamNN
region = us-east-1
output = json

[profile nba]
role_arn = arn:aws:iam::YOUR_WORKLOAD_ACCOUNT_ID:role/NBAHackathonParticipantRole
source_profile = nba-sso
region = us-east-1
output = json
```

> ⚠️ `sso_account_id`, `sso_role_name`, and the account ID inside `role_arn` **differ per team** — copy them from your own Portal page\. The profile names \(`nba-sso` / `nba`\), `sso_start_url`, `sso_region`, and `region` are the same for everyone\.
>
>

**Sign in and verify:**

```bash
aws sso login --profile nba-sso                              # opens a browser, valid for 12 hours
aws sts get-caller-identity --profile nba --region us-east-1 # must show NBAHackathonParticipantRole
```

> If the Arn contains `AWSReservedSSO`, you used the wrong profile\. For day\-to\-day work always use `--profile nba`\.
>
>

**Automated deployment with the AWS CDK \(Cloud Development Kit\):**

To make CDK deployments easier, the organizers have already run CDK bootstrap in us\-east\-1\. **Do not run ****`cdk bootstrap`** — it will fail, and you don't need it\. Just deploy with `cdk deploy`\.

**The only requirement:** add the following to your project's `cdk.json`\. CDK will then automatically attach a permissions boundary to the IAM roles it creates for your Lambda, ECS, etc\. Without it, any deployment that creates an IAM role will fail with `iam:CreateRole AccessDenied`\.

```json
{
  "context": {
    "@aws-cdk/core:permissionsBoundary": { "name": "NBAHackathonParticipantBoundary" }
  }
}
```

**Other notes:**

- Resources can only be deployed in us\-east\-1\.

- Run CDK with the credentials from your SSO sign\-in \(i\.e\. the `--profile nba` above, e\.g\. `cdk deploy --profile nba`\)\.

- If any of this is unclear, hand the description above to your AI coding agent\.

## 8\. Make the most of AI coding tools

We encourage using AI coding tools \(Kiro, Claude Code, Cursor\) throughout — to write code, write CDK, look up AWS docs, and debug errors\. This is not a shortcut; under a 12\-hour format it is normal and necessary engineering practice\.

Three things that pay off immediately:

- **Let it write the CDK\.** Infrastructure code is highly patterned and boilerplate\-heavy — exactly where AI is strongest, and exactly where hand\-writing slows you down\.

- **Hand it your AWS profile\.** Once your profiles are configured \(`nba-sso` to sign in, `nba` for daily work\), you can say things like "using AWS profile nba, create an EC2 instance for me in us\-east\-1" and let it run the CLI and deployments for you\. **State the profile every time** — otherwise it falls back to the default profile, which may not be your contest account at all\.

- **Let it read the errors\.** AWS permission, region, and quota errors are long and unintuitive; pasting them into an AI tool is usually faster than reading docs\.

**Download Kiro:** [https://kiro\.dev](https://kiro.dev)\. With the AWS CLI configured it can create resources, write the Agent, call Bedrock, and run ffmpeg for you, all through conversation\.

Prompts that work:

> "Using AWS profile nba in region us\-east\-1, list all files in my S3 bucket\."
>
>

> "Using profile nba \(us\-east\-1\), write a CDK stack that deploys Bedrock AgentCore, S3, CloudFront, and a static web frontend together\."
>
>

**Two different kinds of model calls — don't mix them up\.** Using an AI tool **to write code** does not consume your contest account budget\. Your Agent calling Bedrock **at runtime** does — debug with cheap models \(Haiku / Nova Lite\) and switch to Sonnet once the pipeline works\.

## 9\. Most common pitfalls

|Symptom|Cause|Fix|
|---|---|---|
|Arn shows `AWSReservedSSO`|Used `nba-sso`|Switch to `--profile nba`|
|Permission errors, account looks empty|Wrong region|Add `--region us-east-1` to every command|
|Claude call returns ValidationException|Missing prefix|Prefix the model ID with `us.` \(e\.g\. `us.anthropic.claude-sonnet-4-5-...`\)|
|GPU instance launch fails|Quota is 0|Use CPU instances \(c7i / m7i / t3\)|
|Everything suddenly fails|SSO session expired after 12 hours|Re\-run `aws sso login --profile nba-sso`|
|AI tool can't operate AWS|No profile specified|Say explicitly "use profile nba, us\-east\-1" in the prompt|

## 10\. Before the contest, and where to start

This edition demands more from your AWS skills, so practise beforehand\. We reserve **2–3 practice days** before the contest — use them to get your environment and AI tools \(sign\-in, profiles, permissions\) ready so you can go straight to producing on the day\.

Pre\-contest checklist:

1. Install AWS CLI v2, configure the profiles, confirm `get-caller-identity` passes

2. Install your AI coding tool and confirm it can operate your account with `profile nba`

3. Deploy a minimal CDK stack once: S3 \+ CloudFront \+ a static page, and confirm the link opens publicly

4. Get a minimal Bedrock AgentCore agent running and callable from your web frontend

5. Close the smallest loop with a practice video: **download the video → overlay one line of text → upload back to S3 → play it on the page**

12 hours is not long\. Get the minimal loop through all three hard requirements \(AgentCore, CloudFront, CDK\) working **in the first two hours** before chasing creative ideas — one CDK template can bring all three up at once, and we will publish a deployable version in the participant guide to shrink this to roughly half an hour\. Spend the rest of your time on the thing only your team would think of\.
