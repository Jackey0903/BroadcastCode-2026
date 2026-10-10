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
