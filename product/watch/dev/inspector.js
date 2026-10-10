import { schema, getConfig, getConfigStatus, subscribe, updateConfig, beginConfigEdit, endConfigEdit, undo, redo, resetConfig, saveConfig, exportConfig, importConfig, listPresets, savePreset, loadPreset, deletePreset, renamePreset } from '../config/config.js';

const glassLabels = { tint: '玻璃染色', tintAlpha: '染色不透明度', color: '文字与图标颜色', refraction: '液态折射', frost: '磨砂强度', bevelDepth: '玻璃边缘深度', bevelWidth: '玻璃边缘宽度' };
const typographyLabels = { fontFamily: '字体', fontWeight: '字重' };
const courtLabels = { width: '面板宽度 · 视口比例', radius: '外壳圆角 · px', courtRadius: '球场内框圆角 · px', fontSize: '面板字号 · px', ...typographyLabels, woodColor: '球场木地板', paintColor: '禁区与边线区', lineColor: '球场线颜色', lineWidth: '球场线粗细', markerSize: '球员点尺寸', ...glassLabels };
const labels = {
  dock: ['左侧抽屉', { width: '抽屉宽度 · px', radius: '外壳圆角 · px', iconSize: '图标尺寸 · px', gap: '图标间距 · px', ...glassLabels }],
  fullCourt: ['全场战术板', courtLabels], halfCourt: ['半场战术板', courtLabels],
  controls: ['播放控制条', { height: '控制条高度 · px', radius: '控制条圆角 · px', fontSize: '时间字号 · px', ...typographyLabels, iconSize: '图标尺寸 · px', gap: '控件间距 · px', ...glassLabels }],
  content: ['内容抽屉', { width: '抽屉宽度 · px', maxHeight: '抽屉最大高度 · px', fontSize: '内容基础字号 · px', titleSize: '标题字号 · px', ...typographyLabels, padding: '内部边距 · px', radius: '抽屉圆角 · px', ...glassLabels }],
  menus: ['设置与菜单', { width: '观看设置宽度 · px', compactWidth: '紧凑菜单宽度 · px', fontSize: '菜单基础字号 · px', titleSize: '设置标题字号 · px', ...typographyLabels, padding: '内部边距 · px', radius: '菜单圆角 · px', itemRadius: '选项圆角 · px', ...glassLabels }],
  topbar: ['顶部功能栏', { fontSize: '按钮字号 · px', ...typographyLabels, radius: '功能栏圆角 · px', gap: '按钮间距 · px', ...glassLabels }],
  heading: ['视频标题', { fontSize: '标题字号 · px', ...typographyLabels, ...glassLabels, color: '标题文字颜色' }],
  mascot: ['篮球吉祥物', { size: '吉祥物尺寸 · px', color: '篮球主体颜色', expression: '表情', style: '绘制样式', labelSize: '关联标签字号 · px', fontFamily: '关联标签字体', fontWeight: '关联标签字重' }],
  courtTheme: ['球队皮肤', { preset: '球场主题' }],
  layout: ['整体空间', { padding: '舞台边距 · px', gap: '视频与侧板间距 · px', dockWidth: '左抽屉宽度 · px', fullWidth: '全场宽度 · 视口比例', halfWidth: '半场宽度 · 视口比例' }],
  motion: ['动画速度', { open: '打开总时长 · ms', morph: '全半场切换 · ms', close: '收起时长 · ms', hideDelay: '离开后收起等待 · ms', controlsIdle: '控件静置隐藏 · ms' }],
  appearance: ['整体外观', { panelRadius: '两侧板统一圆角 · px', videoRadius: '视频圆角 · px', controlRadius: '控制条圆角 · px', titleSize: '标题字号 · px', bodySize: '正文字号 · px' }],
  annotations: ['标注开关', { mascotSize: '吉祥物尺寸 · px', labelSize: '标注字号 · px', enabled: '显示视频分析标注' }],
  glass: ['批量玻璃参数', { refraction: '全部组件折射', bevelDepth: '全部组件边缘深度', bevelWidth: '全部组件边缘宽度', frost: '全部组件磨砂强度', tintAlpha: '全部组件染色不透明度' }],
};
const enumLabels = { default: '原图默认', system: '系统字体', pingfang: '苹方', songti: '宋体', mono: '等宽', '300': '300 · 细', '400': '400 · 常规', '500': '500 · 中等', '600': '600 · 半粗', '700': '700 · 粗体', '800': '800 · 特粗', happy: '微笑', focus: '专注', classic: '经典篮球', minimal: '简洁篮球', source: '跟随当前比赛', neutral: '中性球场', rockets: '休斯顿火箭', mavericks: '达拉斯独行侠' };
const referenceStates = [ ['immersive','01_immersive.png','沉浸式'], ['fullCourt','02_full_court.png','全场'], ['halfCourt','03_half_court.png','半场'] ];
const emit = (name, detail) => window.dispatchEvent(new CustomEvent(name, { detail }));

