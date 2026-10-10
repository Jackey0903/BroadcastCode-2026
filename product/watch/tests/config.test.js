import test from 'node:test';
import assert from 'node:assert/strict';

let instance = 0;
const fresh = () => import(`../config/config.js?test-instance=${++instance}`);
const copy = value => JSON.parse(JSON.stringify(value));
const envelope = (api, config) => ({ ...JSON.parse(api.exportConfig()), config });
const numericRule = value => Array.isArray(value) && value.length >= 2 && typeof value[0] === 'number' && typeof value[1] === 'number';
function alternate(group, values, schema) {
  for (const [key, value] of Object.entries(values)) {
    const rule = schema[group][key];
    if (typeof value === 'boolean') return { [key]: !value };
    if (numericRule(rule) && !['fullWidth', 'halfWidth'].includes(key)) return { [key]: value === rule[0] ? rule[1] : rule[0] };
    if (rule === 'color') return { [key]: value.toLowerCase() === '#123456' ? '#abcdef' : '#123456' };
    if (rule?.enum) return { [key]: rule.enum.find(option => option !== value) };
  }
  throw new Error(`No independent display field found in ${group}`);
}
function unchangedAfterFailure(api, operation) {
  const config = api.getConfig();
  const exported = api.exportConfig();
  const status = api.getConfigStatus();
  assert.throws(operation);
  assert.deepEqual(api.getConfig(), config, 'invalid operation changed current settings');
  assert.equal(api.exportConfig(), exported, 'invalid operation changed exported settings');
  assert.deepEqual(api.getConfigStatus(), status, 'invalid operation changed undo/redo or storage state');
}

test('reference baseline is deeply frozen and returned settings are independent copies', async () => {
  const api = await fresh();
  const config = api.getConfig();
  assert.deepEqual(config, api.baseline);
  assert.ok(Object.isFrozen(api.baseline));
  for (const group of Object.keys(api.baseline)) assert.ok(Object.isFrozen(api.baseline[group]));
  const patch = alternate('layout', config.layout, api.schema);
  Object.assign(config.layout, patch);
  assert.deepEqual(api.getConfig(), api.baseline);
  assert.throws(() => { api.baseline.layout.padding = 1000; });
});

test('component settings stay independent, with only documented legacy aliases and bulk groups propagating', async () => {
  const api = await fresh();
  const allowedPropagation = {
    layout: ['dock', 'fullCourt', 'halfCourt'], appearance: ['fullCourt', 'halfCourt', 'controls', 'heading'],
    glass: ['dock', 'fullCourt', 'halfCourt', 'controls', 'content', 'menus', 'topbar', 'heading'],
    dock: ['layout'], fullCourt: ['layout'], halfCourt: ['layout'], controls: ['appearance'],
    heading: ['appearance'],
  };
  for (const group of Object.keys(api.baseline)) {
    api.resetConfig();
    const before = api.getConfig();
    const patch = alternate(group, before[group], api.schema);
    api.updateConfig({ [group]: patch });
    const updated = api.getConfig();
    for (const other of Object.keys(before)) {
      if (other !== group && !(allowedPropagation[group] || []).includes(other)) assert.deepEqual(updated[other], before[other], `${group} update affected unrelated ${other}`);
    }
    assert.notDeepEqual(updated[group], before[group]);
    assert.equal(api.undo(), true);
    assert.deepEqual(api.getConfig(), before);
    assert.equal(api.redo(), true);
    assert.deepEqual(api.getConfig(), updated);
    api.resetConfig(group);
    assert.deepEqual(api.getConfig()[group], api.baseline[group]);
  }
});

test('resetting a group preserves other customized groups', async () => {
  const api = await fresh();
  const groups = Object.keys(api.baseline);
  const first = groups[0], second = groups[1];
  api.updateConfig({ [first]: alternate(first, api.baseline[first], api.schema), [second]: alternate(second, api.baseline[second], api.schema) });
  const customized = api.getConfig();
  api.resetConfig(first);
  assert.deepEqual(api.getConfig()[first], api.baseline[first]);
  assert.deepEqual(api.getConfig()[second], customized[second]);
});

