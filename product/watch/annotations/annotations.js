import { mascotSVG } from './mascot.js';
export { mascotSVG };

/** Pure validation kept separate for meaningful data-boundary tests.
 * Never consumes CourtLab `image`: those points are foot/floor observations.
 * Only explicit, unexpired normalized head landmarks can become a marker.
 */
export function validHeadAnchors(anchors, time, { focusId, shotId, mediaId } = {}) {
  if (!Array.isArray(anchors) || !Number.isFinite(time)) return [];
  const now = time * 1000;
  const latest = new Map();
  for (const anchor of anchors) {
    if (!anchor || typeof anchor.playerId !== 'string' || !Number.isFinite(anchor.timeMs) || anchor.timeMs > now) continue;
    const old = latest.get(anchor.playerId);
    if (!old || old.timeMs <= anchor.timeMs) latest.set(anchor.playerId, anchor);
  }
  return [...latest.values()].filter(a => {
    const p = a.point;
    return (!focusId || a.playerId === focusId) && (!shotId || a.shotId === shotId) && (!mediaId || a.mediaId === mediaId)
      && a.coordinateSystem === 'video-normalized-top-left' && ['head-top', 'head-center'].includes(a.landmark)
      && ['observed', 'estimated'].includes(a.status) && Number.isFinite(a.expiresAtMs) && now <= a.expiresAtMs
      && p && Number.isFinite(p.x) && Number.isFinite(p.y) && p.x >= 0 && p.x <= 1 && p.y >= 0 && p.y <= 1;
  }).sort((a, b) => b.timeMs - a.timeMs).slice(0, 1);
}

export function createAnnotationLayer({ video, onSelect = () => {} } = {}) {
  const element = document.createElement('div');
  element.className = 'annotation-layer'; element.dataset.component = 'annotations';
  element.setAttribute('aria-label', '比赛画面头部锚点标注');
  let style = { size: 40, color: '#f69529', expression: 'happy', style: 'classic', labelSize: 15 };
  let last = null;
  const marker = document.createElement('button'); marker.type = 'button'; marker.className = 'mascot-marker';
  marker.innerHTML = '<span class="mascot-art"></span><span class="mascot-label"></span><span class="mascot-connector"></span>';
  marker.hidden = true; element.append(marker);
  const art = marker.querySelector('.mascot-art'), label = marker.querySelector('.mascot-label');
  marker.addEventListener('click', () => onSelect(marker.dataset.playerId));
  function setStyle(next = {}) {
    style = { ...style, ...next };
    element.style.setProperty('--annotation-mascot-size', `${Math.max(16, Math.min(100, Number(style.size) || 40))}px`);
    element.style.setProperty('--annotation-label-size', `${Math.max(10, Math.min(26, Number(style.labelSize) || 15))}px`);
    art.innerHTML = mascotSVG(style.size, style);
    if (last) update(last);
  }
  function update(input) {
    last = input;
    const { time, anchors, focusId, enabled, rect, shotId, mediaId } = input;
    const entries = enabled && (!video || video.readyState >= 2) ? validHeadAnchors(anchors, time, { focusId, shotId, mediaId }) : [];
    const anchor = entries[0]; marker.hidden = !anchor;
    element.dataset.activeCount = String(entries.length);
    if (!anchor) return;
    // Host already equals the contained video rectangle; do not add its screen offset twice.
    marker.style.left = `${anchor.point.x * 100}%`; marker.style.top = `${anchor.point.y * 100}%`;
    marker.dataset.playerId = anchor.playerId;
    marker.setAttribute('aria-label', `关注 ${anchor.label || anchor.playerId}`);
    label.textContent = anchor.label || anchor.playerId;
    marker.classList.toggle('is-focused', anchor.playerId === focusId);
    if (rect) { element.dataset.videoWidth = rect.width; element.dataset.videoHeight = rect.height; }
  }
  setStyle();
  return { element, update, setStyle, destroy() { marker.remove(); element.remove(); last = null; } };
}
