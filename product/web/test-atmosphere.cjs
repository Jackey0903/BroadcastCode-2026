const test = require("node:test");
const assert = require("node:assert/strict");
const {spherePoints, seamDistance, rotatePoint, projectPoint,
  createMotionController, initAtmosphere} = require("./atmosphere.js");

test("ball geometry is deterministic and stays on a unit sphere", () => {
  const points = spherePoints(1500);
  assert.equal(points.length, 1500);
  assert.deepEqual(points, spherePoints(1500));
  for (const point of points) assert.ok(Math.abs(Math.hypot(point.x, point.y, point.z) - 1) < 1e-10);
  assert.ok(points.some(point => point.seam));
  assert.ok(points.filter(point => point.seam).length < points.length * .18);
});

test("sample budgets stay bounded on mobile and for invalid inputs", () => {
  assert.equal(spherePoints(680).length, 680);
  assert.equal(spherePoints(Infinity).length, 1500);
  assert.equal(spherePoints(1e9).length, 2400);
  assert.equal(spherePoints(-2).length, 120);
});

test("seam classification and rotation preserve sphere geometry", () => {
  assert.equal(seamDistance({x: 0, y: 1, z: 0}), 0);
  for (const point of spherePoints(680)) {
    const rotated = rotatePoint(point, 1.3);
    assert.ok(Math.abs(Math.hypot(rotated.x, rotated.y, rotated.z) - 1) < 1e-10);
    assert.equal(rotated.seam, point.seam);
  }
});

test("mild perspective is finite for every sphere point and keeps the center", () => {
  assert.equal(projectPoint({x: 0, y: 0, z: 1}, 110, 200, 120).x, 200);
  for (const point of spherePoints(1500)) {
    const result = projectPoint(rotatePoint(point, .62), 110, 200, 120);
    assert.ok(Number.isFinite(result.x) && Number.isFinite(result.y));
    assert.ok(Math.abs(result.x - 200) < 115 && Math.abs(result.y - 120) < 115);
  }
});

function harness() {
  const callbacks = new Map(), draws = [];
  let handle = 0;
  const controller = createMotionController({
    requestFrame(callback) { callbacks.set(++handle, callback); return handle; },
    cancelFrame(id) { callbacks.delete(id); },
    draw(delta, timestamp) { draws.push({delta, timestamp}); }
  });
  return {controller, draws, callbacks,
    frame(timestamp) { const current = [...callbacks.values()]; callbacks.clear(); current.forEach(callback => callback(timestamp)); }};
}

test("animation requires a visible document, viewport intersection and nonempty container", () => {
  const h = harness();
  h.controller.setState({hidden: false, inViewport: true});
  assert.equal(h.callbacks.size, 0);
  assert.equal(h.draws.length, 0);
  h.controller.setState({hasSize: true});
  assert.equal(h.callbacks.size, 1);
  assert.equal(h.draws.length, 1);
  h.controller.setState({inViewport: false});
  assert.equal(h.callbacks.size, 0);
  h.controller.invalidate();
  assert.equal(h.draws.length, 1);
  h.controller.setState({inViewport: true, hidden: true});
  assert.equal(h.callbacks.size, 0);
});

test("leaving the viewport cancels frames and resuming does not advance hidden time", () => {
  const h = harness();
  h.controller.setState({hidden: false, inViewport: true, hasSize: true});
  h.frame(0); h.frame(40);
  assert.equal(h.draws.at(-1).delta, .04);
  h.controller.setState({inViewport: false});
  assert.equal(h.callbacks.size, 0);
  h.controller.setState({inViewport: true});
  h.frame(60000); h.frame(60040);
  assert.equal(h.draws.at(-1).delta, .04);
  assert.ok(h.draws.every(item => item.delta <= .066));
});

test("reduced motion paints one static frame and never schedules animation", () => {
  const h = harness();
  h.controller.setState({hidden: false, inViewport: true, hasSize: true, reducedMotion: true});
  assert.equal(h.draws.length, 1);
  assert.equal(h.draws[0].delta, 0);
  assert.equal(h.callbacks.size, 0);
  h.controller.setState({hidden: false});
  assert.equal(h.draws.length, 1);
  h.controller.invalidate();
  assert.equal(h.draws.length, 2);
  h.controller.setState({reducedMotion: false});
  assert.equal(h.callbacks.size, 1);
  h.controller.setState({reducedMotion: true});
  assert.equal(h.callbacks.size, 0);
});

