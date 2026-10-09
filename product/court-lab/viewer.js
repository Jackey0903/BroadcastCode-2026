/* Local basketball experiment. No detector, fabricated coordinates, or independent clock. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.CourtLab = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const SOURCE_SHA256 = '9c3e4606d04e7f79e29a112952fcf069ebab202af207af500bfbc3338bc079ce';
  const SOURCE_DURATION = 21.548118;
  const VISIBLE = new Set(['observed', 'estimated']);
  const STATUSES = new Set(['observed', 'estimated', 'occluded', 'offscreen']);
  const MAX_GAP = 0.15;
  const SCHEMATIC_MAX_GAP = 0.6;
  const SNAPSHOT_RADIUS = 0.05;
  const finite = value => typeof value === 'number' && Number.isFinite(value);
  function check(condition, message) { if (!condition) throw new Error(message); }
  function validateDataset(data) {
    check(data && typeof data === 'object' && !Array.isArray(data), '数据必须是 JSON 对象。');
    check(data.schema === 'court-lab-v1', 'schema 必须是 court-lab-v1。');
    check(data.presentation === undefined || data.presentation === 'schematic', 'presentation 仅支持 schematic 或省略。');
    check(data.sample === 'flagg', '当前实验只支持弗拉格原片。');
    check(data.sourceSha256 === SOURCE_SHA256, '数据来源哈希与本地原片不一致。');
    check(data.sourceVideo === '/samples/flagg.mp4', '原片路径与当前实验不一致。');
    check(Array.isArray(data.videoSize) && data.videoSize.length === 2 && data.videoSize[0] === 1280 && data.videoSize[1] === 720, '原片尺寸必须是 1280 × 720。');
    check(data.court && data.court.length === 94 && data.court.width === 50 && data.court.unit === 'ft' && data.court.origin === 'left-baseline-near-sideline', '球场必须为 NBA 94 × 50 英尺，并使用约定的坐标原点。');
    check(Array.isArray(data.window) && data.window.length === 2 && data.window.every(finite) && data.window[0] >= 0 && data.window[1] > data.window[0] && data.window[1] <= SOURCE_DURATION, '分析时段必须在弗拉格原片的 21.548118 秒内。');
    check(data.provenance && typeof data.provenance.method === 'string' && data.provenance.method.trim().length > 0 && typeof data.provenance.warning === 'string' && data.provenance.warning.trim().length > 0, '必须保留生成方法和数据局限说明。');
    check(Array.isArray(data.tracks) && data.tracks.length <= 10, 'tracks 必须是最多 10 名在场球员的数组。');
    const ids = new Set();
    for (const track of data.tracks) {
      check(track && (typeof track.id === 'string' || finite(track.id)), '轨迹缺少有效编号。');
      const id = String(track.id);
      check(id.length > 0 && id.length <= 80 && !ids.has(id), '轨迹编号为空、过长或重复。');
      ids.add(id);
      check(['dark', 'white'].includes(track.team), `轨迹 ${id} 的队伍无效。`);
      check(typeof track.label === 'string' && track.label.trim().length > 0 && track.label.length <= 120, `轨迹 ${id} 缺少显示标签。`);
      check(['anonymous', 'reviewed'].includes(track.identityStatus), `轨迹 ${id} 的身份状态无效。`);
      check(Array.isArray(track.points) && track.points.length <= 100000, `轨迹 ${id} 的采样点数组无效。`);
      let previous = -Infinity;
      for (const point of track.points) {
        check(point && finite(point.t) && point.t > previous && point.t >= data.window[0] - 1e-6 && point.t <= data.window[1] + 1e-6, `轨迹 ${id} 的时间必须在分析时段内严格递增。`);
        previous = point.t;
        check(STATUSES.has(point.status), `轨迹 ${id} 的可见性状态无效。`);
        check(typeof point.segment === 'string' && point.segment.length > 0 && point.segment.length <= 100, `轨迹 ${id} 缺少镜头分段。`);
        check(typeof point.reviewed === 'boolean', `轨迹 ${id} 缺少人工核对状态。`);
        if (VISIBLE.has(point.status)) {
          check(finite(point.x) && finite(point.y) && point.x >= 0 && point.x <= 94 && point.y >= 0 && point.y <= 50, `轨迹 ${id} 的可见点必须是球场内有限坐标。`);
        } else {
          check(point.x === null && point.y === null, `轨迹 ${id} 的遮挡或画外位置必须为空。`);
        }
        if (point.image !== undefined && point.image !== null) {
          check(VISIBLE.has(point.status) && Array.isArray(point.image) && point.image.length === 2 && point.image.every(finite) && point.image[0] >= 0 && point.image[0] <= 1280 && point.image[1] >= 0 && point.image[1] <= 720, `轨迹 ${id} 的原片足点坐标无效。`);
        }
      }
    }
    return data;
  }
  function upperBound(points, t) {
    let lo = 0, hi = points.length;
    while (lo < hi) {
      const mid = (lo + hi) >>> 1;
      if (points[mid].t <= t) lo = mid + 1; else hi = mid;
    }
    return lo;
  }
  function unknown(track, reason = 'no-data', point = null) {
    return { id: track.id, label: track.label, team: track.team, identityStatus: track.identityStatus, x: null, y: null, image: null, status: point ? point.status : 'unknown', reason, interpolated: false, reviewed: false };
  }
  function allowedGap(presentation) { return presentation === 'schematic' ? SCHEMATIC_MAX_GAP : MAX_GAP; }
  function positionAt(track, t, presentation) {
    if (!finite(t) || !track.points.length) return unknown(track);
    const maxGap = allowedGap(presentation);
    const i = upperBound(track.points, t);
    const left = track.points[i - 1];
    const right = track.points[i];
    const exact = left && Math.abs(left.t - t) < 1e-6 ? left : (right && Math.abs(right.t - t) < 1e-6 ? right : null);
    const identity = { id: track.id, label: track.label, team: track.team, identityStatus: track.identityStatus };
    if (exact) {
      if (!VISIBLE.has(exact.status)) return unknown(track, exact.status, exact);
      return { ...identity, ...exact, image: exact.image || null, interpolated: false };
    }
    // A sparse, isolated keyframe is displayed as a labelled snapshot only.
    // It cannot create movement or a trail across its surrounding long gaps.
    const nearest = !left ? right : (!right ? left : (t-left.t <= right.t-t ? left : right));
    if (nearest && VISIBLE.has(nearest.status) && Math.abs(nearest.t-t) <= SNAPSHOT_RADIUS+1e-9) {
      const nearestIndex = nearest === left ? i-1 : i;
      const before = track.points[nearestIndex-1], after = track.points[nearestIndex+1];
      const isolated = (!before || nearest.t-before.t > maxGap+1e-9) && (!after || after.t-nearest.t > maxGap+1e-9);
      if (isolated) return { ...identity, ...nearest, image: nearest.image || null, interpolated:false, snapshot:true, snapshotOffset:t-nearest.t };
    }
    if (!left || !right) return unknown(track);
    if (left.segment !== right.segment) return unknown(track, 'scene-cut');
    if (right.t - left.t > maxGap + 1e-9) return unknown(track, 'sampling-gap');
    if (!VISIBLE.has(left.status) || !VISIBLE.has(right.status)) {
      const hidden = !VISIBLE.has(left.status) ? left : right;
      return unknown(track, hidden.status, hidden);
    }
    const fraction = (t - left.t) / (right.t - left.t);
    const mix = (a, b) => a + (b - a) * fraction;
    return { ...identity, t, x: mix(left.x, right.x), y: mix(left.y, right.y), image: left.image && right.image ? [mix(left.image[0], right.image[0]), mix(left.image[1], right.image[1])] : null, status: 'estimated', segment: left.segment, reviewed: false, interpolated: true };
  }
  function samplePositions(data, t) {
    if (!finite(t) || t < data.window[0] - 1e-6 || t > data.window[1] + 1e-6) return data.tracks.map(track => unknown(track, 'outside-window'));
    return data.tracks.map(track => positionAt(track, t, data.presentation));
  }
  function collectTrails(track, t, seconds = 1, presentation) {
    if (!finite(t) || !finite(seconds) || seconds <= 0) return [];
    const maxGap = allowedGap(presentation);
    const start = t - Math.min(seconds, 10);
    const end = upperBound(track.points, t);
    const begin = upperBound(track.points, start - 1e-9);
    const points = track.points.slice(begin, end);
    const current = positionAt(track, t, presentation);
    // Video time may round a frame timestamp slightly below the JSON timestamp.
    // Reuse only the exact sample already accepted by positionAt's microsecond
    // tolerance; never bring a genuinely future anchor into the trail.
    const exactCurrent = !current.snapshot && finite(current.t) && Math.abs(current.t - t) < 1e-6;
    if (VISIBLE.has(current.status) && (current.interpolated || exactCurrent)) {
      const last = points[points.length - 1];
      if (!last || last.t !== current.t) {
        points.push(exactCurrent ? { ...current, t: Math.min(current.t,t) } : current);
      }
    }
    const lines = [];
    for (let i = 1; i < points.length; i++) {
      const a = points[i - 1], b = points[i];
      if (VISIBLE.has(a.status) && VISIBLE.has(b.status) && a.segment === b.segment && b.t - a.t <= maxGap + 1e-9) {
        lines.push({ points: [a, b], status: presentation === 'schematic' || a.status === 'estimated' || b.status === 'estimated' ? 'estimated' : 'observed' });
      }
    }
    return lines;
  }
  function courtToSvg(x, y) { return [30 + x * 10, 530 - y * 10]; }
  return { SOURCE_SHA256, SOURCE_DURATION, MAX_GAP, SCHEMATIC_MAX_GAP, SNAPSHOT_RADIUS, validateDataset, positionAt, samplePositions, collectTrails, courtToSvg };
});
