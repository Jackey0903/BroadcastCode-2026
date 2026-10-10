/** One NBA-size model in feet. View changes never deform the model or its data.
 * Source: https://jr.nba.com/interactive-court/ (checked 2026-10-10).
 * Paint and texture are presentation variables; court dimensions are fixed.
 */
export const COURT = Object.freeze({ width: 50, length: 94, half: 47, rimY: 5.25, threeRadius: 23.75 });
export const SVG_NS = 'http://www.w3.org/2000/svg';
export function svgNode(tag, attributes = {}) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, String(value));
  return node;
}

/** Source axes: baseline-to-baseline x 0..94, near-to-far sideline y 0..50.
 * Broadcast presentation: left basket at the top, camera-near sideline at the
 * left and camera-far sideline at the right. The stored court-lab coordinates
 * keep their original meaning. All players, held positions, routes and the ball
 * use this mapping; changing the viewBox for half court never changes it.
 */
export function toVerticalCourt(x, y) { return { x: y, y: x }; }

let serial = 0;
export function createCourtGeometry() {
  const id = `court-model-${++serial}`;
  const svg = svgNode('svg', { viewBox: '0 0 50 94', preserveAspectRatio: 'xMidYMid meet', class: 'court-svg', role: 'img', 'aria-label': '可编辑纵向篮球场，匿名人员战术示意' });
  // Grain uses vector strips and CSS color/opacity, never a reference-image background.
  const arcY = COURT.rimY + Math.sqrt(COURT.threeRadius ** 2 - 22 ** 2);
  const end = `<rect class="court-paint" x="17" y="0" width="16" height="19"/>
    <g class="court-lines">
      <path d="M17 0V19H33V0M19 0V19M31 0V19"/>
      <path d="M19 19A6 6 0 0 0 31 19"/>
      <path class="court-dashed" d="M19 19A6 6 0 0 1 31 19"/>
      <path d="M3 0V${arcY}A23.75 23.75 0 0 0 47 ${arcY}V0"/>
      <path d="M21 4V5.25A4 4 0 0 0 29 5.25V4"/>
      <path d="M22 4H28" class="court-backboard"/>
      <circle cx="25" cy="5.25" r=".75" class="court-rim"/>
      <path d="M16.1 7H17M33 7H33.9M16.1 10H17M33 10H33.9M16.1 13H17M33 13H33.9M16.1 16H17M33 16H33.9"/>
    </g>`;
  svg.innerHTML = `<defs>
    <pattern id="${id}-planks" patternUnits="userSpaceOnUse" width="8" height="27">
      <rect class="court-plank-light" width="1.6" height="27"/><rect class="court-plank-dark" x="2.1" width=".8" height="27"/>
      <rect class="court-plank-light" x="4.6" width="2.1" height="27"/>
      <path class="court-grain" d="M.4 0V12M1.1 8V27M2.5 0V27M3.4 0V27M5 0V19M5.4 4V27M6.2 0V27M7.5 0V27M0 15H2M2 6H4M4 22H6M6 10H8"/>
    </pattern>
    <linearGradient id="${id}-sheen" x2="1" y2=".3"><stop stop-color="#fff" stop-opacity=".12"/><stop offset=".48" stop-color="#fff" stop-opacity="0"/><stop offset="1" stop-color="#81410e" stop-opacity=".08"/></linearGradient>
    <marker id="${id}-arrow" viewBox="0 0 6 6" refX="4.8" refY="3" markerWidth="4.5" markerHeight="4.5" orient="auto-start-reverse"><path d="M0 .7L4.8 3 0 5.3" fill="none" stroke="context-stroke" stroke-width="1.2"/></marker>
  </defs>
  <g data-group="wood"><rect class="court-floor" width="50" height="94"/><rect width="50" height="94" fill="url(#${id}-planks)"/><rect width="50" height="94" fill="url(#${id}-sheen)"/></g>
  <g data-group="paint-and-lines">${end}<g transform="translate(50 94) rotate(180)">${end}</g>
    <g class="court-lines"><rect x=".12" y=".12" width="49.76" height="93.76"/><path d="M0 47H50M0 28H2M48 28H50M0 66H2M48 66H50"/><circle cx="25" cy="47" r="6"/><circle cx="25" cy="47" r="2"/></g>
  </g>
  <g data-group="team-wordmark" class="court-brand"><text class="court-center-mark" x="25" y="47" text-anchor="middle" dominant-baseline="central">HOU</text></g>
  <g data-group="routes"></g><g data-group="players"></g><g data-group="ball"></g>`;
  return { svg, id, routes: svg.querySelector('[data-group="routes"]'), players: svg.querySelector('[data-group="players"]'), ball: svg.querySelector('[data-group="ball"]') };
}