test('export/import round-trips exact display values and imported objects are copied', async () => {
  const api = await fresh();
  api.updateConfig({ layout: alternate('layout', api.baseline.layout, api.schema) });
  const expected = api.getConfig();
  const exported = api.exportConfig();
  api.resetConfig();
  api.importConfig(exported);
  assert.deepEqual(api.getConfig(), expected);
  assert.equal(api.exportConfig(), exported);
  api.undo();
  assert.deepEqual(api.getConfig(), api.baseline);
  api.redo();
  assert.deepEqual(api.getConfig(), expected);
});

test('new edits after undo clear the redo branch, while invalid edits leave it intact', async () => {
  const api = await fresh();
  api.updateConfig({ layout: alternate('layout', api.baseline.layout, api.schema) });
  api.undo();
  assert.equal(api.getConfigStatus().canRedo, true);
  unchangedAfterFailure(api, () => api.updateConfig({ layout: { padding: -1 } }));
  assert.equal(api.redo(), true);
  api.undo();
  api.updateConfig({ motion: alternate('motion', api.baseline.motion, api.schema) });
  assert.equal(api.redo(), false);
});

test('numeric and boolean fields reject illegal types, nonfinite numbers and out-of-range imports atomically', async () => {
  const api = await fresh();
  api.updateConfig({ layout: alternate('layout', api.baseline.layout, api.schema) });
  for (const [group, fields] of Object.entries(api.schema)) {
    for (const [key, rule] of Object.entries(fields)) {
      const invalid = numericRule(rule) ? [rule[0] - 1, rule[1] + 1, NaN, Infinity, -Infinity, '1', null, true, [], {}]
        : rule === 'boolean' ? [0, 1, 'true', null, [], {}]
        : rule === 'color' ? ['#fff', '#gggggg', '#11223344', 'red', 'url(javascript:alert(1))', ' #123456', 123456, null, true, [], {}]
        : rule?.enum ? ['__proto__', 'not-an-option', null, 1, true, [], {}] : [];
      for (const value of invalid) {
        unchangedAfterFailure(api, () => api.updateConfig({ [group]: { [key]: value } }));
        const candidate = api.getConfig(); candidate[group][key] = value;
        unchangedAfterFailure(api, () => api.importConfig(JSON.stringify(envelope(api, candidate))));
      }
    }
  }
});

test('legal minimum and maximum numeric display values are accepted', async () => {
  const api = await fresh();
  for (const [group, fields] of Object.entries(api.schema)) {
    for (const [key, rule] of Object.entries(fields)) {
      if (!numericRule(rule)) continue;
      for (const value of [rule[0], rule[1]]) {
        const candidate = copy(api.baseline);
        candidate[group][key] = value;
        api.importConfig(JSON.stringify(envelope(api, candidate)));
        assert.equal(api.getConfig()[group][key], value, `${group}.${key} rejected its legal boundary`);
      }
    }
  }
});

test('reference half court is wider, while customized full/half widths accept their own declared ranges', async () => {
  const api = await fresh();
  assert.equal(api.baseline.fullCourt.width, .24);
  assert.equal(api.baseline.halfCourt.width, .30);
  api.updateConfig({ fullCourt: { width: api.schema.fullCourt.width[1] }, halfCourt: { width: api.schema.halfCourt.width[0] } });
  assert.equal(api.getConfig().fullCourt.width, api.schema.fullCourt.width[1]);
  assert.equal(api.getConfig().halfCourt.width, api.schema.halfCourt.width[0]);
  assert.equal(api.getConfig().layout.fullWidth, api.getConfig().fullCourt.width);
  assert.equal(api.getConfig().layout.halfWidth, api.getConfig().halfCourt.width);
  const exported = api.exportConfig(); api.resetConfig(); api.importConfig(exported);
  assert.equal(api.getConfig().fullCourt.width, api.schema.fullCourt.width[1]);
  assert.equal(api.getConfig().halfCourt.width, api.schema.halfCourt.width[0]);
});

test('legacy bulk glass changes propagate while explicit component overrides and sibling independence remain intact', async () => {
  const api = await fresh();
  api.updateConfig({ glass: { frost: 5 }, fullCourt: { frost: 1 } });
  assert.equal(api.getConfig().glass.frost, 5);
  assert.equal(api.getConfig().fullCourt.frost, 1);
  for (const group of ['dock', 'halfCourt', 'controls']) assert.equal(api.getConfig()[group].frost, 5);
  const before = api.getConfig();
  api.updateConfig({ dock: { tint: '#abcdef', frost: 7, width: 90 } });
  for (const group of ['fullCourt', 'halfCourt', 'controls', 'glass']) assert.deepEqual(api.getConfig()[group], before[group]);
  assert.equal(api.getConfig().layout.dockWidth, 90);
  api.updateConfig({ appearance: { panelRadius: 36 } });
  assert.equal(api.getConfig().fullCourt.radius, 36);
  assert.equal(api.getConfig().halfCourt.radius, 36);
});