test("30 fps cap bounds paint cost even with 120 Hz frame callbacks", () => {
  const h = harness();
  h.controller.setState({hidden: false, inViewport: true, hasSize: true});
  for (let timestamp = 0; timestamp <= 1000; timestamp += 1000 / 120) h.frame(timestamp);
  assert.ok(h.draws.length <= 31);
  assert.ok(h.draws.length >= 20);
  assert.equal(h.callbacks.size, 1);
  h.controller.destroy();
  assert.equal(h.callbacks.size, 0);
  h.controller.setState({hidden: false, inViewport: true});
  assert.equal(h.callbacks.size, 0);
});

test("unsupported Canvas environments fall back without crashing page behavior", () => {
  assert.equal(initAtmosphere(null), null);
  assert.equal(initAtmosphere({ownerDocument: {}, getContext: () => null}, {requestAnimationFrame() {}}), null);
});

test("browser scene caps DPR, observes only its container and tears down every listener", () => {
  const frames = new Map(), documentEvents = new Map(), preferenceEvents = new Map();
  const drawCalls = [], observers = [];
  const context = {};
  for (const method of ["setTransform", "clearRect", "save", "translate", "rotate", "beginPath",
    "ellipse", "stroke", "restore", "fillRect", "arc", "fill", "lineTo", "moveTo"])
    context[method] = (...args) => drawCalls.push([method, ...args]);
  let containerWidth = 375, containerHeight = 230;
  const container = {getBoundingClientRect() { return {width: containerWidth, height: containerHeight,
    left: 0, right: containerWidth, top: 10, bottom: 10 + containerHeight}; }};
  const doc = {hidden: false,
    addEventListener(type, handler) { documentEvents.set(type, handler); },
    removeEventListener(type) { documentEvents.delete(type); }};
  const media = {matches: false,
    addEventListener(type, handler) { preferenceEvents.set(type, handler); },
    removeEventListener(type) { preferenceEvents.delete(type); }};
  let serial = 0;
  const env = {devicePixelRatio: 5, innerWidth: 390, innerHeight: 800,
    matchMedia() { return media; },
    requestAnimationFrame(callback) { frames.set(++serial, callback); return serial; },
    cancelAnimationFrame(id) { frames.delete(id); },
    ResizeObserver: class {
      constructor(callback) { this.callback = callback; observers.push(this); }
      observe(target) { this.target = target; }
      disconnect() { this.disconnected = true; }
    },
    IntersectionObserver: class {
      constructor(callback) { this.callback = callback; observers.push(this); }
      observe(target) { this.target = target; }
      disconnect() { this.disconnected = true; }
    }};
  const attributes = {};
  const canvas = {ownerDocument: doc, style: {}, parentElement: container,
    getContext() { return context; }, closest() { return container; },
    setAttribute(key, value) { attributes[key] = value; }};
  const scene = initAtmosphere(canvas, env);
  assert.equal(canvas.width, 750);
  assert.equal(canvas.height, 460);
  assert.equal(canvas.style.pointerEvents, "none");
  assert.equal(attributes["aria-hidden"], "true");
  assert.deepEqual(drawCalls.find(call => call[0] === "setTransform"), ["setTransform", 2, 0, 0, 2, 0, 0]);
  assert.equal(drawCalls.filter(call => call[0] === "arc").length, 1500);
  const desktopDotRadii = drawCalls.filter(call => call[0] === "arc").map(call => call[3]);
  assert.ok(Math.max(...desktopDotRadii) > 1.45);
  assert.ok(observers.every(observer => observer.target === container));
  assert.equal(frames.size, 1);
  containerWidth = 140; containerHeight = 132;
  drawCalls.length = 0;
  observers[0].callback();
  assert.equal(canvas.width, 280);
  assert.equal(canvas.height, 264);
  assert.equal(drawCalls.filter(call => call[0] === "arc").length, 680);
  const mobileDotRadii = drawCalls.filter(call => call[0] === "arc").map(call => call[3]);
  assert.ok(Math.max(...mobileDotRadii) < 1.33);
  assert.equal(frames.size, 1);
  observers[1].callback([{target: container, isIntersecting: false, intersectionRatio: 0}]);
  assert.equal(frames.size, 0);
  observers[1].callback([{target: container, isIntersecting: true, intersectionRatio: 1}]);
  assert.equal(frames.size, 1);
  doc.hidden = true; documentEvents.get("visibilitychange")();
  assert.equal(frames.size, 0);
  doc.hidden = false; documentEvents.get("visibilitychange")();
  media.matches = true; preferenceEvents.get("change")();
  assert.equal(frames.size, 0);
  scene.destroy();
  assert.ok(observers.every(observer => observer.disconnected));
  assert.equal(documentEvents.size, 0);
  assert.equal(preferenceEvents.size, 0);
});
