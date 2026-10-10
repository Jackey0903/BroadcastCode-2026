import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { normalizeStory, sameOriginAsset, loadStoryRecord } from './catalog.js';
const BASE = 'https://deky02484tknr.cloudfront.net/product/watch/';
// Contract fixture only: no fake run is added to the real catalog.
const seed = JSON.parse(await readFile(new URL('../data/stories.json', import.meta.url), 'utf8')).stories.find(s => s.sample === 'flagg');
const jobId = 'c'.repeat(32), outputSha256 = 'd'.repeat(64);
const original = { ...seed, showcaseJobId: jobId, showcaseOutputSha256: outputSha256, enhancedVideo: `/product/outputs/${jobId}/enhanced.mp4`, analysisUrl: `/product/outputs/${jobId}/analysis.json` };
const accepted = { jobId, sample: seed.sample, mode: 'story', outputSha256, verifiedAt: '2026-10-10T00:00:00Z', contentReview: { acceptedForShowcase: true }, analysis: { runId: jobId, sample: seed.sample, preservesSourceTimeline: true, outputVideo: { sha256: outputSha256 }, sourceVideo: { sha256: seed.sourceVideoSha256 } } };
test('same-origin registered enhanced pair stays available; current run does not inherit October 7 history', () => {
 const s = normalizeStory(original, BASE);
 assert.equal(s.sourceVideo, '/samples/flagg.mp4'); assert.equal(s.enhancedVideo, `/product/outputs/${original.showcaseJobId}/enhanced.mp4`); assert.equal(s.analysisUrl, `/product/outputs/${original.showcaseJobId}/analysis.json`); assert.equal(s.enhancedAvailable, true); assert.equal(s.history, null);
});
test('external, credentialed, query-bearing, alternate-job and incomplete enhanced pairs cannot play', () => {
 for (const value of ['https://example.org/product/outputs/' + original.showcaseJobId + '/enhanced.mp4', original.enhancedVideo + '?token=x', original.enhancedVideo + '#t=1', 'https://user:pass@deky02484tknr.cloudfront.net/product/outputs/' + original.showcaseJobId + '/enhanced.mp4', '//deky02484tknr.cloudfront.net/product/outputs/' + original.showcaseJobId + '/enhanced.mp4']) assert.equal(normalizeStory({ ...original, enhancedVideo: value }, BASE).enhancedAvailable, false);
 for (const patch of [{ showcaseJobId: 'a'.repeat(32) }, { analysisUrl: null }, { publication: { originalJobId: 'b'.repeat(32) } }]) assert.equal(normalizeStory({ ...original, ...patch }, BASE).enhancedAvailable, false);
});
test('source rejects external host, unregistered sample, and missing identity', () => {
 for (const patch of [{ sourceVideo: 'https://example.org/samples/flagg.mp4' }, { sample: 'other' }, { sourceVideoSha256: '' }]) assert.throws(() => normalizeStory({ ...original, ...patch }, BASE));
 assert.equal(sameOriginAsset('/samples/flagg.mp4', '/samples/flagg.mp4', BASE), '/samples/flagg.mp4');
});
test('requested current record preserves exact job, accepted review and original verification time', async () => {
 const saved = globalThis.fetch, calls = [];
 globalThis.fetch = async (url, options) => { calls.push({ url, options }); return { ok: true, json: async () => ({ records: [accepted] }) }; };
 try { const r = await loadStoryRecord(normalizeStory({ ...original, publication: { historical: false } }, BASE)); assert.equal(r.jobId, original.showcaseJobId); assert.equal(r.verifiedAt, accepted.verifiedAt); assert.equal(r.historical, false); assert.equal(r.contentReview.acceptedForShowcase, true); assert.equal(calls.length, 1); assert.match(calls[0].url.pathname, /\/watch\/data\/history.json$/); assert.equal(calls[0].options.redirect, 'error'); }
 finally { globalThis.fetch = saved; }
});
test('record from another job or source cannot be attributed to displayed run', async () => {
 const saved = globalThis.fetch;
 try { for (const r of [{ ...accepted, jobId: 'a'.repeat(32) }, { ...accepted, analysis: { ...accepted.analysis, sourceVideo: { ...accepted.analysis.sourceVideo, sha256: 'b'.repeat(64) } } }]) { globalThis.fetch = async () => ({ ok: true, json: async () => ({ records: [r] }) }); await assert.rejects(loadStoryRecord(normalizeStory(original, BASE)), /身份不一致/); } }
 finally { globalThis.fetch = saved; }
});
test('static historical records do not fetch or initiate inference', async () => {
 const saved = globalThis.fetch; globalThis.fetch = () => { throw new Error('Unexpected fetch'); };
 try { const history = { jobId: 'c'.repeat(32), verifiedAt: '2026-10-07T12:00:00Z' }; assert.equal(await loadStoryRecord({ enhancedAvailable: false, history }), history); }
 finally { globalThis.fetch = saved; }
});
