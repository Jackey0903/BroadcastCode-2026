# MiniMax 语音试验

状态（2026-10-10）：MiniMax Speech 2.8 HD英文情绪版已真实生成并接入完整独行侠回合，实际约41.14秒、1280×720。使用国内账户的 `English_Trustworthy_Man`，九句口播分别使用惊讶、中性和高兴情绪。中文可选字幕、旁白期间原声压低、球员高亮和停帧资料卡已接入，完整视频解码及浏览器播放通过。用户反馈该版仍很AI、很假，听感验收失败；具体问题与待验证方向见 [VOICE-ISSUES.md](VOICE-ISSUES.md)。首轮中文Radio Host被拒绝，保留记录而不再作为页面主试听入口。当前不涉及AWS部署。

当前真实音色对照已有两段中文（15.44/16.08秒）、一段美式英文（21.46秒）。第二个英文候选曾返回不完整JSON，未生成，不能称为四段已完成。已补充有限重试及该故障的回归检查；本轮选择已可用的英文声线完成视频。

## 配置与运行

在仓库外保存密钥，例如本机 `C:\Users\zhong\Desktop\draft12\.qa\minimax.env`。本地快照的CLI默认读取其父目录的 `.qa/minimax.env`；其他开发者可用 `--env-file /path/to/private.env`，或设置进程环境变量。不要提交密钥文件。

```env
MINIMAX_API_KEY=your-key
# 国内站账号使用下面一行；国际站默认 https://api.minimax.io/v1
MINIMAX_API_BASE=https://api.minimax.cn/v1
```

Python3.11+，完整渲染另外需要Pillow、FFmpeg、中文字库与已核对的原视频。

```sh
python product/experiments/mlb-rhythm/tts_trial.py check
python product/experiments/mlb-rhythm/tts_trial.py dry-run
python product/experiments/mlb-rhythm/tts_trial.py list-voices
python product/experiments/mlb-rhythm/tts_trial.py preview
python product/experiments/mlb-rhythm/tts_trial.py auditions
python product/experiments/mlb-rhythm/tts_trial.py full
# 当前英文情绪版使用下面的计划：
python product/experiments/mlb-rhythm/tts_trial.py full --plan product/experiments/mlb-rhythm/voice-plan-en.json
python product/experiments/mlb-rhythm/render.py --voice --ffmpeg /path/to/ffmpeg --font /path/to/chinese-font.ttf
python product/experiments/mlb-rhythm/serve.py --port 4180
```

`check`仅输出凭据是否存在，`dry-run`仅检查稿件与画面分组，两者不访问API。`preview`会合成一段短试听；`full`会依次合成九个口播单元。生成前检查账户的系统音色列表；如果默认音色不可用，运行 `list-voices`，以 `--voice "实际voice_id"`选择。相同正文、模型、语速、音色与接口的合成复用本地哈希缓存。

输出在 `product/build/mlb-rhythm/flagg-voice/`：试听 `preview.wav`、缓存、实际音频时长、派生画面计划、句段字幕和独立的语音视频 `enhanced.mp4`。该目录应保持Git忽略。服务启动时建立媒体路由；更新服务代码后重启，生成媒体后刷新页面即可。页面提供音色试听、完整语音版、AI语音披露与可选CC字幕；未生成文件时对应按钮禁用。

当前预览：`http://127.0.0.1:4181/?version=6&voice=1`，点击“播放英文情绪解读”。可选CC字幕为中文含义，按口播单元计时，不是逐词翻译时间戳。字幕与画面保留对防守位置和xFG解释边界的说明。台词与情绪配置见 `voice-plan-en.json`；终结句实际2.73秒，未剪断或加速。除少量停帧补时外，原动作播放速度未改变。

## 首轮听什么

试听：这一球，怎么进的？独行侠三十二号，是二零二五年状元弗拉格。加福德过来掩护，但伊森绕了过去，仍在跟防。

