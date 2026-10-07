"use strict";

// Offline behavior/transport checks. No requests reach AWS and no browser is driven.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { webcrypto, createHash } = require("node:crypto");
const JOB = "b".repeat(32);
const STORE = "hidden-play-studio-job-v1";

function fixture(status = 200, body = {}) {
  class Element {
    constructor(tag = "div") {
      this.tagName = tag.toUpperCase(); this.children = []; this.attributes = {}; this.listeners = {}; this.dataset = {};
      this._text = ""; this.hidden = false; this.disabled = false; this.checked = false; this.value = "";
      this.currentTime = 0; this.duration = 22; this.playbackRate = 1; this.paused = true; this.readyState = 1;
      this.style = { setProperty(key, value) { this[key] = value; } };
      const classes = new Set(); this.classList = { toggle(key, active) { if (active ?? !classes.has(key)) classes.add(key); else classes.delete(key); }, contains(key) { return classes.has(key); }, add(key) { classes.add(key); } };
    }
    get textContent() { return this._text + this.children.map((c) => c.textContent).join(""); }
    set textContent(value) { this._text = String(value); this.children = []; }
    get childNodes() { return this.children; }
    append(...children) { this.children.push(...children); }
    replaceChildren(...children) { this.children = children; this._text = ""; }
    setAttribute(key, value) { this.attributes[key] = String(value); }
    removeAttribute(key) { delete this.attributes[key]; if (key === "src") delete this.src; }
    getAttribute(key) { return key === "src" ? this.src : this.attributes[key]; }
    addEventListener(name, fn) { this.listeners[name] = fn; }
    pause() { this.paused = true; }
    play() { this.paused = false; return Promise.resolve(); }
    load() { this.loadCount = (this.loadCount || 0) + 1; }
    focus() { this.focused = true; }
    cloneNode() { return new Element(this.tagName); }
    closest() { return null; }
    querySelector() { return this.children[0] || new Element(); }
    querySelectorAll() { return []; }
  }
  const elements = new Map();
  const get = (id) => { if (!elements.has(id)) elements.set(id, new Element(id.includes("video") ? "video" : "div")); return elements.get(id); };
  const input = new Element("input"); input.value = "flagg"; input.checked = true;
  const amen = new Element("input"); amen.value = "amen";
  get("create-form").querySelector = (selector) => selector.includes(":checked") ? [input, amen].find((item)=>item.checked) : selector.includes('value="amen"') ? amen : input;
  get("create-form").querySelectorAll = () => [input, amen];
  const timers = new Map(), requests = [], storage = new Map();
  let tick = 0, currentUrl = new URL("https://product.invalid/product/");
  const sandbox = {
    document: { getElementById: get, createElement: (tag) => new Element(tag), createElementNS: (_ns, tag) => new Element(tag), body: new Element("body"), querySelectorAll: () => [], addEventListener() {} },
    window: { addEventListener() {}, scrollTo() {} },
    matchMedia: () => ({ matches: false }),
    location: { get origin() { return currentUrl.origin; }, get href() { return currentUrl.href; } },
    history: { replaceState(_state, _title, address) { currentUrl = new URL(address); } },
    sessionStorage: { getItem: (key) => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value), removeItem: (key) => storage.delete(key) },
    setTimeout(callback, delay) { const id = ++tick; timers.set(id, { callback, delay }); return id; }, clearTimeout: (id) => timers.delete(id),
    URL, AbortController, TextEncoder, Uint8Array, crypto: webcrypto,
    fetch: async (url, options) => { requests.push({ url, options }); return { ok: status >= 200 && status < 300, status, text: async () => typeof body === "string" ? body : JSON.stringify(body), json: async () => typeof body === "string" ? JSON.parse(body) : body }; },
  };
  const source = fs.readFileSync(path.join(__dirname, "app.js"), "utf8");
  const seam = "  loadStories().then(()=>{restoreJob();});";
  assert.ok(source.includes(seam));
  vm.createContext(sandbox);
  vm.runInContext(source.replace(seam, "  globalThis.audit={state,api,checkService,renderJob,pollJob,setMedia,renderOfficial,reveal,keyTime,normalise,renderRunFacts,loadStories,submitJob,syncCreate,renderFrameComparison};"), sandbox);
  Object.assign(sandbox.audit.state, { jobId: JOB, jobSample: "flagg", serviceReady: true, pollStart: Date.now() });
  return { ...sandbox.audit, get, requests, timers, storage, input, amen, currentUrl: () => currentUrl };
}
function story(overrides = {}) { return { id: "flagg", title: "真实片段", sourceVideo: "/samples/flagg.mp4", enhancedVideo: "/products/flagg.mp4", durationSeconds: 22, hook: { choices: [] }, chapters: [], evidence: [], officialEvent: {}, ...overrides }; }
function completed(overrides = {}) { return { status: "completed", mode: "story", videoUrl: "/result.mp4", analysis: { protocol_version: "product-story-v1", summary: "实际分析", evidence: [], trace: [] }, ...overrides }; }

