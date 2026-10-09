"use strict";
/* Pixel layer for the product page. Decorative only: no game data, no tracking, no network.
   - Wordmarks are rasterised from the bundled FusionPixel12 glyphs and drawn one canvas pixel
     per glyph pixel, then scaled by CSS with nearest-neighbour sampling.
   - The court strip is a cartoon attract loop (floor, hoop, ball). It is not a replay of the
     clip and carries no coordinates. It pauses off-screen, in background tabs and under
     prefers-reduced-motion, where a single still frame is drawn instead. */
(function (root) {
  const FONT = "FusionPixel12";
  const GLYPH = 12;
  const FPS = 15;
  const LOOP = 96;
  const ART_HEIGHT = 40;
  const ART_PIXEL = 4;
  const FLOOR = 31;
  const STILL_FRAME = 56;
  const COLORS = {
    ball: "#F4541F", ballLight: "#FFB067", seam: "#2A1206", trail: "#8E2C0D",
    chalk: "#F2F0EA", net: "#D9D5CB", steel: "#5A6070", steelDark: "#363B47",
    wood: ["#C88A45", "#BC7E3B", "#B07232"], woodSeam: "#7A4A1E", courtLine: "#E9E4D8",
  };
  const PALETTES = {
    fire: { bands: ["#FFC27A", "#FF9A3D", "#F4541F", "#D9441A"], ember: "#8E2C0D", shadow: "#3D1205" },
    chalk: { bands: ["#FFFFFF", "#F2F0EA", "#D6D2C7"], ember: "#4A505E", shadow: "#20232B" },
  };
  const BAYER = [0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5];
  // 7x7 basketball, two spin frames: o leather, s seam, h highlight.
  const BALL_FRAMES = [
    ["..oso..", ".hosoo.", "ooosooo", "sssssss", "ooosooo", ".oosoo.", "..oso.."],
    ["..ooo..", ".shoos.", "oososoo", "ooosooo", "oososoo", ".sooos.", "..ooo.."],
  ];
  const BALL_SQUASH = ["..oso..", ".oosoo.", "sssssss", "ooosooo", "ooosooo", ".oosoo."];
  const PLUS_TWO = ["......xxx", ".x......x", "xxx...xxx", ".x....x..", "......xxx"];

  const bayer = (x, y) => (BAYER[(y & 3) * 4 + (x & 3)] + .5) / 16;
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));

  /* ---------- pure helpers (exported for tests) ---------- */

  function bitmapFromAlpha(data, width, height, threshold = 128) {
    const lit = new Uint8Array(width * height);
    let minX = width, maxX = -1, minY = height, maxY = -1;
    for (let y = 0; y < height; y += 1) {
      for (let x = 0; x < width; x += 1) {
        if (data[(y * width + x) * 4 + 3] < threshold) continue;
        lit[y * width + x] = 1;
        if (x < minX) minX = x; if (x > maxX) maxX = x;
        if (y < minY) minY = y; if (y > maxY) maxY = y;
      }
    }
    if (maxX < 0) return { width: 0, height: 0, pixels: [] };
    const pixels = [];
    for (let y = minY; y <= maxY; y += 1) {
      for (let x = minX; x <= maxX; x += 1) if (lit[y * width + x]) pixels.push([x - minX, y - minY]);
    }
    return { width: maxX - minX + 1, height: maxY - minY + 1, pixels };
  }

  /* Largest whole-number block size that fits, so every glyph pixel stays a crisp square. */
  function blockScale(available, artWidth, low = 2, high = 14) {
    if (!(artWidth > 0) || !(available > 0) || !Number.isFinite(available)) return low;
    return clamp(Math.floor(available / artWidth), low, high);
  }

  function bandColor(row, height, bands) {
    if (!bands.length) return "#000";
    return bands[clamp(Math.floor((row / Math.max(1, height)) * bands.length), 0, bands.length - 1)];
  }

  /* Deterministic shuffle so the dissolve-in looks identical on every load. */
  function revealOrder(count, seed = 7) {
    const order = Array.from({ length: Math.max(0, count | 0) }, (_, index) => index);
    let state = (seed >>> 0) || 1;
    for (let index = order.length - 1; index > 0; index -= 1) {
      state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
      const swap = state % (index + 1);
      [order[index], order[swap]] = [order[swap], order[index]];
    }
    return order;
  }

  function spritePixels(rows) {
    const out = [];
    rows.forEach((row, y) => [...row].forEach((cell, x) => { if (cell !== ".") out.push([x, y, cell]); }));
    return out;
  }

  /* Court geometry in art pixels for a strip `width` art pixels wide. */
  function courtLayout(width) {
    const w = Math.max(96, Math.floor(width) || 96);
    const board = w - 12;
    return { width: w, height: ART_HEIGHT, floor: FLOOR, ground: FLOOR - 7, board,
      rimLeft: board - 9, rimRight: board - 1, rimY: 12, rimCenter: board - 5,
      start: 8, shoot: Math.max(24, board - 52) };
  }

  /* Ball state for an attract-loop frame. x/y are the sprite's top-left in art pixels. */
  function ballState(frame, width) {
    const c = courtLayout(width);
    const f = ((Math.floor(frame) % LOOP) + LOOP) % LOOP;
    const DRIBBLE = 48, SHOT = 16, NET = 6, DROP = 8;
    if (f < DRIBBLE) {
      const local = f % 12;
      const height = Math.round(9 * Math.sin((Math.PI * local) / 12));
      return { phase: "dribble", x: Math.round(c.start + ((c.shoot - c.start) * f) / DRIBBLE),
        y: c.ground - height, squash: local === 0, spin: Math.floor(f / 2) % 2 };
    }
    if (f < DRIBBLE + SHOT) {
      const t = (f - DRIBBLE) / (SHOT - 1);
      const x0 = c.shoot, y0 = c.ground - 9, x1 = c.rimCenter - 3, y1 = c.rimY - 7;
      const arc = Math.max(0, Math.min(y0, y1) - 1);
      return { phase: "shot", x: Math.round(x0 + (x1 - x0) * t),
        y: Math.round(y0 + (y1 - y0) * t - arc * 4 * t * (1 - t)), squash: false, spin: Math.floor(f / 2) % 2 };
    }
    if (f < DRIBBLE + SHOT + NET) {
      const t = (f - DRIBBLE - SHOT) / (NET - 1);
      return { phase: "net", x: c.rimCenter - 3, y: Math.round(c.rimY - 7 + 10 * t), squash: false, spin: f % 2 };
    }
    if (f < DRIBBLE + SHOT + NET + DROP) {
      const t = (f - DRIBBLE - SHOT - NET) / (DROP - 1);
      const from = c.rimY + 3;
      return { phase: "drop", x: c.rimCenter - 3 - Math.round(4 * t), y: Math.round(from + (c.ground - from) * t),
        squash: t === 1, spin: f % 2 };
    }
    const settle = f - (DRIBBLE + SHOT + NET + DROP);
    const bounce = settle < 8 ? Math.round(3 * Math.sin((Math.PI * settle) / 8)) : 0;
    return { phase: "rest", x: c.rimCenter - 7 - Math.min(settle, 12), y: c.ground - bounce,
      squash: settle === 8, spin: settle < 8 ? settle % 2 : 0 };
  }

  /* ---------- drawing ---------- */

  function rasterize(doc, text) {
    const chars = [...text];
    const canvas = doc.createElement("canvas");
    canvas.width = GLYPH * chars.length + 8; canvas.height = GLYPH + 8;
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    if (!ctx) return { width: 0, height: 0, pixels: [] };
    ctx.font = `${GLYPH}px "${FONT}"`; ctx.textBaseline = "top"; ctx.fillStyle = "#fff";
    ctx.fillText(text, 4, 4);
    return bitmapFromAlpha(ctx.getImageData(0, 0, canvas.width, canvas.height).data, canvas.width, canvas.height);
  }

  function paintMark(ctx, bitmap, depth, palette, shown) {
    ctx.clearRect(0, 0, bitmap.width + depth, bitmap.height + depth);
    const visible = (index) => !shown || shown.has(index);
    for (let step = depth; step >= 1; step -= 1) {
      ctx.fillStyle = step === depth && depth > 1 ? palette.shadow : palette.ember;
      bitmap.pixels.forEach(([x, y], index) => { if (visible(index)) ctx.fillRect(x + step, y + step, 1, 1); });
    }
    bitmap.pixels.forEach(([x, y], index) => {
      if (!visible(index)) return;
      ctx.fillStyle = bandColor(y, bitmap.height, palette.bands);
      ctx.fillRect(x, y, 1, 1);
    });
  }

  function drawSprite(ctx, rows, left, top) {
    const tone = { o: COLORS.ball, s: COLORS.seam, h: COLORS.ballLight };
    for (const [x, y, cell] of spritePixels(rows)) {
      ctx.fillStyle = tone[cell] || COLORS.ball;
      ctx.fillRect(left + x, top + y, 1, 1);
    }
  }

  function paintCourtLayer(ctx, layout) {
    const { width, height, floor, board } = layout;
    ctx.clearRect(0, 0, width, height);
    const fade = 30;
    for (let y = floor; y < height; y += 1) {
      for (let x = 0; x < width; x += 1) {
        const edge = Math.min(x, width - 1 - x) / fade;
        if (edge < 1 && bayer(x, y) >= edge) continue;
        if (y === floor) { ctx.fillStyle = COLORS.courtLine; ctx.fillRect(x, y, 1, 1); continue; }
        const plank = Math.floor((y - floor - 1) / 3);
        const seam = (x + plank * 17) % 29 === 0;
        ctx.fillStyle = seam ? COLORS.woodSeam : COLORS.wood[plank % COLORS.wood.length];
        ctx.fillRect(x, y, 1, 1);
      }
    }
    ctx.fillStyle = COLORS.steelDark; ctx.fillRect(board + 4, 6, 2, floor - 6);
    ctx.fillStyle = COLORS.steel; ctx.fillRect(board + 4, 6, 1, floor - 6); ctx.fillRect(board + 1, 6, 4, 1);
    ctx.fillStyle = COLORS.chalk; ctx.fillRect(board, 2, 1, 14);
    ctx.fillStyle = COLORS.ball; ctx.fillRect(layout.rimLeft, layout.rimY, layout.rimRight - layout.rimLeft + 1, 1);
  }

  function paintNet(ctx, layout, swish) {
    ctx.fillStyle = COLORS.net;
    const top = layout.rimY + 1, stretch = swish ? 1 : 0;
    for (let row = 0; row < 6 + stretch; row += 1) {
      const inset = Math.floor(row / 2);
      for (let x = layout.rimLeft + inset; x <= layout.rimRight - inset; x += 1) {
        if ((x + row + (swish ? 1 : 0)) % 2 === 0) ctx.fillRect(x, top + row, 1, 1);
      }
    }
  }

  function paintFrame(ctx, layer, layout, frame) {
    ctx.clearRect(0, 0, layout.width, layout.height);
    ctx.drawImage(layer, 0, 0);
    const ball = ballState(frame, layout.width);
    const f = ((frame % LOOP) + LOOP) % LOOP;
    if (ball.phase === "shot" || ball.phase === "net") {
      ctx.fillStyle = COLORS.trail;
      for (let back = 48; back < Math.min(f, 64); back += 2) {
        const past = ballState(back, layout.width);
        ctx.fillRect(past.x + 3, past.y + 3, 1, 1);
      }
    }
    const shadowWidth = clamp(7 - Math.round((layout.ground - ball.y) / 3), 2, 7);
    ctx.fillStyle = "rgba(0,0,0,.45)";
    ctx.fillRect(ball.x + Math.floor((7 - shadowWidth) / 2), layout.floor + 1, shadowWidth, 1);
    const behindNet = ball.phase === "net";
    if (behindNet) drawSprite(ctx, BALL_FRAMES[ball.spin], ball.x, ball.y);
    paintNet(ctx, layout, ball.phase === "net");
    if (!behindNet) drawSprite(ctx, ball.squash ? BALL_SQUASH : BALL_FRAMES[ball.spin], ball.x, ball.y + (ball.squash ? 1 : 0));
    if (f >= 64 && f < 86 && Math.floor(f / 3) % 2 === 0) {
      ctx.fillStyle = COLORS.ball;
      for (const [x, y] of spritePixels(PLUS_TWO)) ctx.fillRect(layout.rimCenter - 4 + x, 2 + y, 1, 1);
    }
  }

  /* ---------- runtime ---------- */

  function createTicker(win, step) {
    let raf = 0, last = 0, running = false;
    const frameMs = 1000 / FPS;
    function loop(now) {
      if (!running) return;
      if (!last || now - last >= frameMs) { last = now; step(); }
      raf = win.requestAnimationFrame(loop);
    }
    return {
      start() { if (running) return; running = true; last = 0; raf = win.requestAnimationFrame(loop); },
      stop() { running = false; if (raf) win.cancelAnimationFrame(raf); raf = 0; },
      get running() { return running; },
    };
  }

  function reducedMotion(win) {
    try { return Boolean(win.matchMedia && win.matchMedia("(prefers-reduced-motion: reduce)").matches); }
    catch { return false; }
  }

  async function initMarks(doc, win) {
    const canvases = [...doc.querySelectorAll("canvas[data-pixel-text]")];
    if (!canvases.length || !doc.fonts || typeof doc.fonts.load !== "function") return false;
    try { await doc.fonts.load(`${GLYPH}px "${FONT}"`); } catch { return false; }
    if (typeof doc.fonts.check === "function" && !doc.fonts.check(`${GLYPH}px "${FONT}"`)) return false;
    const marks = canvases.map((canvas) => {
      const bitmap = rasterize(doc, canvas.dataset.pixelText || "");
      const depth = clamp(Number(canvas.dataset.depth) || 1, 0, 3);
      return { canvas, bitmap, depth, palette: PALETTES[canvas.dataset.palette] || PALETTES.chalk,
        fraction: clamp(Number(canvas.dataset.fill) || .8, .2, 1), max: Number(canvas.dataset.max) || 12 };
    }).filter((mark) => mark.bitmap.pixels.length);
    if (!marks.length) return false;
    const fit = () => marks.forEach((mark) => {
      const host = mark.canvas.parentElement;
      const available = (host && host.clientWidth) || win.innerWidth || 1200;
      const art = mark.bitmap.width + mark.depth;
      const scale = blockScale(available * mark.fraction, art, 2, mark.max);
      mark.canvas.style.width = `${art * scale}px`;
      mark.canvas.style.height = `${(mark.bitmap.height + mark.depth) * scale}px`;
    });
    marks.forEach((mark) => {
      mark.canvas.width = mark.bitmap.width + mark.depth;
      mark.canvas.height = mark.bitmap.height + mark.depth;
    });
    fit();
    if (typeof win.ResizeObserver === "function") {
      const observer = new win.ResizeObserver(fit);
      marks.forEach((mark) => mark.canvas.parentElement && observer.observe(mark.canvas.parentElement));
    } else win.addEventListener("resize", fit);
    const still = reducedMotion(win);
    marks.forEach((mark) => {
      const ctx = mark.canvas.getContext("2d");
      if (!ctx) return;
      if (still) { paintMark(ctx, mark.bitmap, mark.depth, mark.palette, null); return; }
      const order = revealOrder(mark.bitmap.pixels.length, mark.bitmap.pixels.length);
      const started = win.performance ? win.performance.now() : Date.now();
      const duration = 760;
      const step = (now) => {
        const progress = clamp((now - started) / duration, 0, 1);
        paintMark(ctx, mark.bitmap, mark.depth, mark.palette,
          progress >= 1 ? null : new Set(order.slice(0, Math.ceil(order.length * progress))));
        if (progress < 1) win.requestAnimationFrame(step);
      };
      win.requestAnimationFrame(step);
    });
    const hero = doc.querySelector("[data-arcade-hero]");
    if (hero) hero.classList.add("is-drawn");
    return true;
  }

  function initCourt(doc, win) {
    const canvas = doc.getElementById("arcade-court");
    if (!canvas || !canvas.getContext) return null;
    const ctx = canvas.getContext("2d");
    if (!ctx) return null;
    const layer = doc.createElement("canvas");
    const layerCtx = layer.getContext("2d");
    let layout = courtLayout(96), frame = 0, inView = true, reduced = reducedMotion(win);
    const size = () => {
      const host = canvas.parentElement;
      const cssWidth = (host && host.clientWidth) || win.innerWidth || 1200;
      layout = courtLayout(Math.floor(cssWidth / ART_PIXEL));
      canvas.width = layout.width; canvas.height = layout.height;
      canvas.style.width = `${layout.width * ART_PIXEL}px`; canvas.style.height = `${layout.height * ART_PIXEL}px`;
      layer.width = layout.width; layer.height = layout.height;
      if (layerCtx) paintCourtLayer(layerCtx, layout);
      paintFrame(ctx, layer, layout, reduced ? STILL_FRAME : frame);
    };
    const ticker = createTicker(win, () => { frame = (frame + 1) % LOOP; paintFrame(ctx, layer, layout, frame); });
    const sync = () => { if (inView && !doc.hidden && !reduced) ticker.start(); else ticker.stop(); };
    size();
    if (typeof win.ResizeObserver === "function") new win.ResizeObserver(size).observe(canvas.parentElement || canvas);
    else win.addEventListener("resize", size);
    if (typeof win.IntersectionObserver === "function") {
      new win.IntersectionObserver((entries) => { inView = entries.some((entry) => entry.isIntersecting); sync(); })
        .observe(canvas);
    }
    doc.addEventListener("visibilitychange", sync);
    try {
      const query = win.matchMedia("(prefers-reduced-motion: reduce)");
      const change = () => { reduced = query.matches; if (reduced) paintFrame(ctx, layer, layout, STILL_FRAME); sync(); };
      if (query.addEventListener) query.addEventListener("change", change);
    } catch { /* matchMedia unavailable: keep animating */ }
    sync();
    return { ticker, get frame() { return frame; }, get layout() { return layout; }, sync };
  }

  /* Exposes the video column's height to CSS for the sticky stage (layout only). */
  function initStickyStage(doc, win) {
    const room = doc.getElementById("film-room");
    const column = room && room.querySelector(".screen-column");
    if (!room || !column || typeof column.getBoundingClientRect !== "function") return null;
    const measure = () => room.style.setProperty("--stage-h", `${Math.ceil(column.getBoundingClientRect().height)}px`);
    measure();
    if (typeof win.ResizeObserver === "function") new win.ResizeObserver(measure).observe(column);
    else win.addEventListener("resize", measure);
    return measure;
  }

  function init(doc = root.document, win = root) {
    if (!doc) return null;
    const court = initCourt(doc, win);
    const stage = initStickyStage(doc, win);
    const marks = initMarks(doc, win);
    return { court, stage, marks };
  }

  const api = { FONT, GLYPH, FPS, LOOP, ART_HEIGHT, ART_PIXEL, STILL_FRAME, PALETTES,
    bitmapFromAlpha, blockScale, bandColor, revealOrder, spritePixels, courtLayout, ballState,
    paintMark, paintFrame, createTicker, initStickyStage, init };
  if (typeof module === "object" && module.exports) module.exports = api;
  else {
    root.Arcade = api;
    if (root.document && root.document.readyState === "loading") root.document.addEventListener("DOMContentLoaded", () => init());
    else init();
  }
})(typeof window !== "undefined" ? window : globalThis);
