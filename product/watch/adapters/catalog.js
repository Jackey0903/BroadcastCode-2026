import { historicalRecords } from './historical-records.js';

const SAMPLE_IDS = new Set(['flagg', 'amen']);

/** Preserve the received record while making media playback local-only. */
export function normalizeStory(source) {
  if (!source || !SAMPLE_IDS.has(source.sample)) throw new Error('未登记的本地比赛素材。');
  const src = `/samples/${source.sample}.mp4`;
  const history = historicalRecords.find(record => record.jobId === source.showcaseJobId) || null;
  return {
    ...source,
    rawSourceRecord: source,
    src,
    sourceVideo: src,
    enhancedVideo: null,
    enhancedAvailable: false,
    analysisUrl: null,
    history,
    media: {
      source: { src, status: 'unchecked', sha256: source.sourceVideoSha256 },
      enhanced: { src: null, available: false, status: 'missing', reason: '本机未恢复增强成片；可查看 10 月 7 日的历史验收记录。' },
    },
  };
}

/** One same-origin fetch. External provenance URLs are never fetched automatically. */
export async function loadCatalog() {
  const response = await fetch(new URL('../data/stories.json', import.meta.url), { cache: 'no-store', credentials: 'same-origin' });
  if (!response.ok) throw new Error(`比赛目录暂不可用（HTTP ${response.status}）。`);
  const catalog = await response.json();
  if (!Array.isArray(catalog.stories)) throw new Error('比赛目录格式无效。');
  return catalog.stories.map(normalizeStory);
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