for (const modes of [undefined, ["readiness"], []]) {
  test(`legacy / unavailable modes ${JSON.stringify(modes)} never enable story creation`, async () => {
    const run = fixture(200, { ready: true, samples: ["flagg", "amen"], modes }); await run.checkService();
    assert.equal(run.state.serviceReady, false); assert.equal(run.get("generate-button").disabled, true);
    assert.match(run.get("service-status").textContent, /尚未开放/); assert.equal(run.requests.length, 1);
  });
}
test("ready story service enables only supported sample inputs", async () => {
  const run = fixture(200, { ready: true, samples: ["flagg"], modes: ["readiness", "story"] }); await run.checkService();
  assert.equal(run.state.serviceReady, true); assert.equal(run.get("generate-button").disabled, false);
});
test("empty available samples keeps creation disabled", async () => {
  const run = fixture(200, { ready: true, samples: [], modes: ["story"] }); await run.checkService();
  assert.equal(run.get("generate-button").disabled, true); assert.equal(run.input.disabled, true);
});
for (const result of [completed({ mode: "readiness" }), completed({ analysis: { protocol_version: "team02-readiness-v1" } }), completed({ mode: undefined })]) {
  test(`completed legacy result is not exposed as product success (${result.mode}/${result.analysis.protocol_version})`, () => {
    const run = fixture(); run.renderJob(result);
    assert.equal(run.get("generated-video").hidden, true); assert.equal(run.get("actual-analysis").hidden, true);
    assert.equal(run.state.resultUrl, null); assert.equal(run.state.busy, false); assert.match(run.get("job-badge").textContent, /不匹配/);
  });
}
test("product result shows the actual video and analysis", () => {
  const run = fixture(); run.renderJob(completed());
  assert.equal(run.get("generated-video").hidden, false); assert.equal(run.get("generated-video").src, "https://product.invalid/result.mp4");
  assert.equal(run.get("actual-summary").textContent, "实际分析"); assert.equal(run.state.busy, false);
});
test("POST uses exact UTF-8 SHA256 and story mode", async () => {
  const run = fixture(202, { jobId: JOB, mode: "story", status: "queued" });
  const body = JSON.stringify({ sample: "flagg", mode: "story" }); await run.api("/api/jobs", { method: "POST", body });
  const request = run.requests[0]; assert.equal(request.options.body, body);
  assert.equal(request.options.headers["x-amz-content-sha256"], createHash("sha256").update(body, "utf8").digest("hex"));
  assert.equal(request.options.credentials, "same-origin"); assert.equal(run.requests.length, 1);
});
test("submit action sends story mode and does not repeat POST", async () => {
  const run = fixture(202, { jobId: JOB, mode: "story", status: "queued" }); run.get("generate-button").disabled = false;
  await run.submitJob({ preventDefault() {} }); await new Promise(setImmediate);
  const posts = run.requests.filter((request) => request.options.method === "POST"); assert.equal(posts.length, 1); assert.deepEqual(JSON.parse(posts[0].options.body), { sample: "flagg", mode: "story" });
});
for (const status of [400, 404]) {
  test(`HTTP ${status} unlocks missing-job state without resubmitting`, async () => {
    const run = fixture(status, { error: "任务不存在" }); run.state.busy = true; run.storage.set(STORE, JOB);
    await run.pollJob(); assert.equal(run.state.busy, false); assert.equal(run.storage.has(STORE), false);
    assert.equal(run.requests.length, 1); assert.equal(run.requests[0].options.method, undefined); assert.equal(run.timers.size, 0);
  });
}
test("temporary status failure retains busy state and retries only GET", async () => {
  const run = fixture(503, { error: "temporary failure" }); run.state.busy = true;
  await run.pollJob(); assert.equal(run.state.busy, true); assert.equal(run.get("generate-button").disabled, true);
  assert.deepEqual([...run.timers.values()].map((t) => t.delay), [6000]); assert.equal(run.requests.length, 1);
});
test("HTTP status survives a non-JSON upstream response", async () => {
  const run = fixture(503, "<html>Unavailable</html>"); await assert.rejects(run.api("/api/status"), (error) => error.status === 503);
});
test("switching video versions preserves same time, speed, and playback intent", () => {
  const run = fixture(); run.state.story = story(); const video = run.get("story-video"); video.currentTime = 16.5; video.playbackRate = .5; video.paused = false;
  run.setMedia("enhanced"); video.onloadedmetadata(); assert.equal(video.currentTime, 16.5); assert.equal(video.playbackRate, .5); assert.equal(video.paused, false); assert.equal(video.dataset.version, "enhanced");
  run.setMedia("source"); video.onloadedmetadata(); assert.equal(video.currentTime, 16.5); assert.equal(video.dataset.version, "source");
});
test("missing enhanced asset cannot masquerade as a produced film", () => {
  const run = fixture(); run.state.story = story({ enhancedVideo: undefined }); run.setMedia("enhanced");
  assert.equal(run.state.version, "source"); assert.equal(run.get("story-video").src, undefined);
});
test("each perspective reveals its own copy, seek point, and cited evidence", () => {
  const run = fixture(); run.state.story = story({ hook: { choices: [{ id: "player", label: "持球人", revealTitle: "看推进", revealBody: "实际观察一", focusTime: 15.5, evidenceIds: ["frame-a"] }, { id: "defender", label: "防守人", revealTitle: "看干扰", revealBody: "实际观察二", focusTime: 16.5, evidenceIds: ["frame-b"] }] }, evidence: [{ id: "frame-a", kind: "observation", title: "A", body: "画面 A" }, { id: "frame-b", kind: "observation", title: "B", body: "画面 B" }] });
  run.state.choice = "player"; run.reveal(); assert.equal(run.get("reveal-title").textContent, "看推进"); assert.equal(run.keyTime(), 15.5); assert.match(run.get("detail-evidence").children[0].className, /perspective-evidence/);
  run.state.choice = "defender"; run.reveal(); assert.equal(run.get("reveal-title").textContent, "看干扰"); assert.equal(run.keyTime(), 16.5); assert.match(run.get("detail-evidence").children[1].className, /perspective-evidence/); assert.doesNotMatch(run.get("detail-evidence").children[0].className, /perspective-evidence/);
});
test("unverified or missing official probabilities never become numeric claims", () => {
  const run = fixture(); run.state.story = story({ officialEvent: { verified: false, expectedFg: .51 } }); run.renderOfficial();
  assert.doesNotMatch(run.get("detail-official").textContent, /51\.0/);
  run.state.story.officialEvent = { verified: true, expectedFg: null }; run.renderOfficial(); assert.doesNotMatch(run.get("detail-official").textContent, /0\.0/);
});
test("verified official xFG stays separate from the observed made shot", () => {
  const run = fixture(); run.state.story = story({ officialEvent: { verified: true, expectedFg: .51, made: true, shotLocation: { locX: "89", locY: "55", side: "right" } } }); run.renderOfficial();
  assert.match(run.get("detail-official").textContent, /51\.0/); assert.match(run.get("detail-official").textContent, /本次实际结果：命中/); assert.match(run.get("detail-official").textContent, /非运动轨迹/);
  const figure = run.get("detail-official").children.find((child) => child.tagName === "FIGURE"); const point = figure.children[0].children.at(-1);
  assert.equal(Number(point.getAttribute("cx")), .89 * 94); assert.equal(Number(point.getAttribute("cy")), .55 * 50);
});
test("actual trace is readable and validation is not presented as accuracy certification", () => {
  const run = fixture(); run.renderRunFacts({ analysis: { model_id: "actual-model", elapsedSeconds: 12.34, evidence: [{ id: "a" }], trace: [{ tool: "inspect_frames", status: "succeeded", elapsedMs: 30, result: { frames: [{ id: "frame-a" }, { id: "frame-b" }] } }], validation: { passed: true, checks: ["cited_frames_actually_inspected", "no_model_authored_numbers"] } } });
  assert.match(run.get("run-facts").textContent, /actual-model/); assert.match(run.get("run-trace").textContent, /实际读取 2 帧/); assert.match(run.get("run-validation").textContent, /不等于独立的篮球事实认证/);
});
test("unavailable story data displays an honest error without fabricated cases", async () => {
  const run = fixture(404, {}); await run.loadStories(); assert.equal(run.state.stories.length, 0); assert.equal(run.get("data-notice").hidden, false); assert.equal(run.get("watch-original").disabled, true);
});
test("all fixed DOM IDs referenced by the frontend exist in the document", () => {
  const html = fs.readFileSync(path.join(__dirname, "index.html"), "utf8"), source = fs.readFileSync(path.join(__dirname, "app.js"), "utf8");
  const ids = new Set([...html.matchAll(/id="([^"]+)"/g)].map((match) => match[1]));
  for (const match of source.matchAll(/\$\("([^"]+)"\)/g)) assert.ok(ids.has(match[1]), `missing #${match[1]}`);
});

for (const [sample, seconds, labels] of [
  ["flagg", [15.5, 16.5], ["接近篮下", "起跳时，正面防守人举臂"]],
  ["amen", [17.5, 18], ["防守人已起跳，阿门仍持球", "阿门起跳出手"]],
]) {
  test(`${sample} comparison uses only its two registered evidence frames and exact seconds`, () => {
    const run=fixture(); const data=JSON.parse(fs.readFileSync(path.join(__dirname,"../data/stories.json"),"utf8"));
    run.state.story=run.normalise(data.stories.find((item)=>item.id===sample));run.renderFrameComparison();
    assert.equal(run.get("frame-comparison").hidden,false);const buttons=run.get("comparison-frames").children;assert.equal(buttons.length,2);
    buttons.forEach((button,index)=>{const evidence=run.state.story.evidence.find((item)=>item.id===button.dataset.evidenceId);assert.equal(evidence.videoTime,seconds[index]);assert.equal(button.children[0].src,new URL(evidence.frameUrl,"https://product.invalid").href);assert.equal(button.children[2].textContent,labels[index]);assert.match(button.getAttribute("aria-label"),/定位原片并暂停/);});
  });
}
test("clicking either comparison frame seeks the exact original timestamp and pauses playback", () => {
  const run=fixture();run.state.story=story({evidence:[{id:"flagg-frame-15-5",frameUrl:"/frames/flagg-15.5s.jpg",videoTime:15.5},{id:"flagg-frame-16-5",frameUrl:"/frames/flagg-16.5s.jpg",videoTime:16.5}]});
  run.renderFrameComparison();const [before,after]=run.get("comparison-frames").children;const video=run.get("story-video");video.paused=false;
  before.listeners.click();assert.equal(video.currentTime,15.5);assert.equal(video.paused,true);assert.equal(before.getAttribute("aria-pressed"),"true");
  video.paused=false;after.listeners.click();assert.equal(video.currentTime,16.5);assert.equal(video.paused,true);assert.equal(before.getAttribute("aria-pressed"),"false");assert.equal(after.getAttribute("aria-pressed"),"true");assert.match(run.get("page-announcement").textContent,/16.5 秒并暂停/);
});
test("comparison switches enhanced playback to original and stays paused after metadata loads", () => {
  const run=fixture();run.state.story=story({evidence:[{id:"amen-frame-17-5",frameUrl:"/frames/amen-17.5s.jpg",videoTime:17.5},{id:"amen-frame-18",frameUrl:"/frames/amen-18s.jpg",videoTime:18}],id:"amen",sourceVideo:"/samples/amen.mp4"});run.state.version="enhanced";
  const video=run.get("story-video");video.paused=false;run.renderFrameComparison();run.get("comparison-frames").children[1].listeners.click();video.onloadedmetadata();
  assert.equal(run.state.version,"source");assert.equal(video.src,"https://product.invalid/samples/amen.mp4");assert.equal(video.currentTime,18);assert.equal(video.paused,true);assert.match(run.get("source-download").textContent,/打开原片/);
});
test("missing or invalid comparison evidence hides the pair instead of inventing a frame", () => {
  const run=fixture();for(const evidence of [[],[{id:"flagg-frame-15-5",frameUrl:"/frames/flagg-15.5s.jpg",videoTime:15.5}],[{id:"flagg-frame-15-5",frameUrl:"/frames/flagg-15.5s.jpg",videoTime:15.5},{id:"flagg-frame-16-5",frameUrl:"/frames/flagg-16.5s.jpg",videoTime:null}]]){run.state.story=story({evidence});run.renderFrameComparison();assert.equal(run.get("frame-comparison").hidden,true);assert.equal(run.get("comparison-frames").children.length,0);}
});

test("restoring an Amen task overrides a Flagg selection before completed state settles", () => {
  const run=fixture();run.state.busy=true;run.state.jobSample="flagg";run.input.checked=true;run.amen.checked=false;
  run.renderJob(completed({sample:"amen"}));
  assert.equal(run.state.jobSample,"amen");assert.equal(run.amen.checked,true);assert.equal(run.input.checked,false);assert.equal(run.state.busy,false);
});
test("refreshing a finished task preserves the next sample selected by the user", () => {
  const run=fixture();run.state.busy=true;run.renderJob(completed({sample:"amen"}));
  run.amen.checked=false;run.input.checked=true;run.syncCreate();
  run.renderJob(completed({sample:"amen"}));
  assert.equal(run.input.checked,true);assert.equal(run.amen.checked,false);assert.equal(run.state.jobSample,"amen");assert.equal(run.get("generate-button").disabled,false);
});
