import test from 'node:test';
import assert from 'node:assert/strict';
import { validHeadAnchors } from './annotations.js';
import { toVerticalCourt } from '../court/court-geometry.js';

const anchor = (values = {}) => ({ playerId: 'D5', mediaId: 'flagg', shotId: 'wide-1', timeMs: 1000, expiresAtMs: 1200, coordinateSystem: 'video-normalized-top-left', landmark: 'head-top', status: 'observed', point: { x: .4, y: .5 }, ...values });
test('head markers require explicit current head coordinates; court foot points never qualify', () => {
  assert.equal(validHeadAnchors([anchor()], 1.1).length, 1);
  assert.equal(validHeadAnchors([anchor({ landmark: 'foot-contact' })], 1.1).length, 0);
  assert.equal(validHeadAnchors([{ image: [200, 500], t: 1, x: 4, y: 25 }], 1.1).length, 0);
  assert.equal(validHeadAnchors([anchor({ point: { x: .4, y: 1.2 } })], 1.1).length, 0);
  assert.equal(validHeadAnchors([anchor({ coordinateSystem: 'court-feet-50x94-top-left' })], 1.1).length, 0);
});
test('future, stale, occluded, and last-known head positions disappear instead of being extended', () => {
  assert.equal(validHeadAnchors([anchor()], .9).length, 0);
  assert.equal(validHeadAnchors([anchor()], 1.201).length, 0);
  assert.equal(validHeadAnchors([anchor({ status: 'last-known' })], 1.1).length, 0);
  const cut = anchor({ timeMs: 1100, status: 'occluded', point: null });
  assert.equal(validHeadAnchors([anchor(), cut], 1.12).length, 0);
});
test('media, camera and player identity constraints prevent cross-shot or cross-person attachment', () => {
  assert.equal(validHeadAnchors([anchor()], 1.1, { shotId: 'wide-2' }).length, 0);
  assert.equal(validHeadAnchors([anchor()], 1.1, { mediaId: 'amen' }).length, 0);
  assert.equal(validHeadAnchors([anchor()], 1.1, { focusId: 'W2' }).length, 0);
  assert.equal(validHeadAnchors([anchor(), anchor({ playerId: 'W2' })], 1.1).length, 1);
});
test('court projection uses broadcast near-left orientation without scaling or changing distances', () => {
  assert.deepEqual(toVerticalCourt(0, 0), { x: 0, y: 0 });
  assert.deepEqual(toVerticalCourt(94, 50), { x: 50, y: 94 });
  assert.deepEqual(toVerticalCourt(5.25, 25), { x: 25, y: 5.25 });
  const a = toVerticalCourt(7, 11), b = toVerticalCourt(13, 19);
  assert.equal(Math.hypot(a.x - b.x, a.y - b.y), 10);
});
