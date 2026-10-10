# liquidGL 3.0.0 / BroadcastCode adapter

Source: npm liquid-gl@3.0.0; upstream commit 88f681ab7035fd55b04f63edff1841e32c4199e9. npm tarball SHA1: 30200ae22230ca040e1a4ba67f79f8f2c2823113. MIT license retained in vendor/liquid-gl/LICENSE. No upstream demo assets or fonts are included.

## Public controls

The readable vendored source provides `setOptics` for validated in-place display settings and `getRenderStatus` for actual backend, texture, live-canvas update count and restored-video-region count. All components use GlassManager; none access renderer internals. Turning glass off still destroys every lens and GPU canvas; turning it on reinitializes those renderers without rebuilding the video.

## Live background correction (broadcastcode-optics-safari-source-v3)

Upstream `registerDynamic` ignores Canvas nodes during DOM rasterisation, while canvas pixel writes do not trigger its DOM animation invalidation. Registering a wrapper also ignores its child canvas. Upstream's built-in DOM painter does not apply CSS `filter`, so a snapshot after resize could contain sharp, bright video imagery instead of the visible dark blurred ambience. Upstream's video uploader follows current DOM rectangles but does not restore the old uploaded rectangle after a layout change.

The bounded local changes address those source errors:

- `ambience-source.js` reads the existing primary video into the **same canvas visible behind the UI**. It bakes blur, brightness, saturation and the background shade. The former CSS filter/scale/shade are removed to avoid double filtering. Canvas aspect follows the actual stage; pause and resize repaint the same source. No second player, media timeline, generated match imagery or audio is added.
- Registered Canvas sources use their live bitmap and explicit `data-liquid-frame` revision, rather than asynchronous DOM recapture. Their source opacity includes zero correctly. BroadcastCode's ambient canvas is composited below its current video rectangle, including the video's corner clip. Non-canvas dynamic DOM keeps the upstream capture path.
- Static restore snapshots exclude videos, registered live canvases and elements marked `data-liquid-dynamic-container`. Thus an old video frame is never used as static background. The mark is on the video's surface only; it does not prevent automatic video sampling.
- A moving video's previously uploaded region is restored from the static background, invalidating intersecting dynamic sources. The current ambient bitmap and current video geometry are then composited. Layout animation does not rasterise the full DOM on every frame.
- Diagnostics expose `liveCanvasUpdates`, `restoredVideoRegions` and each source canvas's `frame`, dimensions and `filterBaked`. These prove source updates occurred, not visual acceptance by themselves.

### Safari source and visibility correction

Canvas filter support is now checked with actual blackened test pixels. When unsupported or ineffective (including tested native Safari), a 96-pixel-wide software path performs three separable box-blur passes with replicated edges, then multiplies brightness and reduces saturation in RGB pixels. It is upsampled into the same 384-pixel source canvas; it does not depend on CSS blur. Diagnostics report `filterBaked:true` plus `filterMethod:canvas2d-native` or `software-box-blur`. Both paths receive the same baked scene shade. Software blur is an approximation of the native Gaussian and needs device visual calibration.

The detached GPU canvas previously ignored its lens element's ancestors. Every render frame now computes cached ancestor opacity/visibility/display before metrics can early-return, records the opacity in the render signature, and uses the existing fade uniform for per-lens opacity. At zero opacity the lens is omitted; if all lenses are hidden the renderer canvas is hidden. This follows control and tab fade transitions without destroying or restarting renderers. Lens diagnostics expose `ancestorOpacity` (zero when hidden). The target's own opacity remains owned by upstream reveal logic, avoiding double fade.

The WebGPU/WebGL/CSS backend selection is unchanged. The optical shader is corrected below.

## Smooth optical correction (broadcastcode-optics-smooth-v4, superseded by v5 below)

The upstream frost branch used 16 disc samples whose angle and distance were a hash of each fragment's UV. Adjacent pixels therefore received different random estimates, especially visibly over NBA court lines, spectators and scoreboard edges. This was stochastic sampling noise, not an intentional grain layer. Turning frost to zero concealed the defect without making nonzero frost usable.

Both GLSL and WGSL now call `smoothFrost`, generated from the same positive normalized 7×7 Gaussian kernel in `glass/optics-model.js` (axis sigma 1.25). All fragments share the same 49 offsets and weights; the kernel has zero positional bias. Color dispersion uses the same smooth kernel for red, green and blue, never a separate random estimate. A zero setting samples the source directly, with the existing controlled chromatic displacement. The unused UV random functions and noisy shadow alpha quantization are removed. Nonzero frost remains adjustable live through the existing uniform upload and `setOptics`; no renderer, canvas or lens recreation is required.

