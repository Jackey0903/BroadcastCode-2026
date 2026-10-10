import test from 'node:test';
import assert from 'node:assert/strict';

// In-memory configuration checks only: never calls saveConfig/savePreset or a browser.
const surfaces = ['dock', 'fullCourt', 'halfCourt', 'controls', 'content', 'menus', 'topbar', 'heading'];
const optics = ['tint', 'tintAlpha', 'color', 'refraction', 'frost', 'bevelDepth', 'bevelWidth'];
let instance = 0;
const fresh = () => import(`../config/config.js?glass-contract=${++instance}`);

test('all eight visual surfaces expose complete independent glass schema and baseline values', async () => {
  const api = await fresh();
  for (const group of surfaces) for (const field of optics) {
    assert.ok(Object.hasOwn(api.schema[group], field), `${group}.${field} must be adjustable`);
    assert.ok(Object.hasOwn(api.baseline[group], field), `${group}.${field} must have a reference value`);
  }
});

test('changing any individual glass surface preserves every other surface exactly', async () => {
  const api = await fresh();
  for (const group of surfaces) {
    api.resetConfig();
    const before = api.getConfig();
    api.updateConfig({ [group]: { tint: '#183652', tintAlpha: .57, color: '#c4d8ee', refraction: .027, frost: 4.1, bevelDepth: .12, bevelWidth: .23 } });
    const after = api.getConfig();
    assert.equal(after[group].refraction, .027);
    for (const peer of surfaces.filter(name => name !== group)) assert.deepEqual(after[peer], before[peer], `${group} must not alter ${peer}`);
    api.undo(); assert.deepEqual(api.getConfig(), before, `${group} adjustment must undo as one operation`);
  }
});

test('the explicit batch glass group updates eight surfaces and allows a same-patch scoped override', async () => {
  const api = await fresh();
  api.resetConfig();
  api.updateConfig({ glass: { refraction: .025, frost: 4 }, heading: { frost: 2.7 } });
  const after = api.getConfig();
  for (const group of surfaces) {
    assert.equal(after[group].refraction, .025, `${group} missing batch update`);
    assert.equal(after[group].frost, group === 'heading' ? 2.7 : 4, `${group} must honor scoped override precedence`);
  }
});
