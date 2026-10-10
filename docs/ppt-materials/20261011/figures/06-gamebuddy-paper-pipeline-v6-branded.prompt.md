# GameBuddy 架构图品牌版生成记录

方式：内置图像生成工具；接口未暴露模型选择参数。

输入：已核对的v3架构图；前端篮球小人精灵表第一行第一列；AWS彩色Logo；NBA红蓝徽标。后两者来源与输入哈希见`brand-inputs/README.md`和`brand-inputs/source-manifest.json`。原v3图保留。

最终输出：`06-gamebuddy-paper-pipeline-v6-branded.png`。顶部采用左侧篮球小人、中间GameBuddy标题、右侧AWS/NBA标识；五模块结构与AWS调度带保留，细化留白与对齐。图4数据卡的来源标签最终采用清晰的`Official source`。

## 品牌布局与整体排版

```text
Use case: compositing / precise-object-edit.
Create a refined branded version of the existing GameBuddy technical architecture figure for a defense PPT.

INPUT ROLES:
Image 1 is the EDIT TARGET: the approved five-panel GameBuddy paper-style architecture. Preserve its architecture, correct English labels, data relationships, arrows, numbered modules, side-branch DynamoDB, separate automatic RL sample / editorial 55s showcase labels, and bottom AWS infrastructure band.
Image 2 is the SUPPORTING BRAND ART: the actual frontend GameBuddy basketball character sprite sheet. Select ONLY ONE complete mascot from the TOP ROW, FIRST COLUMN: front-facing, smiling orange basketball character, headset and microphone, white gloves, black basketball outfit, white shoes. Precisely preserve this character's established design, colors, face, headset and proportions. Extract only that single character as a clean cutout; the sprite sheet background is transparent. Do not show a sprite grid, duplicate characters, a black background tile, or invent a new mascot.
Image 3 is the SUPPORTING AWS LOGO: use the supplied dark lowercase "aws" wordmark with orange smile arrow, retaining its recognizable proportions and colors. Isolate logo itself, discard excess empty margins.
Image 4 is the SUPPORTING NBA LOGO: use its canonical red/blue rounded vertical badge and white dribbling-player silhouette, faithfully matching the reference. Use the compact badge portion on the LEFT of this supplied horizontal asset; omit the large white letters on its right. A small dark navy "NBA" label below the badge is acceptable to identify it.

MAIN EDIT:
Add a polished brand masthead above the architecture.
LEFT: one GameBuddy mascot, roughly 80–100 pixels tall at this scale, neatly placed at the upper left with generous clean white surrounding space.
CENTER: retain the exact main title "GameBuddy: Evidence-driven Basketball Companion", navy serif, centered and clearly dominant. Retain exact subtitle "Three-layer data • Agentic RL • Multimodal agents • AWS delivery" in blue below it.
RIGHT: the AWS logo followed by the compact NBA badge, distinct from one another with comfortable spacing, both optically aligned to the masthead's vertical center. AWS logo should have a visible orange smile; NBA stays red, blue and white. Logos are restrained and clear, not giant sponsor blocks, and do not collide with the title.
Aim for an elegant left-brand / central-title / right-event-brand balance across the same horizontal header. Keep the center heading comfortably separated from both logo groups. If needed, slightly enlarge the top white header space and subtly refit the lower figure, but preserve a wide landscape 16:9 presentation format and readable technical text. Nothing cropped off.

GLOBAL POLISH:
Maintain the clean white academic figure style, thin blue dashed rounded panel outlines, circled step numerals, italic serif module headings, pastel lavender/mint/blue/amber internal blocks, thin dark connector arrows. Refine consistent outer margins, equal gutters, inner padding and optical alignment. Use slightly calmer visual spacing so the figure feels intentionally typeset, not a collage. Avoid gradients, large shadows, banners, decorative backgrounds or extra slogans.
Keep the full five numbered panels and bottom infrastructure band. Do not remove details, change service names, add metrics, add game clocks, or add new algorithm claims. All existing technical content must remain legible and accurate. Especially preserve: video → visual Agent; typed data → Qwen evidence scout; Lambda Worker → EventBridge after MP4 saved; DynamoDB as a separate state branch.
This request is a top-header branding and overall layout polish edit, not a redesign of the technical system. One final crisp PNG-like architecture illustration.
```

## 文字核对尝试

```text
Precise one-word text correction to the input image, which is the edit target. Keep the entire branded GameBuddy architecture figure unchanged: same canvas, mascot at upper left, central title and subtitle, AWS/NBA logos at upper right, five numbered panels, all colors, every box, diagram and connector, footer and all other text.

Only fix a misspelling in PANEL 4, the small rightmost "Data cards" box beneath the enhanced MP4.
The three lines in that one small box MUST read EXACTLY:
Official xFG
Verified source
Shot-event scope

The current second line mistakenly reads "Verifieal source". Replace it with "Verified source", spelled V-e-r-i-f-i-e-d, with clearly legible letter d. Match the current dark navy serif font, text size and alignment. Do not modify "Official source" in the viewer of panel 5 or any other label.
No redesign, no new details, no layout change. Preserve the whole image and perform only this local text correction.
```

## 最终来源标签修订

```text
Edit the input architecture image. Preserve every pixel-level layout, the mascot, title, AWS and NBA logos, every diagram module, all connector arrows, white background, colors and typography. Only replace ONE short text line in panel 4's tiny rightmost Data cards box.

The box currently has "Official xFG", a difficult-to-read middle phrase, and "Shot-event scope".
Replace the middle phrase with the exact text "Official source". Copy the spelling and clean letterforms of the existing "Official source" phrase in panel 5's player information card.
Final three lines of the panel 4 box must be:
Official xFG
Official source
Shot-event scope

Do not use the word Verified or any variant of that word. Do not change any other text or any logo, geometry or layout. One local label replacement only.
```
