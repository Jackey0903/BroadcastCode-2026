import test from 'node:test';
import assert from 'node:assert/strict';
import { GlassManager } from './glass-manager.js';
import { paintAmbienceSource } from './ambience-source.js';
import { baseline } from '../config/config.js';

function stageFixture() {
 const properties = new Map();
 const target = { closest: () => null, style: { setProperty: (key, value) => properties.set(key, value) } };
 return { dataset: {}, querySelectorAll: () => [target], properties };
}
test('normal startup uses CSS without initializing liquidGL or changing saved optics', () => {
 const stage = stageFixture(), config = structuredClone(baseline), before = structuredClone(config);
 const manager = new GlassManager(stage, () => config);
 manager.start(); manager.apply(); manager.start();
 assert.equal(manager.enabled, false);
 assert.equal(manager.ready, true);
 assert.equal(stage.dataset.glass, 'css');
 assert.equal(manager.lenses.size, 0);
 assert.deepEqual(manager.errors, []); // liquidGL is unavailable in Node: any initialization would fail.
 assert.deepEqual(config, before);
 assert.ok(stage.properties.get('--material-tint').startsWith('rgba('));
});
test('returning from an explicitly enabled effect destroys lenses and returns to CSS', () => {
 const stage = stageFixture(), manager = new GlassManager(stage, () => baseline, { enabled: true });
 let destroyed = 0;
 manager.lenses.set({}, { destroy: () => destroyed++ });
 manager.setEnabled(false);
 assert.equal(destroyed, 1);
 assert.equal(manager.lenses.size, 0);
 assert.equal(stage.dataset.glass, 'css');
 assert.equal(manager.ready, true);
});
test('CSS mode suppresses stale ambience resize callbacks before any video/canvas access', () => {
 const forbidden = new Proxy({}, { get() { throw new Error('Unexpected video or canvas access'); } });
 assert.doesNotThrow(() => paintAmbienceSource(forbidden, forbidden, { dataset: { glass: 'css' } }));
});