首轮 `speech-2.8-hd`、`Chinese (Mandarin)_Radio_Host`、语速1.0；该音色被用户拒绝。模型已经是当前官方列出的最新HD系列，因此保留模型，调整音色与口语化稿件。`auditions`依据 `voice-auditions.json`生成真诚青年、温和青年、English Trustworthy Man与Gentle-voiced Man四个候选，使用国内账户实际列出的音色ID。每种语言内部使用同一篇稿件，语言之间为改写；不是受控音质排名。英文短句推进/回看分析与原解说参考的证据限制见 [OFFICIAL-COMMENTARY-REFERENCE.md](OFFICIAL-COMMENTARY-REFERENCE.md)。候选输出 `audition-*.wav`及参数证据。当前不是多人对话模式，也未克隆具体解说员声音。

表达节奏：短悬念 → 简短认识新球员 → 配合尝试 → 防守仍在 → 再次启动 → 看协防者的手与球 → 终结 → 数据参考。倒放桥段不配旁白。文字风格来自当前经核对的稿件，尚未增加自动个性化写稿服务。

## 同步与边界

- 每个WAV读取真实帧数与采样率，按30fps画面时间线排程。每句留0.25秒余量。
- 部分停帧允许有限延长，每次最多1.5—2.5秒；完整故事不得超过55秒。播放和倒放速度保持既有设置。
- 超时长会立即停止并提示修改哪句，保留已完成缓存；不剪断、不强行加速语音。修订 `voice-plan.json`后重跑 `full`。
- 语音版保留球员资料卡、光圈和箭头；移除原烧录底部长稿，提供可选句段字幕。字幕不是逐词时间戳，跨场景句子的逐词高亮尚未实现。
- 合成九句可能产生接缝和语气变化，姓名、年份、挑篮等术语仍需听审。一次合成完整长稿或前后文提示可作为接缝明显后的下一步。
- 渲染混合原比赛声音与解说，并在解说出现时压低比赛声音。音量参数须真实试听后调整，尚未验证听感。
- HTTP200之外还检查业务错误码；鉴权、余额与参数错误立即停止，暂时性错误最多尝试三次。网络超时后重试可能重复计费，厂商未承诺请求幂等。
- 合成锁避免本地重复任务，原始响应与密钥不写入日志。记录音频哈希、参数、trace_id。此锁与文件缓存不构成三人共享云服务；后续团队部署仍需后端任务队列与共享存储。
- xFG51%只说明该出手机会的模型参考，不意味着换人后的命中率或普通球员成功率。战术意图与动作动因仍以可观察证据与明确推断区分。

## 官方依据

- [国内同步语音接口](https://platform.minimax.cn/docs/api-reference/speech-t2a-http)：当前国内API域名为 `api.minimax.cn`。
- [国际同步语音接口](https://platform.minimax.io/docs/api-reference/speech-t2a-http)。
- [可用音色查询](https://platform.minimax.io/docs/api-reference/voice-management-get)。
- [弗拉格2025年状元资料](https://www.nba.com/news/dallas-mavericks-take-cooper-flagg-no-1-pick-nba-draft)。

已通过七项离线回归：业务限流重试/鉴权不重试、缓存复用与哈希变化、成功但无音频拒绝、停帧延长后的时间线移动、运动场景口播过长拒绝、分组重叠拒绝、不完整JSON重试及英文情绪字段保留。FFmpeg混音用人工正弦波夹具验证两个音频窗口，6.016秒完整解码；这不是MiniMax语音试听。

真实完整视频解码通过，实际约41.14秒；来源仍为1291帧原片，来源哈希核对一致。浏览器检查三段实际候选音频及原片音轨可播放、完整语音视频可播放、`voice=1`入口默认加载英文版、九段中文字幕载入、返回故事停止其他音频、移动端无溢出且无页面脚本异常。抽帧检查伊森停帧资料卡与圈选仍在，没有原烧录底部长稿。

真实接口成功一次不能证明厂商总体稳定性、发音、声线一致性或最终视频舒适度。音色接受度以用户试听反馈为准。
