import test from 'node:test';
import assert from 'node:assert/strict';
import { COURT, toVerticalCourt } from '../court/court-geometry.js';

test('broadcast court puts the camera-near sideline left and the far sideline right', () => {
  assert.deepEqual(toVerticalCourt(0, 0), { x: 0, y: 0 });
  assert.deepEqual(toVerticalCourt(0, COURT.width), { x: 50, y: 0 });
  assert.deepEqual(toVerticalCourt(COURT.length, 0), { x: 0, y: 94 });
  assert.deepEqual(toVerticalCourt(COURT.length, COURT.width), { x: 50, y: 94 });
  assert.deepEqual(toVerticalCourt(5.25, 25), { x: 25, y: 5.25 });
});

test('13s visible near/far players retain the broadcast side relationship', () => {
  // Existing flagg.json at PTS 12.996333333333334. Original image foot anchors:
  // D2 [949,620] is on the near side; D3 [936,333] is on the far side.
  // These are editorial source coordinates, not a new tracking observation.
  const nearD2 = toVerticalCourt(29.541, 10.344);
  const farD3 = toVerticalCourt(22.92, 47.215);
  assert.deepEqual(nearD2, { x: 10.344, y: 29.541 });
  assert.deepEqual(farD3, { x: 47.215, y: 22.92 });
  assert.ok(nearD2.x < COURT.width / 2);
  assert.ok(farD3.x > COURT.width / 2);
});

test('last-frame ball holder and defender retain the same near-side ordering', () => {
  // Existing flagg.json at the real final frame PTS 21.521522222222224.
  const holderW2 = toVerticalCourt(7.768, 11.778);
  const defenderD5 = toVerticalCourt(10.703, 12.276);
  const farD3 = toVerticalCourt(38.442, 27.803);
  assert.deepEqual(holderW2, { x: 11.778, y: 7.768 });
  assert.deepEqual(defenderD5, { x: 12.276, y: 10.703 });
  assert.ok(holderW2.x < defenderD5.x && defenderD5.x < farD3.x);
});

test('a route and its held endpoint keep one mapping through full/half view crops', () => {
  const sourceTrail = [{ x: 12, y: 8 }, { x: 16, y: 12 }];
  const rendered = sourceTrail.map(point => toVerticalCourt(point.x, point.y));
  assert.deepEqual(rendered, [{ x: 8, y: 12 }, { x: 12, y: 16 }]);
  for (const viewLength of [COURT.length, COURT.half]) {
    assert.ok(rendered.every(point => point.y < viewLength));
    assert.deepEqual(toVerticalCourt(sourceTrail[1].x, sourceTrail[1].y), rendered[1]);
  }
  assert.equal(Math.hypot(rendered[1].x - rendered[0].x, rendered[1].y - rendered[0].y),
    Math.hypot(sourceTrail[1].x - sourceTrail[0].x, sourceTrail[1].y - sourceTrail[0].y));
});
