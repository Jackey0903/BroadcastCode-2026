import { historicalRecords } from './historical-records.js';

const SAMPLE_IDS = new Set(['flagg', 'amen']);

const DEFAULT_BASE = () => globalThis.location?.href || 'http://localhost/';
const JOB_ID = /^[0-9a-f]{32}$/;
const SHA256 = /^[0-9a-f]{64}$/;

/** Playback accepts only the registered same-origin asset path, without redirects. */
export function sameOriginAsset(value, path, base = DEFAULT_BASE()) {
  if (typeof value !== 'string' || !value || value.startsWith('//')) return null;
  try {
    const url = new URL(value, base), origin = new URL(base).origin;
    if (!['http:', 'https:'].includes(url.protocol) || url.origin !== origin || url.username || url.password || url.search || url.hash || url.pathname !== path) return null;
    return path;
  } catch { return null; }
}

/** The served manifest has already passed publication identity and media checks. */
export function normalizeStory(source, base = DEFAULT_BASE()) {
  if (source?.sample === "formal") return normalizeFormalStory(source, base);
  if (!source || !SAMPLE_IDS.has(source.sample)) throw new Error('未登记的比赛素材。');
  const src = sameOriginAsset(source.sourceVideo, `/samples/${source.sample}.mp4`, base);
  if (!src || !SHA256.test(source.sourceVideoSha256 || '')) throw new Error('原片地址或身份未核验。');
  const jobId = source.showcaseJobId;
  const registered = JOB_ID.test(jobId || '') && SHA256.test(source.showcaseOutputSha256 || '')
    && (!source.publication?.originalJobId || source.publication.originalJobId === jobId);
  const enhanced = registered ? sameOriginAsset(source.enhancedVideo, `/product/outputs/${jobId}/enhanced.mp4`, base) : null;
  const analysis = registered ? sameOriginAsset(source.analysisUrl, `/product/outputs/${jobId}/analysis.json`, base) : null;
  const available = !!(enhanced && analysis);
  const history = historicalRecords.find(record => record.jobId === jobId && record.sample === source.sample) || null;
  return {
    ...source,
    rawSourceRecord: source,
    src,
    sourceVideo: src,
    enhancedVideo: available ? enhanced : null,
    enhancedAvailable: available,
    analysisUrl: available ? analysis : null,
    history,
    media: {
      source: { src, status: 'unchecked', sha256: source.sourceVideoSha256 },
      enhanced: { src: available ? enhanced : null, available, status: available ? 'unchecked' : 'missing', reason: available ? '' : '当前目录未提供可核验的同源增强成片。' },
    },
  };
}

/** Read original accepted-run records only after the viewer requests them. */
export async function loadStoryRecord(story) {
  if (story?.production?.mode === 'editorial') {
    if (!story.enhancedAvailable) return null;
    const response = await fetch(story.production.manifestUrl, { cache: 'no-store', credentials: 'same-origin', redirect: 'error' });
    if (!response.ok) throw new Error('编辑成片记录暂不可用。');
    const record = await response.json();
    if (record.sourceSha256 !== story.sourceVideoSha256 || record.outputSha256 !== story.production.outputSha256 || !validEditorialProduction(record, story.durationSeconds)) throw new Error('编辑成片记录与当前素材身份不一致。');
    return record;
  }

  if (!story?.enhancedAvailable) return story?.history || null;
  const response = await fetch(new URL('../data/history.json', import.meta.url), { cache: 'no-store', credentials: 'same-origin', redirect: 'error' });
  if (!response.ok) throw new Error(`成片记录暂不可用（HTTP ${response.status}）。`);
  const payload = await response.json();
  if (!Array.isArray(payload.records)) throw new Error('成片记录格式无效。');
  const record = payload.records.find(item => item.jobId === story.showcaseJobId && item.sample === story.sample);
  const analysis = record?.analysis;
  if (!record || record.mode !== 'story' || record.outputSha256 !== story.showcaseOutputSha256
      || analysis?.runId !== story.showcaseJobId || analysis.sample !== story.sample
      || analysis.preservesSourceTimeline !== true || analysis.outputVideo?.sha256 !== story.showcaseOutputSha256
      || analysis.sourceVideo?.sha256 !== story.sourceVideoSha256) throw new Error('成片记录与当前素材身份不一致。');
  return { ...record, historical: story.publication?.historical === true, recordSource: record.recordSource || `product/evidence/run-${record.jobId}.json` };
}

