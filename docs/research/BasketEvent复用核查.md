# BasketEvent / PlayNet 复用核查

核查日期：2026-10-06。用途：判断 Rao 学长参与的研究怎样帮助 [关键一拍方案](../关键一拍-冲冠产品与技术方案.md)。本轮只读公开页面、仓库元数据和小型文本文件；没有下载权重或视频数据集，没有安装或运行其代码，没有部署云资源。

## 结论

**公开代码、推理入口、PlayNet checkpoint 和标注数据都真实存在，值得做有时间上限的复用验证。它目前不能直接替代我们的完整篮球 Agent，也不能照 README 在本队 T4 上保证一次运行成功。** 最有价值的潜在角色是“提供球员级宏观事件候选与粗时间证据”，再由赛事数据、连续画面与 Agent 核验，最终交给我们自己的叙事和渲染系统。

最先向学长核准三件事：代码/权重/标注的使用许可；与公开 checkpoint 对应的可运行单卡版本和时间定位导出方式；训练比赛清单。公开训练片段可能与研究数据存在比赛重合，不能把样片跑通自动宣传为全新比赛泛化。

## 1. 公开资产核查

GitHub 核查快照为 `2154ec110d799891c843bd5af16eea280bdbaf4a`，HF 数据仓库快照为 `85aaa3ce62bc096e3995c39ecfa6773fcc9fe5e1`。后续若作者更新，按新提交重新检查。

