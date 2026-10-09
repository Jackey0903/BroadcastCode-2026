"use strict";

// Offline checks for the decorative pixel layer. No browser, network or real canvas.
const test = require("node:test");
const assert = require("node:assert/strict");
const arcade = require("./arcade.js");
const { bitmapFromAlpha, blockScale, bandColor, revealOrder, spritePixels, courtLayout, ballState,
  createTicker, initStickyStage, init, LOOP, ART_HEIGHT, STILL_FRAME, PALETTES } = arcade;

function alpha(width, height, lit) {
  const data = new Uint8ClampedArray(width * height * 4);
  for (const [x, y, a = 255] of lit) data[(y * width + x) * 4 + 3] = a;
  return data;
}

test("glyph bitmaps are thresholded and cropped to their lit pixels", () => {
  const bitmap = bitmapFromAlpha(alpha(8, 6, [[2, 1], [5, 1], [3, 4], [6, 4, 90]]), 8, 6);
  assert.deepEqual([bitmap.width, bitmap.height], [4, 4]);
  assert.deepEqual(bitmap.pixels, [[0, 0], [3, 0], [1, 3]]);
  assert.deepEqual(bitmapFromAlpha(alpha(4, 4, []), 4, 4), { width: 0, height: 0, pixels: [] });
});

test("block scale is a whole number inside its bounds so pixels stay square", () => {
  assert.equal(blockScale(1000, 49, 2, 12), 12);
  assert.equal(blockScale(300, 49, 2, 12), 6);
  assert.equal(blockScale(20, 49, 2, 12), 2);
  for (const bad of [0, -5, NaN, Infinity]) assert.equal(blockScale(bad, 49, 3, 9), 3);
  assert.equal(blockScale(500, 0, 3, 9), 3);
  assert.ok(Number.isInteger(blockScale(777.7, 13.1)));
});

test("colour bands cover every row without going out of range", () => {
  const bands = PALETTES.fire.bands;
  assert.equal(bandColor(0, 12, bands), bands[0]);
  assert.equal(bandColor(11, 12, bands), bands[bands.length - 1]);
  assert.equal(bandColor(99, 12, bands), bands[bands.length - 1]);
  assert.equal(bandColor(-3, 12, bands), bands[0]);
});

test("dissolve order is a deterministic permutation", () => {
  const order = revealOrder(300, 300);
  assert.deepEqual(order, revealOrder(300, 300));
  assert.deepEqual([...order].sort((a, b) => a - b), Array.from({ length: 300 }, (_, i) => i));
  assert.notDeepEqual(order, Array.from({ length: 300 }, (_, i) => i));
  assert.deepEqual(revealOrder(0), []);
});

test("sprites ignore empty cells and keep their codes", () => {
  assert.deepEqual(spritePixels([".o", "s."]), [[1, 0, "o"], [0, 1, "s"]]);
});

test("the attract-loop ball never leaves the strip and finishes through the rim", () => {
  for (const width of [96, 180, 360, 480]) {
    const layout = courtLayout(width);
    assert.ok(layout.shoot > layout.start && layout.rimLeft < layout.rimRight && layout.rimRight < layout.width);
    for (let frame = 0; frame < LOOP; frame += 1) {
      const ball = ballState(frame, width);
      assert.ok(ball.x >= 0 && ball.x + 7 <= layout.width, `x out of strip at ${width}/${frame}`);
      assert.ok(ball.y >= 0 && ball.y + 7 <= layout.floor, `y out of strip at ${width}/${frame}`);
    }
    const release = ballState(63, width);
    assert.equal(release.phase, "shot");
    assert.equal(release.x + 3, layout.rimCenter);
    assert.ok(release.y + 7 <= layout.rimY, "ball arrives above the rim");
    assert.equal(ballState(64, width).phase, "net");
  }
  assert.deepEqual(ballState(5, 300), ballState(5 + LOOP, 300));
  assert.equal(ART_HEIGHT, courtLayout(200).height);
  assert.equal(ballState(STILL_FRAME, 300).phase, "shot");
});

test("the ticker starts once and stops cleanly", () => {
  let queued = 0, cancelled = 0, steps = 0, callback = null;
  const win = { requestAnimationFrame(fn) { queued += 1; callback = fn; return queued; }, cancelAnimationFrame() { cancelled += 1; } };
  const ticker = createTicker(win, () => { steps += 1; });
  ticker.start(); ticker.start();
  assert.equal(queued, 1);
  callback(1000); callback(1010); callback(1100);
  assert.equal(steps, 2);
  ticker.stop();
  assert.equal(ticker.running, false); assert.equal(cancelled, 1);
  callback(2000);
  assert.equal(steps, 2);
});

function canvasStub() {
  const calls = [];
  const ctx = new Proxy({}, { get: (_t, key) => (key in _t ? _t[key] : (...args) => calls.push([key, ...args])), set: (_t, key, value) => { _t[key] = value; return true; } });
  return { calls, canvas: { width: 0, height: 0, style: {}, dataset: {}, parentElement: { clientWidth: 1440 }, getContext: () => ctx } };
}

test("reduced motion paints a single still court frame and never starts the loop", () => {
  const court = canvasStub(), layer = canvasStub();
  let frames = 0;
  const doc = {
    hidden: false, getElementById: (id) => (id === "arcade-court" ? court.canvas : null),
    createElement: () => layer.canvas, querySelectorAll: () => [], querySelector: () => null, addEventListener() {},
  };
  const win = { innerWidth: 1440, matchMedia: () => ({ matches: true, addEventListener() {} }),
    requestAnimationFrame: () => { frames += 1; return frames; }, cancelAnimationFrame() {}, addEventListener() {} };
  const result = init(doc, win);
  assert.equal(result.court.ticker.running, false);
  assert.equal(frames, 0);
  assert.equal(court.canvas.width, 360);
  assert.equal(court.canvas.style.width, "1440px");
  assert.ok(court.calls.some(([name]) => name === "drawImage"), "still frame drawn");
});

test("the sticky stage exposes the column height and missing markup is harmless", () => {
  const values = {};
  const room = { style: { setProperty: (key, value) => { values[key] = value; } },
    querySelector: () => ({ getBoundingClientRect: () => ({ height: 811.2 }) }) };
  const measure = initStickyStage({ getElementById: () => room }, { addEventListener() {} });
  assert.equal(typeof measure, "function");
  assert.equal(values["--stage-h"], "812px");
  assert.equal(initStickyStage({ getElementById: () => null }, {}), null);
  assert.doesNotThrow(() => init({ getElementById: () => null, querySelectorAll: () => [], querySelector: () => null, addEventListener() {} }, {}));
});
