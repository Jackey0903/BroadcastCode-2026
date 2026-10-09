/* Local basketball experiment. No detector, fabricated coordinates, or independent clock. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.CourtLab = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const SOURCE_SHA256 = '9c3e4606d04e7f79e29a112952fcf069ebab202af207af500bfbc3338bc079ce';
  const SOURCE_DURATION = 21.548118;
  const VISIBLE = new Set(['observed', 'estimated', 'inferred']);
  const STATUSES = new Set(['observed', 'estimated', 'inferred', 'occluded', 'offscreen']);
  const PHASES = new Set(['held', 'pass', 'shot', 'score', 'change', 'unknown']);
  const MAX_GAP = 0.15;
  const SCHEMATIC_MAX_GAP = 0.6;
  const SCHEMATIC_GAP_LIMIT = 1.25;
  const SNAPSHOT_RADIUS = 0.05;
  const finite = value => typeof value === 'number' && Number.isFinite(value);
  function check(condition, message) { if (!condition) throw new Error(message); }
  function validatePoints(points, data, name, isBall = false) {
    check(Array.isArray(points) && points.length <= 100000, `${name} 的采样点数组无效。`);
    let previous = -Infinity;
    for (const point of points) {
      check(point && finite(point.t) && point.t > previous && point.t >= data.window[0] - 1e-6 && point.t <= data.window[1] + 1e-6, `${name} 的时间必须在分析时段内严格递增。`);
      previous = point.t;
      check(STATUSES.has(point.status), `${name} 的可见性状态无效。`);
      check(point.status !== 'inferred' || data.presentation === 'schematic', `${name} 的推断站位仅用于战术示意。`);
      check(typeof point.segment === 'string' && point.segment.length > 0 && point.segment.length <= 100, `${name} 缺少镜头分段。`);
      check(typeof point.reviewed === 'boolean', `${name} 缺少人工核对状态。`);
      if (VISIBLE.has(point.status)) {
        check(finite(point.x) && finite(point.y) && point.x >= 0 && point.x <= 94 && point.y >= 0 && point.y <= 50, `${name} 的可见点必须是球场内有限坐标。`);
      } else {
        check(point.x === null && point.y === null, `${name} 的遮挡或画外位置必须为空。`);
      }
      if (point.status === 'inferred') check(point.image === null, `${name} 的推断站位必须 image:null，不可标在原片。`);
      if (isBall) check(point.image === undefined || point.image === null, '篮球示意坐标不可包含原片像素点。');
      if (point.image !== undefined && point.image !== null) {
        check(VISIBLE.has(point.status) && Array.isArray(point.image) && point.image.length === 2 && point.image.every(finite) && point.image[0] >= 0 && point.image[0] <= 1280 && point.image[1] >= 0 && point.image[1] <= 720, `${name} 的原片足点坐标无效。`);
      }
    }
  }
  function validateIntervals(intervals, data, name) {
    check(Array.isArray(intervals) && intervals.length <= 10000, `${name} 必须为区间数组。`);
    let previousEnd = -Infinity;
    for (const interval of intervals) {
      check(interval && finite(interval.start) && finite(interval.end) && interval.start >= data.window[0] && interval.end <= data.window[1] && interval.start < interval.end && interval.start >= previousEnd, `${name} 必须在分析时段内有序、非重叠。`);
      previousEnd = interval.end;
    }
  }
  function validateDataset(data) {
    check(data && typeof data === 'object' && !Array.isArray(data), '数据必须是 JSON 对象。');
    check(data.schema === 'court-lab-v1', 'schema 必须是 court-lab-v1。');
    check(data.presentation === undefined || data.presentation === 'schematic', 'presentation 仅支持 schematic 或省略。');
    if (data.schematic !== undefined) {
      check(data.presentation === 'schematic' && data.schematic && typeof data.schematic === 'object' && !Array.isArray(data.schematic), 'schematic 配置仅支持战术示意模式。');
      const config = data.schematic;
      check(config.maxGapSeconds === undefined || (finite(config.maxGapSeconds) && config.maxGapSeconds > 0 && config.maxGapSeconds <= SCHEMATIC_GAP_LIMIT), '示意插值间隔必须在 0–1.25 秒内。');
      for (const key of ['holdLastKnown', 'holdAcrossSegments']) check(config[key] === undefined || typeof config[key] === 'boolean', `${key} 必须是布尔值。`);
    }
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
      validatePoints(track.points, data, `轨迹 ${id}`);
    }
    if (data.scenes !== undefined) {
      validateIntervals(data.scenes, data, '镜头分段');
      const sceneIds = new Set();
      for (const scene of data.scenes) {
        check(typeof scene.id === 'string' && scene.id.length > 0 && scene.id.length <= 100 && !sceneIds.has(scene.id), '镜头编号为空、过长或重复。');
        sceneIds.add(scene.id);
        check(scene.type === undefined || ['wide', 'closeup'].includes(scene.type), '镜头类型必须为 wide 或 closeup。');
        check(scene.label === undefined || typeof scene.label === 'string', '镜头标签必须是文字。');
      }
    }
    if (data.possession !== undefined) {
      check(data.presentation === 'schematic', '持球编辑只用于战术示意。');
      validateIntervals(data.possession, data, '持球阶段');
      for (const interval of data.possession) {
        check(interval.holder === null || ((typeof interval.holder === 'string' || finite(interval.holder)) && ids.has(String(interval.holder))), '持球球员必须是现有编号或 null。');
        check(PHASES.has(interval.phase), '持球阶段无效。');
        check(typeof interval.label === 'string' && interval.label.length <= 200, '持球阶段缺少文字标签。');
        check(interval.source === 'editorial', '持球阶段须声明编辑来源 editorial。');
      }
    }
    if (data.ball !== undefined) {
      check(data.presentation === 'schematic' && data.ball && data.ball.kind === 'court-schematic', '篮球位置只支持 court-schematic 战术示意。');
      validatePoints(data.ball.points, data, '篮球示意', true);
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
    return { id: track.id, label: track.label, team: track.team, identityStatus: track.identityStatus, x: null, y: null, image: null, status: point ? point.status : 'unknown', segment: point ? point.segment : null, reason, interpolated: false, reviewed: false };
  }
  // The old string argument remains supported. Wider gaps and retained snapshots
  // require an explicit schematic configuration in the complete dataset.
  function policyFor(context) {
    const presentation = typeof context === 'string' ? context : context && context.presentation;
    const schematic = presentation === 'schematic';
    const config = schematic && typeof context === 'object' ? context.schematic || {} : {};
    const maxGap = schematic && finite(config.maxGapSeconds) && config.maxGapSeconds > 0 && config.maxGapSeconds <= SCHEMATIC_GAP_LIMIT ? config.maxGapSeconds : (schematic ? SCHEMATIC_MAX_GAP : MAX_GAP);
    return { schematic, maxGap, hold: schematic && config.holdLastKnown === true, across: schematic && config.holdAcrossSegments === true };
  }
  function intervalAt(intervals, t, includeLastEndpoint = false) {
    if (!finite(t) || !Array.isArray(intervals)) return null;
    const index = intervals.findIndex((interval, i) => t >= interval.start && (t < interval.end || (includeLastEndpoint && i === intervals.length - 1 && t === interval.end)));
    return index < 0 ? null : { interval: intervals[index], index };
  }
  function sceneAt(data, t) {
    if (!finite(t) || !data || t < data.window[0] || t > data.window[1]) return null;
    const found = intervalAt(data.scenes, t, true);
    return found ? found.interval : null;
  }
  function possessionAt(data, t) {
    // All intermediate phase boundaries stay half-open. The final video frame
    // belongs to the last phase only when its end is the analysis-window end.
    return intervalAt(data.possession, t, t === data.window[1]);
  }
  function rawPositionAt(track, t, context) {
    if (!finite(t) || !track.points.length) return unknown(track);
    const { maxGap } = policyFor(context);
    const i = upperBound(track.points, t);
    const left = track.points[i - 1];
    const right = track.points[i];
    const exact = left && Math.abs(left.t - t) < 1e-6 ? left : (right && Math.abs(right.t - t) < 1e-6 ? right : null);
    const identity = { id: track.id, label: track.label, team: track.team, identityStatus: track.identityStatus };
    const scene = context && typeof context === 'object' && context.window ? sceneAt(context, t) : null;
    if (exact) {
      if (scene && exact.segment !== scene.id && exact.t <= t) return unknown(track, 'scene-cut', exact);
      if (!VISIBLE.has(exact.status)) return unknown(track, exact.status, exact);
      return { ...identity, ...exact, image: exact.status === 'inferred' ? null : exact.image || null, interpolated: false };
    }
    // A sparse, isolated keyframe is displayed as a labelled snapshot only.
    // It cannot create movement or a trail across its surrounding long gaps.
    const nearest = !left ? right : (!right ? left : (t-left.t <= right.t-t ? left : right));
    if (nearest && VISIBLE.has(nearest.status) && Math.abs(nearest.t-t) <= SNAPSHOT_RADIUS+1e-9) {
      const nearestIndex = nearest === left ? i-1 : i;
      const before = track.points[nearestIndex-1], after = track.points[nearestIndex+1];
      const isolated = (!before || nearest.t-before.t > maxGap+1e-9) && (!after || after.t-nearest.t > maxGap+1e-9);
      if (isolated && (!scene || nearest.segment === scene.id)) return { ...identity, ...nearest, image: nearest.status === 'inferred' ? null : nearest.image || null, interpolated:false, snapshot:true, snapshotOffset:t-nearest.t };
    }
    if (!left || !right) return unknown(track);
    if (left.segment !== right.segment) return unknown(track, 'scene-cut', left);
    if (scene && left.segment !== scene.id) return unknown(track, 'scene-cut', left);
    if (right.t - left.t > maxGap + 1e-9) return unknown(track, 'sampling-gap', left);
    if (!VISIBLE.has(left.status) || !VISIBLE.has(right.status)) {
      const hidden = !VISIBLE.has(left.status) ? left : right;
      return unknown(track, hidden.status, hidden);
    }
    const fraction = (t - left.t) / (right.t - left.t);
    const mix = (a, b) => a + (b - a) * fraction;
    return { ...identity, t, x: mix(left.x, right.x), y: mix(left.y, right.y), image: left.image && right.image ? [mix(left.image[0], right.image[0]), mix(left.image[1], right.image[1])] : null, status: 'estimated', segment: left.segment, reviewed: false, interpolated: true };
  }
  function positionAt(track, t, context) {
    const policy = policyFor(context);
    if (context && typeof context === 'object' && context.window && (t < context.window[0] - 1e-6 || t > context.window[1] + 1e-6)) return unknown(track, 'outside-window');
    let position = rawPositionAt(track, t, context);
    // A first future keyframe is not a last-known position. Keep its player in
    // the unknown roster until video playback actually reaches that keyframe.
    if (policy.hold && position.snapshot) position = unknown(track, 'sampling-gap');
    if (!policy.hold || (VISIBLE.has(position.status) && finite(position.x) && finite(position.y)) || !finite(t)) return position;
    const scene = typeof context === 'object' && context.window ? sceneAt(context, t) : null;
    const left = track.points[upperBound(track.points, t) - 1];
    let previous = null;
    for (let i = upperBound(track.points, t) - 1; i >= 0; i--) {
      if (VISIBLE.has(track.points[i].status)) { previous = track.points[i]; break; }
    }
    if (!previous) return position;
    const segment = scene ? scene.id : left ? left.segment : previous.segment;
    const crossSegment = previous.segment !== segment;
    if (crossSegment && !policy.across) return position;
    return { id: track.id, label: track.label, team: track.team, identityStatus: track.identityStatus,
      t, x: previous.x, y: previous.y, image: null, status: 'last-known', held: true,
      age: Math.max(0, t - previous.t), sourceTime: previous.t, sourceStatus: previous.status,
      sourceSegment: previous.segment, segment, crossSegment, reason: position.reason,
      interpolated: false, reviewed: false };
  }
  function samplePositions(data, t) {
    if (!finite(t) || t < data.window[0] - 1e-6 || t > data.window[1] + 1e-6) return data.tracks.map(track => unknown(track, 'outside-window'));
    return data.tracks.map(track => positionAt(track, t, data));
  }
  function collectTrails(track, t, seconds = 1, context) {
    if (!finite(t) || !finite(seconds) || seconds <= 0) return [];
    const policy = policyFor(context);
    const { maxGap } = policy;
    const start = t - Math.min(seconds, 25);
    const end = upperBound(track.points, t);
    const begin = upperBound(track.points, start - 1e-9);
    const points = track.points.slice(begin, end);
    const current = positionAt(track, t, context);
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
      if (context && typeof context === 'object' && Array.isArray(context.scenes) && context.scenes.length) {
        const before = sceneAt(context, a.t), after = sceneAt(context, b.t);
        if (!before || !after || before.id !== after.id || before.id !== a.segment || after.id !== b.segment) continue;
      }
      if (VISIBLE.has(a.status) && VISIBLE.has(b.status) && a.segment === b.segment && b.t - a.t <= maxGap + 1e-9) {
        lines.push({ points: [a, b], status: policy.schematic || a.status !== 'observed' || b.status !== 'observed' ? 'estimated' : 'observed' });
      }
    }
    return lines;
  }
  function sampleBall(data, t) {
    const found = possessionAt(data, t);
    const interval = found && found.interval;
    const result = { holder: interval ? interval.holder : null, phase: interval ? interval.phase : 'unknown',
      label: interval ? interval.label : '持球状态待确认', x: null, y: null,
      kind: 'court-schematic', status: 'unknown', heldPosition: false, sourceTime: null, image: null };
    if (!finite(t) || t < data.window[0] - 1e-6 || t > data.window[1] + 1e-6) return { ...result, holder: null, phase: 'unknown', label: '分析时段外' };
    if (interval && interval.phase === 'held' && interval.holder !== null) {
      const track = data.tracks.find(track => String(track.id) === String(interval.holder));
      const position = track && positionAt(track, t, data);
      if (position && finite(position.x) && finite(position.y)) return { ...result, x: position.x, y: position.y,
        status: position.status, heldPosition: position.held === true,
        sourceTime: position.held ? position.sourceTime : position.t, segment: position.segment };
      return result;
    }
    if (!data.ball || !Array.isArray(data.ball.points)) return result;
    // Possession boundaries are also interpolation boundaries. They describe
    // edited phases, not measured airborne ball travel or ground projection.
    const points = data.ball.points.map(point => {
      const phase = possessionAt(data, point.t);
      return { ...point, segment: `${point.segment}::phase-${phase ? phase.index : 'unknown'}` };
    });
    const context = { ...data, scenes: undefined, schematic: { ...(data.schematic || {}), holdLastKnown: false, holdAcrossSegments: false } };
    const position = rawPositionAt({ id: 'ball', label: '球', points }, t, context);
    if (!finite(position.x) || !finite(position.y) || position.snapshot && position.t > t + 1e-6) return result;
    const pointPhase = possessionAt(data, position.t);
    if ((found ? found.index : null) !== (pointPhase ? pointPhase.index : null)) return result;
    const scene = sceneAt(data, t);
    const segment = position.segment.split('::phase-')[0];
    if (scene && segment !== scene.id) return result;
    return { ...result, x: position.x, y: position.y, status: position.status,
      sourceTime: position.t, interpolated: position.interpolated, snapshot: position.snapshot === true,
      segment, image: null };
  }
  function courtToSvg(x, y) { return [30 + x * 10, 530 - y * 10]; }
  return { SOURCE_SHA256, SOURCE_DURATION, MAX_GAP, SCHEMATIC_MAX_GAP, SCHEMATIC_GAP_LIMIT, SNAPSHOT_RADIUS, validateDataset, positionAt, samplePositions, collectTrails, sampleBall, sceneAt, courtToSvg };
});
