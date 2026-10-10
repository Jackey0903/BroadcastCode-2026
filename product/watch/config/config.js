/** Display-only settings. No media facts, coordinates, sources, or resource URLs. */
function freeze(value) { Object.values(value).forEach(v => { if (v && typeof v === 'object') freeze(v); }); return Object.freeze(value); }
// Only these local font stacks can enter CSS; no font URLs or arbitrary CSS.
export const fontFamilies = freeze({
  system: '-apple-system,BlinkMacSystemFont,"Helvetica Neue","PingFang SC",sans-serif',
  pingfang: '"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif',
  songti: '"Songti SC","STSong","SimSun",serif',
  mono: 'ui-monospace,"SFMono-Regular",Menlo,Monaco,Consolas,"Liberation Mono",monospace',
});
const typographyRules = { fontFamily: { enum: ['default', ...Object.keys(fontFamilies)] }, fontWeight: { enum: ['default', '300', '400', '500', '600', '700', '800'] } };
const typographyBase = { fontFamily: 'default', fontWeight: 'default' };
const typographyGroups = ['fullCourt', 'halfCourt', 'controls', 'content', 'menus', 'topbar', 'heading', 'annotations'];
const glassRules = { tint: 'color', tintAlpha: [0, .85, .01], color: 'color', refraction: [0, .06, .001], frost: [0, 8, .1], bevelDepth: [0, .2, .01], bevelWidth: [.02, .4, .01] };
const courtRules = { width: [.18, .44, .01], radius: [8, 48, 1], courtRadius: [0, 32, 1], fontSize: [12, 24, 1], ...typographyRules, woodColor: 'color', paintColor: 'color', lineColor: 'color', lineWidth: [.1, 1.2, .05], markerSize: [1, 3.5, .1], ...glassRules };
export const schema = freeze({
  layout: { padding: [0, 48, 1], gap: [8, 48, 1], dockWidth: [56, 108, 1], fullWidth: [.18, .44, .01], halfWidth: [.18, .44, .01] },
  motion: { open: [120, 700, 10], morph: [100, 600, 10], close: [100, 500, 10], hideDelay: [100, 1000, 10], controlsIdle: [500, 8000, 100] },
  appearance: { panelRadius: [12, 48, 1], videoRadius: [0, 36, 1], controlRadius: [12, 40, 1], titleSize: [18, 40, 1], bodySize: [12, 22, 1] },
  glass: { refraction: [0, .06, .001], bevelDepth: [0, .2, .01], bevelWidth: [.02, .4, .01], frost: [0, 8, .1], tintAlpha: [0, .7, .01] },
  annotations: { labelSize: [12, 22, 1], enabled: 'boolean', ...typographyRules },
  dock: { width: [56, 108, 1], radius: [12, 48, 1], iconSize: [18, 38, 1], gap: [4, 32, 1], ...glassRules },
  fullCourt: { ...courtRules },
  halfCourt: { ...courtRules },
  controls: { height: [52, 96, 1], radius: [12, 40, 1], fontSize: [12, 24, 1], ...typographyRules, iconSize: [18, 34, 1], gap: [6, 24, 1], ...glassRules },
  content: { width: [300, 640, 10], maxHeight: [300, 900, 10], fontSize: [12, 22, 1], titleSize: [18, 32, 1], ...typographyRules, padding: [12, 36, 1], radius: [12, 40, 1], ...glassRules },
  menus: { width: [280, 480, 10], compactWidth: [96, 220, 4], fontSize: [12, 22, 1], titleSize: [16, 28, 1], ...typographyRules, padding: [12, 32, 1], radius: [8, 36, 1], itemRadius: [6, 24, 1], ...glassRules },
  topbar: { fontSize: [12, 24, 1], ...typographyRules, radius: [8, 32, 1], gap: [4, 28, 1], ...glassRules },
  heading: { fontSize: [18, 40, 1], ...typographyRules, ...glassRules },
  courtTheme: { preset: { enum: ['rockets', 'mavericks'] } },
});