|资产|核查结果|实际意义|
|---|---|---|
|[论文项目页](https://zhangyu2003.github.io/BasketEvent/)|列作者 Yu Zhang、Jiayuan Rao、Haoning Wu、Weidi Xie，标注 BMVC 2026|能确认研究关联；不是部署包|
|[GitHub 主仓库](https://github.com/zhangyu2003/BasketEvent)|有 `track_one_video.py`、`recognize.py`、`inference.py`、`train.py`、`src/model.py`、`src/dataset.py` 和 SAM3 子模块|有实际研究实现，不是只有宣传页|
|[单视频推理入口](https://github.com/zhangyu2003/BasketEvent/blob/2154ec110d799891c843bd5af16eea280bdbaf4a/inference.py)|要求视频、清理后的框序列 JSON 和 checkpoint|不是“给任意 MP4 就完整自动得到姓名+精确时刻”的单文件入口|
|[HF 数据与 checkpoint](https://huggingface.co/datasets/zaywas/BasketEvent/tree/main)|`playnet.pt` 约 1.81 GB；有 `train/test/valid`；API 返回 35,490 个文件条目|checkpoint 公开存在，但本轮未下载、未验证它与当前代码完全匹配|
|HF 资源类型|API 文件后缀只有 JSON、PT 和 `.gitattributes`|当前 HF 仓库不是完整视频数据集的可直接下载镜像；标注不能替代原视频|
|[GitHub 示例目录](https://github.com/zhangyu2003/BasketEvent/tree/2154ec110d799891c843bd5af16eea280bdbaf4a/examples)|有一条示例 MP4、原始/清理 JSON、名单、时间标注 CSV|有可用于环境复现的小例子；本轮未下载视频|
|[时间标注 CSV](https://github.com/zhangyu2003/BasketEvent/blob/2154ec110d799891c843bd5af16eea280bdbaf4a/examples/event_time_labels.csv)|实际 998 条，列为比赛、视频、人物 ID、起止时间|与论文 v1 的约 1,000 样本描述有细微差异，应引用实际文件或注明版本|
|评测脚本|README 提到 `test.py`，当前完整 Git 树里没有该文件；release 列表为空|时间指标复现流程还缺一部分，不能宣称已经完整复现|
|代码许可|完整 Git 树没有仓库级 `LICENSE`；GitHub API `license=null`|不能把“公开可读”记成“已核准赛事复制/分发许可”|
|数据/PlayNet 权重许可|HF 无 dataset card，`cardData=null`，未提供 license 元数据|需要作者补充明确许可与数据使用范围|

项目网页页脚的 CC BY-SA 4.0 是网站许可；arXiv 的 CC BY 4.0 是论文许可。**二者都不能直接替代仓库代码、NBA 视频、数据标注和 PlayNet 权重各自的许可。** SAM3 和 Qwen 的上游许可也需分别遵循，不能由 BasketEvent 网页统一覆盖。

元数据可复核入口：[GitHub 仓库 API](https://api.github.com/repos/zhangyu2003/BasketEvent)、[完整文件树](https://api.github.com/repos/zhangyu2003/BasketEvent/git/trees/2154ec110d799891c843bd5af16eea280bdbaf4a?recursive=1)、[HF 数据仓库 API](https://huggingface.co/api/datasets/zaywas/BasketEvent)。

本轮还只读核查了一个约 155 KB 的 [HF 测试标注 JSON](https://huggingface.co/datasets/zaywas/BasketEvent/blob/85aaa3ce62bc096e3995c39ecfa6773fcc9fe5e1/test/0022500003/02336878-36b3-dd51-66e6-88d8103bbd1e_1280x720.json)：包含球员号码、队服色、姓名、事件记录，以及 260 帧的球员/球框序列。它证实标注文件有实际内容，但不能据一条文件确认全部标注质量，也没有下载其对应比赛视频。

## 2. 它能识别什么、依赖什么

公开代码的分类空间是 10 类宏观事件加背景：投篮未中、投篮命中、罚球、犯规、失误、跳球、篮板、抢断、盖帽、助攻，以及 `blank`。代码实际字符串包括 `steal`、`block`、`ast`，适配器需要统一命名。[类别定义](https://github.com/zhangyu2003/BasketEvent/blob/2154ec110d799891c843bd5af16eea280bdbaf4a/src/dataset.py#L26)

**没有掩护、假投、切入、协防、突破节奏、空位形成等直接输出类别。** 因而它可能帮助锁定我们的投篮/助攻候选，却不能独立生成“为什么形成这次出手”的战术故事。`Foul` 也不能在赛事作品里变成自主判罚模块。

公开处理链：SAM3 获得球员和篮球的图像框序列 → Qwen2.5-VL 清除裁判/观众等错误对象、挑选球、结合比赛名单识别球衣色与号码 → TimeSformer 事件模型读取视频和这些框，输出球员级类别。名单 JSON 需要球队、队服颜色、号码与姓名，当前身份前处理明确读取它。[身份处理源码](https://github.com/zhangyu2003/BasketEvent/blob/2154ec110d799891c843bd5af16eea280bdbaf4a/recognize.py)

事件推理入口接收已清理的 `player_N` / `ball` 框 JSON，模型不会从零提供官方球员 ID；入口最终打印的也是 `player_N` 与事件名。将匿名 ID 关联为真实姓名是上游职责。正式测试数据的轨迹与事件关联做过人工核验；论文表现不能被直接解释为我们对任意原始 1080p 视频执行全链后的身份准确率。

论文中的 `trajectory` 是逐帧图像边界框序列。若仅用它定位可见人物、提取视觉特征或让标签短时跟随，不等于重建真实球场中的运动轨迹；仍须按本赛事范围限制用途。我们不输出跑动路径、距离、速度、数字孪生，不由出手瞬间的官方点位插值出整段轨迹。[方法与输入定义](https://arxiv.org/html/2607.21267v1#S4.SS2)

## 3. 时间定位结果不能当精确出手帧

论文 v1 从每个球员最高权重的短片段读出粗时间窗；它不是直接回归精确球离手时刻。其时间重叠指标分母是两个时间段长度的较小值，**不是标准时间 IoU 的并集长度**。例如预测 `[0,20]` 秒、真值 `[9,10]` 秒时，该定义可得 1，但预测边界显然很粗。[论文评价定义](https://arxiv.org/html/2607.21267v1#S5.SS2)

版本数值存在实质差异：

|来源|事件指标|时间指标|
|---|---|---|
|[arXiv v1 表 2](https://arxiv.org/html/2607.21267v1#S5.SS4)|F1 0.682；Rec@1 0.701|Hit@0.3/0.5 为 0.424/0.380|
|[当前项目页](https://zhangyu2003.github.io/BasketEvent/)|F1 0.669；Rec@1 0.700|端到端 Hit@0.1/0.3/0.5 为 0.448/0.284/0.138；仅正确识别事件上的数值为 0.608/0.385/0.187|

网页未在正文解释它与 v1 的协议变化，仓库又未包含 README 指向的 `test.py`，所以**不把两版数值混成同一组实验，也不声称网页必然采用 v1 的同一重叠定义**。应请作者确认当前评测协议。即使仅谈当前网页的最好分类结果，也不能推导“准确定位全部动作”；尤其不能把候选窗直接当出手时间烧录到成片。

本项目验收需要另外测：人物与类别是否正确；出手等关键事件相对人工核验帧的时间误差；支持解释的窗口是否真的含有效证据。原论文指标提供研究比较，不能代替这三项应用验收。

## 4. 针对本地约 22 秒 NBA 样片的直接复用障碍

本地两段样片为 1080p、约 59.94 fps，存在切镜、移动镜头和遮挡；详情见 [公开训练样片核查](公开训练样片核查.md)。静态源码核查发现：

|问题|来源与影响|试用前应如何处理|
|---|---|---|
|推理设备硬编码 `cuda:4`|[inference.py](https://github.com/zhangyu2003/BasketEvent/blob/2154ec110d799891c843bd5af16eea280bdbaf4a/inference.py)；单张 T4 没有第 5 个设备|改成明确可配置设备，单卡使用 `cuda:0`|
|跟踪默认 GPU 编号为 6|[track_one_video.py](https://github.com/zhangyu2003/BasketEvent/blob/2154ec110d799891c843bd5af16eea280bdbaf4a/track_one_video.py)|显式配置 0，不照默认命令运行|
|默认 `fps_in=25` 且参数为整数|样片实际约 59.94 fps；采样步长与时间映射会受影响|先产生统一帧率的工作副本，视频和框必须来自同一副本，并保留映射回原视频的时间表|
|完整视频解码入内存|推理脚本为计帧和抽样可能两次完整解码；22 秒 1080p 60 fps 的原始 RGB 约 8 GB，不含其他开销|改为一次探测和稀疏解码/降采样，避免把帧全集当普通小文件|
|入口不导出时间窗|`return_weights=False`，只打印非背景人物—事件；模型内部可返回 `gate_weights`|补 JSON 输出、gate 权重与采样区间解码；候选窗再细查，不把粗窗叫精确边界|
|checkpoint 加载 `strict=False`|缺失或额外键可能不使程序立即退出|记录并核准 missing/unexpected keys；不能以“进程没报错”判断权重正确加载|
|SAM3 与身份模型是额外依赖|[requirements.txt](https://github.com/zhangyu2003/BasketEvent/blob/2154ec110d799891c843bd5af16eea280bdbaf4a/requirements.txt) 固定 PyTorch 2.7/cu126，其他多项版本未锁|与本队曾测的 PyTorch 2.9/cu130 不能直接视作相同环境；固定一份可重现镜像|
|Qwen 路径需调整|源码加载字符串为 `Qwen2.5-VL-7B-Instruct`，README 下载示例路径不同|明确本地模型目录或正确 Hub ID，不依赖作者机器路径|

上述检查没有执行模型，因此没有精度、时延或显存结论。即使做完这些适配，仍要解决关键球员、球框和名单输入；赛事出手瞬间点位不足以构造 PlayNet 要求的整段视觉框 JSON。

## 5. T4 上的现实路线

**优先验证 PlayNet 事件模型本体，不把 SAM3 + 本地 Qwen7B + PlayNet 一次性全塞进 T4。** 本队只有 `ml.g4dn.xlarge` Training 的 T4 CUDA 通路已实测，模型兼容性、峰值内存和作业时长都未测。Training 与 Processing 是不同配额，后续实验遵照主办方允许的用途和 SageMaker 路径。

全链中的额外风险有明确依据：SAM3 权重需要 Hugging Face 授权，且有其独立 SAM 许可；仓库所固定 SAM3 子模块的 `sam3_base_predictor.py` 使用 BF16 autocast，T4 的本机 BF16 硬件能力不同于 Ampere 及之后架构，不能承诺原样运行，必须先做算子/精度兼容性检查。Qwen 身份脚本默认整模型加载、没有量化或 offload 设置，16 GB 级 T4 的实际余量要测，不能只按“7B”名称估算可行性。[SAM3 主仓库](https://github.com/facebookresearch/sam3)、[固定子模块 BF16 路径](https://github.com/facebookresearch/sam3/blob/5dd401d1c5c1d5c3eedff06d41b77af824517619/sam3/model/sam3_base_predictor.py#L205)、[NVIDIA BF16 能力说明](https://docs.nvidia.com/cuda/archive/13.2.0/cuda-programming-guide/05-appendices/mathematical-functions.html)

建议的试用顺序（未来实施计划，本轮未执行）：

1. 获得明确复用许可和作者推荐的匹配代码/权重版本；拿到时间窗导出方法，不重新训练整个数据集。
2. 先用作者已有视频与对应框做单卡事件头验证，确认依赖、权重加载和输出。这只能算环境复现，不算本地 NBA 样片已验证。
3. 再对我们一段 22 秒样片生成一致帧率的工作副本、必要的图像框和名单关联。可以评估已有 Bedrock Qwen3-VL/Claude 替代本地 Qwen2.5-VL 的身份步骤，但这是需要写适配器、重新测试的改变，不是无差别替换。
4. 将 PlayNet 输出接到 `candidate_events`，由 Agent 结合原片和官方记录验证；准确通过者才进入成片。未识别出的掩护、节奏、切入等由现有证据流程处理，不臆造为 PlayNet 类别。
5. 记录整条链的时间、峰值 RAM/VRAM、框覆盖、身份错误、事件准确与时间误差，并与纯 Bedrock 基线对照。未显著改善准确性或时间成本时，将它保留为实验插件，不放在考试主链的必经位置。

SAM3 的 BF16 路径可否稳定改成 FP16、PlayNet 是否能在 T4 低精度下达到合适吞吐，以及选择另一有配额的 SageMaker GPU 是否值得，均是实验问题。本轮没有证据保证任一方案，不能把“有 checkpoint”和“T4 曾算过矩阵”合并成“整个项目能直接跑”。

## 6. 可以立即吸收的方法，而不依赖整套模型

- **人物、动作、证据时刻三元组**：让每条叙事落到明确主体和视频窗口；这是适合我们数据契约的组织方法。
- **同时查看主体、周围球员、球和全局画面**：不能只把某个球员裁剪放大后让模型猜整回合。对于遮挡动作主动回看上下文。
- **粗候选再细核验**：事件头或 VLM 提供片段候选，出手/传球时刻通过局部加密帧确认；门控权重不是篮球因果证明。
- **身份识别有名单约束**：使用本场名单和队服信息，避免靠通用模型记忆猜球星。

这些设计本身应通过我们的样片验证，不把论文的 F1 当成改写后系统的成绩。最值得请 Rao 学长提供的帮助是：推荐可复现 commit、权重与代码许可、单卡显存/时间经验、缺失评测脚本、当前时间指标协议、身份前处理与训练比赛清单。当前没有向学长或其他人发送消息。