The sampling support is `8*frost/(frost+2)` **CSS pixels**, strictly increasing over the editor's 0–8 range and bounded below 8px. Frost 2 gives 4px, frost 3 gives 4.8px and frost 8 gives 6.4px. Limiting support avoids the old wide, sparse sample footprint. Kernel spacing is support/3; all samples remain bilinearly filtered. The 49 taps cost 49 source samples without aberration or 147 with RGB aberration, versus the former 16 or 64 source calls. This is a quality/cost tradeoff; browser playback measurements are still required.

Refraction and bevel previously added normalized whole-scene UV offsets: a bevel of .08 could pull content by about 134px from a 1672px scene. They now mean bounded local CSS-pixel strengths: `min(12, refraction*160)` and `min(8, bevelDepth*60)`. The defaults .012/.08 therefore have a maximum combined displacement of 6.72px before the edge and centre factors, independent of viewport width and DPR. Tilt is similarly limited to 12px per axis. The renderer uploads `sourcePixelSize = snapshotScale/textureSize`; multiplying CSS distances by this value converts them to the correct source UV on either backend. The WGSL field uses previously unused uniform padding at floats 26–27, preserving all existing field offsets. Texture updates and stack/video sample bounds use the same shared model, rather than retaining oversized stale-UV padding.

`getRenderStatus` exposes `opticalPatch`, `frostKernel`, `frostSamples` and the actually uploaded `opticalMetrics`. `optics-model.test.js` exercises the runtime kernel and uniform-distance model numerically: normalization, symmetry, constant/affine-scene stability, monotonic softened contrast edges without bright duplicates, zero-frost clarity, live radius ordering and viewport/scale independence. These numerical checks do not replace visual acceptance on the real match video.

## Smooth kernel performance correction (broadcastcode-optics-smooth-v5, current)

Real six-second playback with glass enabled showed that v4's unrolled 49-point shader caused a major regression on the tested browser. Static source inspection found that every point contained uniform-conditional color and stack sample paths. That inspection identifies possible predication/register costs; it does not prove a compiler disassembly or the exact number of physically executed texture fetches.

The current kernel starts with a normalized nine-point Gaussian on each axis (sigma 1.75). Adjacent weights are merged at their weighted sample positions: five bilinear positions per axis give **25 fixed taps**. This reproduces the corresponding nine-point discrete filter for an aligned unit-texel grid; at the adjustable CSS-pixel radius or fractional source coordinates it is a smooth positive approximation, not a mathematically identical 9×9 filter. It has no stochastic positions and retains exact normalization, symmetry and affine-image stability. With frost 3 the nominal unmerged Gaussian sigma is 2.02 CSS px, close to v4's 1.96px; the same bounded support mapping and bounded refraction distances are retained.

Both backends cache static feature variants for color dispersion and lower-glass stacking. GLSL programs use compile-time `LIQUID_CHROMATIC` / `LIQUID_STACK` defines and retain their own uniform locations and vertex buffers. WebGPU pipelines use `CHROMATIC_ENABLED` / `STACK_ENABLED` override constants. The actually chosen variant is determined from each draw's aberration value and stack region; a colorless, unstacked kernel contains only **25 background samples**, without per-tap uniform RGB/stack branches. Chromatic kernels have 75 source samples; a stacked source may read both source and lower-glass textures. One additional unblurred source lookup remains for the existing transparent-source guard. Cached variants do not recompile when editing frost, refraction, bevel or tint, and do not recreate lenses, canvases or the video.

Diagnostics report `frostKernel:paired-gaussian-9x9-25tap`, `frostSamples:25`, `opticalPatch:broadcastcode-optics-smooth-v5` and the actual `shaderVariant` with kernel source/maximum texture sample counts. The shared selector is numerically tested alongside the Gaussian kernel and CSS-pixel distance model. Real playback, visual grain checks and native Safari verification are required after loading v5; source sample count alone is not a performance acceptance result.

## Verification required after refreshing the real browser

Use one paused video frame. Capture immersive → half → full → immersive without reloading, then repeat after resizing from 1672×941 to 1440×810. Confirm the right panel only refracts the dim blurred stage background, while glass over the actual video refracts that video. There must be no old full-size video silhouette outside the new video rectangle. `restoredVideoRegions` should increase during layout motion and `liveCanvasUpdates` during playback; pause/seek/resize must update the same source, without recreating the `video` element. Repeat with glass disabled, which must report zero lenses/canvases.

Safari verification: pause in half court, allow controls to auto-hide, and confirm both foreground and glass disappear together while the court remains. Move the pointer to restore them without changing lens/canvas count. Confirm ambience reports `software-box-blur`, remains dark and soft after resize/seek, and does not duplicate a sharp full-screen video.
