// Shared atlas coordinates only: no events, DOM, API or application state.
export const ATLAS = Object.freeze({ width: 1536, height: 1872, cellWidth: 192, cellHeight: 208 });
export const ANIMATIONS = Object.freeze(Object.fromEntries(Object.entries({
  idle: { row: 0, frames: 6, fps: 6 },
  'running-right': { row: 1, frames: 8, fps: 10 },
  'running-left': { row: 2, frames: 8, fps: 10 },
  waving: { row: 3, frames: 4, fps: 7 },
  jumping: { row: 4, frames: 5, fps: 8 },
  failed: { row: 5, frames: 8, fps: 7 },
  waiting: { row: 6, frames: 6, fps: 6 },
  running: { row: 7, frames: 6, fps: 7 },
  review: { row: 8, frames: 6, fps: 6 },
}).map(([name, spec]) => [name, Object.freeze(spec)])));
