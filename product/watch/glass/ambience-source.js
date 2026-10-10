/** One bitmap is both visible behind the UI and sampled by liquidGL.
 * Reads the existing video; it creates no second player or media clock.
 */
const observed = new WeakSet(), softwareBuffers = new WeakMap();
let nativeFilterSupport;
function supportsCanvasFilter() {
  if (nativeFilterSupport !== undefined) return nativeFilterSupport;
  const probe = document.createElement('canvas'); probe.width = probe.height = 2;
  const ctx = probe.getContext('2d', { willReadFrequently: true });
  if (!('filter' in ctx)) return (nativeFilterSupport = false);
  // Test pixels, not property presence: some WebKit builds expose a no-op filter.
  ctx.filter = 'brightness(0)'; ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, 2, 2);
  return (nativeFilterSupport = ctx.getImageData(0, 0, 1, 1).data[0] < 8);
}

/** Three separable box passes approximate Gaussian blur at a small resolution.
 * Edge replication avoids dark fringes; tone is baked into opaque RGB pixels.
 */
export function softenAmbiencePixels(data, width, height, radius, scratch) {
  const work = scratch || new Float32Array(width * height * 4);
  const r = Math.max(1, Math.round(radius)), divisor = 2 * r + 1;
  for (let pass = 0; pass < 3; pass++) {
    for (let y = 0; y < height; y++) for (let c = 0; c < 3; c++) {
      let sum = 0;
      for (let x = -r; x <= r; x++) sum += data[(y * width + Math.max(0, Math.min(width - 1, x))) * 4 + c];
      for (let x = 0; x < width; x++) {
        work[(y * width + x) * 4 + c] = sum / divisor;
        sum += data[(y * width + Math.min(width - 1, x + r + 1)) * 4 + c] - data[(y * width + Math.max(0, x - r)) * 4 + c];
      }
    }
    for (let x = 0; x < width; x++) for (let c = 0; c < 3; c++) {
      let sum = 0;
      for (let y = -r; y <= r; y++) sum += work[(Math.max(0, Math.min(height - 1, y)) * width + x) * 4 + c];
      for (let y = 0; y < height; y++) {
        data[(y * width + x) * 4 + c] = sum / divisor;
        sum += work[(Math.min(height - 1, y + r + 1) * width + x) * 4 + c] - work[(Math.max(0, y - r) * width + x) * 4 + c];
      }
    }
  }
  for (let i = 0; i < data.length; i += 4) {
    const luma = .2126 * data[i] + .7152 * data[i + 1] + .0722 * data[i + 2];
    for (let c = 0; c < 3; c++) data[i + c] = (luma + (data[i + c] - luma) * .65) * .30;
    data[i + 3] = 255;
  }
  return data;
}

export function paintAmbienceSource(canvas, video, stage) {
  if (!canvas || video.readyState < 2 || !video.videoWidth) return;
  const width = 384;
  const height = Math.max(1, Math.round(width * stage.clientHeight / Math.max(1, stage.clientWidth)));
  if (canvas.width !== width || canvas.height !== height) { canvas.width = width; canvas.height = height; }
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, width, height);
  const scale = Math.max(width / video.videoWidth, height / video.videoHeight) * 1.1;
  const dw = video.videoWidth * scale, dh = video.videoHeight * scale;
  const native = supportsCanvasFilter();
  if (native) {
    ctx.save();
    ctx.filter = `blur(${32 * width / Math.max(1, stage.clientWidth)}px) brightness(.30) saturate(.65)`;
    ctx.drawImage(video, (width - dw) / 2, (height - dh) / 2, dw, dh);
    ctx.restore();
  } else {
    let buffer = softwareBuffers.get(canvas);
    if (!buffer) {
      const surface = document.createElement('canvas');
      buffer = { surface, context: surface.getContext('2d', { willReadFrequently: true }) };
      softwareBuffers.set(canvas, buffer);
    }
    const sw = 96, sh = Math.max(1, Math.round(sw * height / width));
    if (buffer.surface.width !== sw || buffer.surface.height !== sh) {
      buffer.surface.width = sw; buffer.surface.height = sh;
      buffer.scratch = new Float32Array(sw * sh * 4);
    }
    const sx = sw / width, sy = sh / height;
    buffer.context.drawImage(video, (width - dw) * sx / 2, (height - dh) * sy / 2, dw * sx, dh * sy);
    const pixels = buffer.context.getImageData(0, 0, sw, sh);
    softenAmbiencePixels(pixels.data, sw, sh, 32 * sw / Math.max(1, stage.clientWidth), buffer.scratch);
    buffer.context.putImageData(pixels, 0, 0);
    ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(buffer.surface, 0, 0, width, height);
  }
  // Former scene-shade overlay is baked too, preserving source layer order.
  const radial = ctx.createRadialGradient(width * .75, height, 0, width * .75, height, Math.max(width, height) * .75);
  radial.addColorStop(0, '#23304445'); radial.addColorStop(.65, '#23304400'); radial.addColorStop(1, '#23304400');
  ctx.fillStyle = radial; ctx.fillRect(0, 0, width, height);
  const shade = ctx.createLinearGradient(0, 0, width, height);
  shade.addColorStop(0, '#11192433'); shade.addColorStop(1, '#0b0b1133');
  ctx.fillStyle = shade; ctx.fillRect(0, 0, width, height);
  canvas.dataset.liquidFrame = String((Number(canvas.dataset.liquidFrame) || 0) + 1);
  canvas.dataset.filterBaked = 'true';
  canvas.dataset.filterMethod = native ? 'canvas2d-native' : 'software-box-blur';
  if (!observed.has(canvas)) {
    observed.add(canvas);
    const resize = new ResizeObserver(() => paintAmbienceSource(canvas, video, stage));
    resize.observe(stage);
    window.addEventListener('pagehide', () => resize.disconnect(), { once: true });
  }
}
