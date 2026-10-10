// Shared by the liquidGL uniform uploader and both GPU shader generators.
// Distances are CSS pixels, never a percentage of the complete video texture.
export const OPTICS_PATCH = 'broadcastcode-optics-smooth-v5';
export const FROST_KERNEL_RADIUS = 4;
const sigma = 1.75;
const axis = Array.from({length: 9}, (_, i) => ({x: i - 4, weight: Math.exp(-((i - 4) ** 2) / (2 * sigma ** 2))}));
const axisTotal = axis.reduce((a, b) => a + b.weight, 0);
axis.forEach(tap => tap.weight /= axisTotal);
const pair = (a, b) => ({x: (a.x * a.weight + b.x * b.weight) / (a.weight + b.weight), weight: a.weight + b.weight});
// Pair adjacent Gaussian weights into a single bilinear fetch. Exact for an
// aligned, unit-texel grid; at fractional/variable support it is a smooth
// positive approximation. Five positions per axis reduce 81 fetches to 25.
const pairedAxis = [pair(axis[0], axis[1]), pair(axis[2], axis[3]), axis[4], pair(axis[5], axis[6]), pair(axis[7], axis[8])];
export const FROST_KERNEL = Object.freeze(pairedAxis.flatMap(ty =>
  pairedAxis.map(tx => Object.freeze({x: tx.x, y: ty.x, weight: tx.weight * ty.weight}))));

const nonnegative = value => Number.isFinite(value) ? Math.max(0, value) : 0;
export function opticalMetrics(options = {}, source = {}) {
  const frost = nonnegative(options.frost);
  const refractionCss = Math.min(12, nonnegative(options.refraction) * 160);
  const bevelCss = Math.min(8, nonnegative(options.bevelDepth) * 60);
  // Smooth and strictly increasing throughout the editor's 0–8 range. Bounded
  // support prevents a sparse kernel from producing separated image copies.
  const frostRadiusCss = 8 * frost / (frost + 2);
  const scale = Math.max(.001, Number(source.scaleFactor) || 1);
  const sourcePixelSize = [scale / Math.max(1, Number(source.width) || 1), scale / Math.max(1, Number(source.height) || 1)];
  const maxOffsetCss = refractionCss + bevelCss;
  const aberration = nonnegative(options.aberration);
  return {refractionCss, bevelCss, frostRadiusCss, sourcePixelSize, maxOffsetCss,
    samplePaddingCss: maxOffsetCss * (1 + aberration) + Math.max(.5, frostRadiusCss)};
}

export function tiltDisplacementCss(degrees = 0) {
  return Math.min(12, Math.abs(Math.tan((Number(degrees) || 0) * Math.PI / 180) * 8));
}

// Actual backend program/pipeline selection uses this key. Constant variants
// remove both expensive inner per-tap conditionals from the common path.
export function opticsShaderVariant(aberration = 0, stacked = false) {
  const chromatic = Number(aberration) > 0;
  const stack = !!stacked;
  return {key: (chromatic ? 1 : 0) + (stack ? 2 : 0), chromatic, stack,
    name: `${chromatic ? 'chromatic' : 'clear'}-${stack ? 'stacked' : 'source'}`,
    sourceSamples: FROST_KERNEL.length * (chromatic ? 3 : 1),
    maxTextureSamples: FROST_KERNEL.length * (chromatic ? 3 : 1) * (stack ? 2 : 1)};
}

// Each fragment uses this same positive, normalized kernel. No screen-space
// hash, time seed, random offset, or color-channel-specific stochastic sample.
// Unrolled constants avoid GLSL ES 1.0 array-indexing restrictions.
export function gaussianShader(language) {
  const glsl = language === 'glsl';
  if (!glsl && language !== 'wgsl') throw new TypeError('Unknown shader language');
  const float = n => Number(n).toFixed(10);
  const taps = FROST_KERNEL.map(({x, y, weight}) => glsl
    ? `  sum += gaussianSource(uv + vec2(${float(x)}, ${float(y)}) * stepSize, chroma) * ${float(weight)};`
    : `  sum += gaussianSource(uv + vec2<f32>(${float(x)}, ${float(y)}) * stepSize, chroma) * ${float(weight)};`).join('\n');
  return glsl ? `
vec4 gaussianSource(vec2 uv, vec2 chroma) {
  vec4 middle = sampleSource(uv);
#if LIQUID_CHROMATIC
  return vec4(sampleSource(uv - chroma).r, middle.g, sampleSource(uv + chroma).b, middle.a);
#else
  return middle;
#endif
}
vec4 smoothFrost(vec2 uv, vec2 chroma, vec2 sourcePixelSize, float radiusCss) {
  vec2 stepSize = sourcePixelSize * (radiusCss / ${float(FROST_KERNEL_RADIUS)});
  vec4 sum = vec4(0.0);
${taps}
  return sum;
}` : `
fn gaussianSource(uv: vec2<f32>, chroma: vec2<f32>) -> vec4<f32> {
  let middle = sampleSource(uv);
  if (!CHROMATIC_ENABLED) { return middle; }
  return vec4<f32>(sampleSource(uv - chroma).r, middle.g, sampleSource(uv + chroma).b, middle.a);
}
fn smoothFrost(uv: vec2<f32>, chroma: vec2<f32>, sourcePixelSize: vec2<f32>, radiusCss: f32) -> vec4<f32> {
  let stepSize = sourcePixelSize * (radiusCss / ${float(FROST_KERNEL_RADIUS)});
  var sum = vec4<f32>(0.0);
${taps}
  return sum;
}`;
}

// Numerical mirror of the same generated kernel, used for impulse/edge tests.
export function sampleSmoothFrost(sample, x, y, radiusCss) {
  const step = radiusCss / FROST_KERNEL_RADIUS;
  return FROST_KERNEL.reduce((sum, tap) => sum + sample(x + tap.x * step, y + tap.y * step) * tap.weight, 0);
}
