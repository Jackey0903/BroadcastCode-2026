import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const fixture = JSON.parse(readFileSync(new URL('./fixtures/display-v2.json', import.meta.url)));
const copy = value => JSON.parse(JSON.stringify(value));
let serial = 0;
const fresh = () => import(`../config/config.js?migration-test=${++serial}`);
const storageKey = 'broadcastcode.ui.display.v1';
const presetsKey = 'broadcastcode.ui.named-presets.v2';
function assertPreserved(api, old) {
  const next = api.getConfig();
  for (const [group, value] of Object.entries(old)) {
    if (!['mascot', 'annotations'].includes(group)) assert.deepEqual(next[group], value, `${group} changed during migration`);
  }
  assert.deepEqual(next.annotations, { enabled: old.annotations.enabled, labelSize: old.mascot.labelSize, fontFamily: old.mascot.fontFamily || 'default', fontWeight: old.mascot.fontWeight || 'default' });
  assert.equal(Object.hasOwn(next, 'mascot'), false);
  assert.equal(Object.hasOwn(next.annotations, 'mascotSize'), false);
}

test('old full display files preserve all remaining settings and export only current fields', async () => {
  const api = await fresh(); const file = copy(fixture);
  file.config.controls.frost = 1; file.config.controls.tintAlpha = .24;
  file.config.halfCourt.width = .36; file.config.heading.fontFamily = 'songti';
  file.config.courtTheme.preset = 'mavericks';
  file.config.mascot.labelSize = 18; file.config.mascot.fontFamily = 'mono'; file.config.mascot.fontWeight = '600';
  api.importConfig(JSON.stringify(file)); assertPreserved(api, file.config);
  const exported = JSON.parse(api.exportConfig()); assert.equal(exported.schemaVersion, 3);
  assert.equal(JSON.stringify(exported).includes('mascot'), false);
  assert.throws(() => api.updateConfig({ mascot: { size: 50 } }));
  assert.throws(() => api.updateConfig({ annotations: { mascotSize: 50 } }));
  api.undo(); assert.deepEqual(api.getConfig(), api.baseline); api.redo(); assertPreserved(api, file.config);
});

test('pre-typography display files migrate without changing layout or optics', async () => {
  const api = await fresh(); const file = copy(fixture);
  for (const group of Object.values(file.config)) { delete group.fontFamily; delete group.fontWeight; }
  file.config.dock.gap = 20; file.config.fullCourt.frost = 7;
  api.importConfig(JSON.stringify(file));
  for (const [group, values] of Object.entries(file.config)) {
    if (['mascot', 'annotations'].includes(group)) continue;
    for (const [key, value] of Object.entries(values)) assert.equal(api.getConfig()[group][key], group === 'courtTheme' && ['source', 'neutral'].includes(value) ? 'mavericks' : value);
  }
  assert.equal(api.getConfig().annotations.fontFamily, 'default');
});

test('stored current and named legacy presets remain readable without silently overwriting storage', async () => {
  const previous = globalThis.localStorage; const current = copy(fixture);
  current.config.controls.frost = 1; current.config.courtTheme.preset = 'rockets';
  const saved = JSON.stringify(current);
  const named = JSON.stringify({ schemaVersion: 2, presets: { 'Apple TV 材质对照': { updatedAt: '2026-10-10T01:00:00Z', config: current.config } } });
  const store = new Map([[storageKey, saved], [presetsKey, named]]);
  globalThis.localStorage = { getItem: key => store.get(key) ?? null, setItem: (key, value) => store.set(key, value) };
  try {
    const api = await fresh(); assertPreserved(api, current.config);
    assert.match(api.getConfigStatus().storageMessage, /已读取/);
    assert.equal(api.listPresets()[0].name, 'Apple TV 材质对照');
    api.loadPreset('Apple TV 材质对照'); assertPreserved(api, current.config);
    assert.equal(store.get(storageKey), saved); assert.equal(store.get(presetsKey), named);
    api.savePreset('无角色新版');
    const all = JSON.parse(store.get(presetsKey)); assert.equal(all.schemaVersion, 3);
    assert.equal(JSON.stringify(all).includes('mascot'), false);
    api.loadPreset('Apple TV 材质对照'); assertPreserved(api, current.config);
    api.saveConfig(); assert.equal(JSON.stringify(JSON.parse(store.get(storageKey))).includes('mascot'), false);
  } finally { if (previous === undefined) delete globalThis.localStorage; else globalThis.localStorage = previous; }
});

test('malformed legacy fields fail atomically and cannot bypass the configuration boundary', async () => {
  const api = await fresh(); api.updateConfig({ controls: { frost: 1 } });
  for (const mutate of [
    c => { c.mascot.size = '50'; },
    c => { c.mascot.endpoint = 'https://example.test/'; },
    c => { delete c.controls.fontWeight; },
    c => { c.annotations.mascotSize = 999; },
    c => { Object.defineProperty(c.mascot, '__proto__', { value: { polluted: true }, enumerable: true }); },
  ]) {
    const file = copy(fixture); mutate(file.config); const before = api.exportConfig(); const status = api.getConfigStatus();
    assert.throws(() => api.importConfig(JSON.stringify(file)));
    assert.equal(api.exportConfig(), before); assert.deepEqual(api.getConfigStatus(), status);
  }
  assert.equal({}.polluted, undefined);
});


test('two court skins default to Dallas and retired saved choices migrate without changing other settings', async () => {
  const api = await fresh();
  assert.equal(api.baseline.courtTheme.preset, 'mavericks');
  assert.deepEqual(api.schema.courtTheme.preset.enum, ['rockets', 'mavericks']);
  for (const preset of ['source', 'neutral', 'rockets', 'mavericks']) {
    const file = JSON.parse(api.exportConfig());
    file.config.courtTheme.preset = preset; file.config.halfCourt.width = .36;
    api.importConfig(JSON.stringify(file));
    assert.equal(api.getConfig().courtTheme.preset, ['source', 'neutral'].includes(preset) ? 'mavericks' : preset);
    assert.equal(api.getConfig().halfCourt.width, .36);
  }
  api.resetConfig('courtTheme'); assert.equal(api.getConfig().courtTheme.preset, 'mavericks');
});