/** One same-origin fetch. External provenance URLs are never fetched automatically. */
export async function loadCatalog() {
  const response = await fetch(new URL('../data/stories.json', import.meta.url), { cache: 'no-store', credentials: 'same-origin', redirect: 'error' });
  if (!response.ok) throw new Error(`比赛目录暂不可用（HTTP ${response.status}）。`);
  const catalog = await response.json();
  if (!Array.isArray(catalog.stories)) throw new Error('比赛目录格式无效。');
  return catalog.stories.map(story => normalizeStory(story));
}

/** Only local same-origin paths and explicit http(s) sources may be opened. */
export function safeSourceUrl(value, base = globalThis.location?.href || 'http://localhost/') {
  if (typeof value !== 'string' || !value.trim()) return null;
  try {
    const parsed = new URL(value, base);
    if (!['http:', 'https:'].includes(parsed.protocol) || parsed.username || parsed.password) return null;
    if (!/^https?:\/\//i.test(value) && (!value.startsWith('/') || value.startsWith('//') || parsed.origin !== new URL(base).origin)) return null;
    return parsed.href;
  } catch { return null; }
}

export function formatVideoTime(value) {
  const seconds = Math.max(0, Number(value) || 0);
  return `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${(seconds % 60).toFixed(1).padStart(4, '0')}`;
}

export function formatBeijingDate(value) {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return '时间未记录';
  return new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(date) + ' 北京时间';
}

// Viewing preferences are deliberately independent of display/optical presets.
const PREFERENCE_KEY = 'broadcastcode.watch.preferences.v1';
export const defaultPreferences = Object.freeze({ player: 'all', familiarity: 'beginner', purpose: 'enjoy' });
export function readPreferences(storage = globalThis.localStorage) {
  try { const value = JSON.parse(storage?.getItem(PREFERENCE_KEY) || 'null'); return {
    player: typeof value?.player === 'string' ? value.player : 'all',
    familiarity: value?.familiarity === 'familiar' ? 'familiar' : 'beginner',
    purpose: value?.purpose === 'analyze' ? 'analyze' : 'enjoy',
  }; } catch { return { ...defaultPreferences }; }
}
export function savePreferences(value, storage = globalThis.localStorage) { storage.setItem(PREFERENCE_KEY, JSON.stringify(value)); }

/** Only explicit identities in the current game's supplied official roster.
 * A roster key is a local selection key, never an invented NBA player ID.
 * Anonymous court D/W identifiers are intentionally not used here.
 */
export function followPlayers(story) {
  if (!story?.game?.gameId) return [];
  const players = [];
  const main = story.player, event = story.officialEvent;
  if (main?.name && event?.verified === true && event.gameId === story.game.gameId && event.playerId) {
    players.push({ id: String(event.playerId), name: main.name, number: main.number, team: main.team, teamAbbreviation: main.teamAbbreviation, evidenceIds: (story.evidence || []).filter(e => e.kind === 'official' && e.gameId === event.gameId && String(e.playerId) === String(event.playerId)).map(e => e.id) });
  }
  for (const evidence of story.evidence || []) {
    if (evidence.kind !== 'official' || evidence.gameId !== story.game.gameId || !/本场名单/.test(evidence.body || '')) continue;
    let team = '';
    for (const clause of evidence.body.split(/[，；。]/)) {
      const match = clause.match(/(?:本场名单：)?([^：\d]*?)\s*(\d{1,2})\s*号为([^，；。]+?)(?:，|$)/);
      if (!match) continue;
      if (match[1].trim()) team = match[1].trim();
      const name = match[3].trim(), number = match[2];
      if (!team || players.some(p => p.name === name)) continue;
      players.push({ id: `roster:${story.game.gameId}:${team}:${number}`, name, number, team, evidenceIds: [evidence.id] });
    }
  }
  return players;
}
export function validatePreferences(preferences, story) {
  return { ...preferences, player: preferences.player === 'all' || followPlayers(story).some(p => p.id === preferences.player) ? preferences.player : 'all' };
}

/** Reuse only already timestamped observations, after their source frame exists.
 * Do not use chapter start times or option descriptions: those can mention later results.
 * Splitting source sentences preserves their words, without generating new analysis.
 */
export function followEvents(story) {
  const players = followPlayers(story), events = [];
  for (const evidence of story?.evidence || []) {
    if (!Number.isFinite(evidence.videoTime) || !evidence.sourceUrl || !evidence.body) continue;
    if (evidence.kind === 'official') {
      if (evidence.playerId && evidence.eventId === story.officialEvent?.eventId && story.officialEvent?.verified === true && !evidence.unit)
        events.push({ id: evidence.id, time: evidence.videoTime, text: evidence.body, category: 'offense', playerIds: [String(evidence.playerId)], evidenceIds: [evidence.id], sourceLabel: evidence.sourceLabel });
      continue;
    }
    if (!['observation', 'video_frame'].includes(evidence.kind)) continue;
    for (const [i, clause] of evidence.body.split(/[，；。]/).entries()) {
      const category = /无球|掩护|空切/.test(clause) ? 'offball' : /投篮|出手|持球|推进/.test(clause) ? 'offense' : /防守|双臂|已起跳|正在下落/.test(clause) ? 'defense' : null;
      if (!category) continue;
      const numbers = [...clause.matchAll(/(\d{1,2})\s*号/g)].map(m => m[1]);
      const ids = players.filter(p => clause.includes(p.name) || numbers.some(n => n === p.number && players.filter(other => other.number === n).length === 1)).map(p => p.id);
      events.push({ id: `${evidence.id}:${i}`, time: evidence.videoTime, text: clause, category, playerIds: ids, evidenceIds: [evidence.id], sourceLabel: `${evidence.sourceLabel} · 编辑观察，未人工复核` });
    }
  }
  return events.sort((a,b) => a.time - b.time);
}
export function reminderAt(events, time, preferences) {
  if (!Number.isFinite(time)) return null;
  const relevant = events.filter(e => preferences.player === 'all' || e.playerIds.includes(preferences.player));
  // Deterministic, sparse schedule. Simultaneous candidates resolve to one entry;
  // deeper explanations remain behind an explicit user action.
  let last = -Infinity, selected = null;
  const interval = preferences.purpose === 'enjoy' ? 5 : 3;
  for (const event of relevant) {
    if (event.time > time) break;
    if (event.time - last < interval) continue;
    last = event.time; selected = event;
  }
  if (!selected || time - selected.time >= (preferences.purpose === 'enjoy' ? 2.2 : 2.8)) return null;
  const text = selected.copy?.[preferences.familiarity] || selected.text;
  return { ...selected, text };
}
/** Explicit reviewed, time-bounded links only. Historical/future links never follow. */
export function followMapping(story, playerId, time) {
  if (!story?.playerIdentityMappings?.length || playerId === 'all' || !followPlayers(story).some(p => p.id === playerId)) return null;
  return (story.playerIdentityMappings || []).find(m => m.playerId === playerId && m.verified === true && m.sourceEvidenceIds?.length && m.sourceEvidenceIds.every(id => story.evidence?.some(e => e.id === id)) && Number.isFinite(m.start) && Number.isFinite(m.end) && time >= m.start && time <= m.end) || null;
}

/** Editorial movies have their own proof and clock; they are never cloud jobs. */
export function validEditorialProduction(production, sourceDuration) {
  if (production?.mode !== 'editorial' || production.status !== 'local-render-ready'
      || production.agentCoreUsedForThisRender !== false || production.rlModelUsedForThisRender !== false
      || production.preservesSourceTimeline !== false || production.fullVideoAudioDecode !== true
      || !SHA256.test(production.sourceSha256 || '') || !SHA256.test(production.outputSha256 || '')
      || !(production.durationSeconds > 0 && production.durationSeconds < 60)
      || !Array.isArray(production.timeline) || !production.timeline.length) return false;
  let previous = 0;
  for (const segment of production.timeline) {
    const {outputStart:a,outputEnd:b,sourceStart:c,sourceEnd:d} = segment;
    if (![a,b,c,d].every(Number.isFinite) || Math.abs(a - previous) > .05 || b <= a
        || c < 0 || d < 0 || c > sourceDuration || d > sourceDuration) return false;
    previous = b;
  }
  return Math.abs(previous - production.durationSeconds) <= .1;
}

function normalizeFormalStory(source, base) {
  const src = sameOriginAsset(source.sourceVideo, '/product/media/formal/source.mp4', base);
  if (!src || !SHA256.test(source.sourceVideoSha256 || '') || !(source.durationSeconds > 0)) throw new Error('正式原片地址或身份未核验。');
  const production = source.production || {};
  const registered = validEditorialProduction(production, source.durationSeconds)
    && production.sourceSha256 === source.sourceVideoSha256
    && sameOriginAsset(production.manifestUrl, '/product/media/formal/manifest.json', base);
  const enhanced = registered ? sameOriginAsset(source.enhancedVideo, '/product/media/formal/enhanced.mp4', base) : null;
  const clean = {...source};
  for (const key of ['scout','playerComparison','rlEvidenceSources','rlEvidencePeriods','rlVideoUse','rlAudit','showcaseJobId','showcaseOutputSha256','publication']) delete clean[key];
  return {...clean, rawSourceRecord:source, src, sourceVideo:src,
    enhancedVideo:enhanced, enhancedAvailable:!!enhanced, analysisUrl:null, history:null,
    media:{source:{src,status:'unchecked',sha256:source.sourceVideoSha256},
      enhanced:{src:enhanced,available:!!enhanced,status:enhanced?'unchecked':'missing',reason:enhanced?'':'正式片特效版本正在联调。'}}};
}

/** Map source anchors to the first forward showing, skipping titles and replay. */
export function sourceToOutputTime(story, value) {
  const time = Math.max(0, Math.min(story.durationSeconds, Number(value) || 0));
  if (story.production?.mode !== 'editorial' || !story.enhancedAvailable) return time;
  const forward = (story.production.timeline || []).filter(s => s.sourceEnd > s.sourceStart && !['replay','rewind'].includes(s.kind));
  const segment = forward.find(s => time >= s.sourceStart && time < s.sourceEnd)
    || forward.find(s => time >= s.sourceStart && time <= s.sourceEnd);
  if (!segment) return null;
  return segment.outputStart + (time-segment.sourceStart)/(segment.sourceEnd-segment.sourceStart)*(segment.outputEnd-segment.outputStart);
}

/** Reverse mapping retains frozen frames and deliberate replay direction. */
export function outputToSourceTime(story, value) {
  const time = Math.max(0, Number(value) || 0);
  if (story.production?.mode !== 'editorial' || !story.enhancedAvailable) return time;
  const timeline = story.production.timeline || [];
  const segment = timeline.find(s => time >= s.outputStart && time < s.outputEnd) || timeline.at(-1);
  if (!segment) return null;
  const ratio = Math.max(0,Math.min(1,(time-segment.outputStart)/(segment.outputEnd-segment.outputStart)));
  return segment.sourceStart + ratio*(segment.sourceEnd-segment.sourceStart);
}
