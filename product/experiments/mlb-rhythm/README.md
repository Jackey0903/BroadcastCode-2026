# 独行侠：完整回合与同步画面解读

支线 `experiment/mlb-narrative-rhythm`，只有独行侠 / 弗拉格案例。当前完整成片约38.96秒，1280×720：开场终结一次，短倒放桥段约1.7秒，然后回到原片开头，按顺序讲完整进攻回合。默认故事不反复慢放终结。

## 已完成

- `story-plan.json`：统一描述章节、来源时间、暂停、字幕和画面标注位置。
- `render.py`：画面内章节、同步字幕、球员光圈、箭头与头顶标签；突破阶段短暂移动高亮。比分栏保留。
- `reverse.mp4`：原片16.3—17.4秒区间，0.65×真实倒放。
- 1291张原片解码帧：59.94fps，按原始解码顺序编号，交互预览支持前后逐帧、关键帧定位与标注。
- 先看配合，再看正面17号伊森，最后看篮下7号杜兰特举臂；姓名由画面球衣号码与官方名单交叉核对。
- xFG51.0%在完整回合末尾展示，沿用已核对game0022500701 / event666。

## 本地复现

Python3.11+、Pillow、FFmpeg与中文字库。原片放在 `data/reference/train_video/train_video/训练_弗拉格2月1日.mp4`，也支持 `flagg.mp4`。

```sh
python product/experiments/mlb-rhythm/render.py --sample flagg --ffmpeg /path/to/ffmpeg --font /path/to/chinese-font.ttf
python product/experiments/mlb-rhythm/serve.py --port 4180
```

打开 `http://127.0.0.1:4180/`。输出在 `product/build/mlb-rhythm/flagg/`：enhanced.mp4、reverse.mp4、frames/、evidence.json。媒体与字库保留在本地忽略目录，GitHub提交包含源代码、解读计划和数据规划。

## 已验证

原片哈希与官方出手关联一致；成片完整FFmpeg解码通过，实际38.96秒；提取1291张源帧。已检查右侧配合、队友向篮下移动、伊森、杜兰特与弗拉格、xFG五处画面，圈选与标签和来源帧一致。身份与动作标注由编辑核对，未调用新的AWS/Agent推理。

真实覆盖面积、替代球员是否被断/盖，属于后续数据与模型工作。见 [DATA-PLAN.md](DATA-PLAN.md)。当前标签依据画面，身体资料附官方链接；不把身体臂展或xFG直接当作反事实结果。
