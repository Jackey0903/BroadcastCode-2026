# 原比赛解说参考与英文试稿

## 已找到的参考

- [NBA官方发布：Mavericks at Rockets，2026-01-31全场集锦](https://www.youtube.com/watch?v=UG9E636IzfE)。搜索结果核对发布者为认证NBA频道；属于当前 `0022500701` 同场比赛。
- [NBA官方：弗拉格34分集锦](https://www.nba.com/watch/video/highlights-from-cooper-flagg-34-point-game?game-highlights=0022500701&plsrc=nba)。
- 已有训练原片提取约21.55秒的原音轨 `product/build/mlb-rhythm/flagg-voice/original-commentary.wav`，可在试听页面与AI样本对照。该文件来自已有本地原片，未下载远程媒体。抽帧可见ESPN转播标识；解说员姓名和逐字台词尚未核对，不能只因找到同场官方集锦就将其标为NBA官方制作的旁白。

## 当前证据限制

官方视频页面文本抓取失败，浏览器读取超时；随后读取官方YouTube公开页面也未得到captionTracks。没有拿到可靠的解说文字稿，也未完成原声音频的听辨或转录。因此以下节奏是本项目拟尝试的体育解说方向，不能描述为已经逐句复盘官方原解说的结论。

## 本轮实际修改

用户认为首轮Radio Host“太AI”，该声线暂停用于完整视频。模型保持 `speech-2.8-hd`，更换音色和文稿。国内账户英文系统声线经 `get_voice` 实查：`English_Trustworthy_Man`、`English_Gentle-voiced_man`可用；公开国际列表中的FriendlyPerson、expressive_narrator没有出现在当前账户的系统列表，未强行使用，也未静默换模型。

中文使用真诚青年、温和青年候选，正文保持口语化解释。英文改为短动作句推进，终结后进入回看分析。两种英文音色同稿同模型同语速，便于比较声线。

### 英文原创试稿

Flagg. Eason stays with him. Seven on the clock. Flagg attacks again. Durant at the rim... and he gets it to go! Let's take another look. That's Cooper Flagg, Dallas's number one pick in twenty twenty-five. Eason gets around the screen. He's still on Flagg's hip. And Durant is right there in front of him.

上述稿件基于已核对的画面与球员资料，由本项目编写；不是NBA原话或翻译。当前为独立音色试听，尚未与视频逐句对齐。

后续按用户“带有感情色彩并接入视频”的要求，已用 `voice-plan-en.json`生成九段英文口播，并渲染约41.14秒完整视频。模型 `speech-2.8-hd`，声线 `English_Trustworthy_Man`；开场/突破使用 `surprised`、终结 `happy`、回看解释 `calm`。这些字段已按官方API Schema核对支持；用户随后反馈仍很AI、很假，听感验收失败，见 [VOICE-ISSUES.md](VOICE-ISSUES.md)。情绪版使用新的分段稿，不是上方长试听稿的直接硬塞。

## 完整版的拟定节奏

1. 开场与终结：短动作句，优先让观众感受到动作，球进后留出现场声音。
2. 回合重启：再补新球员身份，避免突破时插入人物履历。
3. 停帧解释：降低语速，每次只解释一个防守压力点，声音点到球员时画面同步聚焦。
4. 原比赛音轨与AI旁白不能同时抢话；若保留原解说，AI分析尽量放在停帧与回看时段。
5. 不把每句都念得同样饱满，不以持续喊叫制造情绪；呼吸、动作高潮和安静段落需要完整听审。

下一步需在实际可播放的官方片段上标记开口/停顿、重音、高潮与回看分析段，并人工复核转录。正式制作前先确定可接受的声线；用户反馈比厂商的音色名称或模型标签更有决定作用。
