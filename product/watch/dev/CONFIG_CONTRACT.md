# 可视化调参接口

`createInspector()` 可从正常本地页面设置入口打开。返回 `element`、`open()`、`close()`、`selectComponent(group)`、`isOpen` 和 `destroy()`。非模态窗口，可拖动标题调整位置。三态恢复按钮保留原有显示参数；缩略图已从活动前端撤下。

## 组件分组

- `dock`：width、radius、iconSize、gap，以及独立玻璃参数。
- `fullCourt` / `halfCourt`：各自的 width（视口比例）、radius（外壳）、courtRadius（内场圆角，默认 10/8 px）、fontSize、woodColor、paintColor、lineColor、lineWidth、markerSize，以及独立玻璃参数。
- `controls`：height、radius、fontSize、iconSize、gap，以及独立玻璃参数。
- `content`：width、maxHeight、fontSize、titleSize、padding、radius，以及独立玻璃参数。
- `menus`：width（观看设置宽度）、compactWidth（倍速等紧凑菜单宽度）、fontSize、titleSize、padding、radius、itemRadius，以及独立玻璃参数。
- `topbar`：fontSize、radius、gap，以及完整独立玻璃参数。
- `heading`：fontSize，以及完整独立玻璃参数；color 控制标题文字，玻璃参数控制标题胶囊。
- `annotations`：enabled、labelSize、fontFamily、fontWeight；保留纯文字标注。
- `courtTheme.preset`：source / neutral / rockets / mavericks；只改变皮肤，不改变比赛资料。
- `layout`、`motion`、`appearance`、`annotations` 保留整体参数。`glass` 明确标为批量调整组，会同步修改 dock/fullCourt/halfCourt/controls/content/menus/topbar/heading 八组。单独调整任一组件不会传到其他组件。

独立玻璃参数：tint（严格六位十六进制色值）、tintAlpha、color、refraction、frost、bevelDepth、bevelWidth。每个组件默认值和精确边界由 `config/config.js` 的冻结 `baseline` / `schema` 定义。

独立字体参数：`fullCourt`、`halfCourt`、`controls`、`content`、`menus`、`topbar`、`heading`、`annotations` 各自包含 `fontFamily` 与 `fontWeight`。`fontFamily` 枚举为 `default/system/pingfang/songti/mono`，分别对应原图默认、系统字体、苹方、宋体、等宽；白名单 CSS 栈由导出的 `fontFamilies` 定义，只用本机字体。`fontWeight` 是字符串枚举 `default/300/400/500/600/700/800`。默认均为 `default`，不输出覆盖，所以原有 550/620/730 等层级保持原样。选择具体字重后，当前组件内的文字统一使用该值。两字段均无跨组别名或批量传播。Dock 为纯 SVG 图标，不提供无效的字体字段。

兼容别名同步：layout.dockWidth ↔ dock.width；layout.fullWidth ↔ fullCourt.width；layout.halfWidth ↔ halfCourt.width；appearance.controlRadius ↔ controls.radius；appearance.titleSize ↔ heading.fontSize。整体面板圆角及整体玻璃调节是明确的批量入口，独立组件修改不会改变其他组件。

## 配置与存储

`getConfig()`、`subscribe(fn)`、`updateConfig(patch)`、`undo()`、`redo()`、`resetConfig(group?)`、`saveConfig()`、`exportConfig()`、`importConfig(json)`。

`beginConfigEdit()` / `endConfigEdit()` 将一次滑杆拖动组合为一次可撤销操作。

命名预设：`listPresets()`、`savePreset(name,{overwrite:false})`、`loadPreset(name)`、`renamePreset(oldName,newName)`、`deletePreset(name)`。新增同名不会静默覆盖，更新按钮显式覆盖所选项。最多 50 个预设，名称 1–48 字。存储仅使用当前来源的 localStorage，不发送数据。

导出版本为 3；完整导入严格校验版本、组、字段、类型、数值边界、颜色和枚举，校验成功才整体替换。旧版本 1/2 及 v2 命名预设在读取时验证并转换：退役图形参数不进入新配置，关联文字字号与字体转入 annotations，其余布局、颜色、光学与组件设置保持原值。旧版 v2 在所有字体字段都不存在时统一补 default；部分缺失仍拒绝。读取不会覆盖原存储，保存或更新后才写入版本 3。非法导入不修改当前值和撤销历史。

## 事件

Inspector 向 window 派发：

- `broadcast-config-select`：`{ component: group }`，界面应让被选组件显示并进入对应全/半场。
- `broadcast-layout-request`：`{ layout: 'immersive' | 'fullCourt' | 'halfCourt' }`，已先恢复全部基线。
- `broadcast-inspector-state`：`{ open: boolean }`。
- `broadcast-config-pick`：`{ active: boolean }`。

画面点选读取最近的 `[data-component]` 元素。组件值对应分组键；切换全/半场时需同步侧板键名。Inspector 点选捕获只消费选择动作，不触发下层播放器按钮。

## CSS 与实际材质

配置自动生成每组的 kebab-case CSS 变量，如 `--dock-width`、`--full-court-wood-color`、`--half-court-refraction`、`--controls-font-size`。尺寸、字号、圆角等带 px；球场比例、光学参数不带单位。已有全局别名继续可用。

字体绑定在 `config/config.js` 的 `applyTypography()`，无需媒体或布局组件参与。自定义时生成 `#broadcast-component-typography` 样式，选项改回默认即撤除相应规则；全部默认时该节点不存在。每组的 `--<group>-font-family` 输出可信 CSS 字体栈，`--<group>-font-weight` 输出数字字符串，默认移除变量。规则覆盖各作用域后代，包含球场 SVG 的 `text` 与硬编码字体，但不修改全局字体。

| 组 | 实际 DOM 作用域 |
|---|---|
| fullCourt / halfCourt | `#court-shell[data-component="fullCourt"]` / `#court-shell[data-component="halfCourt"]` 及后代，自动跟随现有形态标记 |
| controls | `.player-controls` 下 `.control-button`、`.media-time`、`.media-resolution`、`.sr-only` 及后代，不给共同祖先写字体，防止倍速菜单继承串组 |
| content | `[data-component="content"]` 及后代，包括动态更新的抽屉内容 |
| menus | `[data-component="menus"]` 及后代，覆盖观看设置与倍速菜单 |
| topbar / heading | `#top-tabs` / `#moment-heading` 及后代 |
| annotations | `.annotation-layer .annotation-label` 及后代，不制造缺失的头锚 |

播放器已应用 `--controls-height/radius/font-size/icon-size/gap/color`。倍速菜单另用 `--menus-compact-width/radius/font-size/item-radius/color`，保持与控制条独立。其余组件由对应组件层接入；GlassManager 读取各组光学参数并把 tint 与 tintAlpha 组合成 RGBA。调参面板读取 `window.broadcastDiagnostics` 对象或函数，展示实际引擎/状态，不把 CSS 降级报告为 liquidGL 成功。