const glassBase = { tint: '#10131c', tintAlpha: .38, color: '#f6f7fa', refraction: .012, frost: 2, bevelDepth: .08, bevelWidth: .15 };
const courtBase = { radius: 28, fontSize: 16, ...typographyBase, woodColor: '#d9ad7a', paintColor: '#aa1734', lineColor: '#fff8ec', lineWidth: .24, markerSize: 2.05, ...glassBase, tint: '#181420', tintAlpha: .42, frost: 3 };
export const baseline = freeze({
  layout: { padding: 16, gap: 16, dockWidth: 72, fullWidth: .24, halfWidth: .30 },
  motion: { open: 350, morph: 300, close: 220, hideDelay: 150, controlsIdle: 2000 },
  appearance: { panelRadius: 28, videoRadius: 20, controlRadius: 22, titleSize: 28, bodySize: 16 },
  glass: { refraction: .012, bevelDepth: .08, bevelWidth: .15, frost: 2, tintAlpha: .38 },
  annotations: { labelSize: 15, enabled: true, ...typographyBase },
  dock: { width: 72, radius: 28, iconSize: 26, gap: 18, ...glassBase, frost: 3, tintAlpha: .4 },
  fullCourt: { width: .24, courtRadius: 10, ...courtBase },
  halfCourt: { width: .30, courtRadius: 8, ...courtBase },
  controls: { height: 66, radius: 22, fontSize: 17, ...typographyBase, iconSize: 26, gap: 16, ...glassBase, tint: '#0c1019' },
  content: { width: 370, maxHeight: 680, fontSize: 13, titleSize: 21, ...typographyBase, padding: 22, radius: 26, ...glassBase, tint: '#191d24', tintAlpha: .56, frost: 3 },
  menus: { width: 350, compactWidth: 120, fontSize: 16, titleSize: 19, ...typographyBase, padding: 22, radius: 24, itemRadius: 15, ...glassBase, tint: '#151c26', tintAlpha: .64, frost: 3 },
  topbar: { fontSize: 16, ...typographyBase, radius: 22, gap: 16, ...glassBase },
  heading: { fontSize: 28, ...typographyBase, ...glassBase },
  courtTheme: { preset: 'mavericks' },
});

const STORAGE_KEY = 'broadcastcode.ui.display.v1';
const PRESETS_KEY = 'broadcastcode.ui.named-presets.v2';
const listeners = new Set();
const clone = value => JSON.parse(JSON.stringify(value));
let current = clone(baseline);
let past = [];
let future = [];
let storageMessage = '';
let editSession = null;