export function createInspector() {
  const element = document.createElement('dialog');
  element.className = 'config-inspector'; element.dataset.liquidIgnore = '';
  element.setAttribute('aria-label', '中文可视化调参');
  element.innerHTML = `<div class="inspector-heading"><div><h2>可视化调参</h2><p>点选组件 · 实时预览 · 仅本机保存</p></div><button type="button" class="inspector-close" aria-label="关闭调参">×</button></div>
    <div class="inspector-tools"><button type="button" data-action="pick">在画面中点选</button><button type="button" data-action="undo">撤销</button><button type="button" data-action="redo">重做</button></div>
    <div class="inspector-component-grid" aria-label="选择组件">${['dock','fullCourt','halfCourt','controls','content','menus','topbar','heading','mascot','courtTheme'].map(group => `<button type="button" data-component-choice="${group}">${labels[group][0]}</button>`).join('')}</div>
    <label class="inspector-group-picker">正在调整<select class="group-select" aria-label="参数组">${Object.entries(labels).map(([group, [title]]) => `<option value="${group}">${title}</option>`).join('')}</select></label>
    <p class="inspector-scope-note">每个组件的玻璃独立生效；调整全场不会改变半场。</p>
    <div class="inspector-fields"></div>
    <button type="button" data-action="reset-group" class="inspector-reset-group">恢复当前组件</button>
    <details class="inspector-reference"><summary>三张原图基准 · 一键恢复</summary><div class="inspector-reference-grid">${referenceStates.map(([mode,file,title]) => `<button type="button" data-reference="${mode}"><img src="${new URL('./references/' + file, import.meta.url).href}" alt="${title}原图"><span>恢复${title}</span></button>`).join('')}</div><p>恢复全部显示参数并进入对应形态，可撤销参数。</p></details>
    <details class="inspector-presets"><summary>命名预设 · 仅本机浏览器</summary><div class="preset-save-row"><input class="preset-name" type="text" maxlength="48" placeholder="新预设名称" aria-label="预设名称"><button type="button" data-action="preset-create">新建</button></div><select class="preset-select" aria-label="已保存预设"><option value="">尚无命名预设</option></select><div class="preset-actions"><button type="button" data-action="preset-load">应用</button><button type="button" data-action="preset-update">更新</button><button type="button" data-action="preset-rename">重命名</button><button type="button" data-action="preset-delete">删除</button></div></details>
    <details class="inspector-diagnostics"><summary>实际 liquidGL 渲染状态</summary><pre aria-live="off"></pre></details>
    <p class="inspector-note">调参只影响界面与球场皮肤；球员身份、坐标、比分与来源保持只读。</p><p class="inspector-message" role="status" aria-live="polite"></p>
    <div class="inspector-footer"><button type="button" data-action="save" class="inspector-primary">保存当前配置</button><button type="button" data-action="export">导出 JSON</button><button type="button" data-action="import">导入 JSON</button><input type="file" accept="application/json,.json" hidden aria-label="导入本机显示预设"></div>`;
  const $ = selector => element.querySelector(selector);
  const fields = $('.inspector-fields'), picker = $('.group-select'), message = $('.inspector-message');
  const presetPicker = $('.preset-select'), presetName = $('.preset-name');
  const pickBanner = document.createElement('div'); pickBanner.className = 'inspector-pick-banner'; pickBanner.hidden = true; pickBanner.textContent = '点击要调整的组件 · Esc 取消';
  let diagnosticTimer, picking = false, selectedNode = null, headerDrag = null;
  const setMessage = (text, error = false) => { message.textContent = text; message.classList.toggle('is-error', error); };
  function run(action, success) { endConfigEdit(); try { action(); if (success) setMessage(success); } catch (error) { setMessage(error.message, true); sync(); } }
  function renderGroup() {
    const group = picker.value; fields.replaceChildren();
    $('.inspector-scope-note').textContent = group === 'glass' ? '批量操作：同时修改左抽屉、内容抽屉、全场、半场、控制条、菜单、顶部功能栏和标题胶囊八组玻璃。' : ['dock','fullCourt','halfCourt','controls','content','menus','topbar','heading'].includes(group) ? '当前组件独立生效；字体、字重、玻璃、尺寸和颜色不会串到其他组件。原图默认保留原有字体层次。' : group === 'courtTheme' ? '皮肤只改变场地外观，不改变当前比赛与球员资料。' : '调整会立即作用于画面；拖动面板标题可移动此调参窗口。';
    element.querySelectorAll('[data-component-choice]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.componentChoice === group)));
    for (const [key, rule] of Object.entries(schema[group])) {
      const label = document.createElement('label'); label.className = 'inspector-field';
      const text = document.createElement('span'); text.textContent = labels[group][1][key];
      const inputs = document.createElement('span'); inputs.className = 'inspector-field-inputs';
      const input = document.createElement(rule.enum ? 'select' : 'input'); input.dataset.key = key; input.setAttribute('aria-label', text.textContent);
      if (rule.enum) { for (const value of rule.enum) { const option = document.createElement('option'); option.value = value; option.textContent = enumLabels[value] || value; input.append(option); } }
      else if (rule === 'boolean') input.type = 'checkbox';
      else if (rule === 'color') { input.type = 'color'; input.title = text.textContent; }
      else { input.type = 'number'; input.min = rule[0]; input.max = rule[1]; input.step = rule[2]; input.inputMode = 'decimal'; }
      const apply = source => {
        if (source.type === 'number' && source.value.trim() === '') return;
        const value = rule === 'boolean' ? source.checked : rule === 'color' || rule.enum ? source.value : Number(source.value);
        try { updateConfig({ [group]: { [key]: value } }); setMessage('正在实时预览。保存后才会保留到下次打开。'); }
        catch (error) { setMessage(error.message, true); }
      };
      const wire = source => { source.addEventListener('input', () => apply(source)); source.addEventListener('focus', beginConfigEdit); source.addEventListener('blur', () => { endConfigEdit(); sync(); }); source.addEventListener('pointerdown', beginConfigEdit); source.addEventListener('pointerup', endConfigEdit); source.addEventListener('pointercancel', endConfigEdit); };
      if (Array.isArray(rule)) {
        const range = document.createElement('input'); range.type = 'range'; range.dataset.key = key; range.min = rule[0]; range.max = rule[1]; range.step = rule[2]; range.setAttribute('aria-label', text.textContent); wire(range); inputs.append(range);
      }
      wire(input); inputs.append(input);
      if (rule === 'color') { const colorValue = document.createElement('output'); colorValue.dataset.colorFor = key; inputs.append(colorValue); }
      label.append(text, inputs); fields.append(label);
    }
    sync();
  }
  function sync() {
    const config = getConfig(), status = getConfigStatus();
    fields.querySelectorAll('[data-key]').forEach(input => { const value = config[picker.value][input.dataset.key]; if (input.type === 'checkbox') input.checked = value; else if (input !== document.activeElement || input.type !== 'number') input.value = value; });
    fields.querySelectorAll('[data-color-for]').forEach(output => { output.textContent = config[picker.value][output.dataset.colorFor]; });
    $('[data-action="undo"]').disabled = !status.canUndo; $('[data-action="redo"]').disabled = !status.canRedo;
  }
  function syncPresets(selection) {
    const prior = selection ?? presetPicker.value; presetPicker.replaceChildren(); const presets = listPresets();
    if (!presets.length) { const option = document.createElement('option'); option.value = ''; option.textContent = '尚无命名预设'; presetPicker.append(option); }
    for (const preset of presets) { const option = document.createElement('option'); option.value = preset.name; option.textContent = preset.name; presetPicker.append(option); }
    if (presets.some(item => item.name === prior)) presetPicker.value = prior;
    element.querySelectorAll('.preset-actions button').forEach(button => button.disabled = !presets.length);
  }
  function diagnostics() {
    let details;
    try { const value = typeof window.broadcastDiagnostics === 'function' ? window.broadcastDiagnostics() : window.broadcastDiagnostics; details = value ? JSON.stringify(value, null, 2) : '尚未收到渲染器状态。无法据此认定 liquidGL 已实际生效。'; }
    catch (error) { details = `状态读取失败：${error.message}`; }
    $('.inspector-diagnostics pre').textContent = details;
  }
  function close() { endConfigEdit(); clearInterval(diagnosticTimer); if (element.open) element.close(); emit('broadcast-inspector-state', { open: false }); }
  function open() { if (!element.isConnected) document.body.append(element); if (!element.open) element.show(); sync(); diagnostics(); try { syncPresets(); } catch (error) { setMessage(error.message, true); } clearInterval(diagnosticTimer); diagnosticTimer = setInterval(diagnostics, 800); emit('broadcast-inspector-state', { open: true }); }
  function selectComponent(group) { if (!Object.hasOwn(labels, group)) return false; picker.value = group; renderGroup(); emit('broadcast-config-select', { component: group }); return true; }
  function clearPicking() { picking = false; pickBanner.hidden = true; document.documentElement.classList.remove('inspector-picking'); selectedNode?.classList.remove('inspector-pick-highlight'); selectedNode = null; emit('broadcast-config-pick', { active: false }); }
  function startPicking() { close(); picking = true; if (!pickBanner.isConnected) document.body.append(pickBanner); pickBanner.hidden = false; document.documentElement.classList.add('inspector-picking'); emit('broadcast-config-pick', { active: true }); }
  function pickTarget(target) { return target instanceof Element ? target.closest('[data-component]') : null; }
  function onPickMove(event) { if (!picking) return; const target = pickTarget(event.target); if (target === selectedNode) return; selectedNode?.classList.remove('inspector-pick-highlight'); selectedNode = target; target?.classList.add('inspector-pick-highlight'); }
  function onPickClick(event) { if (!picking) return; const target = pickTarget(event.target); if (!target || !Object.hasOwn(labels,target.dataset.component)) return; event.preventDefault(); event.stopImmediatePropagation(); const group = target.dataset.component; clearPicking(); selectComponent(group); open(); }
  function onPickKey(event) { if (picking && event.key === 'Escape') { event.preventDefault(); event.stopImmediatePropagation(); clearPicking(); open(); } }
  document.addEventListener('pointermove', onPickMove, true); document.addEventListener('click', onPickClick, true); document.addEventListener('keydown', onPickKey, true);
  picker.addEventListener('change', () => selectComponent(picker.value));
  $('.inspector-close').addEventListener('click', close); element.addEventListener('close', () => clearInterval(diagnosticTimer));
  element.addEventListener('keydown', event => { if (event.key === 'Escape') { event.stopPropagation(); close(); } });
  const header = $('.inspector-heading');
  header.addEventListener('pointerdown', event => { if (event.target.closest('button')) return; const rect = element.getBoundingClientRect(); headerDrag = { x: event.clientX - rect.left, y: event.clientY - rect.top }; header.setPointerCapture(event.pointerId); event.preventDefault(); });
  header.addEventListener('pointermove', event => { if (!headerDrag) return; const left = Math.max(0, Math.min(innerWidth - element.offsetWidth,event.clientX - headerDrag.x)), top = Math.max(0, Math.min(innerHeight - 60,event.clientY - headerDrag.y)); element.style.left = `${left}px`; element.style.top = `${top}px`; element.style.right = 'auto'; element.style.bottom = 'auto'; element.style.margin = '0'; });
  header.addEventListener('pointerup', () => { headerDrag = null; }); header.addEventListener('pointercancel', () => { headerDrag = null; });
  element.addEventListener('click', event => {
    const choice = event.target.closest('[data-component-choice]')?.dataset.componentChoice; if (choice) selectComponent(choice);
    const reference = event.target.closest('[data-reference]')?.dataset.reference;
    if (reference) run(() => { resetConfig(); emit('broadcast-layout-request', { layout: reference }); }, `已恢复${referenceStates.find(item => item[0] === reference)[2]}原图基线。`);
    const action = event.target.closest('[data-action]')?.dataset.action;
    if (action === 'pick') startPicking();
    if (action === 'undo') run(undo, '已撤销上一步调参。');
    if (action === 'redo') run(redo, '已重做上一步调参。');
    if (action === 'reset-group') run(() => resetConfig(picker.value), '当前组件已恢复参考基线，可撤销。');
    if (action === 'save') run(saveConfig, '当前配置已保存，仅本机浏览器。');
    if (action === 'preset-create') run(() => syncPresets(savePreset(presetName.value)), '命名预设已新建，仅本机浏览器。');
    if (action === 'preset-update') run(() => syncPresets(savePreset(presetPicker.value, { overwrite: true })), '已用当前画面参数更新所选预设。');
    if (action === 'preset-load') run(() => loadPreset(presetPicker.value), '已应用命名预设，可撤销。');
    if (action === 'preset-delete') run(() => { deletePreset(presetPicker.value); syncPresets(); }, '已删除所选本机预设，当前画面参数保留。');
    if (action === 'preset-rename') run(() => syncPresets(renamePreset(presetPicker.value, presetName.value)), '预设已重命名。');
    if (action === 'import') $('input[type="file"]').click();
    if (action === 'export') run(() => { const url = URL.createObjectURL(new Blob([exportConfig()], { type: 'application/json' })); const link = document.createElement('a'); link.href = url; link.download = 'BroadcastCode-显示预设-v2.json'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); }, '已导出显示预设；导出不会保存或发布。');
  });
  $('input[type="file"]').addEventListener('change', async event => { const file = event.target.files?.[0]; if (!file) return; try { if (file.size > 32768) throw new Error('显示预设上限为 32 KB。'); importConfig(await file.text()); setMessage('已导入并实时预览，可撤销。点击保存才会保留到下次。'); } catch (error) { setMessage(`未导入，当前配置已保留。${error.message}`, true); } finally { event.target.value = ''; } });
  const unsubscribe = subscribe(sync); renderGroup(); setMessage(getConfigStatus().storageMessage || '当前使用参考基线。所有参数修改均可撤销。');
  return { element, open, close, selectComponent, get isOpen() { return element.open || picking; }, destroy() { close(); clearPicking(); unsubscribe(); document.removeEventListener('pointermove',onPickMove,true); document.removeEventListener('click',onPickClick,true); document.removeEventListener('keydown',onPickKey,true); pickBanner.remove(); element.remove(); } };
}
