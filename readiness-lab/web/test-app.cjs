"use strict";

// Offline state/transport checks only; no browser or network requests.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { webcrypto, createHash } = require("node:crypto");

const JOB = "a".repeat(32);
const STORAGE_KEY = "broadcastcode-readiness-job-v1";

function fixture(status, body) {
  const inputs = [{ value: "flagg", checked: true }, { value: "amen", checked: false }];
  function element() {
    return {
      textContent: "", hidden: false, disabled: false,
      classList: { toggle() {} }, addEventListener() {},
      querySelector(selector) { return selector.includes("input") ? inputs[0] : element(); },
      querySelectorAll() { return inputs; }, replaceChildren() {}, append() {},
    };
  }
  const elements = new Map();
  const timers = new Map();
  const requests = [];
  let timerId = 0;
  let currentUrl = new URL(`https://readiness.invalid/?job=${JOB}`);
  const storage = new Map([[STORAGE_KEY, JSON.stringify({ jobId: JOB, sample: "flagg" })]]);
  const sandbox = {
    document: {
      getElementById(id) { if (!elements.has(id)) elements.set(id, element()); return elements.get(id); },
      createElement: element,
    },
    window: { addEventListener() {} },
    location: { get origin() { return currentUrl.origin; }, get href() { return currentUrl.href; } },
    history: { replaceState(_state, _title, url) { currentUrl = new URL(url); } },
    sessionStorage: { getItem(key) { return storage.get(key) ?? null; }, removeItem(key) { storage.delete(key); } },
    setTimeout(callback, delay) { const id = ++timerId; timers.set(id, { callback, delay }); return id; },
    clearTimeout(id) { timers.delete(id); },
    URL, AbortController, TextEncoder, Uint8Array, crypto: webcrypto,
    fetch: async (url, options) => {
      requests.push({ url, options });
      return { ok: status >= 200 && status < 300, status, text: async () => typeof body === "string" ? body : JSON.stringify(body) };
    },
  };
  const source = fs.readFileSync(path.join(__dirname, "app.js"), "utf8");
  const bootstrap = "  checkEnvironment();\n  restoreJob();";
  assert.ok(source.includes(bootstrap), "test seam must replace only automatic startup");
  vm.createContext(sandbox);
  vm.runInContext(source.replace(bootstrap, "  globalThis.audit = { api, pollJob, state, ui };"), sandbox);
  Object.assign(sandbox.audit.state, { environmentReady: true, busy: true, jobId: JOB, pollStartedAt: Date.now() });
  return { ...sandbox.audit, requests, timers, storage, currentUrl: () => currentUrl };
}

for (const status of [400, 404]) {
  test(`HTTP ${status} releases restored-job lock and removes both recovery pointers`, async () => {
    const run = fixture(status, { error: "offline missing/invalid job" });
    await run.pollJob();
    assert.equal(run.state.busy, false);
    assert.equal(run.ui.start.disabled, false);
    assert.equal(run.state.jobId, JOB, "retain the original ID on screen for review");
    assert.equal(run.storage.has(STORAGE_KEY), false);
    assert.equal(run.currentUrl().searchParams.has("job"), false);
    assert.equal(run.requests.length, 1);
    assert.equal(run.timers.size, 0, "do not keep retrying a missing job");
  });
}

test("HTTP 503 retains the job and retries GET without enabling another submission", async () => {
  const run = fixture(503, { error: "offline transient service error" });
  await run.pollJob();
  assert.equal(run.state.busy, true);
  assert.equal(run.ui.start.disabled, true);
  assert.equal(run.state.jobId, JOB);
  assert.equal(run.storage.has(STORAGE_KEY), true);
  assert.equal(run.currentUrl().searchParams.get("job"), JOB);
  assert.equal(run.requests.length, 1);
  assert.equal(run.requests[0].options.method, undefined);
  assert.deepEqual([...run.timers.values()].map((timer) => timer.delay), [6000]);
});

test("POST sends the SHA256 of its exact UTF-8 body for the Lambda URL origin", async () => {
  const run = fixture(202, { jobId: JOB, status: "queued" });
  const body = JSON.stringify({ sample: "flagg", testNote: "离线测试" });
  await run.api("/api/jobs", { method: "POST", body });
  assert.equal(run.requests.length, 1);
  const request = run.requests[0];
  assert.equal(request.options.body, body);
  assert.equal(request.options.headers["x-amz-content-sha256"], createHash("sha256").update(body, "utf8").digest("hex"));
  assert.equal(request.options.headers["Content-Type"], "application/json");
  assert.equal(request.options.credentials, "same-origin");
});

test("POST error is surfaced once without an automatic second submission", async () => {
  const run = fixture(503, { error: "offline queue unavailable" });
  await assert.rejects(run.api("/api/jobs", { method: "POST", body: '{"sample":"amen"}' }), (error) => error.status === 503);
  assert.equal(run.requests.length, 1);
  assert.equal(run.timers.size, 0);
});

test("HTTP error status survives a non-JSON upstream response", async () => {
  const run = fixture(503, "<html>upstream unavailable</html>");
  await assert.rejects(run.api("/api/jobs/" + JOB), (error) => error.status === 503 && error.detail.response.includes("upstream"));
});
