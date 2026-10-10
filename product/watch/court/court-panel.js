import { createCourtGeometry, svgNode, toVerticalCourt } from './court-geometry.js';
import { getCourtTheme } from './themes.js';

const finite = Number.isFinite;
const clock = t => `${Math.floor(Math.max(0, t) / 60)}:${String(Math.floor(Math.max(0, t) % 60)).padStart(2, '0')}`;

/** Court content only. Stage owns its glass shell, screen position and animation. */
export function createCourtPanel({ onMode = () => {}, onSelect = () => {}, onTheme = () => {} } = {}) {
  const element = document.createElement('section');
  element.className = 'court-content'; element.dataset.component = 'halfCourt';
  element.innerHTML = `<header class="court-header">
    <span class="court-team-badge"><img class="court-team-logo" alt="" hidden><span class="court-team-short">DAL</span></span>
    <div class="court-team-heading"><span class="court-city">DALLAS</span><strong class="court-team-name">MAVERICKS</strong></div>
  </header>
  <div class="court-segments" role="group" aria-label="球场视野">
    <button type="button" data-court-mode="fullCourt" aria-pressed="true">全场</button>
    <button type="button" data-court-mode="halfCourt" aria-pressed="false">半场</button>
    <span class="court-segment-highlight" aria-hidden="true"></span>
  </div>
  <label class="court-theme-choice"><select aria-label="球场"><option value="mavericks">独行侠</option><option value="rockets">火箭</option></select></label>
  <div class="court-view-zone"><div class="court-floor-frame"><div class="court-baseline top">DALLAS MAVERICKS</div><div class="court-drawing"></div><div class="court-baseline bottom">DALLAS MAVERICKS</div></div>
  </div>
  <div class="court-legend" aria-label="战术图例">
    <span><i class="white-team"></i>红色 · 火箭</span><span><i class="dark-team"></i>浅色 · 独行侠</span>
    <span><i class="route-swatch"></i>示意移动</span><span><i class="held-swatch"></i>过去位置</span>
  </div>
`;
  const q = selector => element.querySelector(selector);
  const geometry = createCourtGeometry(); q('.court-drawing').append(geometry.svg);
  const zone = q('.court-view-zone'), floorFrame = q('.court-floor-frame');
  const markers = new Map(); let progress = 0, data = null, time = 0, focusId = null;
  let theme = getCourtTheme('dallas'), modeStyle = {}, destroyed = false;
  let lastAvailable = null, lastStyleKey = '', cachedZone = { width: 0, height: 0 };
  const ballNode = svgNode('g', { class: 'court-ball' });
  ballNode.innerHTML = '<circle r="1.05"/><path d="M-1 0H1M0-1V1M-.7-.7Q.5 0-.7.7M.7-.7Q-.5 0 .7 .7"/>';
  geometry.ball.append(ballNode);
  function measure() {
    if (destroyed) return;
    const rect = zone.getBoundingClientRect(); cachedZone = { width: rect.width, height: rect.height }; fitCourt();
  }
  function fitCourt() {
    const { width: availableW, height: availableH } = cachedZone;
    if (!availableW || !availableH) return;
    const h = 94 - 47 * progress;
    // Baseline wordmarks are outside the playing field. Every playing-field axis stays uniform.
    const capUnits = 3.8 + 2 * progress;
    // Reserve the frame's two border pixels so the SVG's displayed ratio is exact.
    const width = Math.max(0, Math.min(availableW - 2, (availableH - 2) * 50 / (h + capUnits * (2 - progress))));
    floorFrame.style.width = `${width + 2}px`;
    geometry.svg.style.height = `${width * h / 50}px`;
    floorFrame.style.setProperty('--court-cap-height', `${width * capUnits / 50}px`);
    q('.court-baseline.bottom').style.height = `${width * capUnits * (1 - progress) / 50}px`;
  }
  function setView(value) {
    progress = Math.max(0, Math.min(1, finite(value) ? value : 0));
    const half = progress >= .5;
    element.dataset.view = half ? 'half' : 'full'; element.dataset.component = half ? 'halfCourt' : 'fullCourt';
    element.style.setProperty('--court-half-progress', progress);
    geometry.svg.setAttribute('viewBox', `0 0 50 ${94 - 47 * progress}`);
    markers.forEach(node => node.setAttribute('tabindex', node.style.display !== 'none' && Number(node.dataset.courtY) <= 94 - 47 * progress ? '0' : '-1'));
    element.querySelectorAll('[data-court-mode]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.courtMode === (half ? 'halfCourt' : 'fullCourt'))));
    // Read this frame's new panel/auxiliary geometry before fitting the same SVG.
    // Relying only on ResizeObserver would retain the previous frame's court size.
    measure();
  }
  function applyTheme() {
    q('.court-city').textContent = theme.city; q('.court-team-name').textContent = theme.name;
    const badge = q('.court-team-badge'), logo = q('.court-team-logo'), centerLogo = q('.court-center-logo');
    const hasLogo = Boolean(theme.logo);
    badge.classList.toggle('has-logo', hasLogo);
    badge.title = theme.caption;
    logo.hidden = !hasLogo; logo.alt = hasLogo ? `${theme.caption} Logo` : '';
    q('.court-team-short').textContent = theme.short;
    q('.court-team-short').hidden = hasLogo;
    centerLogo.style.display = hasLogo ? '' : 'none';
    if (hasLogo) { logo.src = theme.logo; centerLogo.setAttribute('href', theme.logo); }
    else { logo.removeAttribute('src'); centerLogo.removeAttribute('href'); }
    centerLogo.setAttribute('aria-label', `${theme.caption} Logo`);
    q('.court-center-mark').style.display = hasLogo ? 'none' : '';
    element.querySelectorAll('.court-baseline').forEach(node => { node.textContent = `${theme.city} ${theme.name}`; });
    q('.court-center-mark').textContent = theme.short;
    element.style.setProperty('--court-theme-paint', theme.paint);
    element.style.setProperty('--court-theme-wood', theme.wood);
    element.style.setProperty('--court-theme-line', theme.line);
  }
  function setTheme(id) { theme = getCourtTheme(id); element.dataset.theme = id; applyTheme(); }
  function setStyle(next = {}) {
    const key = JSON.stringify(next);
    if (key === lastStyleKey) return;
    lastStyleKey = key;
    modeStyle = next;
    const colors = { woodColor: '--court-wood', paintColor: '--court-paint', lineColor: '--court-line', color: '--court-text' };
    for (const [key, css] of Object.entries(colors)) {
      if (/^#[0-9a-f]{3,8}$/i.test(next[key] || '')) element.style.setProperty(css, next[key]);
      else element.style.removeProperty(css);
    }
    const numerics = { courtRadius: ['--court-radius', 'px', 0, 32], fontSize: ['--court-font-size', 'px', 10, 30], lineWidth: ['--court-line-width', '', .08, 1.2], markerSize: ['--court-marker-size', '', 1, 3.5] };
    for (const [key, [css, unit, min, max]] of Object.entries(numerics)) if (finite(next[key])) element.style.setProperty(css, `${Math.max(min, Math.min(max, next[key]))}${unit}`);
    // Marker radius lives in the same field coordinate model; this changes appearance only.
    for (const marker of markers.values()) marker.querySelector('circle').setAttribute('r', String(next.markerSize || 2.05));
    measure();
  }
  function setStory() {
    data = null; update(null, 0, null);
  }
  function playerNode(position) {
    let node = markers.get(position.id);
    if (!node) {
      node = svgNode('g', { class: 'court-player', role: 'button', tabindex: '0', 'aria-label': `关注匿名编号 ${position.id}` });
      node.dataset.playerId = position.id;
      const circle = svgNode('circle', { r: modeStyle.markerSize || 2.05 });
      const label = svgNode('text', { 'text-anchor': 'middle', 'dominant-baseline': 'central' }); label.textContent = position.id;
      const title = svgNode('title'); node.append(circle, label, title);
      const choose = () => { onSelect(position.id); };
      node.addEventListener('click', choose);
      node.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); choose(); } });
      geometry.players.append(node); markers.set(position.id, node);
    }
    return node;
  }
  function drawRoutes(dataset, t, selected) {
    geometry.routes.replaceChildren();
    if (!dataset || !globalThis.CourtLab) return;
    const focus = CourtLab.trailFocus(dataset, t, selected || 'all');
    if (!focus.id) return;
    const track = dataset.tracks.find(item => item.id === focus.id);
    if (!track) return;
    const segments = CourtLab.collectTrails(track, t, Math.min(2, Math.max(0, t - focus.start)), dataset);
    for (const segment of segments) {
      const [a, b] = segment.points.map(p => toVerticalCourt(p.x, p.y));
      if (Math.hypot(a.x - b.x, a.y - b.y) < .2) continue;
      geometry.routes.append(svgNode('path', { d: `M${a.x} ${a.y}L${b.x} ${b.y}`, class: 'court-route', 'marker-end': `url(#${geometry.id}-arrow)` }));
    }
  }
  function update(dataset, t, selected) {
    data = dataset; time = finite(t) ? t : 0; focusId = selected;
    const available = !!(dataset && globalThis.CourtLab);
    if (lastAvailable !== available) { element.dataset.hasData = String(available); lastAvailable = available; }
    markers.forEach(node => { node.style.display = 'none'; });
    let positions = [], ball = null;
    if (available) {
      positions = CourtLab.samplePositions(dataset, time); ball = CourtLab.sampleBall(dataset, time);
      for (const position of positions) {
        if (!finite(position.x) || !finite(position.y)) continue;
        const node = playerNode(position), point = toVerticalCourt(position.x, position.y);
        node.style.display = ''; node.setAttribute('transform', `translate(${point.x} ${point.y})`);
        node.dataset.courtY = String(point.y); node.setAttribute('tabindex', point.y <= 94 - 47 * progress ? '0' : '-1');
        node.dataset.team = position.team; node.dataset.status = position.status;
        node.classList.toggle('is-focused', position.id === focusId);
        node.classList.toggle('is-holder', position.id === ball?.holder);
        node.setAttribute('aria-pressed', String(position.id === focusId));
        node.querySelector('title').textContent = `${position.id} · ${position.held ? `过去位置 ${clock(position.sourceTime)}` : '编辑示意位置'} · 未经人工复核`;
      }
    }
    drawRoutes(dataset, time, selected);
    const showBall = ball && finite(ball.x) && finite(ball.y);
    ballNode.style.display = showBall ? '' : 'none';
    if (showBall) { const point = toVerticalCourt(ball.x, ball.y); ballNode.setAttribute('transform', `translate(${point.x + (ball.holder ? 2.3 : 0)} ${point.y + (ball.holder ? 1.4 : 0)})`); ballNode.classList.toggle('is-held-position', ball.heldPosition === true); }

  }
  element.querySelectorAll('[data-court-mode]').forEach(button => button.addEventListener('click', () => onMode(button.dataset.courtMode)));
  q('.court-theme-choice select').addEventListener('change', e => onTheme(e.target.value));
  const observer = new ResizeObserver(measure); observer.observe(zone);
  applyTheme(); setView(0); update(null, 0, null);
  return { element, setThemeChoice(value) { q('.court-theme-choice select').value = value; }, setView, update, setTheme, setStyle, setStory, destroy() { destroyed = true; observer.disconnect(); markers.clear(); element.remove(); } };
}
