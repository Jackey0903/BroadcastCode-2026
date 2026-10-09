'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const C = require('../court-lab/viewer.js');
function point(t, x) { return { t, x, y: 25, status: 'estimated', segment: 'wide', reviewed: false, image: null }; }
function fixture() {
  return {
    presentation: 'schematic', window: [0, C.SOURCE_DURATION],
    schematic: { maxGapSeconds: 1.25, holdLastKnown: true, holdAcrossSegments: true },
    scenes: [{ id: 'wide', start: 0, end: C.SOURCE_DURATION, type: 'wide' }],
    tracks: [{ id: 'W2', team: 'white', label: 'W2', identityStatus: 'anonymous', points: [point(21, 50), point(C.SOURCE_DURATION, 55)] }],
    possession: [
      { start: 0, end: 20, holder: null, phase: 'unknown', label: '尚未确认', source: 'editorial' },
      { start: 20, end: C.SOURCE_DURATION, holder: 'W2', phase: 'held', label: 'W2 控球', source: 'editorial' }
    ]
  };
}
test('the exact video endpoint retains the last holder and its final coordinate', () => {
  const d = fixture();
  const ball = C.sampleBall(d, C.SOURCE_DURATION);
  assert.equal(ball.holder, 'W2');
  assert.equal(ball.phase, 'held');
  assert.equal(ball.label, 'W2 控球');
  assert.equal(ball.x, 55);
  assert.equal(ball.sourceTime, C.SOURCE_DURATION);
  assert.equal(C.sampleBall(d, C.SOURCE_DURATION + .001).phase, 'unknown');
});
test('intermediate boundaries stay half-open and an earlier final interval is not extended', () => {
  const d = fixture();
  assert.equal(C.sampleBall(d, 19.999).phase, 'unknown');
  assert.equal(C.sampleBall(d, 20).phase, 'held');
  d.possession.at(-1).end = 21;
  assert.equal(C.sampleBall(d, 21).phase, 'unknown');
  assert.equal(C.sampleBall(d, C.SOURCE_DURATION).phase, 'unknown');
});
test('independent ball points assign the final endpoint to the same phase as their preceding anchor', () => {
  const d = fixture();
  d.possession.at(-1).holder = null;
  d.possession.at(-1).phase = 'pass';
  d.ball = { kind: 'court-schematic', points: [point(21, 50), point(C.SOURCE_DURATION, 55)] };
  const middle = C.sampleBall(d, (21 + C.SOURCE_DURATION) / 2);
  assert.equal(middle.phase, 'pass');
  assert.ok(Math.abs(middle.x - 52.5) < 1e-8);
  assert.equal(middle.interpolated, true);
  const end = C.sampleBall(d, C.SOURCE_DURATION);
  assert.equal(end.phase, 'pass');
  assert.equal(end.x, 55);
  assert.equal(end.sourceTime, C.SOURCE_DURATION);
});
test('the final endpoint exception cannot join independent ball points across an earlier phase change', () => {
  const d = fixture();
  d.possession = [
    { start: 0, end: 21.3, holder: null, phase: 'shot', label: '投篮', source: 'editorial' },
    { start: 21.3, end: C.SOURCE_DURATION, holder: null, phase: 'score', label: '入篮', source: 'editorial' }
  ];
  d.ball = { kind: 'court-schematic', points: [point(21, 50), point(C.SOURCE_DURATION, 55)] };
  assert.equal(C.sampleBall(d, 21.2).x, null);
  assert.equal(C.sampleBall(d, 21.4).x, null);
  assert.equal(C.sampleBall(d, C.SOURCE_DURATION).phase, 'score');
  assert.equal(C.sampleBall(d, C.SOURCE_DURATION).x, 55);
});
