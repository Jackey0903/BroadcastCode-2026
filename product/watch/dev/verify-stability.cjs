// Run with Playwright available on NODE_PATH; outputs are kept outside source.
// node dev/verify-stability.cjs http://127.0.0.1:4178 /absolute/evidence/directory
const { chromium } = require('playwright');
const fs = require('node:fs/promises');
const assert = require('node:assert/strict');
const path = require('node:path');
const [base = 'http://127.0.0.1:4178', out] = process.argv.slice(2);
if (!out) throw new Error('An evidence output directory is required');
(async () => {
 await fs.mkdir(out, { recursive: true });
 const browser = await chromium.launch({ channel: 'chrome', headless: false, args: ['--autoplay-policy=no-user-gesture-required'] });
 const context = await browser.newContext({ viewport: { width: 1512, height: 949 }, deviceScaleFactor: 1 });
 const page = await context.newPage();
 await fs.writeFile(path.join(out,'concurrent-processes-start.txt'),require('node:child_process').execFileSync('ps',['-axo','pcpu,comm'],{encoding:'utf8'}));
 const errors = [];
 page.on('pageerror', error => errors.push(String(error)));
 page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
 await page.addInitScript(() => {
  window.__work = { gpuContexts: 0, videoCanvasCopies: 0 };
  const getContext = HTMLCanvasElement.prototype.getContext;
  HTMLCanvasElement.prototype.getContext = function (type, ...args) {
   if (['webgl', 'webgl2', 'webgpu'].includes(type)) window.__work.gpuContexts++;
   return getContext.call(this, type, ...args);
  };
  const drawImage = CanvasRenderingContext2D.prototype.drawImage;
  CanvasRenderingContext2D.prototype.drawImage = function (image, ...args) {
   if (image instanceof HTMLVideoElement) window.__work.videoCanvasCopies++;
   return drawImage.call(this, image, ...args);
  };
 });
 async function load(mode) {
  await page.goto(`${base}/?mode=halfCourt${mode === 'liquid' ? '&glass=liquid' : ''}`);
  await page.waitForFunction(() => window.broadcastUI?.glass()?.ready && window.broadcastUI.video.readyState >= 2);
  await page.evaluate(async () => {
   const ui = window.broadcastUI;
   ui.video.pause(); ui.video.muted = true; ui.video.currentTime = 3;
   await new Promise(resolve => ui.video.addEventListener('seeked', resolve, { once: true }));
   window.__hold = setInterval(() => ui.showControls(), 500);
  });
  if(mode==='none') await page.addStyleTag({content:'*,*::before,*::after{-webkit-backdrop-filter:none!important;backdrop-filter:none!important}.glass-target{background:#181b24!important;box-shadow:none!important}'});
  await page.waitForTimeout(500);
 }
 const runs = [];
 for (let round = 1; round <= 3; round++) for (const mode of ['liquid', 'css', 'none']) {
  await load(mode);
  await page.evaluate(() => window.broadcastUI.video.play());
  await page.waitForTimeout(1000);
  const result = await page.evaluate(async () => {
   const ui = window.broadcastUI, video = ui.video, times = [];
   const before = video.getVideoPlaybackQuality(), copies = window.__work.videoCanvasCopies, initialTime = video.currentTime;
   const renderers = [...new Set([...ui.glass().lenses.values()].map(l => l.renderer))];
   const counts = { renders: 0, uploads: 0, uploadedPixels: 0 };
   for (const renderer of renderers) {
    const render = renderer._renderFrame;
    renderer._renderFrame = function (...args) { counts.renders++; return render.apply(this, args); };
    const upload = renderer.backend.uploadRegion;
    renderer.backend.uploadRegion = function (x, y, source, ...args) { counts.uploads++; counts.uploadedPixels += source.width * source.height; return upload.call(this, x, y, source, ...args); };
   }
   const start = performance.now();
   await new Promise(resolve => { function tick(t) { times.push(t); if (t - start < 6000) requestAnimationFrame(tick); else resolve(); } requestAnimationFrame(tick); });
   const after = video.getVideoPlaybackQuality(), diagnostics = window.broadcastDiagnostics();
   video.pause(); clearInterval(window.__hold);
   const intervals = times.slice(1).map((t, i) => t - times[i]), sorted = [...intervals].sort((a, b) => a - b);
   return { initialTime, finalTime: video.currentTime, raf: { frames: intervals.length, mean: intervals.reduce((a, b) => a + b, 0) / intervals.length, p95: sorted[Math.floor(sorted.length * .95)], over25: intervals.filter(x => x > 25).length }, video: { total: after.totalVideoFrames - before.totalVideoFrames, dropped: after.droppedVideoFrames - before.droppedVideoFrames }, counts, work: { ...window.__work, videoCanvasCopies: window.__work.videoCanvasCopies - copies }, diagnostics, times };
  });
  if (mode !== 'liquid') {
   assert.equal(result.diagnostics.glass.mode, 'css');
   assert.equal(result.diagnostics.glass.lenses, 0);
   assert.equal(result.diagnostics.glass.canvases, 0);
   assert.equal(result.work.gpuContexts, 0);
   assert.equal(result.work.videoCanvasCopies, 0);
  } else assert.equal(result.diagnostics.glass.backend, 'webgpu');
  const run = { mode, round, capturedAt: new Date().toISOString(), ...result };
  runs.push(run);
  await fs.writeFile(path.join(out, `${mode}-${round}.json`), JSON.stringify(run, null, 2));
  console.log(JSON.stringify({ mode, round, raf: result.raf, video: result.video, counts: result.counts, work: result.work }));
 }
 const transitions = [];
 for (const mode of ['liquid', 'css']) {
  await load(mode);
  await page.evaluate(() => { window.broadcastUI.layout.to('immersive', { immediate: true }); });
  await page.waitForTimeout(100);
  await page.evaluate(() => window.broadcastUI.video.play());
  for (const [target, automatic] of [['halfCourt', true], ['fullCourt', false], ['immersive', false]]) {
   const result = await page.evaluate(async ({ target, automatic }) => {
    const ui = window.broadcastUI, originalVideo = ui.video, frames = [], start = performance.now();
    if (automatic) ui.openAutomatic(); else ui.setMode(target, true);
    await new Promise(resolve => { function tick(now) {
     frames.push({ elapsed: now - start, phase: ui.layout.phase, rects: structuredClone(ui.layout.rects) });
     if (['open', 'closed'].includes(ui.layout.phase)) resolve(); else requestAnimationFrame(tick);
    } requestAnimationFrame(tick); });
    return { target, automatic, duration: frames.at(-1).elapsed, sameVideo: originalVideo === document.querySelector('#match-video'), frames };
   }, { target, automatic });
   const gaps=result.frames.map((f,i)=>f.elapsed-(i?result.frames[i-1].elapsed:0));
   result.maxFrameGap=Math.max(0,...gaps);
   await fs.writeFile(path.join(out, `${mode}-transition-${target}.json`), JSON.stringify(result,null,2));
   console.log(JSON.stringify({mode,target,duration:result.duration,frames:result.frames.length,maxFrameGap:result.maxFrameGap}));
   assert.ok(result.sameVideo);
   for (const frame of result.frames) {
    const { video, panel, controls } = frame.rects;
    assert.ok(Math.abs(video.width / video.height - 16 / 9) < 1e-6);
    if (panel.width > .01) {
     assert.ok(video.x + video.width <= panel.x + .01);
     assert.ok(controls.x + controls.width <= panel.x + .01);
    }
   }
   const expected = automatic ? 350 : target === 'immersive' ? 220 : 300;
   assert.ok(result.duration >= expected - 2 && result.duration < expected + 100, `${mode} ${target}: ${result.duration}`);
   if(mode==='css') assert.ok(result.maxFrameGap<50, `CSS animation stalled: ${result.maxFrameGap}ms`);
   transitions.push({ mode, ...result });
   await page.screenshot({ path: path.join(out, `${mode}-${target}.png`) });
  }
  await page.evaluate(() => { window.broadcastUI.video.pause(); clearInterval(window.__hold); });
 }
 assert.deepEqual(errors, []);
 await fs.writeFile(path.join(out, 'comparison.json'), JSON.stringify({ device: {model:require('node:child_process').execFileSync('sysctl',['-n','hw.model'],{encoding:'utf8'}).trim(),cpu:require('node:child_process').execFileSync('sysctl',['-n','machdep.cpu.brand_string'],{encoding:'utf8'}).trim(),memoryBytes:Number(require('node:child_process').execFileSync('sysctl',['-n','hw.memsize'],{encoding:'utf8'}))},date: new Date().toISOString(), timezone: 'Asia/Shanghai', browser: browser.version(), viewport: [1512, 949], dpr: 1, runs: runs.map(({ times, diagnostics, ...r }) => r), transitions, errors }, null, 2));
 console.log('PASS: alternating playback comparisons, three states, original video identity and geometry, 350ms automatic animation, zero CSS-mode video copies/GPU contexts.');
 await browser.close();
})().catch(error => { console.error(error); process.exit(1); });
