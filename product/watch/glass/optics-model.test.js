import test from 'node:test';
import assert from 'node:assert/strict';
import {FROST_KERNEL, opticalMetrics, sampleSmoothFrost, tiltDisplacementCss, opticsShaderVariant} from './optics-model.js';

test('smooth frost kernel is positive, normalized and symmetric, with zero positional bias', () => {
  assert.equal(FROST_KERNEL.length, 25);
  assert.ok(FROST_KERNEL.every(t => t.weight > 0));
  assert.ok(Math.abs(FROST_KERNEL.reduce((s, t) => s + t.weight, 0) - 1) < 1e-14);
  assert.ok(Math.abs(FROST_KERNEL.reduce((s, t) => s + t.x * t.weight, 0)) < 1e-14);
  for (const tap of FROST_KERNEL) {
    assert.equal(tap.weight, FROST_KERNEL.find(t => t.x === -tap.x && t.y === -tap.y).weight);
  }
});

test('the common runtime selects static colorless and unstacked shader paths with 25 source fetches', () => {
  assert.deepEqual(opticsShaderVariant(0, false), {key:0, chromatic:false, stack:false, name:'clear-source', sourceSamples:25, maxTextureSamples:25});
  assert.equal(opticsShaderVariant(.003, false).key, 1);
  assert.equal(opticsShaderVariant(0, true).key, 2);
  assert.equal(opticsShaderVariant(.003, true).key, 3);
  assert.equal(opticsShaderVariant(.003, false).sourceSamples, 75);
  assert.equal(opticsShaderVariant(0, true).maxTextureSamples, 50);
});

test('every adjacent fragment receives the same blur: constant and affine scenes retain smooth pixels', () => {
  for (let y = -6; y <= 6; y += .5) for (let x = -6; x <= 6; x += .5) {
    assert.ok(Math.abs(sampleSmoothFrost(() => .75, x, y, 4.8) - .75) < 1e-12);
    const source = (sx, sy) => .4 + sx * .01 + sy * .015;
    assert.ok(Math.abs(sampleSmoothFrost(source, x, y, 4.8) - source(x, y)) < 1e-12);
  }
});

test('fixed frost softens a contrast edge continuously without overshoot or separated bright copies', () => {
  // Bilinear sampling of a one-pixel transition between black and white.
  const edge = (x) => Math.max(0, Math.min(1, x + .5));
  const values = Array.from({length: 129}, (_, i) => sampleSmoothFrost(edge, -8 + i / 8, 0, 4.8));
  assert.equal(values[0], 0);
  assert.ok(Math.abs(values.at(-1) - 1) < 1e-12);
  for (let i = 1; i < values.length; i++) {
    assert.ok(values[i] >= values[i - 1] - 1e-12);
    assert.ok(values[i] - values[i - 1] < .05);
  }
  assert.ok(Math.abs(values[64] - .5) < 1e-12);
});

test('frost zero remains a genuinely clear sample, and supported values continuously increase bounded softness', () => {
  const scene = (x, y) => .2 + Math.sin(x * .8 + y * .2) * .1;
  assert.ok(Math.abs(sampleSmoothFrost(scene, 2, 3, 0) - scene(2, 3)) < 1e-12);
  let last = -1;
  for (let frost = 0; frost <= 16; frost += .1) {
    const radius = opticalMetrics({frost}).frostRadiusCss;
    assert.ok(radius > last);
    assert.ok(radius < 8);
    last = radius;
  }
  assert.equal(opticalMetrics({frost: 3}).frostRadiusCss, 4.8);
});

test('edge refraction is a bounded CSS-pixel distance independent of source size and DPR', () => {
  const options = {refraction: .012, bevelDepth: .08, frost: 3, aberration: .003};
  for (const [cssW, cssH, scale] of [[1440, 810, 1], [1920, 1080, 1], [1440, 810, 2], [1440, 810, .5]]) {
    const metrics = opticalMetrics(options, {width: cssW * scale, height: cssH * scale, scaleFactor: scale});
    assert.ok(Math.abs(metrics.maxOffsetCss - 6.72) < 1e-12);
    assert.ok(Math.abs(metrics.sourcePixelSize[0] * cssW - 1) < 1e-12);
    assert.ok(Math.abs(metrics.sourcePixelSize[1] * cssH - 1) < 1e-12);
    assert.ok(Math.abs(metrics.sourcePixelSize[0] * metrics.maxOffsetCss * cssW - 6.72) < 1e-12);
  }
  assert.ok(opticalMetrics({refraction: 10, bevelDepth: 10}).maxOffsetCss <= 20);
  assert.equal(tiltDisplacementCss(0), 0);
  assert.equal(tiltDisplacementCss(80), 12);
});