function plain(value) { return value !== null && typeof value === 'object' && !Array.isArray(value) && (Object.getPrototypeOf(value) === Object.prototype || Object.getPrototypeOf(value) === null); }
function validate(candidate, partial = false, rules = schema) {
  if (!plain(candidate)) throw new TypeError('配置必须为对象。');
  for (const group of Object.keys(candidate)) {
    if (!Object.hasOwn(rules, group)) throw new TypeError(`不允许的配置组：${group}`);
    if (!plain(candidate[group])) throw new TypeError(`${group} 必须为对象。`);
    for (const [key, value] of Object.entries(candidate[group])) {
      if (!Object.hasOwn(rules[group], key)) throw new TypeError(`不允许的字段：${group}.${key}`);
      const rule = rules[group][key];
      if (rule === 'boolean') { if (typeof value !== 'boolean') throw new TypeError(`${group}.${key} 必须为布尔值。`); }
      else if (rule === 'color') { if (typeof value !== 'string' || !/^#[0-9a-f]{6}$/i.test(value)) throw new TypeError(`${group}.${key} 必须为 #RRGGBB 颜色。`); }
      else if (rule.enum) { if (typeof value !== 'string' || !rule.enum.includes(value)) throw new TypeError(`${group}.${key} 不在允许选项中。`); }
      else if (typeof value !== 'number' || !Number.isFinite(value) || value < rule[0] || value > rule[1]) throw new RangeError(`${group}.${key} 必须为 ${rule[0]} 至 ${rule[1]} 的数字。`);
    }
    if (!partial) for (const key of Object.keys(rules[group])) if (!Object.hasOwn(candidate[group], key)) throw new TypeError(`缺少字段：${group}.${key}`);
  }
  if (!partial) for (const group of Object.keys(rules)) if (!Object.hasOwn(candidate, group)) throw new TypeError(`缺少配置组：${group}`);
  return candidate;
}

// Read-only compatibility for existing files. Retired art settings never enter
// the current schema, exported config, CSS, inspector, or rendering modules.
const compatibleThemeSchema = { ...schema, courtTheme: { preset: { enum: ['source', 'neutral', 'rockets', 'mavericks'] } } };
function migrateCourtTheme(candidate) {
  validate(candidate, false, compatibleThemeSchema);
  const migrated = clone(candidate);
  if (['source', 'neutral'].includes(migrated.courtTheme.preset)) migrated.courtTheme.preset = 'mavericks';
  return validate(migrated);
}
const legacySchema = freeze({ ...compatibleThemeSchema,
  annotations: { mascotSize: [24, 72, 1], labelSize: [12, 22, 1], enabled: 'boolean' },
  mascot: { size: [24, 72, 1], color: 'color', expression: { enum: ['happy', 'focus'] }, style: { enum: ['classic', 'minimal'] }, labelSize: [12, 22, 1], ...typographyRules },
});
function migrateLegacy(candidate, partial = false) {
  validate(candidate, true, legacySchema);
  const oldGroups = [...typographyGroups.filter(group => group !== 'annotations'), 'mascot'];
  const old = clone(candidate);
  const noTypography = oldGroups.every(group => !Object.hasOwn(old[group] || {}, 'fontFamily') && !Object.hasOwn(old[group] || {}, 'fontWeight'));
  if (noTypography) for (const group of oldGroups) if (plain(old[group])) Object.assign(old[group], typographyBase);
  if (!partial) validate(old, false, legacySchema);
  const migrated = partial ? clone(baseline) : old;
  if (partial) for (const [group, values] of Object.entries(old)) if (group !== 'mascot' && group !== 'annotations') Object.assign(migrated[group], values);
  const annotations = { ...baseline.annotations, ...old.annotations };
  delete annotations.mascotSize;
  if (old.mascot) {
    if (!partial) annotations.labelSize = old.mascot.labelSize;
    annotations.fontFamily = old.mascot.fontFamily ?? typographyBase.fontFamily;
    annotations.fontWeight = old.mascot.fontWeight ?? typographyBase.fontWeight;
  }
  migrated.annotations = annotations;
  delete migrated.mascot;
  return migrateCourtTheme(migrated);
}

function applyTypography() {
  const scopes = {
    fullCourt: ['#court-shell[data-component="fullCourt"]'],
    halfCourt: ['#court-shell[data-component="halfCourt"]'],
    // Bind text branches, not the bar ancestor: the nested rate menu must retain
    // its own typography, even when its settings are left at the original default.
    controls: ['.player-controls .control-button', '.player-controls .media-time', '.player-controls .media-resolution', '.player-controls .sr-only'],
    content: ['[data-component="content"]'],
    menus: ['[data-component="menus"]'],
    topbar: ['#top-tabs'],
    heading: ['#moment-heading'],
    annotations: ['.annotation-layer .annotation-label'],
  };
  const rules = [];
  for (const group of typographyGroups) {
    const config = current[group], declarations = [];
    if (config.fontFamily !== 'default') declarations.push(`font-family:${fontFamilies[config.fontFamily]}!important`);
    if (config.fontWeight !== 'default') declarations.push(`font-weight:${config.fontWeight}!important`);
    if (declarations.length) rules.push(`${scopes[group].flatMap(selector => [selector, `${selector} *`]).join(',')}{${declarations.join(';')}}`);
  }
  let style = document.getElementById('broadcast-component-typography');
  if (!rules.length) { style?.remove(); return; }
  if (!style) { style = document.createElement('style'); style.id = 'broadcast-component-typography'; document.head.append(style); }
  style.textContent = rules.join('\n');
}

function applyVariables() {
  if (typeof document === 'undefined') return;
  const root = document.documentElement;
  const mapping = {
    '--stage-padding': [current.layout.padding, 'px'], '--panel-gap': [current.layout.gap, 'px'], '--dock-width': [current.dock.width, 'px'],
    '--panel-radius': [current.appearance.panelRadius, 'px'], '--video-radius': [current.appearance.videoRadius, 'px'], '--control-radius': [current.controls.radius, 'px'],
    '--title-size': [current.heading.fontSize, 'px'], '--body-size': [current.appearance.bodySize, 'px'],
    '--label-size': [current.annotations.labelSize, 'px'], '--glass-tint-alpha': [current.glass.tintAlpha, ''],
  };
  for (const [key, [value, unit]] of Object.entries(mapping)) root.style.setProperty(key, `${value}${unit}`);
  const pixelFields = new Set(['width', 'radius', 'courtRadius', 'fontSize', 'titleSize', 'size', 'iconSize', 'gap', 'height', 'labelSize', 'padding', 'maxHeight', 'compactWidth', 'itemRadius']);
  for (const group of ['dock', 'controls', 'content', 'menus', 'topbar', 'heading', 'annotations', 'fullCourt', 'halfCourt']) {
    const groupName = group.replace(/[A-Z]/g, ch => `-${ch.toLowerCase()}`);
    for (const [key, value] of Object.entries(current[group])) {
      const name = key.replace(/[A-Z]/g, ch => `-${ch.toLowerCase()}`);
      if (key === 'fontFamily' || key === 'fontWeight') {
        const property = `--${groupName}-${name}`;
        if (value === 'default') root.style.removeProperty(property);
        else root.style.setProperty(property, key === 'fontFamily' ? fontFamilies[value] : value);
        continue;
      }
      const unit = typeof value === 'number' && pixelFields.has(key) && !(key === 'width' && group.endsWith('Court')) ? 'px' : '';
      root.style.setProperty(`--${groupName}-${name}`, `${value}${unit}`);
    }
  }
  applyTypography();
}
function emit() { applyVariables(); listeners.forEach(fn => fn(getConfig(), getConfigStatus())); }
function commit(candidate) {
  validate(candidate);
  if (JSON.stringify(current) === JSON.stringify(candidate)) return getConfig();
  if (!editSession || !editSession.recorded) { past.push(clone(current)); if (past.length > 100) past.shift(); if (editSession) editSession.recorded = true; }
  future = []; current = clone(candidate); emit(); return getConfig();
}
export function getConfig() { return clone(current); }
export function getConfigStatus() { return { schemaVersion: 3, canUndo: past.length > 0, canRedo: future.length > 0, storageMessage, saveScope: '仅本机浏览器' }; }
export function subscribe(fn) { if (typeof fn !== 'function') throw new TypeError('订阅者必须为函数。'); listeners.add(fn); return () => listeners.delete(fn); }
export function beginConfigEdit() { editSession = { recorded: false }; }
export function endConfigEdit() { editSession = null; }
export function updateConfig(patch) {
  validate(patch, true);
  const next = clone(current);
  for (const [group, values] of Object.entries(patch)) Object.assign(next[group], values);
  // Legacy aliases stay usable, while every component keeps an independent surface.
  const aliases = [['layout','dockWidth','dock','width'], ['layout','fullWidth','fullCourt','width'], ['layout','halfWidth','halfCourt','width'], ['appearance','controlRadius','controls','radius'], ['appearance','titleSize','heading','fontSize']];
  for (const [a, ak, b, bk] of aliases) {
    if (Object.hasOwn(patch[b] || {}, bk)) next[a][ak] = next[b][bk];
    else if (Object.hasOwn(patch[a] || {}, ak)) next[b][bk] = next[a][ak];
  }
  if (patch.appearance?.panelRadius !== undefined) for (const group of ['fullCourt', 'halfCourt']) if (patch[group]?.radius === undefined) next[group].radius = patch.appearance.panelRadius;
  // Explicit batch controls cover eight surfaces; scoped edits never propagate to peers.
  if (patch.glass) for (const group of ['dock', 'fullCourt', 'halfCourt', 'controls', 'content', 'menus', 'topbar', 'heading']) for (const [key,value] of Object.entries(patch.glass)) if (patch[group]?.[key] === undefined) next[group][key] = value;
  return commit(next);
}
export function undo() { if (!past.length) return false; future.push(clone(current)); current = past.pop(); emit(); return true; }
export function redo() { if (!future.length) return false; past.push(clone(current)); current = future.pop(); emit(); return true; }
export function resetConfig(group) {
  if (group === undefined) return commit(clone(baseline));
  if (!Object.hasOwn(schema, group)) throw new TypeError(`不允许的配置组：${group}`);
  return updateConfig({ [group]: clone(baseline[group]) });
}
export function exportConfig() { return JSON.stringify({ schemaVersion: 3, presetId: 'broadcastcode-local', config: current }, null, 2); }
function parseImport(json) {
  if (typeof json !== 'string' || json.length > 32768) throw new TypeError('请导入不大于 32 KB 的 JSON 文本。');
  const data = JSON.parse(json);
  if (!plain(data) || Object.keys(data).some(key => !['schemaVersion', 'presetId', 'config'].includes(key))) throw new TypeError('配置文件包含未允许的字段。');
  if (![1, 2, 3].includes(data.schemaVersion) || data.presetId !== 'broadcastcode-local') throw new TypeError('配置版本或预设格式不受支持。');
  if (data.schemaVersion === 1) {
    const migrated = migrateLegacy(data.config, true);
    migrated.dock.width = migrated.layout.dockWidth;
    migrated.fullCourt.width = migrated.layout.fullWidth;
    migrated.halfCourt.width = migrated.layout.halfWidth;
    migrated.fullCourt.radius = migrated.halfCourt.radius = migrated.appearance.panelRadius;
    migrated.controls.radius = migrated.appearance.controlRadius;
    migrated.heading.fontSize = migrated.appearance.titleSize;
    return validate(migrated);
  }
  return data.schemaVersion === 2 ? migrateLegacy(data.config) : migrateCourtTheme(data.config);
}
export function importConfig(json) { return commit(parseImport(json)); }
export function saveConfig() {
  if (typeof localStorage === 'undefined') throw new Error('此浏览器不支持本机保存。');
  try { localStorage.setItem(STORAGE_KEY, exportConfig()); storageMessage = '已保存，仅本机浏览器。'; emit(); return true; }
  catch { storageMessage = '无法保存：浏览器存储不可用或空间不足。'; emit(); throw new Error(storageMessage); }
}
function presetName(name) {
  if (typeof name !== 'string' || !name.trim() || name.trim().length > 48 || /[\u0000-\u001f<>]/.test(name) || ['__proto__', 'constructor', 'prototype'].includes(name.trim())) throw new TypeError('预设名称需为 1–48 字，不能含控制符或尖括号。');
  return name.trim();
}
function readPresets() {
  const text = typeof localStorage !== 'undefined' ? localStorage.getItem(PRESETS_KEY) : null;
  if (!text) return {};
  const value = JSON.parse(text);
  if (!plain(value) || ![2, 3].includes(value.schemaVersion) || !plain(value.presets)) throw new Error('本机预设列表格式无效，未覆盖原存储。');
  const result = {};
  for (const [name, item] of Object.entries(value.presets)) { presetName(name); if (!plain(item) || typeof item.updatedAt !== 'string') throw new Error('预设记录格式无效。'); result[name] = { ...clone(item), config: value.schemaVersion === 2 ? migrateLegacy(item.config) : migrateCourtTheme(item.config) }; }
  return result;
}
function writePresets(presets) {
  if (typeof localStorage === 'undefined') throw new Error('此浏览器不支持本机保存。');
  if (Object.keys(presets).length > 50) throw new Error('最多保存 50 个命名预设。');
  localStorage.setItem(PRESETS_KEY, JSON.stringify({ schemaVersion: 3, presets }));
}
export function listPresets() { return Object.entries(readPresets()).map(([name, data]) => ({ name, updatedAt: data.updatedAt })).sort((a,b) => a.name.localeCompare(b.name, 'zh-CN')); }
export function savePreset(name, { overwrite = false } = {}) {
  name = presetName(name); const presets = readPresets();
  if (Object.hasOwn(presets, name) && !overwrite) throw new Error('同名预设已存在。选择它并点击“更新”即可覆盖。');
  presets[name] = { updatedAt: new Date().toISOString(), config: getConfig() }; writePresets(presets); return name;
}
export function loadPreset(name) { name = presetName(name); const presets = readPresets(); if (!Object.hasOwn(presets, name)) throw new Error('预设不存在。'); return commit(presets[name].config); }
export function deletePreset(name) { name = presetName(name); const presets = readPresets(); if (!Object.hasOwn(presets,name)) throw new Error('预设不存在。'); delete presets[name]; writePresets(presets); return true; }
export function renamePreset(oldName, newName) { oldName = presetName(oldName); newName = presetName(newName); const presets = readPresets(); if (!Object.hasOwn(presets, oldName)) throw new Error('预设不存在。'); if (oldName === newName) return newName; if (Object.hasOwn(presets, newName)) throw new Error('新名称已存在。'); presets[newName] = presets[oldName]; delete presets[oldName]; writePresets(presets); return newName; }
// Loading is read-only; previews are persisted only after the explicit save action.
try { const saved = typeof localStorage !== 'undefined' ? localStorage.getItem(STORAGE_KEY) : null; if (saved) { current = clone(parseImport(saved)); storageMessage = '已读取本机预设。'; } }
catch { storageMessage = '本机预设无效，已使用参考基线；原存储未覆盖。'; }
applyVariables();
