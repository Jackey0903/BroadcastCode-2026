/*
 * The Hidden Play — decorative basketball point cloud, never player tracking.
 * Local visual reference: draftcode/local_nbadraft_workspace/
 * 绿黑黑客松视觉效果试衣间.html (setupCanvas) and index.html (setupMatrix).
 * Retains their local Canvas / capped-DPR approach; replaces the full-screen,
 * perpetual loop with a bounded hero scene, deterministic geometry, and
 * visibility / reduced-motion guards. No old draft-business content is reused.
 */
(function (root) {
  "use strict";

  const TAU = Math.PI * 2;
  const SMALL_CONTAINER_WIDTH = 220;
  const SEAM_NORMALS = [
    [1, 0, 0], [0, 1, 0],
    [Math.SQRT1_2, 0, Math.SQRT1_2],
    [Math.SQRT1_2, 0, -Math.SQRT1_2]
  ];

  function seamDistance(point) {
    return Math.min(...SEAM_NORMALS.map(([x, y, z]) =>
      Math.abs(point.x * x + point.y * y + point.z * z)));
  }

  function spherePoints(count) {
    const size = Math.max(120, Math.min(2400,
      Number.isFinite(count) ? Math.floor(count) : 1500));
    const goldenAngle = Math.PI * (3 - Math.sqrt(5));
    return Array.from({length: size}, (_, index) => {
      const y = 1 - 2 * (index + .5) / size;
      const radial = Math.sqrt(1 - y * y);
      const azimuth = index * goldenAngle;
      const point = {x: Math.cos(azimuth) * radial, y,
        z: Math.sin(azimuth) * radial};
      return {...point, seam: seamDistance(point) < .026};
    });
  }

  function pointRotator(yaw, pitch = -.22, roll = -.18) {
    const cy = Math.cos(yaw), sy = Math.sin(yaw);
    const cp = Math.cos(pitch), sp = Math.sin(pitch);
    const cr = Math.cos(roll), sr = Math.sin(roll);
    return point => {
      const x = point.x * cy + point.z * sy;
      const z = -point.x * sy + point.z * cy;
      const y = point.y * cp - z * sp;
      const depth = point.y * sp + z * cp;
      return {x: x * cr - y * sr, y: x * sr + y * cr,
        z: depth, seam: !!point.seam};
    };
  }

  function rotatePoint(point, yaw, pitch = -.22, roll = -.18) {
    return pointRotator(yaw, pitch, roll)(point);
  }

  function projectPoint(point, radius, centerX = 0, centerY = 0) {
    // Mild perspective gives depth without enlarging the front hemisphere.
    const scale = 3.6 / (3.6 - point.z);
    return {x: centerX + point.x * radius * scale,
      y: centerY + point.y * radius * scale, z: point.z,
      scale, seam: !!point.seam};
  }

  function createMotionController({requestFrame, cancelFrame, draw, fps = 30}) {
    const state = {hidden: true, inViewport: false, reducedMotion: false,
      hasSize: false};
    let pending = null, lastTime = null, dirty = true, disposed = false;
    const interval = 1000 / Math.min(30, Math.max(1, fps));
    const eligible = () => !disposed && !state.hidden && state.inViewport && state.hasSize;
    const animated = () => eligible() && !state.reducedMotion;

    function stop() {
      if (pending !== null) cancelFrame(pending);
      pending = null;
      lastTime = null;
    }
    function queue() {
      if (animated() && pending === null) pending = requestFrame(tick);
    }
    function tick(timestamp) {
      pending = null;
      if (!animated()) { stop(); return; }
      if (lastTime === null) lastTime = timestamp;
      else if (timestamp - lastTime >= interval) {
        draw(Math.min((timestamp - lastTime) / 1000, .066), timestamp);
        lastTime = timestamp;
      }
      queue();
    }
    function sync() {
      if (!animated()) stop();
      if (eligible() && dirty) { draw(0, null); dirty = false; }
      queue();
    }
    return {
      setState(next) {
        const wasEligible = eligible();
        const wasReduced = state.reducedMotion;
        Object.assign(state, next);
        if (!wasEligible && eligible() || wasReduced !== state.reducedMotion) dirty = true;
        sync();
      },
      invalidate() { dirty = true; sync(); },
      snapshot() { return {...state, pending: pending !== null, disposed}; },
      destroy() { disposed = true; stop(); }
    };
  }

  function initAtmosphere(canvas, environment) {
    const win = environment || root;
    const doc = canvas && canvas.ownerDocument;
    if (!canvas || !doc || !win || typeof win.requestAnimationFrame !== "function") return null;
    let ctx;
    try { ctx = canvas.getContext("2d", {alpha: true}); } catch (_) { return null; }
    if (!ctx) return null;
    canvas.setAttribute("aria-hidden", "true");
    canvas.style.pointerEvents = "none";
    const container = canvas.closest(".hero-art") || canvas.parentElement;
    if (!container) return null;
    let width = 0, height = 0, radius = 0, elapsed = 0, points = [];
    let resizeObserver = null, intersectionObserver = null;
    const motionQuery = typeof win.matchMedia === "function"
      ? win.matchMedia("(prefers-reduced-motion: reduce)") : null;

    function paint(delta) {
      elapsed += delta;
      const yaw = .62 + (motionQuery && motionQuery.matches ? 0 : elapsed * .13);
      const rotate = pointRotator(yaw);
      const centerX = width * .51, centerY = height * .50;
      ctx.clearRect(0, 0, width, height);

      // Two quiet elliptical marks suggest a broadcast emblem, not a data path.
      ctx.save();
      ctx.translate(centerX, centerY);
      ctx.rotate(-.20);
      ctx.strokeStyle = "rgba(31, 38, 32, .15)";
      ctx.lineWidth = .8;
      ctx.beginPath();
      ctx.ellipse(0, 0, radius * 1.32, radius * .32, 0, 0, TAU);
      ctx.stroke();
      ctx.restore();

      // Bounded deterministic background specks; no pairwise particle graph.
      const specks = width < SMALL_CONTAINER_WIDTH ? 10 : 18;
      for (let index = 0; index < specks; index++) {
        const x = (index * .61803398875 % 1) * width;
        const y = ((index + 4) * .41421356237 % 1) * height;
        if (Math.hypot(x - centerX, y - centerY) < radius * 1.08) continue;
        ctx.fillStyle = index % 3 ? "rgba(31, 38, 32, .18)" : "rgba(227, 100, 44, .34)";
        ctx.fillRect(x, y, 1.5, 1.5);
      }

      const projected = points.map(point => projectPoint(
        rotate(point), radius, centerX, centerY)).sort((a, b) => a.z - b.z);
      const dotSize = width < SMALL_CONTAINER_WIDTH ? 1.16 : 1.30;
      for (const point of projected) {
        const front = (point.z + 1) / 2;
        const alpha = point.z < 0 ? .08 + front * .18 : .40 + front * .51;
        ctx.fillStyle = point.seam
          ? `rgba(27, 34, 28, ${alpha * .92})`
          : `rgba(224, 98, 43, ${alpha})`;
        ctx.beginPath();
        ctx.arc(point.x, point.y, dotSize * (.76 + front * .38), 0, TAU);
        ctx.fill();
      }

      // Fine front-only great circles join the darker seam dots into a ball.
      ctx.strokeStyle = "rgba(27, 34, 28, .76)";
      ctx.lineWidth = 1.25;
      for (const normal of SEAM_NORMALS) {
        const basis = normal[1] ? [1, 0, 0] : [0, 1, 0];
        const tangent = [normal[1] * basis[2] - normal[2] * basis[1],
          normal[2] * basis[0] - normal[0] * basis[2],
          normal[0] * basis[1] - normal[1] * basis[0]];
        let connected = false;
        ctx.beginPath();
        for (let step = 0; step <= 160; step++) {
          const angle = step / 160 * TAU;
          const transformed = rotate({
            x: basis[0] * Math.cos(angle) + tangent[0] * Math.sin(angle),
            y: basis[1] * Math.cos(angle) + tangent[1] * Math.sin(angle),
            z: basis[2] * Math.cos(angle) + tangent[2] * Math.sin(angle)
          });
          if (transformed.z < .035) { connected = false; continue; }
          const point = projectPoint(transformed, radius, centerX, centerY);
          if (connected) ctx.lineTo(point.x, point.y);
          else ctx.moveTo(point.x, point.y);
          connected = true;
        }
        ctx.stroke();
      }
    }

    const controller = createMotionController({
      requestFrame: callback => win.requestAnimationFrame(callback),
      cancelFrame: handle => win.cancelAnimationFrame(handle), draw: paint
    });

    function viewportVisible() {
      const rect = container.getBoundingClientRect();
      return rect.bottom > 0 && rect.right > 0 && rect.top < win.innerHeight && rect.left < win.innerWidth;
    }
    function resize() {
      const rect = container.getBoundingClientRect();
      width = Math.max(0, rect.width); height = Math.max(0, rect.height);
      const dpr = Math.min(2, Math.max(1, win.devicePixelRatio || 1));
      canvas.width = Math.max(1, Math.round(width * dpr));
      canvas.height = Math.max(1, Math.round(height * dpr));
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      radius = Math.min(112, width * .32, height * .43);
      points = spherePoints(width < SMALL_CONTAINER_WIDTH ? 680 : 1500);
      controller.setState({hasSize: width > 0 && height > 0, inViewport: viewportVisible()});
      controller.invalidate();
    }
    function visibility() { controller.setState({hidden: !!doc.hidden}); }
    function preference() { controller.setState({reducedMotion: !!(motionQuery && motionQuery.matches)}); }
    function scrollVisibility() { controller.setState({inViewport: viewportVisible()}); }

    if (typeof win.ResizeObserver === "function") {
      resizeObserver = new win.ResizeObserver(resize); resizeObserver.observe(container);
    } else win.addEventListener("resize", resize, {passive: true});
    if (typeof win.IntersectionObserver === "function") {
      intersectionObserver = new win.IntersectionObserver(entries => {
        const entry = entries.find(item => item.target === container);
        if (entry) controller.setState({inViewport: entry.isIntersecting && entry.intersectionRatio > 0});
      }, {threshold: 0});
      intersectionObserver.observe(container);
    } else win.addEventListener("scroll", scrollVisibility, {passive: true});
    doc.addEventListener("visibilitychange", visibility);
    if (motionQuery && motionQuery.addEventListener) motionQuery.addEventListener("change", preference);
    else if (motionQuery && motionQuery.addListener) motionQuery.addListener(preference);
    resize(); preference(); visibility();
    return {
      controller,
      destroy() {
        controller.destroy();
        if (resizeObserver) resizeObserver.disconnect();
        else win.removeEventListener("resize", resize);
        if (intersectionObserver) intersectionObserver.disconnect();
        else win.removeEventListener("scroll", scrollVisibility);
        doc.removeEventListener("visibilitychange", visibility);
        if (motionQuery && motionQuery.removeEventListener) motionQuery.removeEventListener("change", preference);
        else if (motionQuery && motionQuery.removeListener) motionQuery.removeListener(preference);
      }
    };
  }

  const api = {spherePoints, seamDistance, rotatePoint, projectPoint,
    createMotionController, initAtmosphere};
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root && root.document) {
    const boot = () => {
      const canvas = root.document.getElementById("hero-particles");
      if (canvas && !canvas.dataset.atmosphereReady) {
        const scene = initAtmosphere(canvas, root);
        if (scene) canvas.dataset.atmosphereReady = "true";
      }
    };
    if (root.document.readyState === "loading") root.document.addEventListener("DOMContentLoaded", boot, {once: true});
    else boot();
  }
})(typeof window === "object" ? window : null);
