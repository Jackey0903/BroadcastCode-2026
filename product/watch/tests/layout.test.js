import test from 'node:test';
import assert from 'node:assert/strict';
import { geometry, fitContain } from '../stage/layout.js';
import { baseline, schema } from '../config/config.js';

const EPSILON = 1e-7;
const VIEWPORTS = [[1672, 941], [1440, 900], [1920, 1080], [1280, 720]];
const ASPECTS = [16 / 9, 1280 / 900];
const copy = value => JSON.parse(JSON.stringify(value));

function assertContained(rect, width, height, label) {
  for (const [key, value] of Object.entries(rect)) assert.ok(Number.isFinite(value), `${label}.${key} must be finite`);
  assert.ok(rect.width >= 0 && rect.height > 0, `${label} dimensions must be nonnegative`);
  assert.ok(rect.x >= -EPSILON && rect.y >= -EPSILON, `${label} starts outside viewport: ${JSON.stringify(rect)}`);
  assert.ok(rect.x + rect.width <= width + EPSILON, `${label} right edge exceeds ${width}: ${JSON.stringify(rect)}`);
  assert.ok(rect.y + rect.height <= height + EPSILON, `${label} bottom edge exceeds ${height}: ${JSON.stringify(rect)}`);
}
function assertDisjoint(a, b, label) {
  const separated = a.x + a.width <= b.x + EPSILON || b.x + b.width <= a.x + EPSILON || a.y + a.height <= b.y + EPSILON || b.y + b.height <= a.y + EPSILON;
  assert.ok(separated, `${label} overlap: ${JSON.stringify({ a, b })}`);
}
function assertFrame(frame, width, height, aspect, context) {
  assertContained(frame.video, width, height, `${context}: video`);
  assertContained(frame.panel, width, height, `${context}: panel`);
  assertContained(frame.controls, width, height, `${context}: controls`);
  assert.ok(Math.abs(frame.video.width / frame.video.height - aspect) < EPSILON, `${context}: video aspect ratio changed`);
  if (frame.panel.width > EPSILON) {
    assertDisjoint(frame.video, frame.panel, `${context}: court/video`);
    assertDisjoint(frame.controls, frame.panel, `${context}: court/controls`);
    assert.ok(frame.video.x + frame.video.width <= frame.panel.x + EPSILON, `${context}: court must stay to the right of the video`);
  }
}

function layoutBoundaryConfigs() {
  const keys = ['padding', 'gap', 'dockWidth', 'fullWidth', 'halfWidth'];
  const configs = [copy(baseline)];
  for (let mask = 0; mask < 2 ** keys.length; mask++) {
    const config = copy(baseline);
    keys.forEach((key, index) => { config.layout[key] = schema.layout[key][(mask >> index) & 1]; });
    // V2 component widths share the same allowed range; custom full may exceed half.
    for (const controlHeight of [schema.controls.height[0], schema.controls.height[1]]) {
      const candidate = copy(config);
      candidate.controls.height = controlHeight;
      configs.push(candidate);
    }
  }
  return configs;
}

test('fitContain preserves both raw and historical enhanced-video aspect ratios', () => {
  for (const [width, height] of VIEWPORTS) {
    for (const aspect of ASPECTS) {
      for (const [slotWidth, slotHeight] of [[width, height], [width * .4, height * .8], [width * .8, height * .3], [1, 1]]) {
        const fitted = fitContain(slotWidth, slotHeight, aspect);
        assert.ok(fitted.width > 0 && fitted.height > 0);
        assert.ok(fitted.width <= slotWidth + EPSILON && fitted.height <= slotHeight + EPSILON);
        assert.ok(Math.abs(fitted.width / fitted.height - aspect) < EPSILON);
        assert.ok(Math.abs(fitted.width - slotWidth) < EPSILON || Math.abs(fitted.height - slotHeight) < EPSILON, 'contain must use all available width or height');
      }
    }
  }
});

const paths = {
  'immersive → full': t => [t, 0],
  'full → half': t => [1, t],
  'half → full': t => [1, 1 - t],
  'half → immersive': t => [1 - t, 1 - t],
  'full → immersive': t => [1 - t, 0],
  'single edge → continuous half': t => {
    const open = 1 - (1 - Math.min(1, t / .70)) ** 3;
    const z = Math.min(1, t / .95);
    return [open, z * z * (3 - 2 * z)];
  },
};

for (const [width, height] of VIEWPORTS) {
  for (const aspect of ASPECTS) {
    test(`${width}×${height}, aspect ${aspect}: every transition stays disjoint and inside the viewport at legal layout extremes`, () => {
      for (const [index, config] of layoutBoundaryConfigs().entries()) {
        for (const [path, progress] of Object.entries(paths)) {
          for (let sample = 0; sample <= 100; sample++) {
            const [open, half] = progress(sample / 100);
            assertFrame(geometry(width, height, aspect, open, half, config), width, height, aspect, `config ${index}, ${path}, ${sample}%`);
          }
        }
      }
    });
  }
}

test('interrupted and reversed transitions are safe for independent open/half values', () => {
  for (const [width, height] of VIEWPORTS) {
    for (const aspect of ASPECTS) {
      for (let open = 0; open <= 100; open++) {
        for (let half = 0; half <= 100; half++) {
          assertFrame(geometry(width, height, aspect, open / 100, half / 100, baseline), width, height, aspect, `interrupted open=${open}, half=${half}`);
        }
      }
    }
  }
});

test('full court remains a distinct manually holdable state', () => {
  for (const [width, height] of VIEWPORTS) {
    const full = geometry(width, height, 16 / 9, 1, 0, baseline);
    const half = geometry(width, height, 16 / 9, 1, 1, baseline);
    assert.ok(full.panel.width > 0);
    assert.ok(half.panel.width > full.panel.width);
    assert.deepEqual(geometry(width, height, 16 / 9, 1, 0, baseline), full, 'holding full must not advance toward half');
  }
});

test('the geometry function is pure and transition geometry is continuous', () => {
  const config = copy(baseline);
  const before = copy(config);
  for (const progress of Object.values(paths)) {
    let previous = null;
    for (let sample = 0; sample <= 100; sample++) {
      const [open, half] = progress(sample / 100);
      const next = geometry(1672, 941, 16 / 9, open, half, config);
      if (previous) {
        for (const name of ['video', 'panel', 'controls']) {
          for (const key of ['x', 'y', 'width', 'height']) {
            assert.ok(Math.abs(next[name][key] - previous[name][key]) < 1672 * .05, `${name}.${key} jumps between consecutive 1% samples`);
          }
        }
      }
      previous = next;
    }
  }
  assert.deepEqual(config, before, 'calculating layout must not mutate display settings');
});