test('valid colors and enum options round-trip without entering content or data fields', async () => {
  const api = await fresh();
  for (const [group, fields] of Object.entries(api.schema)) {
    for (const [key, rule] of Object.entries(fields)) {
      const values = rule === 'color' ? ['#000000', '#FFFFFF', '#1a2B3c'] : rule?.enum || [];
      for (const value of values) {
        api.updateConfig({ [group]: { [key]: value } });
        assert.equal(api.getConfig()[group][key], value);
        api.importConfig(api.exportConfig());
        assert.equal(api.getConfig()[group][key], value);
      }
    }
  }
});

test('one continuous parameter edit undoes as one action', async () => {
  const api = await fresh();
  const before = api.getConfig();
  api.beginConfigEdit();
  for (const padding of [17, 18, 19, 20]) api.updateConfig({ layout: { padding } });
  api.endConfigEdit();
  assert.equal(api.getConfig().layout.padding, 20);
  assert.equal(api.undo(), true);
  assert.deepEqual(api.getConfig(), before);
  assert.equal(api.redo(), true);
  assert.equal(api.getConfig().layout.padding, 20);
});

test('unknown fields, resource URLs, data facts and prototype pollution keys cannot enter configuration', async () => {
  const api = await fresh();
  for (const patch of [
    { backend: { endpoint: 'https://example.test/' } },
    { media: { src: 'https://example.test/video.mp4' } },
    { layout: { position: 20 } },
    { annotations: { playerName: 'guessed identity' } },
    { glass: { constructor: 'forbidden' } },
    JSON.parse('{"__proto__":{"polluted":true}}'),
    JSON.parse('{"layout":{"__proto__":{"polluted":true}}}'),
    JSON.parse('{"layout":{"prototype":{"polluted":true}}}'),
  ]) {
    unchangedAfterFailure(api, () => api.updateConfig(patch));
    const candidate = api.getConfig();
    for (const [group, fields] of Object.entries(patch)) {
      if (Object.hasOwn(candidate, group)) Object.defineProperties(candidate[group], Object.getOwnPropertyDescriptors(fields));
      else Object.defineProperty(candidate, group, { value: fields, enumerable: true });
    }
    unchangedAfterFailure(api, () => api.importConfig(JSON.stringify(envelope(api, candidate))));
  }
  assert.equal({}.polluted, undefined);
});

test('malformed, partial, wrong-version and oversize imports cannot replace valid settings', async () => {
  const api = await fresh();
  api.updateConfig({ layout: alternate('layout', api.baseline.layout, api.schema) });
  const base = JSON.parse(api.exportConfig());
  const missing = copy(base); delete missing.config.layout.padding;
  const missingGroup = copy(base); delete missingGroup.config.layout;
  const foreignGroupType = copy(base); foreignGroupType.config.layout = [];
  for (const value of [
    '', '{', null, {}, '[]', 'null', ' '.repeat(32769),
    JSON.stringify({ ...base, schemaVersion: '1' }),
    JSON.stringify({ ...base, schemaVersion: 999 }),
    JSON.stringify({ ...base, presetId: 'untrusted-preset' }),
    JSON.stringify({ ...base, url: 'https://example.test/' }),
    JSON.stringify(missing), JSON.stringify(missingGroup), JSON.stringify(foreignGroupType),
  ]) unchangedAfterFailure(api, () => api.importConfig(value));
});

test('patch validation is transactional when one group is valid and another is invalid', async () => {
  const api = await fresh();
  unchangedAfterFailure(api, () => api.updateConfig({ layout: alternate('layout', api.baseline.layout, api.schema), glass: { refraction: '0.02' } }));
  unchangedAfterFailure(api, () => api.updateConfig(null));
  unchangedAfterFailure(api, () => api.updateConfig([]));
  unchangedAfterFailure(api, () => api.updateConfig({ layout: Object.create({ padding: 20 }) }));
  unchangedAfterFailure(api, () => api.resetConfig('__proto__'));
});
