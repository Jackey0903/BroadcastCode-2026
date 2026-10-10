import { ATLAS, ANIMATIONS } from './sprite-atlas.js';

const mounted = new WeakMap();
const defaultAsset = new URL('./assets/game-buddy-crt.webp', import.meta.url).href;
const defaultSequence = Object.freeze(['idle']);
function makeClips(sequence) {
  if (!Array.isArray(sequence) || !sequence.length || sequence.length > 64 || Array.from(sequence).some(name => !Object.hasOwn(ANIMATIONS, name))) throw new TypeError('sequence must contain 1–64 existing atlas actions');
  return sequence.map(name => ({ ...ANIMATIONS[name], duration: ANIMATIONS[name].frames / ANIMATIONS[name].fps * 1000 }));
}

/** Pure transparent ambient animation. One instance per container; no event logic. */
export function mountGameBuddyAmbient(container, { width = 192, sequence = defaultSequence, assetUrl = defaultAsset, onError = error => console.warn(error) } = {}) {
  const doc = container?.ownerDocument;
  const view = doc?.defaultView;
  if (!view || !(container instanceof view.Element)) throw new TypeError('A DOM container is required');
  if (!Number.isFinite(width) || width <= 0 || width > 4096) throw new RangeError('width must be a number in (0, 4096]');
  if (typeof onError !== 'function') throw new TypeError('onError must be a function');
  let clips = makeClips(sequence);
  let duration = clips.reduce((sum, clip) => sum + clip.duration, 0);
  const host = doc.createElement('div');
  // All layout is local to this private child. The caller positions its own container.
  host.style.cssText = `all:initial;display:block;position:relative;width:${width}px;height:${width * ATLAS.cellHeight / ATLAS.cellWidth}px;pointer-events:none;overflow:hidden;background:transparent;border:0;padding:0;margin:0;box-shadow:none;`;
  host.setAttribute('aria-hidden', 'true');
  const shadow = host.attachShadow({ mode: 'open' });
  const style = doc.createElement('style');
  style.textContent = 'canvas{all:initial;display:block;width:100%;height:100%;pointer-events:none;background:transparent;border:0;padding:0;margin:0;box-shadow:none;}';
  const canvas = doc.createElement('canvas');
  const dpr = Math.min(3, Math.max(1, view.devicePixelRatio || 1));
  canvas.width = Math.round(width * dpr);
  canvas.height = Math.round(width * ATLAS.cellHeight / ATLAS.cellWidth * dpr);
  const context = canvas.getContext('2d', { alpha: true });
  if (!context) throw new Error('Canvas 2D is unavailable');
  shadow.append(style, canvas);
  const image = new view.Image();
  const media = view.matchMedia('(prefers-reduced-motion: reduce)');
  let reduced = media.matches;
  let paused = false;
  let destroyed = false;
  let ready = false;
  let elapsed = 0;
  let started = null;
  let timer = null;
  let raf = null;
  let drawn = '';
  const now = () => view.performance.now();
  function cancelPending() {
    if (timer !== null) view.clearTimeout(timer);
    if (raf !== null) view.cancelAnimationFrame(raf);
    timer = raf = null;
  }
  function freeze() {
    if (started !== null) elapsed += now() - started;
    started = null;
    cancelPending();
  }
  function frameAt(time) {
    let offset = ((time % duration) + duration) % duration;
    for (const clip of clips) {
      if (offset < clip.duration) {
        const frame = Math.min(clip.frames - 1, Math.floor(offset * clip.fps / 1000));
        return { row: clip.row, frame, remaining: (frame + 1) * 1000 / clip.fps - offset };
      }
      offset -= clip.duration;
    }
    return { row: clips[0].row, frame: 0, remaining: 1000 / clips[0].fps };
  }
  function paint() {
    if (destroyed || !ready || doc.hidden) return;
    const frame = reduced
      ? { row: ANIMATIONS.idle.row, frame: 0 }
      : frameAt(elapsed + (started === null ? 0 : now() - started));
    const key = `${frame.row}:${frame.frame}`;
    if (key !== drawn) {
      context.clearRect(0, 0, canvas.width, canvas.height);
      context.drawImage(image, frame.frame * ATLAS.cellWidth, frame.row * ATLAS.cellHeight,
        ATLAS.cellWidth, ATLAS.cellHeight, 0, 0, canvas.width, canvas.height);
      drawn = key;
    }
    // One timed wake-up per frame; RAF is requested only when that frame is due.
    if (started !== null && !reduced && !paused) timer = view.setTimeout(() => {
      timer = null;
      raf = view.requestAnimationFrame(() => { raf = null; paint(); });
    }, Math.max(1, frame.remaining));
  }
  function sync() {
    freeze();
    if (destroyed || !ready || doc.hidden) return;
    if (!paused && !reduced) started = now();
    paint();
  }
  const onVisibility = () => sync();
  const onMotion = event => { reduced = event.matches; sync(); };
  function setSequence(sequence) {
    if (destroyed) return;
    const next = makeClips(sequence);
    freeze();
    clips = next;
    duration = clips.reduce((sum, clip) => sum + clip.duration, 0);
    elapsed = 0;
    sync();
  }
  const handle = {
    play(action) { setSequence([action]); },
    setSequence,
    pause() { if (!destroyed && !paused) { paused = true; sync(); } },
    resume() { if (!destroyed && paused) { paused = false; sync(); } },
    destroy() {
      if (destroyed) return;
      destroyed = true; freeze();
      doc.removeEventListener('visibilitychange', onVisibility);
      media.removeEventListener('change', onMotion);
      image.onload = image.onerror = null;
      host.remove();
      if (mounted.get(container) === handle) mounted.delete(container);
    },
  };
  image.onload = () => {
    if (destroyed) return;
    if (image.naturalWidth !== ATLAS.width || image.naturalHeight !== ATLAS.height) { image.onerror(); return; }
    ready = true; sync();
  };
  image.onerror = () => {
    if (destroyed) return;
    ready = false; freeze();
    context.clearRect(0, 0, canvas.width, canvas.height);
    onError(new Error('Game Buddy atlas failed to load or is not 1536×1872'));
  };
  // Validate/create first, then replace only this component's prior child in this container.
  mounted.get(container)?.destroy();
  mounted.set(container, handle);
  container.append(host);
  doc.addEventListener('visibilitychange', onVisibility);
  media.addEventListener('change', onMotion);
  image.src = assetUrl;
  return handle;
}
